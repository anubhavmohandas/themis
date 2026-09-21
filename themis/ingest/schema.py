"""STEP 2 - schema mapping. The inference itself lives in preflight.py (column
meaning is decided from a column's name AND its values, against the vocabulary
in config/preflight.yml); this keeps the small `infer_mapping` entry point the
CLI, the API and the tests use: which column plays which claim role, plus the
detection block. Nothing here is final until confirmed by the caller.
"""
from __future__ import annotations
from . import preflight as _preflight


def infer_mapping(rows: list[dict], fieldnames: list[str], sample_size: int | None = None) -> dict:
    pf = _preflight.run(rows, fieldnames, sample_size=sample_size)
    return dict(detection=pf["detection"], mapping=pf["mapping"], columns=pf["columns"])
