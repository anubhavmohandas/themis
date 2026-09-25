"""Which downstream analyses may run for an uploaded dataset, and why not when
they may not. A metric that cannot validly be computed is reported with one of
these states instead of a misleading zero: "0 attribution conflicts" would say
the labels were compared and agreed, when nothing was comparable.

    computed            ran; the figure means what it says
    not_applicable      its prerequisite input does not exist for this dataset
    insufficient_data   the input exists but is too thin to conclude anything
    unsupported_schema  the dataset failed pre-flight; nothing may run
"""
from __future__ import annotations
from .. import config_io

COMPUTED = "computed"
NOT_APPLICABLE = "not_applicable"
INSUFFICIENT_DATA = "insufficient_data"
UNSUPPORTED_SCHEMA = "unsupported_schema"

ANALYSES = ("provenance", "reference_match", "conflicts", "staleness", "trust")


def _s(state: str, reason: str | None = None, **extra) -> dict:
    return dict(state=state, reason=reason, **extra)


def blocked(preflight: dict) -> dict:
    """Every analysis is unsupported when the dataset did not pass pre-flight."""
    why = (preflight["blockers"][0]["message"] if preflight.get("blockers")
           else "the dataset did not pass pre-flight")
    return {a: _s(UNSUPPORTED_SCHEMA, why) for a in ANALYSES}


def evaluate(preflight: dict, claims: list[dict], target_result: dict, reference) -> dict:
    profile = target_result["profile"]
    out = {}

    declared_values = [(c.get("prov_family") or "").strip() for c in claims]
    declared = sum(1 for v in declared_values if v)
    distinct = len({v for v in declared_values if v})
    if not declared:
        out["provenance"] = _s(INSUFFICIENT_DATA, "no declared-source field is mapped (or it is empty), so the "
                               "provenance of this dataset's claims cannot be established; every claim's root "
                               "stays UNRESOLVED")
    elif (distinct <= config_io.load().preflight["source_class_max_distinct"]
          and len(claims) > config_io.load().preflight["source_class_min_rows_per_value"] * distinct):
        # a handful of values repeated over every claim is a class or method of evidence: it says how a
        # label was made, not which source made it, so it cannot resolve a provenance root
        out["provenance"] = _s(
            INSUFFICIENT_DATA,
            f"the declared-source column holds only {distinct} distinct value(s) across {len(claims):,} claims: a "
            "class or method of evidence, not where each claim came from. No provenance root can be established "
            "from it, and different values are not independent sources; every claim's root stays UNRESOLVED",
            n_declared=declared, n_distinct_declared=distinct)
    else:
        out["provenance"] = _s(COMPUTED, f"{declared:,} of {len(claims):,} claims name a declared source",
                               n_declared=declared, n_distinct_declared=distinct)

    if reference is None:
        out["reference_match"] = _s(NOT_APPLICABLE, "no reference corpus was supplied")
    else:
        out["reference_match"] = _s(COMPUTED, None,
                                    n_matched=profile["reference_comparability"]["comparable"])

    ag = profile["agreement"]
    if ag.get("available") and ag.get("n_comparable"):
        out["conflicts"] = _s(COMPUTED, None, n_comparable=ag["n_comparable"])
    else:
        out["conflicts"] = _s(
            NOT_APPLICABLE, "no comparable attribution labels detected",
            detail=("no reference corpus was supplied" if reference is None
                    else "no address in this dataset has a claim in the reference corpus"))

    basis = preflight.get("currency_basis")
    if basis is None:
        others = {c: r for c, r in preflight["timestamp_roles"].items()}
        out["staleness"] = _s(
            NOT_APPLICABLE, "no attribution timestamp (last updated / last verified) is mapped",
            detail=("timestamp columns present, none of which dates the attribution: "
                    + ", ".join(f"{c} ({r})" for c, r in others.items())) if others else "no timestamp column present")
    elif not any((c.get("lastmod") or "").strip() for c in claims):
        out["staleness"] = _s(INSUFFICIENT_DATA, f"'{basis['column']}' is mapped but no claim carries a parseable date",
                              basis=basis)
    else:
        out["staleness"] = _s(COMPUTED, basis["rule"], basis=basis)

    out["trust"] = (_s(COMPUTED) if claims else
                    _s(INSUFFICIENT_DATA, "no valid claims survived validation"))
    return out
