"""STEP 3 - the canonical claim model. Raw label text is preserved
unchanged; only `canon`/`polarity` are derived, and only through the
taxonomy's declared aliases (config/taxonomy.yml) - never guessed.
"""
from __future__ import annotations
import uuid
from .. import taxonomy

#: the flat claim schema every analysis function in this package reads.
CLAIM_FIELDS = ["address", "source", "raw_label", "canon", "polarity",
                "prov_family", "lastmod", "heuristic", "subcat"]


def normalize_date(value: str) -> str:
    v = (value or "").strip()
    return v[:10] if v else ""


def build_claim(row: dict, mapping: dict, source_id: str, default_heuristic: str = "unknown",
                record_id: str | int | None = None, blockchain: str | None = None) -> dict:
    """One row, one claim. `source_id` should not collide with a bundled
    source id in config/sources/ unless this really is that source - an
    unrecognized id gets no provenance rule and resolves UNRESOLVED, which
    is the correct default for a dataset THEMIS has never seen before.

    `default_heuristic="unknown"` (STEP 9): a dataset THEMIS ingests fresh
    has no declared methodology unless its source config says otherwise, so
    it must resolve to TIER_UNKNOWN, not TIER_DERIVED ("undisclosed" is a
    *declared* fact about a bundled source - that a heuristic was used but
    not described - which is a stronger claim than "we don't know").
    """
    raw_label = (row.get(mapping.get("label")) or "").strip() if mapping.get("label") else ""
    raw_category = (row.get(mapping.get("category")) or "").strip() if mapping.get("category") else ""
    # A dataset can carry a free-text label/name column (label role - might
    # be an entity name, not a category word at all) alongside a distinct,
    # dedicated classification column (category role). Schema inference
    # already tells them apart (schema.py's CATEGORY_HINTS); canonicalizing
    # only ever tried `label`, so a mapped `category` column's value was
    # silently ignored for classification (though still preserved as
    # `subcat`) - a real dataset shaped like address/entity_name/category
    # would stay "unknown" forever even with an unambiguous category value
    # sitting right there. Category is tried first as the more deliberately-
    # classified field when both are mapped; label is the fallback, keeping
    # today's behavior unchanged for the common single-column case.
    canon = (taxonomy.canonicalize_category(raw_category)
            or taxonomy.canonicalize_category(raw_label) or "unknown")
    declared_source = (row.get(mapping.get("source")) or "").strip() if mapping.get("source") else ""
    return {
        "claim_id": uuid.uuid4().hex,
        "record_id": record_id,
        "blockchain": blockchain,
        "address": (row.get(mapping.get("address")) or "").strip(),
        "source": source_id,
        "actor": (row.get(mapping.get("actor")) or "").strip() if mapping.get("actor") else "",
        "raw_label": raw_label,
        "canon": canon,
        "polarity": taxonomy.POLARITY.get(canon, "unknown"),
        "prov_family": declared_source,
        "source_url": declared_source if declared_source.lower().startswith(("http://", "https://")) else "",
        "lastmod": normalize_date(row.get(mapping.get("timestamp"), "")) if mapping.get("timestamp") else "",
        "retrieval_date": None,
        # STEP 8: confidence survives ingestion uninterpreted - normalizing it
        # requires a source registry entry declaring what the value means,
        # which an unseen upload never has.
        "confidence_raw": (row.get(mapping.get("confidence")) or "").strip() if mapping.get("confidence") else "",
        "confidence_normalized": None,
        "heuristic": default_heuristic,
        "subcat": (row.get(mapping.get("category")) or "").strip() if mapping.get("category") else "",
        "notes": "",
    }


def build_claims(rows: list[dict], mapping: dict, source_id: str, default_heuristic: str = "unknown",
                 blockchain: str | None = None) -> list[dict]:
    return [build_claim(r, mapping, source_id, default_heuristic, record_id=i, blockchain=blockchain)
            for i, r in enumerate(rows)]
