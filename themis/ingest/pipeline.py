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
"""
from __future__ import annotations
import csv, gzip

from .. import corpus as _corpus, analysis, reliability
from . import detect as _detect, schema as _schema, validate as _validate, claims as _claims

NOT_CRYPTO_MESSAGE = (
    "This dataset does not appear to contain cryptocurrency attribution data.\n\n"
    "THEMIS's forensic reliability methodology is designed for cryptocurrency "
    "attribution datasets.\n\n"
    "Basic structural data-quality checks can still be performed, but "
    "provenance-aware cryptocurrency attribution analysis is not applicable."
)


def load_csv(path: str) -> tuple[list[dict], list[str]]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def ingest(path: str, source_id: str, mapping_override: dict | None = None,
          reference: "_corpus.Corpus | None" = None, sample_size: int = 500) -> dict:
    rows, fieldnames = load_csv(path)

    inferred = _schema.infer_mapping(rows, fieldnames, sample_size)
    detection = inferred["detection"]

    if detection["confidence"] == _detect.NONE and not mapping_override:
        return dict(source_id=source_id, stopped=True, message=NOT_CRYPTO_MESSAGE,
                    detection=detection,
                    basic_quality=dict(rows=len(rows), columns=fieldnames,
                                       empty_rows=sum(1 for r in rows if not any(r.values()))))

    mapping = dict(inferred["mapping"])
    if mapping_override:
        mapping.update({k: v for k, v in mapping_override.items() if v is not None})

    chain_id = detection.get("blockchain")
    validation = _validate.validate_rows(rows, mapping, chain_id)
    claims = _claims.build_claims(validation["valid_rows"], mapping, source_id)

    capabilities = {"address_validation": True, "claim_normalization": True,
                    "internal_consistency": True}
    limitations = []

    fresh = None
    if mapping.get("timestamp"):
        fresh = analysis.freshness(claims)
        capabilities["freshness"] = True
    else:
        limitations.append("Freshness unavailable: no timestamp field was mapped.")

    agree = indep = kappa = None
    if reference is not None and claims:
        combined = _corpus.Corpus(list(claims) + list(reference.claims), full=True)
        agree = analysis.agreement(combined)
        indep = analysis.independence(combined)
        kappa = analysis.cohen_kappa(combined)
        capabilities["cross_source_comparison"] = True
        capabilities["provenance_extraction"] = True
        if getattr(reference, "sample_note", None):
            limitations.append("Reference corpus is a bundled sample, not the full published "
                               "corpus: cross-source figures above cover only what the sample "
                               "contains. " + reference.sample_note)
    else:
        limitations.append("Cross-source comparison unavailable: no reference corpus was supplied.")
        limitations.append("Provenance extraction limited: this source has no declared "
                           "provenance rule, so every claim's root is UNRESOLVED by default.")

    profile = reliability.build_profile(validation, agreement=agree, independence=indep,
                                        freshness=fresh, kappa=kappa)

    return dict(
        source_id=source_id, stopped=False,
        detection=detection, schema_mapping=mapping,
        validation={k: v for k, v in validation.items() if k != "valid_rows"},
        claims=claims, capabilities=capabilities, limitations=limitations,
        agreement=agree, independence=indep, kappa=kappa, freshness=fresh,
        reliability_profile=profile,
    )
