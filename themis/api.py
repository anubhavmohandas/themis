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
import csv, datetime, hashlib, io, json, os, tempfile, threading, time, traceback

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
except ImportError as e:   # pragma: no cover
    raise SystemExit("themis.api requires the 'ui' extra: pip install -e '.[ui]'") from e

from .corpus import Corpus
from . import analysis, config_io, overview as _overview, provenance, report as _report, graph as _graph, taxonomy, views
from . import __version__
from .paper import reproduce as _paper_repro, verify as _paper_verify
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
    """The reference corpus, loaded once and cached - only ever touched when a
    request explicitly opts into comparing against it. Raises
    FileNotFoundError when it is not present (a release does not ship it)."""
    if "corpus" not in _reference_cache:
        _reference_cache["corpus"] = Corpus.reference()
    return _reference_cache["corpus"]


def _reference_or_none():
    try:
        return _reference_corpus(), None
    except FileNotFoundError as e:
        return None, str(e)


def _get_workspace(analysis_id: str) -> _workspace.AnalysisWorkspace:
    ws = _store.get(analysis_id)
    if ws is None:
        raise HTTPException(404, f"no analysis with id {analysis_id!r}")
    return ws


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
def _run_upload(data: bytes, filename: str | None, source_id: str, use_reference: bool,
                mapping_override: dict | None, progress=None) -> dict:
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
        result = _ingest_pipeline.ingest(tmp_path, source_id, mapping_override=mapping_override,
                                         reference=reference, analysis_as_of_date=today,
                                         progress=progress)
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
        schema_mapping=result.get("schema_mapping"), claims=result.get("claims", []),
        reference_corpus_version=(_scope_of(reference).lower() if reference is not None else None),
        warnings=result.get("limitations", []),
        result=result,
        audit_trail=_report.audit_trail(parameters=dict(source_id=source_id, use_reference=use_reference),
                                        warnings=result.get("limitations", [])),
    )
    _store.put(ws)
    if progress is not None:
        progress("complete", "report", None)
    if not result["stopped"]:
        result = dict(result)
        result["claims"] = result["claims"][:500]   # cap the payload; counts are in `validation`
    return dict(analysis_id=ws.analysis_id, meta=ws.to_meta(), preflight=result)


def _scope_of(corpus: Corpus) -> str:
    return "FULL_CORPUS" if corpus.full else "BUNDLED_SAMPLE"


def _run_paper(progress=None) -> dict:
    if progress is not None:
        progress("start", "load")
    try:
        corpus = _reference_corpus()
    except FileNotFoundError as e:
        raise HTTPException(409, str(e)) from e
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
                          use_reference: bool = Form(True), mapping: str | None = Form(None)):
    """Confirm the schema mapping and run the audit (STEP 10 step 4): creates
    a new UPLOADED_DATASET workspace and returns its analysis_id. Every
    other page-facing route reads through that id, never through a global
    default corpus."""
    mapping_override = _parse_mapping(mapping)
    data = await file.read()
    return _run_upload(data, file.filename, source_id, use_reference, mapping_override)


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
    except Exception as e:   # noqa: BLE001 - surfaced to the client, not swallowed
        job["status"] = "failed"
        job["error"] = str(getattr(e, "detail", None) or e)
        traceback.print_exc()     # the stack stays in the server log, not in the API response
        for st in job["stages"]:
            if st["status"] == "running":
                st["status"] = "failed"
    finally:
        job["finished_at"] = time.time()


@app.post("/api/jobs/analysis")
async def start_analysis_job(file: UploadFile = File(...), source_id: str = Form("uploaded_dataset"),
                             use_reference: bool = Form(True), mapping: str | None = Form(None)):
    mapping_override = _parse_mapping(mapping)
    data = await file.read()
    stages = _UPLOAD_STAGES if use_reference else [s for s in _UPLOAD_STAGES if s[0] != "reference"]
    job = _new_job("upload", stages)
    cb = _progress_for(job)
    threading.Thread(target=_finish, daemon=True, args=(
        job, lambda: _run_upload(data, file.filename, source_id, use_reference, mapping_override, cb))).start()
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


#: occam: page size is capped, not client-controlled, so a request can
#: never pull the whole corpus through this endpoint regardless of what
#: `limit` asks for.
_MAX_CLAIMS_PAGE = 500


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
    if kind not in (None, "", "all", "polarity", "entity", "hierarchical", "incomparable"):
        raise HTTPException(400, f"unknown conflict kind {kind!r}")
    if relationship not in (None, "", "distinct_roots", "shared_root", "unresolved"):
        raise HTTPException(400, f"unknown provenance relationship {relationship!r}")
    return views.conflicts_page(ws, kind=kind or None, source_a=source_a or None,
                                source_b=source_b or None, relationship=relationship or None,
                                q=q, offset=offset, limit=limit)


@app.get("/api/analysis/{analysis_id}/trust-coverage")
def analysis_trust_coverage(analysis_id: str, rules: str = ""):
    """Evidence retention under a chosen set of the existing trust predicates
    (comma-separated rule ids). Uploaded datasets only: paper mode's
    trust-rule sensitivity is /drift against the ransomware-revenue task."""
    ws = _get_workspace(analysis_id)
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
    if ws.mode == _workspace.MODE_PAPER:
        res = analysis.explain(ws.reference_corpus, address, as_of=_as_of_date(ws))
        if res.get("found"):   # same order as the claims explain() just read
            for view, raw in zip(res["claims"], ws.reference_corpus.by_addr[address]):
                view["provenance"] = views.provenance_status(raw)
        return res
    return _explain_in_workspace(ws, address)


@app.get("/api/analysis/{analysis_id}/provenance")
def analysis_provenance(analysis_id: str):
    ws = _get_workspace(analysis_id)
    graph = _graph.lineage_graph()
    inheritance = ws.result.get("target_audit", {}).get("inheritance_candidates", []) \
        if ws.mode == _workspace.MODE_UPLOADED and ws.result else []
    evidence = ws.result.get("independence") if ws.mode == _workspace.MODE_PAPER and ws.result else None
    _annotate_graph(graph, evidence)
    return dict(graph=graph, inheritance_candidates=inheritance, evidence=evidence)


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
    except Exception as e:   # noqa: BLE001 - reported to the client as task state
        cache["task_error"][task] = str(e)
        traceback.print_exc()
        raise HTTPException(500, f"{task} failed: {e}") from e
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
        payload = json.dumps(dict(
            mode=ws.mode, graph=_graph.lineage_graph(),
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
