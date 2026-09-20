"""STEP 23 - new dataset mode: upload -> crypto detection -> schema mapping
-> address validation -> claim normalization -> provenance extraction ->
reference-source comparison -> overlap/agreement/independence ->
freshness -> reliability profile.

Every stage that could not run says so explicitly (STEP 23's "impossible,
because ..."); nothing here fabricates a result for a dataset that lacks the
evidence to support it. An unrecognized `source_id` gets no provenance rule
from config/sources/ and therefore resolves UNRESOLVED by construction
(themis.provenance.resolve) - a brand-new dataset is never silently assumed
either identified or independent.

Loop 2 STEP 3: cross-source comparison is computed by `target_audit`, never
by unioning the target's claims into the reference corpus and re-running the
corpus-wide agreement/independence analyses - that would let reference-
reference relationships the target never touched leak into its numbers.
"""
from __future__ import annotations
import csv, gzip

from .. import corpus as _corpus, analysis, target_audit, chains
from . import detect as _detect, schema as _schema, validate as _validate, claims as _claims

NOT_CRYPTO_MESSAGE = (
    "This dataset does not appear to contain cryptocurrency attribution data.\n\n"
    "THEMIS's forensic reliability methodology is designed for cryptocurrency "
    "attribution datasets.\n\n"
    "Basic structural data-quality checks can still be performed, but "
    "provenance-aware cryptocurrency attribution analysis is not applicable."
)

UNSUPPORTED_CHAIN_MESSAGE = (
    "Cryptocurrency attribution data appears to be present, but this blockchain "
    "is not currently supported for full forensic reliability analysis.\n\n"
    "Column '{field}' contains address-shaped identifiers that no registered "
    "chain adapter ({supported}) validates. THEMIS V1 only ships full address "
    "validation, provenance resolution and cross-source comparison for the "
    "chains it has an adapter for.\n\n"
    "Basic structural data-quality checks can still be performed."
)

CRYPTO_NON_ATTRIBUTION_MESSAGE = (
    "Cryptocurrency data was detected (column '{field}' references a recognized "
    "cryptocurrency), but no usable attribution-label structure was identified.\n\n"
    "This looks like price, market, or transaction data rather than an attribution "
    "dataset (addresses linked to entities or categories). THEMIS's forensic "
    "reliability methodology audits attribution claims, not raw market data.\n\n"
    "Basic structural data-quality checks can still be performed."
)


def load_csv(path: str) -> tuple[list[dict], list[str]]:
    # utf-8-sig strips a leading UTF-8 BOM if present (common from
    # Excel-exported CSVs) and is otherwise identical to utf-8, so a
    # BOM-free file is unaffected; without it the BOM survives as part of
    # the first column's *name* (e.g. "﻿address"), breaking any exact
    # match against it (a --map override, a later schema round-trip).
    # errors="replace" turns a genuinely non-UTF-8 upload (binary content,
    # another encoding entirely) into a readable-if-garbled file instead of
    # an unhandled UnicodeDecodeError - detection then correctly reports no
    # usable address column rather than the request crashing outright.
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def ingest(path: str, source_id: str, mapping_override: dict | None = None,
          reference: "_corpus.Corpus | None" = None, sample_size: int = 500,
          analysis_as_of_date=None, progress=None) -> dict:
    """`progress`, when given, is called as progress("start"|"complete", stage_id,
    detail) around each real stage so a caller (the API's job runner) can
    report genuine pipeline state. It changes nothing about the result."""
    def _p(event, stage, detail=None):
        if progress is not None:
            progress(event, stage, detail)

    _p("start", "parse")
    rows, fieldnames = load_csv(path)
    _p("complete", "parse", f"{len(rows):,} rows \u00b7 {len(fieldnames)} columns")

    _p("start", "detect")
    inferred = _schema.infer_mapping(rows, fieldnames, sample_size)
    detection = inferred["detection"]
    _p("complete", "detect", f"{detection.get('blockchain') or 'no chain'} \u00b7 confidence {detection.get('confidence')}")

    if detection["confidence"] == _detect.NONE and not mapping_override:
        unsupported_field = detection.get("unsupported_chain_field")
        crypto_asset_field = detection.get("crypto_asset_field")
        if unsupported_field:
            supported = ", ".join(sorted(chains.all_adapters())) or "none registered"
            message = UNSUPPORTED_CHAIN_MESSAGE.format(field=unsupported_field, supported=supported)
        elif crypto_asset_field:
            message = CRYPTO_NON_ATTRIBUTION_MESSAGE.format(field=crypto_asset_field)
        else:
            message = NOT_CRYPTO_MESSAGE
        return dict(source_id=source_id, stopped=True, message=message,
                    detection=detection,
                    basic_quality=dict(rows=len(rows), columns=fieldnames,
                                       empty_rows=sum(1 for r in rows if not any(r.values()))))

    mapping = dict(inferred["mapping"])
    if mapping_override:
        mapping.update({k: v for k, v in mapping_override.items() if v is not None})

    chain_id = detection.get("blockchain")
    _p("start", "validate")
    validation = _validate.validate_rows(rows, mapping, chain_id)
    _p("complete", "validate", f"{len(validation['valid_rows']):,} of {len(rows):,} rows have a valid address")
    _p("start", "normalize")
    claims = _claims.build_claims(validation["valid_rows"], mapping, source_id, blockchain=chain_id)
    _p("complete", "normalize", f"{len(claims):,} claims")

    capabilities = {"address_validation": True, "claim_normalization": True,
                    "internal_consistency": True}
    limitations = []

    if not mapping.get("timestamp"):
        limitations.append("Freshness unavailable: no timestamp field was mapped.")
    else:
        capabilities["freshness"] = True

    target_result = None
    _p("start", "compare")
    if reference is not None and claims:
        target_result = target_audit.audit_target_against_reference(
            claims, reference, analysis_as_of_date=analysis_as_of_date)
        capabilities["cross_source_comparison"] = True
        capabilities["provenance_extraction"] = True
        limitations.extend(target_result["limitations"])
        if getattr(reference, "sample_note", None):
            limitations.append("Reference corpus is a bundled sample, not the full published "
                               "corpus: cross-source figures above cover only what the sample "
                               "contains.")
    else:
        limitations.append("Cross-source comparison unavailable: no reference corpus was supplied.")
        limitations.append("Provenance extraction limited: this source has no declared "
                           "provenance rule, so every claim's root is UNRESOLVED by default.")
        fresh = analysis.freshness(claims, as_of=analysis_as_of_date) if mapping.get("timestamp") else None
        target_result = dict(
            n_target_addresses=len({c["address"] for c in claims}), n_target_claims=len(claims),
            address_comparability={}, address_resolution={},
            profile=dict(
                data_quality=dict(available=True, target_addresses=len({c["address"] for c in claims}),
                                  target_claims=len(claims)),
                reference_comparability=_unavailable_dim("no reference corpus was supplied"),
                agreement=_unavailable_dim("no reference corpus was supplied"),
                provenance=_unavailable_dim("no reference corpus was supplied"),
                independence=_unavailable_dim("no reference corpus was supplied"),
                currency=(dict(available=True, **fresh) if fresh is not None
                         else _unavailable_dim("no revision-date field was mapped")),
                evidence_class=target_audit.evidence_class_tally(claims),
            ),
            limitations=[], inheritance_candidates=[],
        )

    _p("complete", "compare",
       "provenance, reference comparison, independence and currency" if reference is not None
       else "internal checks only (no reference corpus)")
    return dict(
        source_id=source_id, stopped=False,
        detection=detection, schema_mapping=mapping,
        validation={k: v for k, v in validation.items() if k != "valid_rows"},
        claims=claims, capabilities=capabilities, limitations=limitations,
        target_audit=target_result, reliability_profile=target_result["profile"],
    )


def _unavailable_dim(reason: str) -> dict:
    return dict(available=False, reason=reason)
