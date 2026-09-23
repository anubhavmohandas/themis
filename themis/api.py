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
import collections, csv, datetime, gzip, hashlib, io, json, logging, os, pathlib, sqlite3, tempfile, threading, time, zlib

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
except ImportError as e:   # pragma: no cover
    raise SystemExit("themis.api requires the 'ui' extra: pip install -e '.[ui]'") from e

from .corpus import Corpus
from . import chains as chains_mod
from . import analysis, config_io, overview as _overview, provenance, report as _report, graph as _graph, taxonomy, views
from . import __version__
from .errors import InputError
from .paper import reproduce as _paper_repro, verify as _paper_verify
from . import workspace as _workspace
from .ingest import (gating as _gating, pipeline as _ingest_pipeline, preflight as _preflight,
                    relational as _relational, sqlite_source as _sqlite)

log = logging.getLogger("themis.api")

#: What a client sees when an internal failure is not one it can act on. The real
#: exception goes to the server log (`log.exception`), never into a response.
GENERIC_ERROR = "Analysis task failed."

# Read once: the middleware below is fixed when the app is built. Threat model in config/api.yml.
_api_cfg = config_io.load().api
_ALLOWED_ORIGINS = frozenset(_api_cfg["cors"]["allowed_origins"])
_ALLOWED_HOSTS = list(_api_cfg["hosts"]["allowed"])
_MAX_UPLOAD = _api_cfg["upload"]["max_bytes"]
_MAX_BODY = _MAX_UPLOAD + _api_cfg["upload"]["multipart_overhead_bytes"]
_PAGING = _api_cfg["paging"]


class _RequestGuard:
    """Refuses, before a route runs, (1) a state-changing request from a browser
    origin outside the allowlist - CORS alone only hides the response, the
    upload would still be processed - and (2) any request body larger than the
    upload limit plus multipart framing. The size is counted as the body is read
    off the wire, so a missing or dishonest Content-Length cannot get past it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope["headers"]}
        origin = headers.get(b"origin")
        if (origin is not None and scope["method"] not in ("GET", "HEAD", "OPTIONS")
                and origin.decode("latin-1") not in _ALLOWED_ORIGINS):
            return await JSONResponse(dict(detail="Cross-origin request refused."), 403)(scope, receive, send)
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > _MAX_BODY:
            return await JSONResponse(dict(detail=_too_large()), 413)(scope, receive, send)
        received = 0

        async def counted_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > _MAX_BODY:
                    raise HTTPException(413, _too_large())
            return msg
        await self.app(scope, counted_receive, send)


def _too_large() -> str:
    return f"The upload is larger than the {_MAX_UPLOAD:,}-byte limit."


app = FastAPI(title="THEMIS API")
app.add_middleware(_RequestGuard)
app.add_middleware(      # added last = outermost, so a refusal from the guard still carries CORS for an allowed origin
    CORSMiddleware,
    allow_origins=sorted(_ALLOWED_ORIGINS),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS, www_redirect=False)   # outermost: DNS rebinding


@app.exception_handler(Exception)
async def _unexpected_error(request, exc):
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(dict(detail=GENERIC_ERROR), 500)

_store = _workspace.WorkspaceStore()
_reference_cache: dict = {}


def _reference_corpus() -> Corpus:
    """The reference corpus, loaded once and cached - only ever touched when a
    request explicitly opts into comparing against it. Raises
    FileNotFoundError when it is not present (a release does not ship it)."""
    if "corpus" not in _reference_cache:
        _reference_cache["corpus"] = Corpus.reference()
    return _reference_cache["corpus"]


#: corpus._MISSING names the server-side directory; a client gets the instruction without the path
_REFERENCE_MISSING = ("No reference corpus is available in this installation: it is not redistributed "
                      "(see THIRD_PARTY_DATA.md). Build it with scripts/build_corpus.py and set THEMIS_DATA_DIR.")


def _reference_or_none():
    try:
        return _reference_corpus(), None
    except FileNotFoundError as e:
        log.info("reference corpus unavailable: %s", e)
        return None, _REFERENCE_MISSING


def _get_workspace(analysis_id: str) -> _workspace.AnalysisWorkspace:
    ws = _store.get(analysis_id)
    if ws is None:
        raise HTTPException(404, f"no analysis with id {analysis_id!r}")
    return ws


def _require_analyzable(ws: _workspace.AnalysisWorkspace) -> None:
    """An uploaded dataset that failed pre-flight has no claims and no analysis:
    every analysis route refuses it with the reason, rather than answering with
    empty tables and zeroes. Its summary and preflight.json stay readable."""
    if ws.mode == _workspace.MODE_UPLOADED and (ws.result or {}).get("stopped"):
        why = ((ws.preflight or {}).get("blockers") or [{}])[0].get("message") or "it failed pre-flight"
        raise HTTPException(409, f"{_gating.UNSUPPORTED_SCHEMA}: this dataset cannot be analysed: {why}")


# CSV-injection guard (OWASP): a cell whose raw text starts with one of these
# opens as a formula/DDE call in Excel/Sheets. Export renders raw, attacker-
# controlled upload content (raw_label, ...) verbatim by design (STEP 23
# preserves raw evidence), so the leading character is neutralized here, at
# the one shared writer, rather than in every caller.
_FORMULA_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe_cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_FORMULA_LEAD_CHARS) else s


def _csv_response(rows: list[list], header: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows([[_csv_safe_cell(cell) for cell in row] for row in rows])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/sources")
def sources():
    return config_io.load().sources


@app.get("/api/taxonomy")
def taxonomy_categories():
    """Canonical categories (config/taxonomy.yml) for filter dropdowns."""
    return {cat: dict(polarity=node.get("polarity", "unknown"), parent=node.get("parent"))
            for cat, node in sorted(taxonomy.CATEGORIES.items())}


# ------------------------------------------------------------- STEP 2 preflight
#: a file that is not the CSV / gzip it claims to be: the client's problem, not a server error
_UNREADABLE_UPLOAD = (gzip.BadGzipFile, EOFError, zlib.error, csv.Error)


def _bad_request(fn):
    """A request naming a column the file lacks, an unknown chain or an unknown
    semantic field is a 400, not a server error. Only `InputError` text (written
    for the caller) is passed through; any other exception is an internal failure
    and reaches the generic handler, with the detail in the server log only."""
    try:
        return fn()
    except InputError as e:
        raise HTTPException(400, str(e)) from e
    except sqlite3.DatabaseError as e:
        log.warning("unreadable SQLite database: %s", e)
        raise HTTPException(422, "this is not a readable SQLite database: it may be corrupt, or still "
                                 "downloading") from e
    except _UNREADABLE_UPLOAD as e:
        log.warning("unreadable upload: %s: %s", type(e).__name__, e)
        raise HTTPException(400, "the file could not be read as CSV (or gzip-compressed CSV)") from e


def _parse_json_object(text: str | None, what: str) -> dict | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"invalid {what} JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(400, f"{what} must be a JSON object")
    return parsed


async def _read_upload(file: UploadFile) -> bytes:
    """The uploaded file's bytes, refusing more than `upload.max_bytes` (an exact
    per-file check; `_RequestGuard` bounds the wire). A .gz is also refused when it
    would DECOMPRESS past the limit, so a small archive cannot expand into an
    unbounded in-memory table."""
    data = await file.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, _too_large())
    if (file.filename or "").endswith(".gz"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as g:
                n = 0
                while chunk := g.read(1 << 20):
                    n += len(chunk)
                    if n > _MAX_UPLOAD:
                        raise HTTPException(413, "The file decompresses to more than the "
                                                 f"{_MAX_UPLOAD:,}-byte upload limit.")
        except _UNREADABLE_UPLOAD + (OSError,):
            pass   # not a valid gzip: the parse step reports that, as a 400
    return data


@app.post("/api/preflight")
async def preflight(file: UploadFile = File(...), sample_rows: int = Form(5), mapping: str | None = Form(None),
                    semantics: str | None = Form(None), chain: str | None = Form(None),
                    confirmed: bool = Form(False)):
    """Inspect an upload before any workspace exists: what each column means (a
    semantic field with a confidence and a validation status), the chain and how
    it was determined, what is missing, and whether analysis may run. The same
    `mapping` / `semantics` / `chain` / `confirmed` the analysis endpoints take
    can be sent here, so the mapping screen shows exactly what would be enforced.
    Creates nothing."""
    name = file.filename or ""
    if _sqlite.is_sqlite_path(name):
        raise HTTPException(400, "SQLite databases are not uploaded through this endpoint (they are too large to "
                                 "hold in memory): place the file under THEMIS_DB_DIR and use /api/sqlite/*.")
    data = await _read_upload(file)
    suffix = ".csv.gz" if name.endswith(".gz") else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        rows, fieldnames = _bad_request(lambda: _ingest_pipeline.load_csv(tmp_path))
    finally:
        os.remove(tmp_path)

    def run():
        overrides = _preflight.overrides_from_roles(_parse_json_object(mapping, "mapping"), fieldnames)
        overrides.update(_parse_json_object(semantics, "semantics") or {})
        return _preflight.run(rows, fieldnames, filename=name, sha256=_hash_bytes(data), input_type=(
            "csv.gz" if suffix.endswith(".gz") else "csv"), overrides=overrides, chain=chain or None,
            confirmed=confirmed)
    pf = _bad_request(run)
    return dict(filename=name, fieldnames=fieldnames, n_rows=len(rows), preflight=pf,
                detection=pf["detection"], mapping=pf["mapping"], sample_rows=rows[:sample_rows],
                semantic_fields=_semantic_field_options(),
                chains=sorted(chains_mod.all_adapters()))


def _semantic_field_options() -> list[dict]:
    """The vocabulary the mapping screen offers, straight from config/preflight.yml."""
    return [dict(id=k, label=v["label"]) for k, v in _preflight.cfg()["semantic_fields"].items()]


# ----------------------------------------------------------------- SQLite inputs
def _db_path(rel: str) -> str:
    """A database is opened by path RELATIVE to THEMIS_DB_DIR, never by an
    arbitrary path: this API answers CORS-open requests, so it must not become a
    way to probe the rest of the filesystem. Unset directory = SQLite disabled."""
    root = os.environ.get("THEMIS_DB_DIR")
    if not root:
        raise HTTPException(409, "SQLite inputs are disabled: set THEMIS_DB_DIR to the directory holding the "
                                 "database file(s), then pass the file name relative to it.")
    base = pathlib.Path(root).resolve()
    try:
        p = (base / rel).resolve()
    except (ValueError, OSError):      # an embedded NUL or an unresolvable name: not a path at all
        p = base
    if base not in p.parents or not _sqlite.is_sqlite_path(str(p)):
        raise HTTPException(400, f"{rel!r} is not a .db / .sqlite / .sqlite3 file inside THEMIS_DB_DIR")
    if not p.is_file():
        raise HTTPException(404, f"no such database: {rel}")
    return str(p)


@app.get("/api/sqlite/tables")
def sqlite_tables(db: str, count: bool = True):
    """Tables (and views) of a database, with exact row counts where they finish
    within the time limit. Read-only; the database is never loaded."""
    path = _db_path(db)
    return _bad_request(lambda: dict(db=db, size_bytes=os.path.getsize(path),
                                     tables=_sqlite.list_tables(path, count=count)))


@app.get("/api/sqlite/columns")
def sqlite_columns(db: str, table: str):
    return _bad_request(lambda: dict(db=db, table=table, columns=_sqlite.columns(_db_path(db), table)))


@app.post("/api/sqlite/preflight")
def sqlite_preflight(db: str = Form(...), table: str = Form(...), semantics: str | None = Form(None),
                     chain: str | None = Form(None), confirmed: bool = Form(False)):
    """Pre-flight one table on a spread-out sample."""
    path = _db_path(db)

    def run():
        sample, names = _sqlite.sample_rows(path, table, _preflight.cfg()["sample_size"])
        with _sqlite.open_readonly(path) as con:
            total = _sqlite.count_rows(con, table, _sqlite.cfg()["count_timeout_seconds"])
        overrides = _preflight.overrides_from_roles(None, names)
        overrides.update(_parse_json_object(semantics, "semantics") or {})
        pf = _preflight.run(sample, names, filename=db, sha256=None, input_type="sqlite", table=table,
                            total_rows=total, overrides=overrides, chain=chain or None, confirmed=confirmed)
        return dict(db=db, table=table, preflight=pf, sample_rows=sample[:5], fieldnames=names,
                    semantic_fields=_semantic_field_options(), chains=sorted(chains_mod.all_adapters()))
    return _bad_request(run)


# ------------------------------------------------------ relational SQLite ingestion
@app.get("/api/sqlite/inspect")
def sqlite_inspect(db: str, count: bool = True):
    """Database Inspection stage (spec Sections 1-2): file, schema, sample
    rows for every table/view - never more than a bounded sample of any one."""
    path = _db_path(db)
    return _bad_request(lambda: dict(db=db, **_sqlite.inspect(path, count=count)))


@app.get("/api/sqlite/integrity")
def sqlite_integrity(db: str, quick: bool = True):
    """A full-file check (time-limited); separate from `/inspect` so a caller
    can skip it for a database already known-good."""
    path = _db_path(db)
    return _bad_request(lambda: dict(db=db, **_sqlite.integrity_check(path, quick=quick)))


@app.get("/api/sqlite/candidates")
def sqlite_candidates(db: str):
    """Table Selection stage (Section 3): which tables look like a claim
    subject, an attribution table, or a lookup/provenance table, and why -
    the user still confirms before anything is joined or analysed."""
    path = _db_path(db)
    return _bad_request(lambda: dict(db=db, candidates=_relational.candidate_roles(path)))


@app.get("/api/sqlite/relationships")
def sqlite_relationships(db: str):
    """Declared foreign keys plus undeclared-but-inferred relationships
    (Section 3/4), for the table-selection screen to propose a JoinSpec from."""
    path = _db_path(db)
    return _bad_request(lambda: dict(db=db, relationships=_relational.infer_relationships(path)))


def _parse_join_spec(spec_json: str) -> dict:
    spec = _parse_json_object(spec_json, "spec")
    if not spec or "driving_table" not in spec:
        raise HTTPException(400, "spec must be a JSON object with at least a driving_table")
    return spec


@app.post("/api/sqlite/relational-preflight")
def sqlite_relational_preflight(db: str = Form(...), spec: str = Form(...), semantics: str | None = Form(None),
                                chain: str | None = Form(None), confirmed: bool = Form(False)):
    """Pre-flight a JoinSpec's sample: the same schema mapping / chain
    resolution / validation-status logic a single table gets, run over the
    joined columns. Nothing is streamed or persisted yet."""
    path = _db_path(db)
    join_spec = _parse_join_spec(spec)

    def run():
        check = _relational.validate_join_spec(path, join_spec)
        sample, names = _relational.joined_sample(path, join_spec, _preflight.cfg()["sample_size"])
        display = [f for f in names if not f.endswith("__rowid")]
        overrides = _preflight.overrides_from_roles(None, display)
        overrides.update({k: v for k, v in (_parse_json_object(semantics, "semantics") or {}).items()
                          if k in display})
        with _sqlite.open_readonly(path) as con:
            total = _sqlite.count_rows(con, join_spec["driving_table"], _sqlite.cfg()["count_timeout_seconds"])
        pf = _preflight.run([{k: v for k, v in r.items() if k in display} for r in sample], display,
                            filename=db, input_type="sqlite", table=join_spec["driving_table"], total_rows=total,
                            overrides=overrides, chain=chain or None, confirmed=confirmed)
        pf["relational"] = dict(join_spec=join_spec, join_warnings=check["warnings"])
        return dict(db=db, spec=join_spec, join_warnings=check["warnings"], preflight=pf,
                    sample_rows=[{k: v for k, v in r.items()} for r in sample[:5]], fieldnames=display,
                    semantic_fields=_semantic_field_options(), chains=sorted(chains_mod.all_adapters()))
    return _bad_request(run)


def _run_sqlite_extract(db: str, spec: dict, source_id: str, use_reference: bool, semantics: dict | None,
                        chain: str | None, confirmed: bool, progress=None, case_metadata: dict | None = None) -> dict:
    """Stream-extract, validate and normalize a JoinSpec into a new
    UPLOADED_DATASET workspace - the SQLite-relational equivalent of
    `_run_upload`, so every existing analysis-id route works unchanged."""
    path = _db_path(db)
    if use_reference and progress is not None:
        progress("start", "reference", None)
    reference, missing = _reference_or_none() if use_reference else (None, None)
    if use_reference and progress is not None:
        progress("complete", "reference", "reference corpus not available: comparison skipped" if missing
                 else "reference corpus loaded")
    today = datetime.date.today()
    result = _bad_request(lambda: _relational.extract(
        path, spec, source_id, semantics=semantics, chain=chain, confirmed=confirmed,
        reference=reference, analysis_as_of_date=today, progress=progress, case_metadata=case_metadata))

    if missing and not result.get("stopped"):
        result = dict(result)
        result["limitations"] = [f"No cross-source comparison was run: {missing}"] + list(result.get("limitations", []))

    if progress is not None:
        progress("start", "report", None)
    ws = _workspace.AnalysisWorkspace(
        analysis_id=_workspace.new_id(), mode=_workspace.MODE_UPLOADED,
        dataset_name=f"{pathlib.Path(db).name} ({spec['driving_table']})", created_at=_workspace.now_iso(),
        analysis_as_of_date=str(today), reference_corpus=reference,
        input_file_hash=(result.get("dataset_preflight") or {}).get("sqlite_metadata", {}).get("database_sha256"),
        blockchain=result["detection"].get("blockchain"), preflight=result["dataset_preflight"],
        schema_mapping=result.get("schema_mapping"), claims=result.get("claims", []),
        reference_corpus_version=(_scope_of(reference).lower() if reference is not None else None),
        warnings=result.get("limitations", []), result=result,
        audit_trail=_report.audit_trail(parameters=dict(source_id=source_id, use_reference=use_reference,
                                                        chain=chain, confirmed=confirmed, db=db, join_spec=spec),
                                        warnings=result.get("limitations", [])),
    )
    _store.put(ws)
    if progress is not None:
        progress("complete", "report", None)
    if not result["stopped"]:
        result = dict(result)
        result["claims"] = result["claims"][:_PAGING["extract_preview_claims"]]
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta(), preflight=result)


@app.post("/api/sqlite/extract")
def sqlite_extract(db: str = Form(...), spec: str = Form(...), source_id: str = Form("sqlite_dataset"),
                   use_reference: bool = Form(True), semantics: str | None = Form(None),
                   chain: str | None = Form(None), confirmed: bool = Form(False),
                   case_metadata: str | None = Form(None)):
    """Confirm the JoinSpec and mapping, then stream the whole driving table
    (chunked, joined, validated) into a new analysis - synchronous, for a
    table small enough that the caller does not need job/progress polling."""
    join_spec = _parse_join_spec(spec)
    sem = _parse_json_object(semantics, "semantics")
    cm = _parse_json_object(case_metadata, "case_metadata")
    return _run_sqlite_extract(db, join_spec, source_id, use_reference, sem, chain or None, confirmed,
                               case_metadata=cm)


# ------------------------------------------------------------ STEP 1/2 analysis
def _run_upload(data: bytes, filename: str | None, source_id: str, use_reference: bool,
                mapping_override: dict | None, progress=None, semantics: dict | None = None,
                chain: str | None = None, confirmed: bool = False) -> dict:
    """Ingest an upload into a new UPLOADED_DATASET workspace. Shared by the
    synchronous endpoint and the background job runner so both go through
    the exact same code path."""
    suffix = ".csv.gz" if (filename or "").endswith(".gz") else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if use_reference and progress is not None:
            progress("start", "reference", None)
        reference, missing = _reference_or_none() if use_reference else (None, None)
        if use_reference and progress is not None:
            progress("complete", "reference", "reference corpus not available: comparison skipped" if missing
                     else "reference corpus loaded")
        today = datetime.date.today()
        result = _bad_request(lambda: _ingest_pipeline.ingest(
            tmp_path, source_id, mapping_override=mapping_override, reference=reference,
            analysis_as_of_date=today, progress=progress, semantics=semantics, chain=chain,
            confirmed=confirmed, original_filename=filename))
    finally:
        os.remove(tmp_path)

    if missing and not result.get("stopped"):
        # say so where the analyst reads the results, not only in workspace metadata
        result = dict(result)
        result["limitations"] = [f"No cross-source comparison was run: {missing}"] + list(result.get("limitations", []))

    if progress is not None:
        progress("start", "report", None)
    ws = _workspace.AnalysisWorkspace(
        analysis_id=_workspace.new_id(), mode=_workspace.MODE_UPLOADED,
        dataset_name=filename or source_id, created_at=_workspace.now_iso(),
        analysis_as_of_date=str(today), reference_corpus=reference,
        input_file_hash=_hash_bytes(data), blockchain=result["detection"].get("blockchain"),
        preflight=result["dataset_preflight"],
        schema_mapping=result.get("schema_mapping"), claims=result.get("claims", []),
        reference_corpus_version=(_scope_of(reference).lower() if reference is not None else None),
        warnings=result.get("limitations", []),
        result=result,
        audit_trail=_report.audit_trail(parameters=dict(source_id=source_id, use_reference=use_reference,
                                                        chain=chain, confirmed=confirmed),
                                        warnings=result.get("limitations", [])),
    )
    _store.put(ws)
    if progress is not None:
        progress("complete", "report", None)
    if not result["stopped"]:
        result = dict(result)
        result["claims"] = result["claims"][:_PAGING["extract_preview_claims"]]   # cap the payload; counts are in `validation`
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta(), preflight=result)


def _scope_of(corpus: Corpus) -> str:
    return "FULL_CORPUS" if corpus.full else "BUNDLED_SAMPLE"


def _run_paper(progress=None) -> dict:
    if progress is not None:
        progress("start", "load")
    try:
        corpus = _reference_corpus()
    except FileNotFoundError as e:
        log.info("reference corpus unavailable: %s", e)
        raise HTTPException(409, _REFERENCE_MISSING) from e
    if progress is not None:
        progress("complete", "load", f"{len(corpus.claims):,} claims in memory")
    result = _report.build_corpus_report(corpus, progress=progress)
    ws = _workspace.AnalysisWorkspace(
        analysis_id=_workspace.new_id(), mode=_workspace.MODE_PAPER,
        dataset_name="Seven-source ICISHCT research corpus", created_at=_workspace.now_iso(),
        analysis_as_of_date=result["analysis_as_of_date"], reference_corpus=corpus,
        claims=corpus.claims, reference_corpus_version=_scope_of(corpus).lower(),
        corpus_scope=_scope_of(corpus), result=result, audit_trail=result["audit_trail"],
    )
    _store.put(ws)
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta())


def _parse_mapping(mapping: str | None) -> dict | None:
    if not mapping:
        return None
    try:
        parsed = json.loads(mapping)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"invalid mapping JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(400, "mapping must be a JSON object of role -> column name")
    return parsed


@app.post("/api/analysis")
async def create_analysis(file: UploadFile = File(...), source_id: str = Form("uploaded_dataset"),
                          use_reference: bool = Form(True), mapping: str | None = Form(None),
                          semantics: str | None = Form(None), chain: str | None = Form(None),
                          confirmed: bool = Form(False)):
    """Confirm the schema mapping and run the audit (STEP 10 step 4): creates
    a new UPLOADED_DATASET workspace and returns its analysis_id. Every
    other page-facing route reads through that id, never through a global
    default corpus."""
    mapping_override = _parse_mapping(mapping)
    data = await _read_upload(file)
    return _run_upload(data, file.filename, source_id, use_reference, mapping_override,
                       semantics=_parse_json_object(semantics, "semantics"), chain=chain or None,
                       confirmed=confirmed)


@app.post("/api/analysis/paper")
def create_paper_reproduction():
    """STEP 20 - a deliberate, separate mode: reproduce the bundled
    seven-source research corpus. Never entered implicitly."""
    return _run_paper()


# ------------------------------------------------------------ background jobs
#: The same two runs as above, executed on a worker thread so the UI can show
#: real pipeline state. A stage is only ever reported by the code that is
#: actually running it (see the `progress` hooks in ingest/pipeline.py and
#: report.py); nothing here simulates progress.
_UPLOAD_STAGES = [("reference", "Load reference corpus"), ("parse", "Parse file"),
                  ("detect", "Detect chain and schema"), ("validate", "Validate addresses"),
                  ("normalize", "Normalize claims"),
                  ("compare", "Provenance, reference comparison, independence, currency"),
                  ("report", "Assemble analysis")]
_PAPER_STAGES = [("load", "Load reference corpus"), ("agreement", "Agreement outcomes"),
                 ("independence", "Provenance and independence"), ("kappa", "Chance-corrected agreement"),
                 ("freshness", "Currency")]
_SQLITE_STAGES = [("reference", "Load reference corpus"), ("inspect", "Validate join spec"),
                  ("detect", "Detect chain and schema from a joined sample"),
                  ("validate", "Stream, validate and normalize claims"),
                  ("compare", "Provenance, reference comparison, independence, currency"),
                  ("profile", "Dataset profile, provenance states, conflicts")]
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 50


def _new_job(kind: str, stages: list) -> dict:
    job = dict(job_id=_workspace.new_id(), kind=kind, status="running", started_at=time.time(),
               finished_at=None, stages=[dict(id=i, label=l, status="pending", detail=None,
                                              started_at=None, elapsed_s=None) for i, l in stages],
               analysis_id=None, meta=None, preflight=None, error=None)
    with _jobs_lock:
        _jobs[job["job_id"]] = job
        while len(_jobs) > _MAX_JOBS:
            _jobs.pop(next(iter(_jobs)))
    return job


def _progress_for(job: dict):
    def cb(event, stage_id, detail=None):
        for st in job["stages"]:
            if st["id"] != stage_id:
                continue
            if event == "start":
                st["status"], st["started_at"] = "running", time.time()
            elif event == "progress":
                st["detail"] = detail    # a real interim count (rows scanned so far), never simulated
            elif event == "complete":
                st["status"] = "complete"
                if detail:
                    st["detail"] = detail
                if st["started_at"]:
                    st["elapsed_s"] = round(time.time() - st["started_at"], 2)
    return cb


def _finish(job: dict, fn):
    try:
        out = fn()
        job.update(out)
        if job.get("preflight", {}) and job["preflight"].get("stopped"):
            job["status"] = "stopped"
        else:
            job["status"] = "complete"
    except (HTTPException, InputError) as e:   # written for the client (see _bad_request)
        _fail(job, str(getattr(e, "detail", None) or e))
    except Exception:   # noqa: BLE001 - logged in full, reported to the client as a generic failure
        log.exception("job %s (%s) failed", job["job_id"], job["kind"])
        _fail(job, GENERIC_ERROR)
    finally:
        job["finished_at"] = time.time()


def _fail(job: dict, message: str) -> None:
    job["status"], job["error"] = "failed", message
    for st in job["stages"]:
        if st["status"] == "running":
            st["status"] = "failed"


@app.post("/api/jobs/analysis")
async def start_analysis_job(file: UploadFile = File(...), source_id: str = Form("uploaded_dataset"),
                             use_reference: bool = Form(True), mapping: str | None = Form(None),
                             semantics: str | None = Form(None), chain: str | None = Form(None),
                             confirmed: bool = Form(False)):
    mapping_override = _parse_mapping(mapping)
    sem = _parse_json_object(semantics, "semantics")
    data = await _read_upload(file)
    stages = _UPLOAD_STAGES if use_reference else [s for s in _UPLOAD_STAGES if s[0] != "reference"]
    job = _new_job("upload", stages)
    cb = _progress_for(job)
    threading.Thread(target=_finish, daemon=True, args=(
        job, lambda: _run_upload(data, file.filename, source_id, use_reference, mapping_override, cb,
                                 semantics=sem, chain=chain or None, confirmed=confirmed))).start()
    return dict(job_id=job["job_id"])


@app.post("/api/jobs/sqlite-extract")
def start_sqlite_extract_job(db: str = Form(...), spec: str = Form(...), source_id: str = Form("sqlite_dataset"),
                             use_reference: bool = Form(True), semantics: str | None = Form(None),
                             chain: str | None = Form(None), confirmed: bool = Form(False),
                             case_metadata: str | None = Form(None)):
    """Same extraction as `/api/sqlite/extract`, on a worker thread so the UI
    can show real per-stage (and, mid-validate, per-chunk) progress on a
    database too large to extract synchronously within a request."""
    join_spec = _parse_join_spec(spec)
    sem = _parse_json_object(semantics, "semantics")
    cm = _parse_json_object(case_metadata, "case_metadata")
    stages = _SQLITE_STAGES if use_reference else [s for s in _SQLITE_STAGES if s[0] != "reference"]
    job = _new_job("sqlite-extract", stages)
    cb = _progress_for(job)
    threading.Thread(target=_finish, daemon=True, args=(
        job, lambda: _run_sqlite_extract(db, join_spec, source_id, use_reference, sem, chain or None,
                                         confirmed, cb, case_metadata=cm))).start()
    return dict(job_id=job["job_id"])


@app.post("/api/jobs/paper")
def start_paper_job():
    job = _new_job("paper", _PAPER_STAGES)
    cb = _progress_for(job)
    threading.Thread(target=_finish, daemon=True, args=(job, lambda: _run_paper(cb))).start()
    return dict(job_id=job["job_id"])


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"no job with id {job_id!r}")
    now = time.time()
    return dict(job, elapsed_s=round((job["finished_at"] or now) - job["started_at"], 2))


@app.get("/api/analysis")
def list_analyses():
    return _store.list()


@app.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: str):
    return _get_workspace(analysis_id).to_meta()


def _present_result(ws) -> dict:
    """The canonical result as the pages render it: the claim list is left
    out (it has its own paged endpoint and export) and each root-concentration
    row says whether that root is resolved, using the same provenance.is_unresolved
    the engine uses. The stored result and the export are untouched."""
    result = {k: v for k, v in (ws.result or {}).items() if k != "claims"}
    ind = result.get("independence")
    if ind and ind.get("root_concentration"):
        ind = dict(ind)
        ind["root_concentration"] = [dict(r, resolved=not provenance.is_unresolved(r["root"]))
                                     for r in ind["root_concentration"]]
        result["independence"] = ind
    result["shares"] = _complement_shares(result)
    return result


def _complement_shares(result: dict) -> dict:
    """Shares the pages need that the engine reports only as one side of a
    pair (unresolved vs resolved, uploaded datasets). Computed here, from the
    engine's own counts, so the UI never does arithmetic on analytic figures.
    Every value is a share of the denominator the page shows beside it. A
    paper reproduction's shares are in result["overview"] (themis/overview.py),
    each with its own unit and population."""
    out: dict = {}
    ta = result.get("target_audit")
    if ta:
        prof = ta.get("profile") or {}
        n_targets = ta.get("n_target_addresses") or 0
        prov = prof.get("provenance") or {}
        if n_targets and prov.get("available"):
            out["resolved_addr_share"] = prov["resolved"] / n_targets
            out["unresolved_addr_share"] = prov["unresolved"] / n_targets
        indep = prof.get("independence") or {}
        n_cmp = (prof.get("agreement") or {}).get("n_comparable") or 0
        if n_cmp and indep.get("available"):
            out["confirmed_independent_share"] = indep["confirmed_independent_multi_root"] / n_cmp
            out["shared_or_inherited_share"] = indep["shared_or_inherited_only"] / n_cmp
            out["independence_unresolved_share"] = indep["independence_unresolved"] / n_cmp
    return out


@app.get("/api/analysis/{analysis_id}/summary")
def analysis_summary(analysis_id: str):
    ws = _get_workspace(analysis_id)
    return dict(meta=ws.to_meta(), result=_present_result(ws), audit_trail=ws.audit_trail)


#: Page size is capped (config/api.yml), not client-controlled, so a request can
#: never pull the whole corpus through this endpoint regardless of what `limit` asks for.
_MAX_CLAIMS_PAGE = _PAGING["claims_max_page"]


@app.get("/api/analysis/{analysis_id}/claims")
def analysis_claims(analysis_id: str, offset: int = 0, limit: int = 100,
                    source: str | None = None, canon: str | None = None,
                    evidence_tier: str | None = None, currency: str | None = None,
                    outcome: str | None = None, comparable: str | None = None,
                    provenance: str | None = None, q: str | None = None):
    """A bounded, filterable claims page. Never the full claim list (that's
    what /export/normalized_claims.csv is for) - a frontend table must page
    through this, not render the whole corpus at once.

    Per-claim filters (source, canon, evidence_tier, currency, provenance, q)
    are cheap dict lookups. Per-address filters (`outcome`, `comparable`) read
    the cached agreement index in themis.views - the same classification
    analysis.agreement() / target_audit compute, never a second one. Each
    returned row also carries the claim's own provenance status and its
    address's agreement outcome (null when the address is not comparable).
    """
    ws = _get_workspace(analysis_id)
    _require_analyzable(ws)
    as_of = _as_of_date(ws)
    claims = ws.claims
    if source:
        claims = [c for c in claims if c.get("source") == source]
    if canon:
        claims = [c for c in claims if c.get("canon") == canon]
    if evidence_tier:
        claims = [c for c in claims if taxonomy.tier_of(c) == evidence_tier]
    if currency:
        # currency_flags() returns [] for "current" (a date exists and
        # isn't stale) - "current" is this endpoint's name for that, since
        # an empty-list flag isn't itself a filterable string value.
        def _currency_status(c):
            flags = taxonomy.currency_flags(c, today=as_of)
            return flags[0] if flags else "current"
        claims = [c for c in claims if _currency_status(c) == currency]
    if outcome and outcome != "single-source" and outcome not in taxonomy.OUTCOMES:
        raise HTTPException(400, f"unknown outcome {outcome!r}")
    if comparable not in (None, "", "yes", "no"):
        raise HTTPException(400, "comparable must be 'yes' or 'no'")
    if provenance not in (None, "", "resolved", "inherited", "unresolved"):
        raise HTTPException(400, "provenance must be resolved, inherited or unresolved")
    claims = views.claims_filter(ws, claims, outcome=outcome or None, comparable=comparable or None,
                                 provenance_filter=provenance or None, q=q)
    total = len(claims)
    limit = max(1, min(limit, _MAX_CLAIMS_PAGE))
    offset = max(0, offset)
    ordered = sorted(claims, key=lambda c: (c["address"], c.get("source", "")))
    page = ordered[offset:offset + limit]
    # which population these records are: a drill-down from a metric of another population must say so
    population = ("uploaded_dataset" if ws.mode == _workspace.MODE_UPLOADED
                  else _overview.NORMALIZED if ws.reference_corpus.full else _overview.SAMPLE)
    return dict(total=total, n_addresses=len({c["address"] for c in claims}), population=population,
               offset=offset, limit=limit, n_returned=len(page),
               claims=[dict(address=c["address"], source=c["source"], raw_label=c.get("raw_label", ""),
                            canon=c.get("canon"), polarity=c.get("polarity"),
                            evidence_tier=taxonomy.tier_of(c), lastmod=c.get("lastmod", ""),
                            provenance=views.provenance_status(c),
                            root=views.resolution_of(c)["root"],
                            outcome=views.outcome_for(ws, c["address"]))
                      for c in page])


@app.get("/api/analysis/{analysis_id}/conflicts")
def analysis_conflicts(analysis_id: str, kind: str | None = None, source_a: str | None = None,
                       source_b: str | None = None, relationship: str | None = None,
                       q: str | None = None, offset: int = 0, limit: int = 50):
    """Per-address disagreement records, paged. `kind` is polarity | entity |
    hierarchical | incomparable (default: all four). A projection of the
    grouping analysis.agreement() already computes - no new classification."""
    ws = _get_workspace(analysis_id)
    _require_analyzable(ws)
    if kind not in (None, "", "all", "polarity", "entity", "hierarchical", "incomparable"):
        raise HTTPException(400, f"unknown conflict kind {kind!r}")
    if relationship not in (None, "", "distinct_roots", "shared_root", "unresolved"):
        raise HTTPException(400, f"unknown provenance relationship {relationship!r}")
    page = views.conflicts_page(ws, kind=kind or None, source_a=source_a or None,
                                source_b=source_b or None, relationship=relationship or None,
                                q=q, offset=offset, limit=limit)
    # "0 conflicts" is only a finding when labels were comparable; otherwise say so
    return dict(page, **views.state_of(ws, "conflicts"))


@app.get("/api/analysis/{analysis_id}/trust-coverage")
def analysis_trust_coverage(analysis_id: str, rules: str = ""):
    """Evidence retention under a chosen set of the existing trust predicates
    (comma-separated rule ids). Uploaded datasets only: paper mode's
    trust-rule sensitivity is /drift against the ransomware-revenue task."""
    ws = _get_workspace(analysis_id)
    _require_analyzable(ws)
    if ws.mode != _workspace.MODE_UPLOADED:
        raise HTTPException(409, "Trust-policy coverage preview is for uploaded datasets; "
                                 "a paper reproduction reports trust-rule sensitivity via /drift.")
    ids = [r for r in (x.strip() for x in rules.split(",")) if r]
    try:
        return views.trust_coverage(ws, ids)
    except KeyError as e:
        raise HTTPException(400, f"unknown trust rule {e.args[0]!r}") from e


@app.get("/api/analysis/{analysis_id}/address/{address:path}")
def analysis_address(analysis_id: str, address: str):
    ws = _get_workspace(analysis_id)
    _require_analyzable(ws)
    if ws.mode == _workspace.MODE_PAPER:
        res = analysis.explain(ws.reference_corpus, address, as_of=_as_of_date(ws))
        if res.get("found"):   # same order as the claims explain() just read
            for view, raw in zip(res["claims"], ws.reference_corpus.by_addr[address]):
                view["provenance"] = views.provenance_status(raw)
        return res
    return _explain_in_workspace(ws, address)


def _provenance_payload(ws) -> dict:
    """Two things that must never be blurred (uploaded-vs-reference separation):

    * `uploaded_dataset`: provenance of THIS file's claims, supported only by what
      the file itself declares plus the relationships measured against the
      reference corpus (each carrying its evidence). A source the registry has
      never seen has no provenance rule, so its root is UNRESOLVED, not borrowed
      from any bundled source.
    * `reference_corpus`: the bundled research sources' own lineage graph. It
      describes THEMIS's reference data, not the uploaded file.

    In a paper reproduction the reference corpus is the subject."""
    ref = ws.reference_corpus
    ref_graph = _graph.lineage_graph()
    ref_block = dict(label="THEMIS Reference Corpus", graph=ref_graph,
                     scope=_scope_of(ref) if ref is not None else None,
                     note="The seven bundled research sources and where each traces to. This is THEMIS's own "
                          "reference data, not provenance discovered for an uploaded file.")
    if ws.mode == _workspace.MODE_PAPER:
        evidence = ws.result.get("independence") if ws.result else None
        _annotate_graph(ref_graph, evidence)
        return dict(subject="reference_corpus", graph=ref_graph, evidence=evidence, inheritance_candidates=[],
                    uploaded_dataset=None, reference_corpus=ref_block)

    _annotate_graph(ref_graph, None)
    src = ws.result["source_id"]
    graph = _graph.lineage_graph({src: dict(display_name=ws.dataset_name)})
    _annotate_graph(graph, None)
    declared = collections.Counter((c.get("prov_family") or "").strip() for c in ws.claims)
    declared.pop("", None)
    roots = collections.Counter(views.resolution_of(c)["root"] for c in ws.claims)
    candidates = ws.result.get("target_audit", {}).get("inheritance_candidates", [])
    uploaded = dict(
        label="Uploaded dataset provenance", source_id=src, dataset_name=ws.dataset_name, n_claims=len(ws.claims),
        state=(ws.result.get("analysis_states") or {}).get("provenance"),
        declared_sources=[dict(value=v, n_claims=n) for v, n in declared.most_common(20)],
        n_distinct_declared_sources=len(declared),
        roots=[dict(root=r, n_claims=n, resolved=not provenance.is_unresolved(r)) for r, n in roots.most_common(20)],
        graph=graph, inheritance_candidates=candidates,
        note="Only relationships supported by this file's own declared sources, or measured between its "
             "addresses and the reference corpus, appear here.")
    return dict(subject="uploaded_dataset", uploaded_dataset=uploaded, reference_corpus=ref_block,
                graph=graph, inheritance_candidates=candidates, evidence=None)


@app.get("/api/analysis/{analysis_id}/provenance")
def analysis_provenance(analysis_id: str):
    ws = _get_workspace(analysis_id)
    _require_analyzable(ws)
    return _provenance_payload(ws)


def _annotate_graph(graph: dict, ind: dict | None) -> None:
    """Attach, to each dataset->root edge, the evidence the engine already
    measured for that specific relationship (paper mode): the field decode
    against the root's owner, naming residue naming the root, directional
    containment between the two sources, and the root's measured propagation
    into the dataset. Roots also get their native `owner` source. Nothing is
    computed here - this only looks up existing results."""
    owners = {}
    for n in graph["nodes"]:
        if n["type"] in ("root", "root_unresolved"):
            owners[n["label"]] = provenance.owner_of_root(n["label"])
            n["owner"] = owners[n["label"]]
    # Registry structure only: which datasets point at each root. A root pointed
    # at by more than one dataset is where apparent corroboration can collapse.
    pointing: dict[str, list[str]] = {}
    for e in graph["edges"]:
        if e["source"].startswith("dataset:") and e["target"].startswith("root:"):
            pointing.setdefault(e["target"], []).append(e["source"][len("dataset:"):])
    for n in graph["nodes"]:
        if n["type"] in ("root", "root_unresolved"):
            n["datasets"] = sorted(set(pointing.get(n["id"], [])))
            n["shared"] = len(n["datasets"]) > 1
    shared_ids = {n["id"] for n in graph["nodes"] if n.get("shared")}
    for e in graph["edges"]:
        if e["target"] in shared_ids and e["source"].startswith("dataset:"):
            e["shared_root"] = True
    if not ind:
        return
    for e in graph["edges"]:
        if not (e["source"].startswith("dataset:") and e["target"].startswith("root:")):
            continue
        ds, root = e["source"][len("dataset:"):], e["target"][len("root:"):]
        owner = owners.get(root)
        ev = {}
        for d in ind.get("field_decodes", []):
            if d["dataset"] == ds and owner and d["candidate"] == owner:
                ev["decode"] = d
        for r in ind.get("naming_residues", []):
            if r["dataset"] == ds and root in r.get("by_root", {}):
                ev["naming_residue"] = dict(field=r["field"], total=r["total"], attributed=r["attributed"],
                                            share=r["share"], count=r["by_root"][root], by_root=r["by_root"])
        if owner:
            cont = [c for c in ind.get("containment_top", [])
                    if (c["source"] == ds and c["inside"] == owner) or (c["source"] == owner and c["inside"] == ds)]
            if cont:
                ev["containment"] = cont
        for p in ind.get("notable_root_propagation", []):
            if p["root"] == root:
                ev["propagation"] = dict(label=p["label"], size=p["size"],
                                         into_dataset=p["propagation"].get(ds))
        if ev:
            e["evidence"] = ev


def _paper_workspace(analysis_id: str):
    ws = _get_workspace(analysis_id)
    if ws.mode != _workspace.MODE_PAPER:
        raise HTTPException(409, "Trust-rule sensitivity is reproduced against the bundled "
                                 "ransomware-revenue task and is only available for a "
                                 "PAPER_REPRODUCTION analysis.")
    return ws


@app.get("/api/analysis/{analysis_id}/drift")
def analysis_drift(analysis_id: str):
    ws = _paper_workspace(analysis_id)
    cache = ws.__dict__.setdefault("_views", {})
    if "drift" not in cache:
        cache["drift"] = analysis.drift(ws.reference_corpus)
    return cache["drift"]


#: the paper-reproduction runs a workspace can perform after it is created.
#: `audit` (agreement + independence + kappa + currency) is done at creation;
#: the others are run on demand and cached on the workspace.
_PAPER_TASKS = ("audit", "drift", "bootstrap", "anchors")


def _task_state(ws, task: str) -> str:
    if task == "audit":
        return "complete"
    cache = ws.__dict__.get("_views", {})
    if task in cache.get("task_error", {}):
        return "failed"
    if task in cache.get("task_running", set()):
        return "running"
    done = {"drift": "drift" in cache,
            "bootstrap": bool(ws.result and ws.result.get("uncertainty")),
            "anchors": bool(ws.result and ws.result.get("anchor_validation"))}
    return "complete" if done[task] else "not_run"


@app.get("/api/analysis/{analysis_id}/tasks")
def analysis_tasks(analysis_id: str):
    ws = _paper_workspace(analysis_id)
    cache = ws.__dict__.setdefault("_views", {})
    return dict(tasks={t: dict(state=_task_state(ws, t), error=cache.get("task_error", {}).get(t))
                       for t in _PAPER_TASKS},
                drift=cache.get("drift"),
                uncertainty=ws.result.get("uncertainty"),
                anchor_validation=ws.result.get("anchor_validation"))


@app.post("/api/analysis/{analysis_id}/run/{task}")
def run_paper_task(analysis_id: str, task: str):
    """Run one of the on-demand paper reproductions - the same functions the
    CLI's `themis drift|bootstrap|anchors` call, on the workspace's corpus."""
    ws = _paper_workspace(analysis_id)
    if task not in ("drift", "bootstrap", "anchors"):
        raise HTTPException(404, f"unknown task {task!r}")
    cache = ws.__dict__.setdefault("_views", {})
    running = cache.setdefault("task_running", set())
    if task in running:
        raise HTTPException(409, f"{task} is already running")
    running.add(task)
    cache.setdefault("task_error", {}).pop(task, None)
    try:
        if task == "drift":
            cache["drift"] = analysis.drift(ws.reference_corpus)
        elif task == "bootstrap":
            ws.result["uncertainty"] = analysis.bootstrap(ws.reference_corpus)
        else:
            ws.result["anchor_validation"] = analysis.anchor_validation(ws.reference_corpus)
    except Exception as e:   # noqa: BLE001 - logged in full, reported to the client as task state
        log.exception("paper task %s failed", task)
        cache["task_error"][task] = GENERIC_ERROR
        raise HTTPException(500, GENERIC_ERROR) from e
    finally:
        running.discard(task)
    return analysis_tasks(analysis_id)


@app.get("/api/analysis/{analysis_id}/export/{name}")
def analysis_export(analysis_id: str, name: str):
    ws = _get_workspace(analysis_id)
    if name == "analysis_summary.json":
        payload = json.dumps(dict(meta=ws.to_meta(), result=ws.result, audit_trail=ws.audit_trail),
                             indent=1, default=str)
        return StreamingResponse(iter([payload]), media_type="application/json",
                                 headers={"Content-Disposition": 'attachment; filename="analysis_summary.json"'})
    if name == "preflight.json":
        if ws.preflight is None:
            raise HTTPException(404, "a paper reproduction has no input file, so no pre-flight")
        payload = json.dumps(dict(ws.preflight, analysis_id=ws.analysis_id, n_claims=len(ws.claims),
                                  stopped=bool((ws.result or {}).get("stopped")),
                                  analysis_states=(ws.result or {}).get("analysis_states")),
                             indent=1, default=str)
        return StreamingResponse(iter([payload]), media_type="application/json",
                                 headers={"Content-Disposition": 'attachment; filename="preflight.json"'})
    if name in ("normalized_claims.csv", "conflicts.csv", "provenance_relationships.json"):
        _require_analyzable(ws)
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
    if name == "conflicts.csv":
        header, rows = views.conflict_export_rows(ws)
        return _csv_response(rows, header, name)
    if name == "provenance_relationships.json":
        indep = (ws.result or {}).get("independence") or {}
        prov = _provenance_payload(ws)
        payload = json.dumps(dict(
            mode=ws.mode, subject=prov["subject"], uploaded_dataset=prov["uploaded_dataset"],
            reference_corpus=prov["reference_corpus"],
            field_decodes=indep.get("field_decodes"), containment_top=indep.get("containment_top"),
            naming_residues=indep.get("naming_residues"),
            notable_root_propagation=indep.get("notable_root_propagation"),
            inheritance_candidates=(ws.result or {}).get("target_audit", {}).get("inheritance_candidates")),
            indent=1, default=str)
        return StreamingResponse(iter([payload]), media_type="application/json",
                                 headers={"Content-Disposition": 'attachment; filename="provenance_relationships.json"'})
    raise HTTPException(404, f"unknown export {name!r}")


# ------------------------------------------------------ paper reproduction (Phase 25-31)
#: three things that must never be blurred (Phase 31)
_PAPER_MODES = [
    dict(id="live", label="Live computation", text="The corpus is loaded and THEMIS recomputes the paper's result."),
    dict(id="frozen", label="Frozen expected artifact", text="A figure shipped with the reference sample for comparison. Not a reproduction."),
    dict(id="declared", label="Manuscript declaration", text="A value the paper states (paper/paper_claims.yml). A PASS needs live computation to equal it.")]


def _paper_corpus_state() -> dict:
    ref, err = _reference_or_none()
    if ref is None:
        return dict(available=False, message=err, required=_paper_repro.required_inputs())
    return dict(available=True, scope=_scope_of(ref),
                n_claims_loaded=len(ref.claims), analysis_as_of_date=str(ref.snapshot_date),
                note=ref.sample_note)


@app.get("/api/paper/status")
def paper_status():
    manifest = _paper_verify.load_manifest()
    v = _paper_repro.load_verification()
    exps = (v or {}).get("experiments", {})
    return dict(
        paper=manifest.get("paper"), software_version=__version__, modes=_PAPER_MODES,
        corpus=_paper_corpus_state(), latest_run=None if v is None else dict(
            run_id=v["run_id"], status=v["status"], groups=v.get("groups"), counts=v["counts"], pdf=v["pdf"],
            failing=v["failing"], blocked_claims=len(v["blocked"]), warnings=v["warnings"]),
        experiments=[dict(id=k, title=e["title"], section=e["section"],
                          status=exps.get(k, {}).get("status", "NOT_RUN")) for k, e in manifest["experiments"].items()],
        stages=[dict(id=i, label=l) for i, l in _paper_repro.STAGES])


@app.post("/api/paper/reproduce")
def start_paper_reproduction():
    """Run `themis reproduce-paper` on a worker thread; stage progress is reported by the code that runs it."""
    if not _paper_corpus_state()["available"]:
        raise HTTPException(409, "PAPER REPRODUCTION DATA REQUIRED: the reference corpus is not present")
    job = _new_job("paper_reproduction", _paper_repro.STAGES)
    cb = _progress_for(job)

    def run():
        out = _paper_repro.reproduce(corpus=_reference_corpus(), progress=cb)
        return dict(run_id=out["run_id"], paper_status=out["status"])
    threading.Thread(target=_finish, daemon=True, args=(job, run)).start()
    return dict(job_id=job["job_id"])


@app.get("/api/paper/claims")
def paper_claims(run_id: str | None = None):
    """The verification matrix. Paper values come from the backend manifest, generated values from the run."""
    v = _paper_repro.load_verification(run_id)
    if v is not None:
        return dict(run_id=v["run_id"], status=v["status"], claims=v["claims"], counts=v["counts"])
    m = _paper_verify.load_manifest()
    rows = [dict(id=k, metric=c.get("metric", k), section=c.get("section"), text=c.get("text"), status="NOT_RUN",
                 paper_value=_paper_verify.paper_value(c), generated_value=None, basis=None, comparison=c.get("comparison"),
                 experiment=c.get("experiment"), **{"class": c.get("class")}) for k, c in m["claims"].items()]
    return dict(run_id=None, status="NOT_RUN", claims=rows, counts={})


@app.get("/api/paper/experiments/{exp_id}")
def paper_experiment(exp_id: str):
    d = _paper_repro.experiment_detail(exp_id)
    if d is None:
        raise HTTPException(404, f"no paper experiment {exp_id!r}")
    return d


@app.get("/api/paper/experiments/{exp_id}/artifact/{name}")
def paper_artifact(exp_id: str, name: str, run_id: str | None = None):
    v = _paper_repro.load_verification(run_id)
    meta = _paper_verify.load_manifest()["experiments"].get(exp_id)
    if v is None or meta is None or name not in meta.get("artifacts", []):
        raise HTTPException(404, "no such artifact for this experiment")
    p = _paper_repro.run_dir_of(v["run_id"]) / name
    if not p.is_file():
        raise HTTPException(404, f"{name} was not generated in run {v['run_id']}")
    return FileResponse(p, filename=name)


def _as_of_date(ws: _workspace.AnalysisWorkspace) -> datetime.date | None:
    """The date this analysis's own aggregate report was frozen to - every
    other view of the same analysis (address inspector included) must use
    this, not the live wall clock, or its stale/currency flags drift out of
    step with the summary the moment you view them on a different day."""
    if not ws.analysis_as_of_date:
        return None
    try:
        return datetime.date.fromisoformat(ws.analysis_as_of_date[:10])
    except ValueError:
        return None


def _explain_in_workspace(ws: _workspace.AnalysisWorkspace, address: str) -> dict:
    """STEP 21 - address inspector scoped to one uploaded-dataset workspace:
    the target's own claim(s) plus only the reference claims that land on
    this same address, never the reference corpus's unrelated agreement."""
    as_of = _as_of_date(ws)
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
                   root_kind=views.resolution_of(c)["kind"], tier=taxonomy.tier_of(c),
                   provenance=views.provenance_status(c),
                   lastmod=c.get("lastmod") or None, flags=taxonomy.currency_flags(c, today=as_of))

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
