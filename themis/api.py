"""Thin JSON API for the THEMIS dashboard (themis[ui] extra).

Every route is a direct pass-through to the existing engine
(report/reliability/analysis/graph/ingest) - no analysis logic lives here,
only request parsing and response serialization, per the mission's "UI must
never contain analytical business logic" rule. The frontend is a separate
React + Vite app; this just serves the canonical result objects it renders.
"""
from __future__ import annotations
import csv, io, json, os, tempfile

try:
    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
except ImportError as e:   # pragma: no cover
    raise SystemExit("themis.api requires the 'ui' extra: pip install -e '.[ui]'") from e

from .corpus import Corpus
from . import analysis, config_io, report as _report, graph as _graph
from .ingest import pipeline as _ingest_pipeline

app = FastAPI(title="THEMIS API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # a local research tool; tighten if this ever leaves localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

_state: dict = {}


def _corpus() -> Corpus:
    if "corpus" not in _state:
        _state["corpus"] = Corpus.demo()
    return _state["corpus"]


def _csv_response(rows: list[list], header: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def sources():
    return config_io.load().sources


@app.get("/api/graph")
def lineage_graph():
    return _graph.lineage_graph()


@app.get("/api/report")
def report(bootstrap: bool = False):
    return _report.build_corpus_report(_corpus(), include_bootstrap=bootstrap)


@app.get("/api/drift")
def drift():
    return analysis.drift(_corpus())


@app.get("/api/address/{address:path}")
def address(address: str):
    return analysis.explain(_corpus(), address)


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...), source_id: str = Form("uploaded"),
                 use_reference: bool = Form(True), mapping: str | None = Form(None)):
    mapping_override = json.loads(mapping) if mapping else None
    suffix = ".csv.gz" if (file.filename or "").endswith(".gz") else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await file.read())
        result = _ingest_pipeline.ingest(tmp_path, source_id, mapping_override=mapping_override,
                                         reference=_corpus() if use_reference else None)
    finally:
        os.remove(tmp_path)

    if not result["stopped"]:
        result = dict(result)
        result["claims"] = result["claims"][:500]   # cap the payload; counts are in `validation`
    return result


@app.get("/api/export/report.json")
def export_report_json():
    payload = json.dumps(_report.build_corpus_report(_corpus()), indent=1, default=str)
    return StreamingResponse(iter([payload]), media_type="application/json",
                             headers={"Content-Disposition": 'attachment; filename="themis_report.json"'})


@app.get("/api/export/sources.csv")
def export_sources_csv():
    rows = [[sid, cfg.get("display_name", ""), cfg.get("chain", ""),
            (cfg.get("provenance") or {}).get("mode", ""), cfg.get("citation", "")]
           for sid, cfg in sorted(config_io.load().sources.items())]
    return _csv_response(rows, ["source_id", "display_name", "chain", "provenance_mode", "citation"],
                         "themis_sources.csv")


@app.get("/api/export/agreement.csv")
def export_agreement_csv():
    a = analysis.agreement(_corpus())
    rows = [[k, v["n"], v["share"]] for k, v in a["outcomes"].items()]
    return _csv_response(rows, ["outcome", "n", "share"], "themis_agreement.csv")


def main():
    import uvicorn
    port = int(os.environ.get("THEMIS_API_PORT", "5001"))
    uvicorn.run("themis.api:app", host="127.0.0.1", port=port,
               reload=os.environ.get("THEMIS_DEBUG") == "1")


if __name__ == "__main__":
    main()
