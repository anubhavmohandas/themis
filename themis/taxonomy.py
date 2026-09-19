"""Reliability taxonomy: tiers, flags, canonical categories, conflict logic.

Every rule here is executable against a label corpus without human judgement
beyond the category mapping itself, and that mapping is loaded from
config/taxonomy.yml rather than declared here - a new category or a new
source's verified roots need a config edit, not a code change.
"""
from __future__ import annotations
import datetime
from . import config_io, provenance

_cfg = config_io.load()
CATEGORIES: dict = _cfg.taxonomy

#: category -> polarity, straight from config
POLARITY = {cat: node.get("polarity", "unknown") for cat, node in CATEGORIES.items()}

#: the underspecified placeholder at the root of each polarity branch - e.g.
#: `illicit_unspec` - pairing one of these with a specific descendant is a
#: refinement, not a conflict.
GENERIC = {cat for cat, node in CATEGORIES.items()
           if node.get("parent") is None and node.get("polarity") in ("licit", "illicit")}

#: lowercased alias -> canonical category, for normalizing a newly-ingested
#: dataset's raw label text (STEP 5). The canonical name and its own aliases
#: both index to themselves/each other.
ALIASES = {}
for _cat, _node in CATEGORIES.items():
    ALIASES[_cat.lower()] = _cat
    for _a in _node.get("aliases", []) or []:
        ALIASES[str(_a).lower()] = _cat


#: separators that mark a "type:entity"-shaped structured label (STEP: see
#: split_structured_label). Config-driven so a new source's own convention
#: doesn't need a code change.
STRUCTURED_LABEL_SEPARATORS = _cfg.thresholds.get("structured_label_separators", [":"])


def split_structured_label(raw: str) -> tuple[str | None, str | None]:
    """If `raw` doesn't canonicalize whole but looks like "type:entity" (or
    another configured separator) and the type-shaped prefix *does*
    canonicalize, return (category, entity). Otherwise (None, None) - a
    structured-looking string whose prefix isn't a known alias stays
    unmapped rather than guessed, exactly like a plain unmapped label
    (e.g. `provenance.py`'s `_after_colon`, the same split THEMIS already
    uses to decode `prov_family` values).

    Only the first configured separator actually present in `raw` is tried,
    and only the text before it - "a:b:c" is (category-of("a"), "b:c"), not
    recursively re-split. A colon inside a URL or free text never matches
    unless the text before it happens to itself be a declared alias, which
    is the same protection whole-string lookup already has.
    """
    raw = (raw or "").strip()
    if not raw or ALIASES.get(raw.lower()) is not None:
        return None, None   # already handled by (or would be, in) whole-string lookup
    for sep in STRUCTURED_LABEL_SEPARATORS:
        if sep in raw:
            prefix, entity = raw.split(sep, 1)
            cat = ALIASES.get(prefix.strip().lower())
            if cat is not None:
                return cat, entity.strip()
            return None, None
    return None, None


def canonicalize_category(raw: str) -> str | None:
    """Map free-text label text to a canonical category via the taxonomy's
    declared aliases, falling back to a structured "type:entity" label's
    type-shaped prefix (STEP: split_structured_label). Returns None - never
    a guess - when nothing matches either way."""
    hit = ALIASES.get((raw or "").strip().lower())
    if hit is not None:
        return hit
    cat, _entity = split_structured_label(raw)
    return cat


def ancestors(cat: str) -> set:
    """`cat` and every category above it up to the root, by parent link."""
    seen = set()
    while cat and cat not in seen and cat in CATEGORIES:
        seen.add(cat)
        cat = CATEGORIES[cat].get("parent")
    return seen


# ---------------------------------------------------------------------- tiers
TIER_VERIFIED = "verified"
TIER_DERIVED = "derived"
TIER_REPORT = "unverified-report"
#: insufficient metadata to place a claim in one of the paper's three
#: evidence classes - distinct from TIER_REPORT, which means the metadata
#: *is* sufficient to say "no heuristic was declared". An arbitrary upload
#: with no declared methodology must land here, never silently become
#: DERIVED (STEP 9): unknown methodology is not evidence of derivation.
TIER_UNKNOWN = "unknown"
TIER_ORDER = [TIER_VERIFIED, TIER_DERIVED, TIER_REPORT, TIER_UNKNOWN]

#: heuristic-dependency value -> tier. Declared per source at ingestion.
TIER_BY_HEURISTIC = {
    # was TIER_VERIFIED. Paper Sec 3 / 4.2: a manual annotation reaches the
    # verified tier only where the underlying evidence is retained and
    # re-checkable, and WatchYourBack's own annotations "do not themselves
    # reach the verified tier". A source calling its output manually verified
    # is a declaration about its process (README: declared confidence is not
    # verified ground truth). A record whose *root* terminates in re-checkable
    # evidence (e.g. an OFAC designation) still lands in VERIFIED through
    # `prov_verified` / VERIFIED_ROOTS in tier_of(), ahead of this table.
    "manual_verified": TIER_DERIVED,
    "curated": TIER_DERIVED,
    "multi_input": TIER_DERIVED,
    "inherited": TIER_DERIVED,
    "undisclosed": TIER_DERIVED,
    "none": TIER_REPORT,
    "": TIER_REPORT,
    "unknown": TIER_UNKNOWN,
}


def _verified_roots_from_config() -> set:
    """Root names that some source config declares `verified: true` for -
    STEP 6: a root terminating in independently re-checkable evidence.
    Only statically-named roots (fixed_root / explicit map entries) can be
    declared this way; a templated fallback root is never verified."""
    roots = set()
    for src in _cfg.sources.values():
        prov = src.get("provenance", {})
        if prov.get("mode") == "fixed_root" and prov.get("verified"):
            roots.add(prov["root"])
        for entry in list((prov.get("map") or {}).values()) + list(prov.get("contains_rules") or []):
            if isinstance(entry, dict) and entry.get("verified"):
                roots.add(entry["root"])
    return roots


VERIFIED_ROOTS = _verified_roots_from_config()
STALE_AFTER_YEARS = float(_cfg.thresholds.get("staleness_years", 3.0))


def tier_of(claim: dict) -> str:
    """Tier for a single claim. A verified provenance root overrides the
    declared heuristic dependency; `prov_verified` is set by the provenance
    resolver at load time, with a name-based fallback for claims built
    without going through it (e.g. in tests)."""
    if claim.get("prov_verified") or claim.get("root") in VERIFIED_ROOTS:
        return TIER_VERIFIED
    return TIER_BY_HEURISTIC.get(claim.get("heuristic", ""), TIER_REPORT)


def currency_flags(claim: dict, today: datetime.date | None = None) -> list[str]:
    """`currency unknown` when no revision field exists; `stale` only when a
    date exists and is older than the threshold. Absence of a date is never
    reported as staleness - it means currency cannot be established either way."""
    today = today or datetime.date.today()
    lm = (claim.get("lastmod") or "").strip()
    if not lm:
        return ["currency-unknown"]
    try:
        d = datetime.date.fromisoformat(lm[:10])
    except ValueError:
        return ["currency-unknown"]
    age = (today - d).days / 365.25
    return ["stale"] if age > STALE_AFTER_YEARS else []


def classify_address(claims: list[dict]) -> str:
    """Agreement outcome for one address carrying claims from >= 2 datasets.

    Walks the taxonomy tree rather than a flat category list, so a claim
    pair is a hierarchical refinement whenever one member is the polarity's
    generic placeholder *or* one category is a taxonomy-declared ancestor of
    the other (STEP 6's "service vs exchange" case), not only in the
    two-level case this corpus happens to use.

    Comparing what sources say requires at least two of them to have said
    something interpretable. A source whose raw label never mapped to a
    canonical category (canon == "unknown" - e.g. Elliptic++'s undocumented
    numeric class codes) contributed no usable opinion; if only one source's
    claim is left after removing those, there is nothing to compare it
    against, and this must be `incomparable`, not "exact agreement" with
    itself. Excluding the unknown claim from `cats` but not from the source
    count would silently launder "we don't know what source B said" into
    "source B agrees with source A".
    """
    known_sources = {c["source"] for c in claims if c["canon"] != "unknown"}
    cats = {c["canon"] for c in claims if c["canon"] != "unknown"}
    if len(known_sources) < 2:
        return "incomparable"
    if len(cats) == 1:
        return "exact"
    pol = {POLARITY.get(c, "unknown") for c in cats} - {"unknown"}
    if len(pol) > 1:
        return "licit/illicit conflict"
    specific = cats - GENERIC
    if len(specific) <= 1:
        return "hierarchical refinement"
    anc = {c: ancestors(c) for c in specific}
    if all(a in anc[b] or b in anc[a] for a in specific for b in specific):
        return "hierarchical refinement"
    return "entity-type conflict"


OUTCOMES = ["exact", "hierarchical refinement", "entity-type conflict",
            "licit/illicit conflict", "incomparable"]


def flags_for_address(claims: list[dict], today=None) -> list[str]:
    """Flags that apply to the address as a whole."""
    out = []
    outcome = classify_address(claims) if len({c["source"] for c in claims}) >= 2 else None
    if outcome in ("licit/illicit conflict", "entity-type conflict"):
        out.append("conflicting")
    if provenance.address_independence(claims)["circular"]:
        out.append("circular")   # at least one apparent confirmation is inherited
    per = [f for c in claims for f in currency_flags(c, today)]
    if per and all(f == "currency-unknown" for f in per):
        out.append("currency-unknown")
    elif "stale" in per:
        out.append("stale")
    return out


def best_tier(claims: list[dict]) -> str:
    tiers = {tier_of(c) for c in claims}
    for t in TIER_ORDER:
        if t in tiers:
            return t
    return TIER_REPORT
