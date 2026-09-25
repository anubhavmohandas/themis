"""STEP 3 - the canonical claim model. Raw label text is preserved
unchanged; only `canon`/`polarity` are derived, and only through the
taxonomy's declared aliases (config/taxonomy.yml) - never guessed.
"""
from __future__ import annotations
import uuid
from .. import taxonomy, provenance, chains

#: the flat claim schema every analysis function in this package reads.
CLAIM_FIELDS = ["address", "raw_address", "source", "raw_label", "canon", "polarity",
                "prov_family", "lastmod", "heuristic", "subcat"]


def normalize_date(value: str) -> str:
    v = (value or "").strip()
    return v[:10] if v else ""


def declared_source(row: dict, mapping: dict) -> str:
    """What the row itself says its source is (the mapped `source` column), or "" when none is mapped."""
    return (row.get(mapping.get("source")) or "").strip() if mapping.get("source") else ""


def build_claim(row: dict, mapping: dict, source_id: str, default_heuristic: str = "unknown",
                record_id: str | int | None = None, blockchain: str | None = None,
                provenance_record: dict | None = None, label_token: str | None = None) -> dict:
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
    label_cell = None
    if label_token is not None:
        # one token of a multi-label cell: it replaces the cell it was split from (the category when there
        # is one, as validation chose it), and the whole cell stays on the claim so nothing is lost
        label_cell = raw_category or raw_label
        if raw_category:
            raw_category = label_token
        else:
            raw_label = label_token
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
    cat_from_category = taxonomy.canonicalize_category(raw_category)
    cat_from_label = None if cat_from_category else taxonomy.canonicalize_category(raw_label)
    canon = cat_from_category or cat_from_label or "unknown"
    # a "type:entity"-shaped label (STEP: taxonomy.split_structured_label)
    # canonicalizes via its prefix; the entity half is real information
    # (who, not what) that the category alone discards, so it's kept here
    # rather than silently dropped.
    winning_text = raw_category if cat_from_category else (raw_label if cat_from_label else "")
    _, structured_entity = taxonomy.split_structured_label(winning_text)
    declared = declared_source(row, mapping)
    raw_address = (row.get(mapping.get("address")) or "").strip()
    adapter = chains.get(blockchain) if blockchain else None
    # the canonical spelling of an identifier on its chain (an EVM address is hex: case is not identity)
    canonical = adapter.normalize_address(raw_address) if adapter else raw_address
    return {
        "claim_id": uuid.uuid4().hex,
        "record_id": record_id,
        "blockchain": blockchain,
        "address": provenance.normalize_address(dict(source=source_id, address=canonical)),
        "raw_address": raw_address,
        "source": source_id,
        "actor": (row.get(mapping.get("actor")) or "").strip() if mapping.get("actor") else "",
        # who the address is said to belong to: metadata about the claim, never evidence for it
        "entity": (row.get(mapping.get("entity")) or "").strip() if mapping.get("entity") else "",
        "label_cell": label_cell,
        "raw_label": raw_label,
        "canon": canon,
        "polarity": taxonomy.POLARITY.get(canon, "unknown"),
        "prov_family": declared,
        "source_url": declared if declared.lower().startswith(("http://", "https://")) else "",
        "lastmod": normalize_date(row.get(mapping.get("timestamp"), "")) if mapping.get("timestamp") else "",
        "retrieval_date": None,
        # STEP 8: confidence survives ingestion uninterpreted - normalizing it
        # requires a source registry entry declaring what the value means,
        # which an unseen upload never has.
        "confidence_raw": (row.get(mapping.get("confidence")) or "").strip() if mapping.get("confidence") else "",
        "confidence_normalized": None,
        "heuristic": default_heuristic,
        "subcat": raw_category,
        "notes": f"structured_label_entity={structured_entity}" if structured_entity else "",
        # STEP: relational extraction (ingest/relational.py) - which database
        # table/row(s) this claim was built from, so a joined claim never
        # loses its way back to the records it came from. None for a plain
        # CSV/upload claim, which has nothing to trace beyond the file itself.
        "provenance_record": provenance_record,
    }


def build_claims(rows: list[dict], mapping: dict, source_id: str, default_heuristic: str = "unknown",
                 blockchain: str | None = None, row_chains: list | None = None,
                 row_labels: list | None = None) -> list[dict]:
    """One claim per row, or one per label token for a row whose label cell was split
    (`row_labels[i]` lists that row's tokens). `row_chains[i]` is the row's own chain when the
    file states it per row; `blockchain` is the file's single chain otherwise."""
    out = []
    for i, r in enumerate(rows):
        chain = row_chains[i] if row_chains else blockchain
        for tok in (row_labels[i] if row_labels and row_labels[i] else [None]):
            out.append(build_claim(r, mapping, source_id, default_heuristic, record_id=i, blockchain=chain,
                                   label_token=tok))
    return out
