"""STEP 21 - composable eligibility predicates for trust-rule policies.

Every predicate takes one claim plus a shared `context` dict for the runtime
data a policy needs but that has no business in a YAML file (an address's
sibling claims, an external anchor set) and returns whether that claim is
eligible. None of them know what a "ransomware" or a "rodwald" is - a policy
is just a named list of these, declared in config/trust_rules.yml.
"""
from __future__ import annotations
from .. import taxonomy, provenance


def _siblings(claim, context):
    return context.get("claims_by_address", {}).get(claim["address"], ())


def root_independent_or_native(claim, context):
    """STEP 12/20 - an address's claims are eligible only if at least one of
    them is independently groundable: unresolved (we cannot prove it
    duplicates anything) or a root's native origin. If every claim at this
    address is a resolved, non-native restatement of another source's
    finding - a copy with nothing here to corroborate it - the whole address
    is excluded, not just the copy, so a downstream address-level
    aggregation (revenue, exposure, ...) still dedups across every eligible
    claim rather than being pinned to whichever one happened to pass alone."""
    sibs = _siblings(claim, context) or (claim,)
    return any(not c.get("prov_resolved") or c.get("prov_native") for c in sibs)


def anchor_membership(claim, context):
    """STEP 14 - eligible only if an independent anchor set names this
    address. A claim can never validate itself through its own provenance
    root, so the anchor set must come from the caller, never be derived from
    the claims being scored."""
    anchors = context.get("anchor_addresses")
    return anchors is not None and claim["address"] in anchors


def resolved_provenance_only(claim, context):
    return bool(claim.get("prov_resolved"))


def min_evidence_tier(claim, context, tier):
    order = taxonomy.TIER_ORDER
    want = order.index(tier) if tier in order else len(order)
    have = order.index(taxonomy.tier_of(claim)) if taxonomy.tier_of(claim) in order else len(order)
    return have <= want


def _address_outcome(claim, context):
    sibs = _siblings(claim, context)
    return taxonomy.classify_address(sibs) if len({c["source"] for c in sibs}) >= 2 else None


def non_circular(claim, context):
    sibs = _siblings(claim, context)
    return not provenance.address_independence(sibs)["circular"]


def exclude_conflicts(claim, context):
    return _address_outcome(claim, context) not in ("entity-type conflict", "licit/illicit conflict")


def exclude_licit_illicit_conflict(claim, context):
    return _address_outcome(claim, context) != "licit/illicit conflict"


def current_only(claim, context):
    # `as_of` (Loop 2 STEP 16): defaults to live "today" only when the
    # caller supplies none, same fallback as taxonomy.currency_flags itself
    # - a paper-reproduction run must pass the corpus's frozen snapshot_date
    # via context, or this policy's eligible set (and therefore any
    # downstream drift figure that uses it) would silently change as real
    # time passes even though the archived corpus never does.
    return "stale" not in taxonomy.currency_flags(claim, today=context.get("as_of"))


REGISTRY = {
    "root_independent_or_native": root_independent_or_native,
    "anchor_membership": anchor_membership,
    "resolved_provenance_only": resolved_provenance_only,
    "min_evidence_tier": min_evidence_tier,
    "non_circular": non_circular,
    "exclude_conflicts": exclude_conflicts,
    "exclude_licit_illicit_conflict": exclude_licit_illicit_conflict,
    "current_only": current_only,
}
