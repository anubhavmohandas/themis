"""Reliability taxonomy: tiers, flags, canonical categories, conflict logic.

Every rule here is executable against a label corpus without human judgement
beyond the category mapping itself, which is declared rather than inferred.
"""
from __future__ import annotations
import datetime

# ---------------------------------------------------------------- categories
POLARITY = {
    "ransomware": "illicit", "mixer": "illicit", "darknet_market": "illicit",
    "ponzi": "illicit", "scam": "illicit", "sextortion": "illicit",
    "malware": "illicit", "extremism": "illicit", "sanctioned": "illicit",
    "hack": "illicit", "terrorism": "illicit", "trafficking": "illicit",
    "exchange": "licit", "mining": "licit", "gambling": "licit",
    "faucet": "licit", "bridge": "licit", "payment_proc": "licit",
    "wallet_service": "licit", "marketplace_legal": "licit", "individual": "licit",
    "illicit_unspec": "illicit", "licit_unspec": "licit",
    "unknown": "unknown",
}
GENERIC = {"illicit_unspec", "licit_unspec"}

# ---------------------------------------------------------------------- tiers
TIER_VERIFIED = "verified"
TIER_DERIVED = "derived"
TIER_REPORT = "unverified-report"
TIER_ORDER = [TIER_VERIFIED, TIER_DERIVED, TIER_REPORT]

#: heuristic-dependency value -> tier. Declared per source at ingestion.
TIER_BY_HEURISTIC = {
    "manual_verified": TIER_VERIFIED,
    "curated": TIER_DERIVED,
    "multi_input": TIER_DERIVED,
    "inherited": TIER_DERIVED,
    "undisclosed": TIER_DERIVED,
    "none": TIER_REPORT,
    "": TIER_REPORT,
}

#: provenance roots that terminate in evidence independent of on-chain inference
VERIFIED_ROOTS = {"ofac_sdn", "watchyourback_manual", "exchange_self_disclosure"}

STALE_AFTER_YEARS = 3.0


def tier_of(claim: dict) -> str:
    """Tier for a single claim. Provenance root overrides heuristic dependency."""
    if claim.get("root") in VERIFIED_ROOTS:
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
    """Agreement outcome for one address carrying claims from >= 2 datasets."""
    cats = {c["canon"] for c in claims if c["canon"] != "unknown"}
    if not cats:
        return "incomparable"
    if len(cats) == 1:
        return "exact"
    pol = {POLARITY.get(c, "unknown") for c in cats} - {"unknown"}
    if len(pol) > 1:
        return "licit/illicit conflict"
    return "hierarchical refinement" if len(cats - GENERIC) <= 1 else "entity-type conflict"


OUTCOMES = ["exact", "hierarchical refinement", "entity-type conflict",
            "licit/illicit conflict", "incomparable"]


def flags_for_address(claims: list[dict], today=None) -> list[str]:
    """Flags that apply to the address as a whole."""
    out = []
    outcome = classify_address(claims) if len({c["source"] for c in claims}) >= 2 else None
    if outcome in ("licit/illicit conflict", "entity-type conflict"):
        out.append("conflicting")
    roots = {c.get("root") for c in claims}
    srcs = {c["source"] for c in claims}
    if len(srcs) >= 2 and len(roots) < len(srcs):
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
