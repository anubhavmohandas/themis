"""Read-only projections of what the engine already computes, shaped for the
workbench UI (claims filters, the conflict explorer, the trust-policy
preview). Nothing here is new science: every classification is a call to
taxonomy.classify_address / provenance.address_independence / the existing
trust predicates. This module only groups, filters and pages their output so
the frontend never has to re-derive an analytical result client-side.

Comparable addresses
--------------------
The per-address agreement outcome only exists for addresses that more than
one dataset speaks about:

* PAPER_REPRODUCTION - every address named by >= 2 of the reference
  corpus's datasets (the same set analysis.agreement() walks).
* UPLOADED_DATASET   - every target address that also carries at least one
  reference claim; the outcome is classified over the target's claim(s)
  plus only that address's own reference claims (target_audit's rule: no
  reference-vs-reference agreement leaks into a target figure).

Everything else is `single-source` (paper) or has no reference match
(uploaded) - unverifiable against any other public source, not unreliable.
"""
from __future__ import annotations
import collections

from . import config_io, taxonomy, provenance
from .trust import predicates
from . import workspace as _workspace

#: agreement outcome -> the short "kind" the UI filters on
KIND_OF_OUTCOME = {
    "licit/illicit conflict": "polarity",
    "entity-type conflict": "entity",
    "hierarchical refinement": "hierarchical",
    "incomparable": "incomparable",
    "exact": "exact",
}
#: kinds the Conflict Explorer lists (everything comparable that is not an
#: exact agreement); "all" means these four together.
LISTED_KINDS = ("polarity", "entity", "hierarchical", "incomparable")
OUTCOME_OF_KIND = {v: k for k, v in KIND_OF_OUTCOME.items()}


# ------------------------------------------------------- analysis states
def state_of(ws, analysis: str) -> dict:
    """{state, reason, ...} for one downstream analysis of an uploaded dataset
    (ingest/gating.py). A paper reproduction has no gating: its analyses are
    over the reference corpus itself, so they are always computed."""
    st = ((ws.result or {}).get("analysis_states") or {}).get(analysis)
    return dict(state=st["state"], reason=st.get("reason"), detail=st.get("detail")) if st \
        else dict(state="computed", reason=None, detail=None)


# ------------------------------------------------------------- claim helpers
def resolution_of(claim: dict) -> dict:
    """root / resolved / native / kind for one claim, whether or not it went
    through Corpus (which stamps these) or a fresh upload (which does not)."""
    if "prov_resolved" in claim and "root" in claim:
        return dict(root=claim["root"], resolved=bool(claim["prov_resolved"]),
                    native=bool(claim.get("prov_native")),
                    verified=bool(claim.get("prov_verified")),
                    kind=claim.get("prov_kind", "UNKNOWN"))
    r = provenance.resolve(claim)
    return dict(root=r["root"], resolved=bool(r["resolved"]), native=bool(r["native"]),
                verified=bool(r["verified"]), kind=r["kind"])


def provenance_status(claim: dict) -> str:
    """resolved (native origin) | inherited (resolved, but a restatement of
    another root) | unresolved (no rule traces it - never treated as
    independent)."""
    r = resolution_of(claim)
    if not r["resolved"]:
        return "unresolved"
    return "resolved" if r["native"] else "inherited"


def claim_view(c: dict, as_of=None) -> dict:
    r = resolution_of(c)
    return dict(source=c["source"], canon=c.get("canon"), raw_label=c.get("raw_label", ""),
                polarity=c.get("polarity"), root=r["root"], root_kind=r["kind"],
                provenance=provenance_status(c), tier=taxonomy.tier_of(c),
                lastmod=c.get("lastmod") or None)


def relationship_of(indep: dict) -> str:
    """How the claims at one address relate by provenance. Precedence:
    shared_root (some resolved root is claimed twice) > unresolved (at least
    one source has no resolved root) > distinct_roots."""
    if indep["shared_root_count"] > 0:
        return "shared_root"
    if indep["unresolved_source_count"] > 0:
        return "unresolved"
    return "distinct_roots"


# ------------------------------------------------------------ per-address index
def _cache(ws) -> dict:
    return ws.__dict__.setdefault("_views", {})


def _comparable_groups(ws) -> dict[str, list]:
    ref = ws.reference_corpus
    if ws.mode == _workspace.MODE_PAPER:
        return {a: ref.by_addr[a] for a in ref.multi_source_addresses()}
    if ref is None:
        return {}
    mine = collections.defaultdict(list)          # subject (chain + address) -> the target's claims
    for c in ws.claims:
        mine[provenance.subject_key(c)].append(c)
    out = {}
    for key, cs in mine.items():
        ref_cs = ref.for_subject(cs[0].get("blockchain"), cs[0]["address"])
        if ref_cs:
            out[key] = cs + ref_cs
    return out


def address_index(ws) -> dict[str, dict]:
    """{subject: record} over the workspace's comparable subjects (chain + address), cached."""
    cache = _cache(ws)
    if "index" in cache:
        return cache["index"]
    idx = {}
    for key, claims in _comparable_groups(ws).items():
        outcome = taxonomy.classify_address(claims)
        indep = provenance.address_independence(claims)
        idx[key] = dict(address=claims[0]["address"], chain=claims[0].get("blockchain"), outcome=outcome, kind=KIND_OF_OUTCOME[outcome],
                         circular=indep["circular"], relationship=relationship_of(indep),
                         independence=indep, sources=sorted({c["source"] for c in claims}),
                         claims=claims)
    cache["index"] = idx
    cache["sorted_addresses"] = sorted(idx)
    return idx


def kind_counts(ws) -> dict:
    idx = address_index(ws)
    c = collections.Counter(r["kind"] for r in idx.values())
    return {k: c.get(k, 0) for k in ("exact",) + LISTED_KINDS}


# --------------------------------------------------------------- claims filters
def claims_filter(ws, claims: list, outcome=None, comparable=None, provenance_filter=None, q=None):
    """The per-address / per-claim filters the claims endpoint layers on top
    of its cheap per-claim ones. `outcome` is an agreement outcome or
    `single-source`; `comparable` is yes|no; `provenance_filter` is
    resolved|inherited|unresolved (claim-level); `q` is a case-insensitive
    substring over address, raw label and source."""
    if outcome or comparable:
        idx = address_index(ws)
        if outcome == "single-source":
            claims = [c for c in claims if provenance.subject_key(c) not in idx]
        elif outcome:
            want = {a for a, r in idx.items() if r["outcome"] == outcome}
            claims = [c for c in claims if provenance.subject_key(c) in want]
        if comparable == "yes":
            claims = [c for c in claims if provenance.subject_key(c) in idx]
        elif comparable == "no":
            claims = [c for c in claims if provenance.subject_key(c) not in idx]
    if provenance_filter:
        claims = [c for c in claims if provenance_status(c) == provenance_filter]
    if q:
        needle = q.strip().lower()
        if needle:
            claims = [c for c in claims
                      if needle in c["address"].lower() or needle in (c.get("raw_label") or "").lower()
                      or needle in c["source"].lower()]
    return claims


def outcome_for(ws, claim: dict):
    """Agreement outcome for the claim's subject, or None when it is not comparable."""
    rec = address_index(ws).get(provenance.subject_key(claim))
    return rec["outcome"] if rec else None


# ------------------------------------------------------------ conflict explorer
def conflicts_page(ws, kind=None, source_a=None, source_b=None, relationship=None,
                   q=None, offset=0, limit=50) -> dict:
    idx = address_index(ws)
    order = _cache(ws)["sorted_addresses"]
    wanted = set(LISTED_KINDS) if kind in (None, "", "all") else {kind}
    matches = []
    for a in order:
        r = idx[a]
        if r["kind"] not in wanted:
            continue
        if source_a and source_a not in r["sources"]:
            continue
        if source_b and source_b not in r["sources"]:
            continue
        if relationship and r["relationship"] != relationship:
            continue
        if q and q.strip().lower() not in r["address"].lower():
            continue
        matches.append(r)
    limit = max(1, min(int(limit), config_io.load().api["paging"]["conflicts_max_page"]))
    offset = max(0, int(offset))
    page = matches[offset:offset + limit]
    src_set = sorted({s for r in idx.values() for s in r["sources"]})
    return dict(
        total=len(matches), offset=offset, limit=limit, n_returned=len(page),
        counts=kind_counts(ws), sources=src_set,
        items=[dict(address=r["address"], chain=r["chain"], kind=r["kind"], outcome=r["outcome"],
                    relationship=r["relationship"], circular=r["circular"],
                    independence=dict(apparent=r["independence"]["apparent_dataset_count"],
                                      confirmed=r["independence"]["confirmed_independent_root_count"],
                                      unresolved=r["independence"]["unresolved_source_count"]),
                    claims=[claim_view(c) for c in r["claims"]]) for r in page])


def conflict_export_rows(ws):
    """One row per claim at every conflict / hierarchical / incomparable address."""
    idx = address_index(ws)
    header = ["address", "kind", "outcome", "provenance_relationship", "source", "canon",
              "raw_label", "polarity", "root", "root_kind", "provenance", "lastmod", "chain"]
    rows = []
    for a in _cache(ws)["sorted_addresses"]:
        r = idx[a]
        if r["kind"] not in LISTED_KINDS:
            continue
        for c in r["claims"]:
            v = claim_view(c)
            rows.append([r["address"], r["kind"], r["outcome"], r["relationship"], v["source"], v["canon"],
                         v["raw_label"], v["polarity"], v["root"], v["root_kind"],
                         v["provenance"], v["lastmod"] or "", r["chain"] or ""])
    return header, rows


# ---------------------------------------------------------------- trust preview
#: rule id -> (label, predicate name, params, address_level, help). `address_level`
#: predicates depend only on the claims sharing an address, so they are
#: evaluated once per address rather than once per claim.
# `requires` names the downstream analysis (ingest/gating.py) whose prerequisite the
# rule's predicate reads. A rule whose prerequisite is not computed for this dataset
# is `not_applicable`: it neither filters nor reports a retention figure, because
# "kept 100%" of nothing-compared would read as a finding.
RULES = [
    dict(id="resolved_provenance_only", label="Resolved provenance only", predicate="resolved_provenance_only",
         params={}, address_level=False,
         help="Keep claims whose provenance root is identified. Unresolved claims are dropped, not treated as independent."),
    dict(id="non_circular", label="Exclude circular corroboration", predicate="non_circular",
         params={}, address_level=True, requires="conflicts",
         help="Drop addresses where at least one apparent confirmation is a restatement of a root already counted."),
    dict(id="exclude_licit_illicit_conflict", label="Exclude licit / illicit conflicts",
         predicate="exclude_licit_illicit_conflict", params={}, address_level=True, requires="conflicts",
         help="Drop addresses where comparable sources disagree on licit versus illicit."),
    dict(id="exclude_conflicts", label="Exclude all conflicts (entity-type and licit / illicit)",
         predicate="exclude_conflicts", params={}, address_level=True, requires="conflicts",
         help="Drop addresses with any entity-type or licit/illicit conflict."),
    dict(id="current_only", label="Exclude stale labels", predicate="current_only", params={},
         address_level=False, requires="staleness",
         help="Drop claims older than the staleness threshold. Claims with no revision date are kept: no date is not evidence of staleness."),
    dict(id="known_evidence_tier", label="Known evidence class only", predicate="min_evidence_tier",
         params={"tier": taxonomy.TIER_REPORT}, address_level=False,
         help="Drop claims whose evidence class is unknown (no declared methodology)."),
]
RULES_BY_ID = {r["id"]: r for r in RULES}


def _enriched(claims: list) -> list:
    """Claims stamped with the provenance fields the predicates read. A fresh
    upload's claims are not; copy so the workspace's own claims stay as-is."""
    out = []
    for c in claims:
        if "prov_resolved" in c and "root" in c:
            out.append(c)
            continue
        r = resolution_of(c)
        out.append(dict(c, root=r["root"], prov_resolved=r["resolved"], prov_native=r["native"],
                        prov_verified=r["verified"], prov_kind=r["kind"]))
    return out


def _context(ws, claims: list) -> dict:
    by_addr = collections.defaultdict(list)          # subject (chain + address) -> claims
    for c in claims:
        by_addr[provenance.subject_key(c)].append(c)
    ref = ws.reference_corpus
    if ref is not None:
        for k, cs in by_addr.items():
            by_addr[k] = cs + list(ref.for_subject(cs[0].get("blockchain"), cs[0]["address"]))
    return dict(claims_by_address=dict(by_addr), as_of=_as_of(ws))


def _as_of(ws):
    import datetime
    if not ws.analysis_as_of_date:
        return None
    try:
        return datetime.date.fromisoformat(ws.analysis_as_of_date[:10])
    except ValueError:
        return None


def _apply(rule: dict, claims: list, ctx: dict) -> list:
    fn = predicates.REGISTRY[rule["predicate"]]
    params = rule["params"]
    if rule["address_level"]:
        verdict = {}
        out = []
        for c in claims:
            a = provenance.subject_key(c)
            if a not in verdict:
                verdict[a] = fn(c, ctx, **params)
            if verdict[a]:
                out.append(c)
        return out
    return [c for c in claims if fn(c, ctx, **params)]


def _rule_state(ws, rule: dict) -> dict:
    need = rule.get("requires")
    return state_of(ws, need) if need else dict(state="computed", reason=None, detail=None)


def trust_coverage(ws, rule_ids: list) -> dict:
    """Apply the selected existing trust predicates to the workspace's own
    claims and report how much evidence is retained. Coverage only - no
    forensic figure, and no claim that the retained subset is more accurate.

    A rule whose prerequisite analysis is not computed for this dataset (conflict
    rules with no comparable labels, the staleness rule with no attribution
    timestamp) is reported `not_applicable` with the reason and is skipped."""
    unknown = [r for r in rule_ids if r not in RULES_BY_ID]
    if unknown:
        raise KeyError(unknown[0])
    cache = _cache(ws)
    if "trust_base" not in cache:
        claims = _enriched(ws.claims)
        cache["trust_base"] = (claims, _context(ws, claims))
        cache["trust_individual"] = {}
    claims, ctx = cache["trust_base"]
    n_claims, n_addr = len(claims), len({provenance.subject_key(c) for c in claims})
    states = {r["id"]: _rule_state(ws, r) for r in RULES}
    applicable = {rid for rid, st in states.items() if st["state"] == "computed"}

    individual = cache["trust_individual"]
    for r in RULES:
        if r["id"] in applicable and r["id"] not in individual:
            kept = _apply(r, claims, ctx)
            individual[r["id"]] = dict(claims=len(kept), addresses=len({provenance.subject_key(c) for c in kept}))

    eligible, steps = claims, []
    for rid in rule_ids:
        if rid not in applicable:
            steps.append(dict(rule=rid, claims=None, addresses=None, **{k: states[rid][k] for k in ("state", "reason")}))
            continue
        eligible = _apply(RULES_BY_ID[rid], eligible, ctx)
        steps.append(dict(rule=rid, state="computed", claims=len(eligible),
                          addresses=len({provenance.subject_key(c) for c in eligible})))
    e_claims, e_addr = len(eligible), len({provenance.subject_key(c) for c in eligible})

    return dict(
        rules=[dict(id=r["id"], label=r["label"], help=r["help"], state=states[r["id"]]["state"],
                    reason=states[r["id"]]["reason"], detail=states[r["id"]]["detail"],
                    **(individual[r["id"]] if r["id"] in applicable else dict(claims=None, addresses=None)),
                    claims_share=(individual[r["id"]]["claims"] / n_claims if n_claims else None)
                    if r["id"] in applicable else None)
               for r in RULES],
        selected=list(rule_ids), steps=steps,
        skipped=[s["rule"] for s in steps if s["state"] != "computed"],
        universe=dict(claims=n_claims, addresses=n_addr),
        eligible=dict(claims=e_claims, addresses=e_addr,
                      claims_share=e_claims / n_claims if n_claims else None,
                      addresses_share=e_addr / n_addr if n_addr else None),
        note="Coverage only: evidence retained under the selected rules. "
             "Retained does not mean correct, and dropped does not mean wrong.")
