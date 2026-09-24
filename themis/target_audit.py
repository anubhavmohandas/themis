"""Loop 2 STEP 3/4/5 - target-vs-reference auditing for an uploaded dataset.

The one rule this module exists to enforce: reference-reference agreement
must never leak into a target dataset's reliability numbers. Every figure
here is computed over the target's own addresses and only the reference
claims that land on those same addresses - never over the reference corpus
as a whole. A reference source disagreeing with another reference source on
addresses the target never mentions cannot move a single number this module
returns.
"""
from __future__ import annotations
import collections, datetime

from . import provenance, taxonomy, config_io, analysis

NO_REFERENCE_MATCH = "NO_REFERENCE_MATCH"
SAME_PROVENANCE = "REFERENCE_MATCH_BUT_SAME_PROVENANCE"
DISTINCT_PROVENANCE = "REFERENCE_MATCH_WITH_DISTINCT_PROVENANCE"
RELATIONSHIP_UNRESOLVED = "REFERENCE_RELATIONSHIP_UNRESOLVED"


def evidence_class_tally(claims: list[dict]) -> dict:
    """STEP 9 - VERIFIED/DERIVED/UNVERIFIED_REPORT/UNKNOWN over a claim
    list. Shared by both the with-reference and no-reference ingest paths
    so the tally is computed once, not re-derived differently in each."""
    tiers = collections.Counter(taxonomy.tier_of(c) for c in claims)
    n = len(claims) or 1
    return dict(available=True, verified=tiers.get(taxonomy.TIER_VERIFIED, 0),
               derived=tiers.get(taxonomy.TIER_DERIVED, 0),
               unverified_report=tiers.get(taxonomy.TIER_REPORT, 0),
               unknown=tiers.get(taxonomy.TIER_UNKNOWN, 0),
               verified_share=tiers.get(taxonomy.TIER_VERIFIED, 0) / n,
               unknown_share=tiers.get(taxonomy.TIER_UNKNOWN, 0) / n)


# ------------------------------------------------- STEP 12 generic discovery
def discover_inheritance_candidates(target_claims: list[dict], reference_corpus, thresholds=None) -> dict:
    """Directional containment between the target's address set and each
    reference source's, plus naming residue in the target's own declared-
    source text. Never declares copying - only a CANDIDATE_INHERITANCE
    signal with its supporting evidence, gated by the same containment
    thresholds already used for the bundled corpus's own field decodes.
    """
    cfg = config_io.load()
    thresholds = thresholds if thresholds is not None else cfg.thresholds
    inherited_share = thresholds.get("containment_inherited_share", 0.999)
    min_group = thresholds.get("min_containment_group", 5)

    residue_hits = _naming_residue(target_claims, cfg.sources)

    out = {}
    for src, ref_addrs in reference_corpus.src_addr.items():
        # only the target's identifiers on the chain this reference source covers can be contained in it
        src_chain = (cfg.sources.get(src) or {}).get("chain")
        target_addrs = {c["address"] for c in target_claims
                        if src_chain is None or c.get("blockchain") in (None, src_chain)}
        inter = target_addrs & ref_addrs
        if not inter or len(target_addrs) < min_group:
            continue
        share_target_in_ref = len(inter) / len(target_addrs)
        evidence = []
        status = "UNRESOLVED"
        relationship = "NO_SIGNAL"
        if share_target_in_ref >= inherited_share:
            evidence.append(f"{100*share_target_in_ref:.1f}% of the target's addresses "
                            f"also appear in reference source '{src}'")
            status, relationship = "INFERRED", "CANDIDATE_INHERITANCE"
        if src in residue_hits:
            evidence.append(f"{residue_hits[src]} target record(s) name '{src}' in their "
                            "own declared-source text")
            if status == "UNRESOLVED":
                status, relationship = "INFERRED", "CANDIDATE_INHERITANCE"
        if evidence:
            out[src] = dict(source=src, n_shared_addresses=len(inter),
                            share_of_target_in_reference=share_target_in_ref,
                            relationship_type=relationship, status=status, evidence=evidence)
    return out


def _naming_residue(target_claims: list[dict], sources_cfg: dict) -> dict:
    hits = collections.Counter()
    names = {}
    min_len = config_io.load().preflight["target_audit"]["min_source_name_length"]
    for sid, scfg in sources_cfg.items():
        candidates = {sid.lower(), str(scfg.get("display_name", "")).lower(),
                     str(scfg.get("citation", "")).lower()}
        names[sid] = {n for n in candidates if len(n) >= min_len}
    for c in target_claims:
        text = " ".join(str(c.get(f) or "") for f in ("prov_family", "source_url", "notes")).lower()
        if not text.strip():
            continue
        for sid, cand in names.items():
            if any(n in text for n in cand):
                hits[sid] += 1
    return dict(hits)


# --------------------------------------------------- per-address comparability
def _address_status(target_claims_here, ref_claims_here, inheritance):
    ref_sources = {c["source"] for c in ref_claims_here}
    flagged = {s for s in ref_sources if inheritance.get(s, {}).get("status") == "INFERRED"}
    if ref_sources and flagged == ref_sources:
        return SAME_PROVENANCE, "resolved"
    # A target claim and a reference claim can resolve to the identical
    # declared root directly (e.g. both trace to the same fixed_root),
    # without the corpus-wide containment heuristic above ever firing - that
    # heuristic needs a large enough address overlap to trigger at all, so a
    # single shared address would otherwise fall through to "unresolved"
    # despite the relationship being directly proven. Checked as a root
    # *intersection* between target and reference specifically, not via
    # address_independence's combined circular/shared_root_count, which
    # would also fire on sharing that is entirely internal to the target's
    # own claims and says nothing about the reference relationship.
    target_roots = {c.get("root", provenance.root_of(c)) for c in target_claims_here}
    ref_roots = {c.get("root", provenance.root_of(c)) for c in ref_claims_here}
    shared_roots = {r for r in target_roots & ref_roots if not provenance.is_unresolved(r)}
    if shared_roots:
        return SAME_PROVENANCE, "resolved"
    combo_indep = provenance.address_independence(target_claims_here + ref_claims_here)
    if combo_indep["confirmed_independent_root_count"] >= 2:
        return DISTINCT_PROVENANCE, "resolved"
    if flagged:
        return RELATIONSHIP_UNRESOLVED, "partially_resolved"
    return RELATIONSHIP_UNRESOLVED, "unresolved"


# --------------------------------------------------------------- the audit
def audit_target_against_reference(target_claims: list[dict], reference_corpus,
                                   analysis_as_of_date: datetime.date | None = None,
                                   thresholds: dict | None = None) -> dict:
    thresholds = thresholds if thresholds is not None else config_io.load().thresholds
    by_addr = collections.defaultdict(list)          # subject (chain + address) -> the target's claims
    for c in target_claims:
        by_addr[provenance.subject_key(c)].append(c)
    n_addr = len(by_addr)

    inheritance = discover_inheritance_candidates(target_claims, reference_corpus, thresholds)

    comparability, resolution, outcome_counter = {}, {}, collections.Counter()
    indep_rows = {}
    for addr, claims in by_addr.items():
        ref_claims = reference_corpus.for_subject(claims[0].get("blockchain"), claims[0]["address"])
        indep_rows[addr] = provenance.address_independence(claims + ref_claims)
        if not ref_claims:
            comparability[addr] = NO_REFERENCE_MATCH
            resolution[addr] = "unresolved"
            continue
        status, res = _address_status(claims, ref_claims, inheritance)
        comparability[addr] = status
        resolution[addr] = res
        # STEP 3: the outcome for this address is classified over the
        # target's own claim(s) plus only *its* matched reference claims -
        # never the reference corpus's other, unrelated internal agreement.
        outcome_counter[taxonomy.classify_address(claims + ref_claims)] += 1

    comparable_addrs = [a for a, s in comparability.items() if s != NO_REFERENCE_MATCH]
    n_comparable = len(comparable_addrs)
    n_incomparable = n_addr - n_comparable
    total_outcomes = sum(outcome_counter.values()) or 1

    apparent_multi = sum(1 for r in indep_rows.values() if r["apparent_dataset_count"] >= 2)
    confirmed_multi = sum(1 for r in indep_rows.values() if r["confirmed_independent_root_count"] >= 2)
    shared_only = sum(1 for a, r in indep_rows.items()
                      if r["apparent_dataset_count"] >= 2 and r["confirmed_independent_root_count"] < 2
                      and r["unresolved_source_count"] == 0)
    indep_unresolved = sum(1 for r in indep_rows.values()
                           if r["apparent_dataset_count"] >= 2 and r["unresolved_source_count"] > 0
                           and r["confirmed_independent_root_count"] < 2)

    fresh = analysis.freshness(target_claims, as_of=analysis_as_of_date)
    prov_resolution = collections.Counter(resolution.values())

    profile = dict(
        data_quality=dict(available=True, target_addresses=n_addr, target_claims=len(target_claims)),
        reference_comparability=dict(
            available=True, comparable=n_comparable, no_reference_match=n_incomparable,
            comparable_share=n_comparable / n_addr if n_addr else 0.0,
            no_reference_match_share=n_incomparable / n_addr if n_addr else 0.0,
        ),
        agreement=dict(
            available=n_comparable > 0,
            outcomes={k: dict(n=outcome_counter.get(k, 0),
                              share=outcome_counter.get(k, 0) / total_outcomes)
                     for k in taxonomy.OUTCOMES},
            n_comparable=n_comparable,
        ) if n_comparable else dict(available=False,
                                    reason="no target address had a matching reference claim"),
        provenance=dict(
            available=True,
            resolved=prov_resolution.get("resolved", 0),
            partially_resolved=prov_resolution.get("partially_resolved", 0),
            unresolved=prov_resolution.get("unresolved", 0),
            inheritance_candidates=list(inheritance.values()),
        ),
        independence=dict(
            available=True,
            apparent_multi_source=apparent_multi,
            confirmed_independent_multi_root=confirmed_multi,
            shared_or_inherited_only=shared_only,
            independence_unresolved=indep_unresolved,
        ),
        currency=dict(available=True, **fresh),
        evidence_class=evidence_class_tally(target_claims),
    )

    limitations = _limitations(n_addr, n_comparable, target_claims, fresh, prov_resolution)

    return dict(
        n_target_addresses=n_addr, n_target_claims=len(target_claims),
        address_comparability=comparability, address_resolution=resolution,
        profile=profile, limitations=limitations,
        inheritance_candidates=list(inheritance.values()),
    )


def _limitations(n_addr, n_comparable, claims, fresh, prov_resolution) -> list[str]:
    out = []
    if n_addr:
        no_match_share = 1 - (n_comparable / n_addr)
        if no_match_share > 0:
            out.append(f"No external public reference claim was available for "
                       f"{100*no_match_share:.1f}% of target addresses.")
    missing_dates = sum(1 for c in claims if not (c.get("lastmod") or "").strip())
    if claims and missing_dates:
        out.append(f"Revision dates were absent for {100*missing_dates/len(claims):.1f}% of claims.")
    if n_addr:
        unresolved_share = prov_resolution.get("unresolved", 0) / n_addr
        if unresolved_share > 0:
            out.append(f"Provenance could not be resolved for {100*unresolved_share:.1f}% "
                       "of target addresses.")
    if not n_comparable:
        out.append("Source-level accuracy cannot be estimated: no comparable external "
                   "evidence was available for this dataset.")
    return out
