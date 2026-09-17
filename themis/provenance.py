"""Provenance roots and the three independence tests (STEPS 7-8).

A *root* is where a claim's evidence actually originates, which is not the
same as the dataset that republished it. `resolve()` assigns one from rules
declared in each source's config/sources/<id>.yml - a fixed identity, a
declared-field lookup, or a decode of an undocumented per-address code - so
this module never names a dataset or a label by string literal. Nothing is
guessed: an unconfigured or undecodable source stays UNRESOLVED, which is
deliberately distinct from "shares a root with everything else unresolved".
"""
from __future__ import annotations
import collections
from . import config_io

_cfg = config_io.load()


def _after_colon(value: str, default: str) -> str:
    return value.split(":", 1)[1] if ":" in value else default


def _fill(template: str, value: str) -> str:
    return template.format(value=value, value_or_unknown=value or "unknown")


def resolve(claim: dict, sources: dict | None = None) -> dict:
    """Assign this claim's provenance root per its source's declared rule.

    Returns {root, resolved, native, verified}. `resolved` means the root is
    a known evidential origin (STEP 7); `native` means this source *is* that
    origin rather than re-describing another one's finding; `verified`
    means the root terminates in independently re-checkable evidence
    (STEP 6) - a declaration a source config must make explicitly, never
    inferred from a dataset calling itself verified.
    """
    sources = sources if sources is not None else _cfg.sources
    src_id = claim.get("source")
    cfg = sources.get(src_id)
    prov = (cfg or {}).get("provenance")
    if not prov:
        return dict(root=f"{src_id}:unresolved", resolved=False, native=False, verified=False)

    mode = prov["mode"]

    if mode == "fixed_root":
        return dict(root=prov["root"], resolved=bool(prov.get("resolved", False)),
                    native=bool(prov.get("native", True)), verified=bool(prov.get("verified", False)))

    if mode == "field_map":
        entry = prov.get("map", {}).get(claim.get(prov["field"], ""))
        d = entry or prov.get("default", {})
        return dict(root=d.get("root", f"{src_id}_other"), resolved=bool(d.get("resolved", False)),
                    native=bool(d.get("native", False)), verified=bool(d.get("verified", False)))

    if mode in ("contains_rules", "substring_map"):
        raw = claim.get(prov["field"], "") or ""
        value = _after_colon(raw, prov.get("parse_default", "")) if prov.get("parse") == "after_colon" else raw
        rules = prov.get(mode, [])
        low = value.lower()
        for rule in rules:
            hit = (rule["contains"] in value) if mode == "contains_rules" else (rule["contains"].lower() in low)
            if hit:
                return dict(root=rule["root"], resolved=bool(rule.get("resolved", False)),
                            native=bool(rule.get("native", False)), verified=bool(rule.get("verified", False)))
        if "residue_prefix_map" in prov:
            residue = (claim.get(prov["residue_field"], "") or "").lower()
            for prefix, root in prov["residue_prefix_map"].items():
                if residue.startswith(prefix):
                    return dict(root=root, resolved=bool(prov.get("residue_resolved", True)),
                                native=bool(prov.get("residue_native", False)),
                                verified=bool(prov.get("residue_verified", False)))
        root = _fill(prov["fallback_template"], value)
        return dict(root=root, resolved=bool(prov.get("fallback_resolved", False)),
                    native=bool(prov.get("fallback_native", True)),
                    verified=bool(prov.get("fallback_verified", False)))

    raise ValueError(f"unknown provenance mode: {mode!r}")


def root_of(claim: dict) -> str:
    """Back-compat convenience: just the root name. Prefer `resolve()`."""
    return resolve(claim)["root"]


def _root_ledger(sources: dict):
    """Every root name a config statically declares (exact matches), plus
    every templated-fallback prefix, each tagged with whether it counts as
    resolved. Built once from config so `is_unresolved` needs no per-dataset
    knowledge of its own."""
    exact, prefixes = {}, []
    for cfg in sources.values():
        prov = cfg.get("provenance", {})
        mode = prov.get("mode")
        if mode == "fixed_root":
            exact[prov["root"]] = bool(prov.get("resolved", False))
        elif mode == "field_map":
            for entry in (prov.get("map") or {}).values():
                exact[entry["root"]] = bool(entry.get("resolved", False))
            d = prov.get("default")
            if d and d.get("root"):
                exact[d["root"]] = bool(d.get("resolved", False))
        elif mode in ("contains_rules", "substring_map"):
            for rule in prov.get(mode, []):
                exact[rule["root"]] = bool(rule.get("resolved", False))
            for root in (prov.get("residue_prefix_map") or {}).values():
                exact[root] = bool(prov.get("residue_resolved", True))
            tmpl = prov.get("fallback_template", "")
            resolved = bool(prov.get("fallback_resolved", False))
            if "{" in tmpl:
                prefixes.append((tmpl.split("{", 1)[0], resolved))
            elif tmpl:
                exact[tmpl] = resolved
    return exact, prefixes


_EXACT_ROOTS, _PREFIX_ROOTS = _root_ledger(_cfg.sources)


def is_unresolved(root: str) -> bool:
    if root in _EXACT_ROOTS:
        return not _EXACT_ROOTS[root]
    for prefix, resolved in _PREFIX_ROOTS:
        if root.startswith(prefix):
            return not resolved
    return True   # a root this pipeline never assigned: unknown stays unknown


# ------------------------------------------------------------ test 1: containment
def containment(src_addr: dict[str, set]) -> dict:
    """Share of each source contained in each other source."""
    out = {}
    for a in src_addr:
        for b in src_addr:
            if a == b or not src_addr[a]:
                continue
            inter = len(src_addr[a] & src_addr[b])
            if inter:
                out[(a, b)] = dict(n=inter, share_of_a=inter / len(src_addr[a]))
    return out


# --------------------------------------------- test 2: provenance-field decoding
def decode_field(claims: list[dict], dataset: str, field: str, candidate: str,
                 candidate_addrs: set, min_group: int | None = None,
                 inherited_share: float | None = None, independent_share: float | None = None) -> dict:
    """Decode an undocumented provenance field by testing each value group for
    containment in a candidate upstream source.

    A value group either lies wholly inside the candidate or is disjoint from
    it; anything in between is inconclusive. Returns the verdict per group.
    Thresholds default to config/thresholds.yml so a stricter or looser split
    can be tried without touching this function.
    """
    min_group = _cfg.thresholds.get("min_containment_group", 5) if min_group is None else min_group
    inherited_share = (_cfg.thresholds.get("containment_inherited_share", 0.999)
                       if inherited_share is None else inherited_share)
    independent_share = (_cfg.thresholds.get("containment_independent_share", 0.001)
                         if independent_share is None else independent_share)

    groups = collections.defaultdict(set)
    for c in claims:
        if c["source"] != dataset:
            continue
        raw = c.get(field, "") or ""
        val = _after_colon(raw, "") if ":" in raw else raw
        groups[val].add(c["address"])
    res = {}
    for val, addrs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        share = len(addrs & candidate_addrs) / len(addrs)
        if not val.isalpha():
            verdict = "malformed"          # e.g. a stray separator in the field
        elif len(addrs) < min_group:
            verdict = "insufficient"       # too few rows to establish containment
        elif share > inherited_share:
            verdict = "inherited"
        elif share < independent_share:
            verdict = "independent"
        else:
            verdict = "mixed"
        res[val] = dict(n=len(addrs), share_in_candidate=share, verdict=verdict)

    inherited = [v for v, r in res.items() if r["verdict"] == "inherited"]
    independent = [v for v, r in res.items() if r["verdict"] == "independent"]
    inconclusive = [v for v, r in res.items()
                    if r["verdict"] in ("mixed", "malformed", "insufficient")]
    # the decode is clean when every conclusive group falls at one extreme
    clean = bool(inherited) and bool(independent) and not [
        v for v, r in res.items() if r["verdict"] == "mixed"]
    # groups too small to judge still inherit if they sit inside the candidate
    carried = sum(r["n"] for v, r in res.items()
                  if r["verdict"] in ("insufficient", "malformed")
                  and r["share_in_candidate"] > inherited_share)
    return dict(dataset=dataset, field=field, candidate=candidate, groups=res,
                clean_split=clean,
                inherited_groups=inherited, independent_groups=independent,
                inconclusive_groups=inconclusive,
                inherited_addresses=sum(res[v]["n"] for v in inherited) + carried)


def owner_of_root(root: str, sources: dict | None = None) -> str | None:
    """Which source natively owns this root, if any - the source whose
    fixed_root equals it. Used to discover a decode's candidate generically:
    a source's undocumented code decodes against whichever source is
    actually shipped as that root's origin, never a hardcoded dataset name."""
    sources = sources if sources is not None else _cfg.sources
    for sid, cfg in sources.items():
        prov = cfg.get("provenance", {})
        if prov.get("mode") == "fixed_root" and prov.get("root") == root and prov.get("native", True):
            return sid
    return None


def discover_decodes(sources: dict | None = None) -> list[dict]:
    """Every (dataset, field, candidate) triple worth decoding, discovered
    from config: a source with `contains_rules` naming a root that some
    other source natively owns. STEP 8B requires this discovery to be
    generic - adding a source only means adding its config entry."""
    sources = sources if sources is not None else _cfg.sources
    out = []
    for sid, cfg in sources.items():
        prov = cfg.get("provenance", {})
        if prov.get("mode") != "contains_rules":
            continue
        for rule in prov.get("contains_rules", []):
            owner = owner_of_root(rule["root"], sources)
            if owner and owner != sid:
                out.append(dict(dataset=sid, field=prov["field"], candidate=owner))
    return out


# ------------------------------------------------------- test 3: naming residue
def naming_residue(claims: list[dict], dataset: str, field: str, prefix_map: dict) -> dict:
    """Claims whose own label text names the upstream study they came from."""
    marked = collections.Counter()
    total = 0
    for c in claims:
        if c["source"] != dataset:
            continue
        total += 1
        val = (c.get(field) or "").lower()
        hit = next((root for pre, root in prefix_map.items() if val.startswith(pre)), None)
        marked[hit or "unmarked"] += 1
    attributed = sum(v for k, v in marked.items() if k != "unmarked")
    return dict(dataset=dataset, field=field, total=total, attributed=attributed,
                share=attributed / total if total else 0.0,
                by_root={k: v for k, v in marked.items() if k != "unmarked"})


def discover_residue_checks(sources: dict | None = None) -> list[dict]:
    """Every (dataset, field, prefix_map) worth checking for naming residue,
    discovered from config rather than named in analysis code."""
    sources = sources if sources is not None else _cfg.sources
    out = []
    for sid, cfg in sources.items():
        prov = cfg.get("provenance", {})
        if prov.get("residue_prefix_map"):
            out.append(dict(dataset=sid, field=prov["residue_field"],
                            prefix_map=prov["residue_prefix_map"]))
    return out


def root_propagation(claims: list[dict], src_addr: dict, seed_source: str,
                     seed_field: str, seed_value: str) -> dict:
    """How far one reference source's addresses for a given root propagate
    into every other source. The seed definition is supplied by the caller
    (config/notable_roots.yml) rather than named here."""
    seed = {c["address"] for c in claims
            if c["source"] == seed_source and c.get(seed_field) == seed_value}
    propagation = {s: len(seed & addrs) for s, addrs in src_addr.items() if s != seed_source}
    return dict(size=len(seed), propagation=propagation)
