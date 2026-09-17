"""STEP 2 - schema mapping. Infers which column plays which semantic role
and shows its interpretation; the caller (CLI/UI) can override any field
before ingestion proceeds - nothing here is final until confirmed.
"""
from __future__ import annotations
import datetime, re
from . import detect as _detect

LABEL_HINTS = ("label", "entity", "actor", "tag", "name")
CATEGORY_HINTS = ("category", "classification", "type")
SOURCE_HINTS = ("source", "origin", "reference", "provenance", "citation")
DATE_HINTS = ("date", "time", "updated", "revision", "lastmod", "retrieved", "seen")
CONFIDENCE_HINTS = ("confidence", "certainty", "trust", "reliability", "score")
_URL_RE = re.compile(r"^https?://", re.I)


def _looks_like_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value.strip()[:10])
        return True
    except ValueError:
        return False


def _looks_like_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


def _best_field(rows, candidates, hints, value_check=None, sample_size=200):
    scored = []
    for f in candidates:
        score = 1.0 if any(h in f.lower() for h in hints) else 0.0
        if value_check:
            sample = _detect.sample_values(rows, f, sample_size)
            if sample and sum(1 for v in sample if value_check(v)) / len(sample) > 0.5:
                score += 0.5
        if score > 0:
            scored.append((score, f))
    scored.sort(key=lambda sf: (-sf[0], sf[1]))
    return scored[0][1] if scored else None


def infer_mapping(rows: list[dict], fieldnames: list[str], sample_size: int = 200) -> dict:
    detection = _detect.detect(rows, fieldnames, sample_size)
    address_field = detection.get("address_field")
    remaining = [f for f in fieldnames if f != address_field]

    label_field = _best_field(rows, remaining, LABEL_HINTS, sample_size=sample_size)
    remaining_2 = [f for f in remaining if f != label_field]
    category_field = _best_field(rows, remaining_2, CATEGORY_HINTS, sample_size=sample_size)
    source_field = _best_field(rows, remaining_2, SOURCE_HINTS, value_check=_looks_like_url,
                               sample_size=sample_size)
    timestamp_field = _best_field(rows, remaining_2, DATE_HINTS, value_check=_looks_like_date,
                                  sample_size=sample_size)
    confidence_field = _best_field(rows, remaining_2, CONFIDENCE_HINTS, sample_size=sample_size)

    return dict(
        detection=detection,
        mapping=dict(address=address_field, label=label_field, category=category_field,
                    source=source_field, timestamp=timestamp_field, confidence=confidence_field),
    )
