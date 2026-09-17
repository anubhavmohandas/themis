"""Thin JSON API for the THEMIS dashboard (themis[ui] extra).

Every route is a direct pass-through to the existing engine
(report/reliability/analysis/graph/ingest/target_audit) - no analysis logic
lives here, only request parsing and response serialization, per the
mission's "UI must never contain analytical business logic" rule.

Loop 2 STEP 1/2/19: every page-facing route is scoped by an analysis_id.
There is no implicit global corpus - Corpus.demo() is only ever loaded when
a request explicitly asks for it (a reference comparison, or a "reproduce
paper" workspace), never as a silent fallback for an uploaded dataset's
pages.
"""
from __future__ import annotations
import csv, datetime, hashlib, io, json, os, tempfile

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
except ImportError as e:   # pragma: no cover
    raise SystemExit("themis.api requires the 'ui' extra: pip install -e '.[ui]'") from e

from .corpus import Corpus
from . import analysis, config_io, provenance, report as _report, graph as _graph, taxonomy
from . import workspace as _workspace
from .ingest import pipeline as _ingest_pipeline, schema as _ingest_schema

app = FastAPI(title="THEMIS API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # a local research tool; tighten if this ever leaves localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = _workspace.WorkspaceStore()
_reference_cache: dict = {}


def _reference_corpus() -> Corpus:
    """The bundled reference corpus, loaded once and cached - only ever
    touched when a request explicitly opts into comparing against it."""
    if "corpus" not in _reference_cache:
        _reference_cache["corpus"] = Corpus.demo()
    return _reference_cache["corpus"]


def _get_workspace(analysis_id: str) -> _workspace.AnalysisWorkspace:
    ws = _store.get(analysis_id)
    if ws is None:
        raise HTTPException(404, f"no analysis with id {analysis_id!r}")
    return ws


def _csv_response(rows: list[list], header: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def sources():
    return config_io.load().sources


# ------------------------------------------------------------- STEP 2 preflight
@app.post("/api/preflight")
async def preflight(file: UploadFile = File(...), sample_rows: int = Form(5)):
    """Inspect an upload before any workspace exists: crypto/non-crypto
    detection, inferred schema mapping, and a few sample rows for the
    mapping-confirmation UI (STEP 10). Creates nothing."""
    data = await file.read()
    suffix = ".csv.gz" if (file.filename or "").endswith(".gz") else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        rows, fieldnames = _ingest_pipeline.load_csv(tmp_path)
    finally:
        os.remove(tmp_path)

    inferred = _ingest_schema.infer_mapping(rows, fieldnames)
    return dict(filename=file.filename, fieldnames=fieldnames, n_rows=len(rows),
               detection=inferred["detection"], mapping=inferred["mapping"],
               sample_rows=rows[:sample_rows])


# ------------------------------------------------------------ STEP 1/2 analysis
@app.post("/api/analysis")
async def create_analysis(file: UploadFile = File(...), source_id: str = Form("uploaded_dataset"),
                          use_reference: bool = Form(True), mapping: str | None = Form(None)):
    """Confirm the schema mapping and run the audit (STEP 10 step 4): creates
    a new UPLOADED_DATASET workspace and returns its analysis_id. Every
    other page-facing route reads through that id, never through a global
    default corpus."""
    mapping_override = json.loads(mapping) if mapping else None
    data = await file.read()
    suffix = ".csv.gz" if (file.filename or "").endswith(".gz") else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        reference = _reference_corpus() if use_reference else None
        today = datetime.date.today()
        result = _ingest_pipeline.ingest(tmp_path, source_id, mapping_override=mapping_override,
                                         reference=reference, analysis_as_of_date=today)
    finally:
        os.remove(tmp_path)

    ws = _workspace.AnalysisWorkspace(
        analysis_id=_workspace.new_id(), mode=_workspace.MODE_UPLOADED,
        dataset_name=file.filename or source_id, created_at=_workspace.now_iso(),
        analysis_as_of_date=str(today), reference_corpus=reference,
        input_file_hash=_hash_bytes(data), blockchain=result["detection"].get("blockchain"),
        schema_mapping=result["schema_mapping"], claims=result.get("claims", []),
        reference_corpus_version=("bundled_sample" if reference is not None else None),
        warnings=result.get("limitations", []), result=result,
        audit_trail=_report.audit_trail(parameters=dict(source_id=source_id, use_reference=use_reference),
                                        warnings=result.get("limitations", [])),
    )
    _store.put(ws)
    if not result["stopped"]:
        result = dict(result)
        result["claims"] = result["claims"][:500]   # cap the payload; counts are in `validation`
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta(), preflight=result)


@app.post("/api/analysis/paper")
def create_paper_reproduction():
    """STEP 20 - a deliberate, separate mode: reproduce the bundled
    seven-source research corpus. Never entered implicitly."""
    corpus = _reference_corpus()
    result = _report.build_corpus_report(corpus)
    ws = _workspace.AnalysisWorkspace(
        analysis_id=_workspace.new_id(), mode=_workspace.MODE_PAPER,
        dataset_name="Seven-source ICISHCT research corpus", created_at=_workspace.now_iso(),
        analysis_as_of_date=result["analysis_as_of_date"], reference_corpus=corpus,
        claims=corpus.claims, reference_corpus_version="bundled_sample",
        result=result, audit_trail=result["audit_trail"],
    )
    _store.put(ws)
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta())


@app.get("/api/analysis")
def list_analyses():
    return _store.list()


@app.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: str):
    return _get_workspace(analysis_id).to_meta()


@app.get("/api/analysis/{analysis_id}/summary")
def analysis_summary(analysis_id: str):
    ws = _get_workspace(analysis_id)
    return dict(meta=ws.to_meta(), result=ws.result, audit_trail=ws.audit_trail)


@app.get("/api/analysis/{analysis_id}/address/{address:path}")
def analysis_address(analysis_id: str, address: str):
    ws = _get_workspace(analysis_id)
    if ws.mode == _workspace.MODE_PAPER:
        return analysis.explain(ws.reference_corpus, address)
    return _explain_in_workspace(ws, address)


@app.get("/api/analysis/{analysis_id}/provenance")
def analysis_provenance(analysis_id: str):
    ws = _get_workspace(analysis_id)
    graph = _graph.lineage_graph()
    inheritance = ws.result.get("target_audit", {}).get("inheritance_candidates", []) \
        if ws.mode == _workspace.MODE_UPLOADED and ws.result else []
    return dict(graph=graph, inheritance_candidates=inheritance)


@app.get("/api/analysis/{analysis_id}/drift")
def analysis_drift(analysis_id: str):
    ws = _get_workspace(analysis_id)
    if ws.mode != _workspace.MODE_PAPER:
        raise HTTPException(409, "Trust-rule sensitivity is reproduced against the bundled "
                                 "ransomware-revenue task and is only available for a "
                                 "PAPER_REPRODUCTION analysis.")
    return analysis.drift(ws.reference_corpus)


@app.get("/api/analysis/{analysis_id}/export/{name}")
def analysis_export(analysis_id: str, name: str):
    ws = _get_workspace(analysis_id)
    if name == "analysis_summary.json":
        payload = json.dumps(dict(meta=ws.to_meta(), result=ws.result, audit_trail=ws.audit_trail),
                             indent=1, default=str)
        return StreamingResponse(iter([payload]), media_type="application/json",
                                 headers={"Content-Disposition": 'attachment; filename="analysis_summary.json"'})
    if name == "normalized_claims.csv":
        fields = ["claim_id", "address", "source", "raw_label", "canon", "polarity", "root",
                  "heuristic", "confidence_raw", "lastmod"]
        rows = [[c.get(f, "") for f in fields] for c in ws.claims]
        return _csv_response(rows, fields, name)
    if name == "limitations.json":
        lims = (ws.result or {}).get("limitations") or (ws.result or {}).get("target_audit", {}).get(
            "limitations", [])
        payload = json.dumps(dict(mode=ws.mode, limitations=lims), indent=1)
        return StreamingResponse(iter([payload]), media_type="application/json",
                                 headers={"Content-Disposition": 'attachment; filename="limitations.json"'})
    raise HTTPException(404, f"unknown export {name!r}")


def _explain_in_workspace(ws: _workspace.AnalysisWorkspace, address: str) -> dict:
    """STEP 21 - address inspector scoped to one uploaded-dataset workspace:
    the target's own claim(s) plus only the reference claims that land on
    this same address, never the reference corpus's unrelated agreement."""
    target_claims = [c for c in ws.claims if c["address"] == address]
    ref_claims = ws.reference_corpus.by_addr.get(address, []) if ws.reference_corpus else []
    if not target_claims and not ref_claims:
        return dict(address=address, found=False)

    combined = target_claims + ref_claims
    indep = provenance.address_independence(combined)
    srcs = sorted({c["source"] for c in combined})
    outcome = taxonomy.classify_address(combined) if len(srcs) >= 2 else "single-source"

    def _claim_view(c):
        return dict(source=c["source"], label=c["canon"], raw=c["raw_label"],
                   root=c.get("root", provenance.root_of(c)),
                   root_kind=c.get("prov_kind", "UNKNOWN"), tier=taxonomy.tier_of(c),
                   lastmod=c.get("lastmod") or None, flags=taxonomy.currency_flags(c))

    return dict(
        address=address, found=True,
        target_claims=[_claim_view(c) for c in target_claims],
        reference_claims=[_claim_view(c) for c in ref_claims],
        datasets=srcs, outcome=outcome,
        apparent_corroboration=indep["apparent_dataset_count"],
        actual_corroboration=indep["confirmed_independent_root_count"],
        circular=indep["circular"], independence=indep,
        comparability=(ws.result.get("target_audit", {}).get("address_comparability", {}).get(address)
                      if ws.result else None),
    )


def main():
    import uvicorn
    port = int(os.environ.get("THEMIS_API_PORT", "5001"))
    uvicorn.run("themis.api:app", host="127.0.0.1", port=port,
               reload=os.environ.get("THEMIS_DEBUG") == "1")


if __name__ == "__main__":
    main()
