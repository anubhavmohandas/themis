"""Loop 2 STEP 1/26 - the analysis workspace. One uploaded dataset, or one
paper-reproduction run, gets its own id and its own stored result; nothing
downstream reads a shared global corpus implicitly (that silent fallback to
Corpus.demo() was the bug this loop exists to fix - see STEP 19/21).
"""
from __future__ import annotations
import dataclasses, datetime, uuid

MODE_UPLOADED = "UPLOADED_DATASET"
MODE_PAPER = "PAPER_REPRODUCTION"


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass
class AnalysisWorkspace:
    analysis_id: str
    mode: str
    dataset_name: str
    created_at: str
    analysis_as_of_date: str
    reference_corpus: object = None          # the Corpus this workspace compares against, if any
    input_file_hash: str | None = None
    blockchain: str | None = None
    schema_mapping: dict | None = None
    claims: list = dataclasses.field(default_factory=list)
    reference_corpus_version: str | None = None
    corpus_scope: str | None = None          # FULL_CORPUS | BUNDLED_SAMPLE, for a paper reproduction
    warnings: list = dataclasses.field(default_factory=list)
    result: dict | None = None               # the canonical AnalysisResult (STEP 24)
    audit_trail: dict | None = None

    def to_meta(self) -> dict:
        """The small, list-friendly summary - never the full claim list."""
        return dict(analysis_id=self.analysis_id, mode=self.mode, dataset_name=self.dataset_name,
                    created_at=self.created_at, analysis_as_of_date=self.analysis_as_of_date,
                    blockchain=self.blockchain, n_claims=len(self.claims), warnings=self.warnings,
                    corpus_scope=self.corpus_scope)


class WorkspaceStore:
    """occam: in-memory dict, one process - the same lifetime/scope as the
    single global `_state` dict this replaces in api.py. Swap for a
    persistent store if THEMIS ever needs multi-worker or durable analysis
    history across restarts."""

    def __init__(self):
        self._by_id: dict[str, AnalysisWorkspace] = {}

    def put(self, ws: AnalysisWorkspace) -> AnalysisWorkspace:
        self._by_id[ws.analysis_id] = ws
        return ws

    def get(self, analysis_id: str) -> AnalysisWorkspace | None:
        return self._by_id.get(analysis_id)

    def list(self) -> list:
        return [ws.to_meta() for ws in
               sorted(self._by_id.values(), key=lambda w: w.created_at, reverse=True)]
