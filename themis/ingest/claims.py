"""STEP 3 - the canonical claim model. Raw label text is preserved
unchanged; only `canon`/`polarity` are derived, and only through the
taxonomy's declared aliases (config/taxonomy.yml) - never guessed.
"""
from __future__ import annotations
from .. import taxonomy

#: the flat claim schema every analysis function in this package reads.
CLAIM_FIELDS = ["address", "source", "raw_label", "canon", "polarity",
                "prov_family", "lastmod", "heuristic", "subcat"]


def normalize_date(value: str) -> str:
    v = (value or "").strip()
    return v[:10] if v else ""


def build_claim(row: dict, mapping: dict, source_id: str, default_heuristic: str = "undisclosed") -> dict:
    """One row, one claim. `source_id` should not collide with a bundled
    source id in config/sources/ unless this really is that source - an
    unrecognized id gets no provenance rule and resolves UNRESOLVED, which
    is the correct default for a dataset THEMIS has never seen before."""
    raw_label = (row.get(mapping.get("label")) or "").strip() if mapping.get("label") else ""
    canon = taxonomy.canonicalize_category(raw_label) or "unknown"
    return {
        "address": (row.get(mapping.get("address")) or "").strip(),
        "source": source_id,
        "raw_label": raw_label,
        "canon": canon,
        "polarity": taxonomy.POLARITY.get(canon, "unknown"),
        "prov_family": (row.get(mapping.get("source")) or "").strip() if mapping.get("source") else "",
        "lastmod": normalize_date(row.get(mapping.get("timestamp"), "")) if mapping.get("timestamp") else "",
        "heuristic": default_heuristic,
        "subcat": (row.get(mapping.get("category")) or "").strip() if mapping.get("category") else "",
    }


def build_claims(rows: list[dict], mapping: dict, source_id: str, default_heuristic: str = "undisclosed") -> list[dict]:
    return [build_claim(r, mapping, source_id, default_heuristic) for r in rows]
