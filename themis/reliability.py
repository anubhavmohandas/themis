"""STEP 16 - the dataset reliability profile: never a single 0-100 score,
always a multidimensional breakdown, and every dimension that could not be
computed says why rather than being filled with a guess (STEP 23).
"""
from __future__ import annotations


def _unavailable(reason: str) -> dict:
    return dict(available=False, reason=reason)


def build_profile(validation: dict, agreement: dict | None = None,
                  independence: dict | None = None, freshness: dict | None = None,
                  kappa: dict | None = None) -> dict:
    profile = {}

    profile["data_quality"] = dict(
        available=True,
        valid_records=validation["n_valid"],
        input_records=validation["n_input"],
        rejected=validation["n_rejected"],
        rejected_by_reason=validation.get("rejected_by_reason", {}),
    )

    if independence is not None:
        total = independence.get("n_roots_total") or 0
        ident = independence.get("n_roots_identified") or 0
        profile["provenance"] = dict(
            available=True,
            roots_total=total, roots_identified=ident,
            roots_unresolved=total - ident,
            unresolved_addresses=independence.get("unresolved_addresses"),
            unresolved_addr_share=independence.get("unresolved_addr_share"),
        )
    else:
        profile["provenance"] = _unavailable(
            "no cross-dataset provenance decode was run for this dataset")

    if agreement is not None:
        outcomes = agreement.get("outcomes", {})
        profile["corroboration"] = dict(
            available=True,
            single_source=agreement.get("single_source"),
            multi_source=agreement.get("n_multi_source"),
            multi_source_rate=agreement.get("multi_source_rate"),
        )
        profile["consistency"] = dict(
            available=True,
            exact=outcomes.get("exact", {}).get("n"),
            hierarchical_refinement=outcomes.get("hierarchical refinement", {}).get("n"),
            entity_type_conflict=outcomes.get("entity-type conflict", {}).get("n"),
            licit_illicit_conflict=outcomes.get("licit/illicit conflict", {}).get("n"),
            incomparable=outcomes.get("incomparable", {}).get("n"),
            chance_corrected=("see kappa" if kappa else None),
        )
    else:
        msg = "no second dataset was available to compare claims against"
        profile["corroboration"] = _unavailable(msg)
        profile["consistency"] = _unavailable(msg)

    if independence is not None and agreement is not None:
        by_root = independence.get("roots_per_multi_address", {})
        apparent = agreement.get("n_multi_source", 0)
        independent_only = by_root.get(1, 0)   # every apparent multi-source address whose claims share one root
        profile["independence"] = dict(
            available=True,
            apparent_multisource=apparent,
            inherited_or_circular=independent_only,
            roots_per_multi_address=by_root,
        )
    else:
        profile["independence"] = _unavailable(
            "independence requires both cross-dataset agreement and provenance decode")

    if freshness is not None:
        profile["currency"] = dict(available=True, **freshness)
    else:
        profile["currency"] = _unavailable("no revision-date field was mapped for this dataset")

    profile["verifiability"] = dict(
        available=True,
        note="externally comparable only where a reference corpus or anchor set was supplied; "
             "coverage below is not a correctness estimate (COVERAGE != ACCURACY)",
        externally_comparable=(agreement.get("n_multi_source") if agreement else None),
        unverifiable=(agreement.get("single_source") if agreement else validation["n_valid"]),
    )
    return profile
