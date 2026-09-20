"""`themis reproduce-paper`: run every paper experiment in a fixed order, write a
self-contained result directory, and compare the outcome with the manuscript.

What "reproduce" means here: recompute the paper's empirical measurements from
the declared inputs and compare them with what the manuscript states. It does
not establish that any attribution label is true. When the input cannot support
a recomputation (no corpus, or only the bundled sample for a corpus-wide figure)
the result says so - a frozen or sampled figure is never reported as a PASS.
"""
from __future__ import annotations
import csv, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time

from .. import __version__, config_io, report as _report
from ..corpus import Corpus, PKG, data_dir
from . import experiments as ex, figures, metrics as pm, verify as pv

STAGES = [("corpus_audit", "Corpus audit"), ("rq1_taxonomy", "RQ1 taxonomy tests"),
          ("source_depth", "Source depth"), ("overlap", "Overlap and coverage"),
          ("rodwald", "Rodwald provenance decode"), ("montreal", "Montreal recurrence"),
          ("currency", "Currency and freshness"), ("unresolved", "Unresolved provenance"),
          ("anchors", "Anchor validation"), ("drift", "Conclusion drift"),
          ("bootstrap", "Provenance-bound bootstrap"), ("table1", "Table 1"), ("figure1", "Figure 1"),
          ("table2", "Table 2"), ("figure2", "Figure 2"), ("metrics", "PaperMetrics"),
          ("verify", "Manuscript verification")]

#: which experiments answer which part of the paper (for the per-RQ / per-table summary)
GROUPS = dict(RQ1=["rq1_taxonomy"],
              RQ2=["source_depth", "overlap_coverage", "currency", "rodwald_containment",
                   "montreal_recurrence", "unresolved_provenance"],
              RQ3=["drift", "condition_d"],
              table1=["corpus_audit"], figure1=["rodwald_containment", "montreal_recurrence"],
              table2=["drift"], figure2=["drift"])


def results_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("THEMIS_RESULTS_DIR") or PKG / "results")


# ------------------------------------------------------------------ identity
def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_obj(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def git_state() -> dict:
    def run(*a):
        return subprocess.run(["git", "-C", str(PKG), *a], capture_output=True, text=True, timeout=20)
    try:
        head = run("rev-parse", "HEAD")
        if head.returncode:
            return dict(commit=None, dirty=None, note="not a git checkout")
        return dict(commit=head.stdout.strip(), dirty=bool(run("status", "--porcelain", "--untracked-files=no").stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        return dict(commit=None, dirty=None, note="git unavailable")


def input_files(observations=None) -> list[dict]:
    d = data_dir()
    paths = [pathlib.Path(observations)] if observations else [d / "observations_sample.csv.gz", d / "manifest.json"]
    paths += [d / n for n in ("revenue.csv.gz", "verified_anchors.txt.gz", "ground_truth.csv")]
    return [dict(path=str(p), name=p.name, bytes=p.stat().st_size, sha256=_sha256(p)) for p in paths if p.is_file()]


def required_inputs() -> dict:
    """What a reviewer must supply: the sources, where they come from, how to build the table."""
    cfg = config_io.load()
    return dict(
        sources=[dict(id=s, name=c.get("display_name", s), citation=c.get("citation"),
                      license=" ".join(str(c.get("license", "not recorded")).split())) for s, c in sorted(cfg.sources.items())],
        build_command="python scripts/build_corpus.py --help   # then: themis --observations <observations.csv.gz> reproduce-paper",
        also_needed=["revenue.csv.gz (per-address USD for the ransomware-revenue task)",
                     "verified_anchors.txt.gz (the externally assembled Condition D anchor set)",
                     "ground_truth.csv (the open anchor set)"],
        data_dir="set THEMIS_DATA_DIR or pass --data-dir DIR",
        docs=["REPRODUCE.md", "THIRD_PARTY_DATA.md"])


def load_corpus(observations=None, as_of=None) -> Corpus:
    c = Corpus.from_file(observations) if observations else Corpus.demo()
    if as_of:
        c.manifest["analysis_as_of_date"] = as_of
    return c


# ------------------------------------------------------------------ writers
def _json(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1, default=str))


def _csv(path: pathlib.Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        w.writeheader()
        w.writerows(rows)


def _md_table(rows: list[dict], cols: list[str]) -> str:
    f = lambda v: "" if v is None else (f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else
                                        f"{v:,.4f}" if isinstance(v, float) else str(v))
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] +
                     ["| " + " | ".join(f(r.get(c)) for c in cols) + " |" for r in rows]) + "\n"


def table1_files(t1: dict, out: pathlib.Path) -> None:
    rows = [dict(source=r["display_name"], unique_addresses=r["unique_addresses"], claims=r["claims"],
                 revision_field="Yes" if r["revision_field"] else "No", provenance_mode=r["provenance_mode"],
                 basis=r["basis"]) for r in t1["rows"]]
    rows.append(dict(source="Total", unique_addresses=t1["total"]["unique_addresses"], claims=t1["total"]["claims"],
                     revision_field="", provenance_mode="", basis=t1["total"]["basis"]))
    _json(out / "table1.json", t1)
    _csv(out / "table1.csv", rows)
    pr = t1["provenance_roots"]
    (out / "table1.md").write_text(
        "Table 1. Source-level corpus (generated by THEMIS from the loaded corpus; nothing typed).\n\n"
        + _md_table(rows, ["source", "unique_addresses", "claims", "revision_field", "provenance_mode", "basis"])
        + f"\nProvenance roots: {pr['total']} ({pr['identified']} identified, {pr['unresolved']} unresolved) [{pr['basis']}].\n"
        "`basis`: LIVE = recomputed from claims; FROZEN_MANIFEST = a corpus figure carried in the sample's manifest, not recomputed.\n")


def table2_files(t2: dict, out: pathlib.Path) -> None:
    rows = t2["rows"]
    _json(out / "table2.json", t2)
    _csv(out / "table2.csv", rows)
    (out / "table2.md").write_text(
        "Table 2. Conclusion drift under four label-trust conditions (generated by THEMIS; the same rows feed Figure 2).\n\n"
        + _md_table(rows, ["condition", "label", "observations", "addresses", "revenue_usd", "ratio_vs_B", "coverage_vs_B"])
        + "\nDerived: " + ", ".join(f"{k} = {v:.4f}" if isinstance(v, float) else f"{k} = {v}" for k, v in t2["derived"].items()) + "\n")


# ------------------------------------------------------------------ RQ1
def run_rq1() -> dict:
    """The paper's claim taxonomy is proved by tests, not by a corpus number."""
    tests = PKG / "tests" / "test_rq1_taxonomy.py"
    if not tests.is_file():
        return dict(status="NOT_RUN", reason="tests/test_rq1_taxonomy.py is not present")
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", str(tests), "-q", "-p", "no:cacheprovider"],
                           cwd=PKG, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return dict(status="NOT_RUN", reason=str(e))
    if "No module named pytest" in p.stderr + p.stdout:
        return dict(status="NOT_RUN", reason="pytest is not installed (pip install -e '.[test]')")
    m = lambda w: int((re.search(rf"(\d+) {w}", p.stdout) or [0, 0])[1])
    return dict(status="PASS" if p.returncode == 0 else "FAIL", passed=m("passed"), failed=m("failed"),
                skipped=m("skipped"), output_tail=p.stdout.strip().splitlines()[-3:])


# ------------------------------------------------------------ status roll-ups
def experiment_statuses(res: dict, rq1: dict | None = None) -> dict:
    out = {}
    for r in res["claims"]:
        e = out.setdefault(r["experiment"] or "(none)", dict(counts={}, claims=0))
        e["counts"][r["status"]] = e["counts"].get(r["status"], 0) + 1
        e["claims"] += 1
    for e in out.values():
        c = e["counts"]
        e["status"] = ("FAIL" if c.get("FAIL") else "NOT_REPRODUCED" if c.get("NOT_REPRODUCED")
                       else "PASS" if c.get("PASS") else "NOT_MACHINE_CHECKABLE" if c.get("NOT_MACHINE_CHECKABLE") else "INFORMATIONAL")
    if rq1 is not None:
        out["rq1_taxonomy"] = dict(status=rq1["status"], counts={rq1["status"]: 1}, claims=1, detail=rq1)
    return out


def group_status(exps: dict, ids: list[str]) -> str:
    st = [exps[i]["status"] for i in ids if i in exps]
    for bad in ("FAIL", "NOT_RUN", "NOT_REPRODUCED"):
        if bad in st:
            return bad
    return "PASS" if "PASS" in st else "NOT_MACHINE_CHECKABLE"


# ------------------------------------------------------------------ main run
def reproduce(corpus: Corpus | None = None, *, observations=None, as_of=None, bootstrap: str = "both",
              out_root: pathlib.Path | None = None, run_id: str | None = None, manifest_path=None, pdf=None,
              with_rq1: bool = True, mirror: bool = True, progress=None) -> dict:
    """Run everything; returns dict(status, run_dir, verification, ...). Never raises for a missing corpus."""
    t0 = time.time()
    P = progress or (lambda *a, **k: None)
    stage_log = {}

    def stage(sid, fn):
        P("start", sid)
        t = time.time()
        r = fn()
        stage_log[sid] = round(time.time() - t, 2)
        P("complete", sid)
        return r

    git = git_state()
    root = pathlib.Path(out_root) if out_root else results_root()
    run_id = run_id or (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "-" + (git["commit"] or "nogit")[:7])
    run_dir = root / "reproduction" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = pv.load_manifest(manifest_path)
    try:
        corpus = corpus or load_corpus(observations, as_of)
    except FileNotFoundError as e:
        blocked = dict(status=pv.BLOCKED, reason="INPUT CORPUS NOT AVAILABLE", message=str(e),
                       required=required_inputs(), paper=manifest.get("paper"))
        _json(run_dir / "blocked.json", blocked)
        _json(run_dir / "metadata.json", dict(run_id=run_id, software_version=__version__, git=git,
                                              paper_version=(manifest.get("paper") or {}).get("version"),
                                              status=pv.BLOCKED))
        (run_dir / "REPRODUCTION_REPORT.md").write_text(blocked_report(blocked, git))
        return dict(status=pv.BLOCKED, run_id=run_id, run_dir=str(run_dir), blocked=blocked, reason=blocked["reason"])

    b = ex.AnalysisBundle(corpus, as_of=datetime.date.fromisoformat(as_of) if as_of else None, bootstrap=bootstrap)
    cfg = config_io.load()
    boot = cfg.thresholds.get("bootstrap", {})
    warnings = []
    if not corpus.manifest.get("analysis_as_of_date"):
        warnings.append("the corpus declares no analysis date: staleness was judged at the newest revision date "
                        "in the claims (a lower bound on the real retrieval date). Pass --as-of.")

    t1 = stage("corpus_audit", lambda: ex.table1(b))
    rq1 = stage("rq1_taxonomy", run_rq1) if with_rq1 else dict(status="NOT_RUN", reason="skipped (--no-rq1)")
    if not with_rq1:
        P("complete", "rq1_taxonomy")
    depth = stage("source_depth", lambda: ex.source_depth(b))
    overlap = stage("overlap", lambda: ex.overlap_matrix(b))
    rod = stage("rodwald", lambda: ex.rodwald_containment(b))
    mont = stage("montreal", lambda: ex.montreal_recurrence(b))
    cur = stage("currency", lambda: ex.currency(b))
    unres = stage("unresolved", lambda: ex.unresolved_provenance(b))
    anch = stage("anchors", lambda: ex.anchors(b))
    t2 = stage("drift", lambda: ex.table2(b))
    trace = ex.condition_d_trace(b)
    boots = stage("bootstrap", lambda: ex.bootstrap_results(b))
    diag = ex.diagnostics(b)

    meta = dict(software_version=__version__, git_commit=git["commit"], git_dirty=git["dirty"],
                config_hash=_report._hash_config())

    def stage_files(sid, fn):
        P("start", sid)
        t = time.time()
        fn()
        stage_log[sid] = round(time.time() - t, 2)
        P("complete", sid)

    stage_files("table1", lambda: table1_files(t1, run_dir))
    r1a, r1b, r2 = figures.fig1a_rows(b), figures.fig1b_rows(b), figures.fig2_rows(b)

    def fig1():
        figures.write_rows(r1a, run_dir / "fig1a_data")
        figures.write_rows(r1b, run_dir / "fig1b_data")
        for n, (f, rows) in dict(fig1a=(figures.render_fig1a, r1a), fig1b=(figures.render_fig1b, r1b)).items():
            f(rows, run_dir, dict(meta, input_artifact=f"{n}_data.json",
                                  analysis_function="themis.provenance." + ("decode_field" if n == "fig1a" else "root_propagation")))
        # Phase 23 names for the same data
        shutil.copy(run_dir / "fig1a_data.csv", run_dir / "rodwald_containment.csv")
        shutil.copy(run_dir / "fig1b_data.csv", run_dir / "montreal_recurrence.csv")
        for n, alias in (("fig1a_rodwald_containment", "fig1a"), ("fig1b_montreal_recurrence", "fig1b")):
            for fmt in figures.FORMATS:
                if (run_dir / f"{n}.{fmt}").exists():
                    shutil.copy(run_dir / f"{n}.{fmt}", run_dir / f"{alias}.{fmt}")
    stage_files("figure1", fig1)
    stage_files("table2", lambda: table2_files(t2, run_dir))

    def fig2():
        figures.write_rows(r2, run_dir / "fig2_data")
        figures.render_fig2(r2, run_dir, dict(meta, input_artifact="fig2_data.json", analysis_function="themis.analysis.drift"))
    stage_files("figure2", fig2)

    _json(run_dir / "source_depth.json", depth)
    _json(run_dir / "overlap_matrix.json", overlap)
    _csv(run_dir / "overlap_matrix.csv", overlap["directed"])
    _json(run_dir / "currency.json", cur)
    _json(run_dir / "unresolved_provenance.json", unres)
    _json(run_dir / "anchors.json", anch)
    _json(run_dir / "condition_d_trace.json", trace)
    _json(run_dir / "drift.json", dict(table2=t2, conditions=b.drift["conditions"], policies=b.drift["policies"]))
    _json(run_dir / "diagnostics.json", diag)
    _json(run_dir / "rq1.json", rq1)
    for k, v in boots.items():
        _json(run_dir / f"bootstrap_{k}.json", v)

    metrics = stage("metrics", lambda: pm.build(b))
    _json(run_dir / "paper_metrics.json", metrics.to_json())
    res = stage("verify", lambda: pv.verify(metrics, manifest, pdf=pdf))
    exps = experiment_statuses(res, rq1)
    if rq1["status"] == "FAIL":
        res["status"] = pv.FAIL
        res["failing"].append("rq1_taxonomy")
    groups = {g: group_status(exps, ids) for g, ids in GROUPS.items()}
    fig_ok = figures.HAVE_MPL
    res.update(experiments=exps, groups=groups, rq1=rq1, figures_rendered=fig_ok)
    if not fig_ok:
        warnings.append("matplotlib is not installed: figure data was written, figures were not rendered")
    _json(run_dir / "verification.json", res)
    (run_dir / "PAPER_CLAIM_MAP.md").write_text(pv.claim_map_markdown(res))

    limitations = build_limitations(corpus, anch, t2, trace, cur, warnings)
    _json(run_dir / "limitations.json", limitations)
    metadata = dict(
        run_id=run_id, software_version=__version__, python=sys.version.split()[0], git=git,
        analysis_date=str(b.as_of) if b.as_of else None, scope=b.scope.kind,
        corpus_hash=_hash_obj([f["sha256"] for f in input_files(observations)]),
        taxonomy_hash=_hash_obj(cfg.taxonomy), source_registry_hash=_hash_obj(cfg.sources),
        threshold_config_hash=_hash_obj(cfg.thresholds), trust_rules_hash=_hash_obj(cfg.trust_rules),
        config_hash=meta["config_hash"], bootstrap=dict(seed=boot.get("seed"), iterations=boot.get("iterations"),
                                                        confidence_level=boot.get("confidence_level"),
                                                        rng="python random.Random (canonical)", mode=bootstrap),
        paper=res["paper"], paper_version=(res["paper"] or {}).get("version"), paper_manifest_sha256=res["manifest_sha256"],
        status=res["status"], stage_seconds=stage_log, total_seconds=round(time.time() - t0, 1), warnings=warnings)
    _json(run_dir / "metadata.json", metadata)
    _json(run_dir / "source_manifest.json", dict(
        input_files=input_files(observations),
        sources=[dict(id=s, display_name=c.get("display_name"), citation=c.get("citation"), license=c.get("license"),
                      config_sha256=_hash_obj(c)) for s, c in sorted(cfg.sources.items())]))
    _json(run_dir / "config_manifest.json", dict(
        config_dir=str(config_io.config_dir()), thresholds=cfg.thresholds, trust_rules=cfg.trust_rules,
        notable_roots=cfg.notable_roots, hashes=dict(taxonomy=metadata["taxonomy_hash"], sources=metadata["source_registry_hash"],
                                                     thresholds=metadata["threshold_config_hash"],
                                                     trust_rules=metadata["trust_rules_hash"], all=metadata["config_hash"])))
    (run_dir / "REPRODUCTION_REPORT.md").write_text(
        reproduction_report(metadata, res, t1, t2, depth, rod, mont, cur, unres, anch, trace, groups, limitations))
    if mirror:
        latest = root / "paper_proof"
        latest.mkdir(parents=True, exist_ok=True)
        for f in run_dir.iterdir():
            if f.is_file():
                shutil.copy(f, latest / f.name)
        (latest / "LATEST_RUN.txt").write_text(f"{run_id}\n")
    return dict(status=res["status"], run_id=run_id, run_dir=str(run_dir), verification=res, groups=groups,
                metadata=metadata, warnings=warnings)


# ---------------------------------------------------------------- narratives
def build_limitations(corpus, anch, t2, trace, cur, warnings) -> dict:
    items = [
        "Reproduction, not truth: THEMIS recomputes the paper's measurements from declared inputs and compares them "
        "with the manuscript. It does not establish that any attribution label is correct.",
        "Single-dataset addresses are uncorroborated, not unreliable.",
        "Condition D is the highest DECLARED confidence tier; the anchor set is not independently re-verified.",
        t2["note"] + ".",
        anch["limitations"],
        "Unresolved provenance stays unknown: it is neither one shared root nor independent roots.",
        cur["interpretation"] + ".",
        "Revenue values are inherited from upstream datasets, not recomputed from the blockchain.",
    ]
    if corpus.sample_note:
        items.insert(1, "Input is the bundled reference SAMPLE: " + corpus.sample_note +
                     " Corpus-wide figures come from its manifest (FROZEN_MANIFEST) and are reported NOT_REPRODUCED, "
                     "never PASS. Currency needs every claim and is not reproducible from the sample.")
    return dict(limitations=items + warnings)


def blocked_report(blocked: dict, git: dict) -> str:
    L = ["# THEMIS PAPER REPRODUCTION", "", "## REPRODUCTION STATUS", "", "**BLOCKED - INPUT CORPUS NOT AVAILABLE**", "",
         "The research package does not redistribute the third-party-derived observation table, and none was found. "
         "Nothing was reproduced, and nothing here is a PASS.", "", f"> {blocked['message']}", "", "## Required sources", ""]
    L += [f"- **{s['name']}** (`{s['id']}`) - {s['citation']}. Licence: {s['license']}" for s in blocked["required"]["sources"]]
    L += ["", "## To reproduce", "", f"1. Fetch the sources above. 2. Build: `{blocked['required']['build_command']}`",
          "3. Also supply: " + "; ".join(blocked["required"]["also_needed"]) + ".",
          f"4. {blocked['required']['data_dir']}. See {', '.join(blocked['required']['docs'])}.", ""]
    return "\n".join(L)


def _v(x):
    return "-" if x is None else (f"{x:,}" if isinstance(x, int) and not isinstance(x, bool) else
                                  f"{x:,.4f}" if isinstance(x, float) else str(x))


def reproduction_report(md, res, t1, t2, depth, rod, mont, cur, unres, anch, trace, groups, lim) -> str:
    cl = res["claims"]
    by = lambda cls: [r for r in cl if r["class"] == cls and r["status"] not in ("INFORMATIONAL", "NOT_MACHINE_CHECKABLE")]
    cnt = lambda rows, s: sum(1 for r in rows if r["status"] == s)
    head = by("HEADLINE_STABLE")
    L = ["# THEMIS PAPER REPRODUCTION", "",
         "Reproduction means recomputing the paper's empirical measurements from declared inputs and comparing them with "
         "the manuscript. It does not prove that any attribution label is true. This report is generated; do not edit it.", "",
         "## Software, paper and input", "",
         f"- Software: THEMIS {md['software_version']}, Python {md['python']}, git {md['git'].get('commit') or 'n/a'}"
         + (" (uncommitted changes)" if md["git"].get("dirty") else ""),
         f"- Paper: {(md['paper'] or {}).get('title')} ({(md['paper'] or {}).get('file')}, version {md['paper_version']})",
         f"- Input: **{md['scope']}**; analysis date {md['analysis_date']} (declared, never the wall clock)",
         f"- Hashes: corpus `{md['corpus_hash'][:16]}`, taxonomy `{md['taxonomy_hash'][:16]}`, source registry "
         f"`{md['source_registry_hash'][:16]}`, thresholds `{md['threshold_config_hash'][:16]}`, paper manifest "
         f"`{(md['paper_manifest_sha256'] or '')[:16]}`",
         f"- Bootstrap: seed {md['bootstrap']['seed']}, {md['bootstrap']['iterations']} iterations, "
         f"{md['bootstrap']['confidence_level']} level, {md['bootstrap']['rng']}", "",
         "## Verdict", "", f"**PAPER ↔ THEMIS: {res['status']}**", "",
         f"- Headline claims: {cnt(head, 'PASS')} PASS, {cnt(head, 'FAIL')} FAIL, {cnt(head, 'NOT_REPRODUCED')} not reproduced "
         f"(of {len(head)} machine-checkable)",
         "- " + "; ".join(f"{g} {s}" for g, s in groups.items()),
         f"- PDF layer: {res['pdf']['status']}" + (f" ({res['pdf'].get('reason')})" if res['pdf'].get("reason") else
                                                    f" ({res['pdf'].get('n_checked')} locators, "
                                                    f"{len(res['pdf'].get('failed', []))} failed)"), ""]
    fails = [r for r in cl if r["status"] == "FAIL" and r["class"] not in ("DIAGNOSTIC", "SENSITIVITY")]
    if fails:
        L += ["## Failures", "", "| claim | paper | THEMIS | delta (THEMIS - paper) | detail |", "|---|---|---|---|---|"]
        L += [f"| {r['id']} | {pv.show(r['paper_value'], r, True)} | {pv.show(r['generated_value'], r)} | "
              f"{'' if r['delta'] is None else format(r['delta'], '+,.2f')} | {r['detail']} |" for r in fails] + [""]
    nr = [r for r in cl if r["status"] == "NOT_REPRODUCED" and r["class"] not in ("DIAGNOSTIC", "SENSITIVITY")]
    if nr:
        L += ["## Not reproduced (the loaded input cannot recompute them)", "",
              "| claim | paper | basis | value in hand |", "|---|---|---|---|"]
        L += [f"| {r['id']} | {pv.show(r['paper_value'], r, True)} | {r['basis']} | {pv.show(r['generated_value'], r)} |" for r in nr] + [""]
    L += ["## RQ1 - claim taxonomy", "", f"Methodology tests: **{res['rq1']['status']}**"
          + (f" ({res['rq1'].get('passed')} passed, {res['rq1'].get('failed')} failed)" if res['rq1'].get("passed") is not None else ""), "",
          "## RQ2 - corroboration, overlap and circularity", "",
          f"- Single-dataset addresses {depth['single_dataset']['addresses']:,} ({100 * depth['single_dataset']['share']:.2f}%), "
          f"multi-dataset {depth['multi_dataset']['addresses']:,}. {depth['interpretation']}: not {depth['not_interpreted_as'].split(' - ')[0]}.",
          f"- Overlap is COVERAGE, not correctness.", ""]
    for d in rod["decodes"]:
        L += [f"- {d['dataset']}.{d['field']} decoded against {d['candidate']} (letters {d['decoded_letters']}): "
              f"{d['shared_addresses']:,} shared addresses = {100 * d['share_of_dataset']:.2f}% of {d['dataset']}, "
              f"{100 * d['share_of_candidate']:.2f}% of {d['candidate']}; clean split {d['clean_split']}."]
    for rt in mont["roots"]:
        L += [f"- {rt['label']}: {rt['seed_addresses']:,} seed addresses; " + ", ".join(
            f"{r['source']} {r['addresses']:,} ({100 * r['share']:.2f}%)" for r in rt["recurrence"] if r["addresses"]) + "."]
    L += ["", "## RQ3 - conclusion drift (Table 2 / Figure 2)", ""]
    L += [_md_table(t2["rows"], ["condition", "observations", "addresses", "revenue_usd", "ratio_vs_B", "coverage_vs_B"])]
    L += [f"Condition D: {trace['retained_addresses']:,} addresses retained ({100 * trace['coverage_vs_B']:.1f}% of B). "
          f"{trace['interpretation']}. Not: {trace['not_interpreted_as']}.", ""]
    L += ["## Table 1 / Figure 1", "", _md_table([dict(source=r["display_name"], addresses=r["unique_addresses"], claims=r["claims"],
                                                       basis=r["basis"]) for r in t1["rows"]], ["source", "addresses", "claims", "basis"]),
          "## Currency", "", f"{cur['interpretation']}. As of {cur['analysis_as_of_date']} ({cur['scope']}).", "",
          "## Unknown provenance", "",
          f"{_v(unres['addresses'])} addresses ({_v(unres['share'])}) have unresolved provenance [{unres['basis']}]. "
          f"{unres['treatment']['default']}.", "",
          "## Anchor limitations", "",
          f"{anch['label']}: {anch['usable_independent_anchors']} of {anch['anchor_addresses']} anchors usable "
          f"({anch['same_root_exclusions']} same-root claims excluded). source_accuracy_robustly_estimable = "
          f"**{str(anch['source_accuracy_robustly_estimable']).lower()}**.", ""]
    L += [f"- {r['source']}: {r['reason']}" for r in anch["not_robustly_estimable_because"]]
    L += ["", "## Trust-rule interpretation", "",
          "The fixed procedure gives a very different figure under each trust rule; an attribution figure is incomplete "
          "unless the rule and its coverage are reported together. D is a low-coverage lower bound, not a corrected estimate.", "",
          "## Limitations", ""] + [f"- {x}" for x in lim["limitations"]] + ["", "## Final status", "", f"**{res['status']}**", ""]
    return "\n".join(L)


# --------------------------------------------------------------- console
def format_summary(out: dict) -> str:
    if out["status"] == pv.BLOCKED and "blocked" in out:
        b = out["blocked"]
        return "\n".join(["=" * 60, "THEMIS - PAPER REPRODUCTION", "=" * 60, "",
                          "PAPER REPRODUCTION DATA REQUIRED", "REPRODUCTION STATUS: BLOCKED - INPUT CORPUS NOT AVAILABLE", "",
                          b["message"], "", "Required sources:"] +
                         [f"  {s['name']}: {s['citation']}" for s in b["required"]["sources"]] +
                         ["", "Build: " + b["required"]["build_command"], "See REPRODUCE.md", "",
                          "PAPER ↔ THEMIS: BLOCKED (nothing was reproduced)"])
    res, g = out["verification"], out["groups"]
    head = [r for r in res["claims"] if r["class"] == "HEADLINE_STABLE" and r["status"] in ("PASS", "FAIL", "NOT_REPRODUCED")]
    n = lambda s: sum(1 for r in head if r["status"] == s)
    L = ["=" * 60, "THEMIS - PAPER REPRODUCTION", "=" * 60, "", f"Paper: {(res['paper'] or {}).get('title')}",
         f"Input: {out['metadata']['scope']}    Run: {out['run_id']}", ""]
    for k, label in (("RQ1", "RQ1"), ("RQ2", "RQ2"), ("RQ3", "RQ3"), ("table1", "Table 1"), ("figure1", "Figure 1"),
                     ("table2", "Table 2"), ("figure2", "Figure 2")):
        L.append(f"{label:<10}{g[k]}")
    L += ["", f"HEADLINE EMPIRICAL CLAIMS   {n('PASS')} PASS   {n('FAIL')} FAIL   {n('NOT_REPRODUCED')} NOT REPRODUCED"]
    for r in res["claims"]:
        if r["status"] == "FAIL" and r["class"] not in ("DIAGNOSTIC", "SENSITIVITY"):
            L.append(f"  FAIL  {r['id']}: paper {pv.show(r['paper_value'], r, True)}, THEMIS {pv.show(r['generated_value'], r)}")
    L += ["", f"Artifacts: {out['run_dir']}", "", "PAPER REPRODUCTION COMPLETE", "", f"PAPER ↔ THEMIS: {res['status']}"]
    if res["status"] == pv.BLOCKED:
        L.append("(no mismatch, but required corpus-wide input was unavailable, so this is not a PASS)")
    return "\n".join(L)


# ------------------------------------------------------------ run store (API)
def latest_run_id(root: pathlib.Path | None = None) -> str | None:
    f = (root or results_root()) / "paper_proof" / "LATEST_RUN.txt"
    return f.read_text().strip() if f.is_file() else None


def run_dir_of(run_id: str, root: pathlib.Path | None = None) -> pathlib.Path | None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id or ""):      # a run id is a name, never a path
        return None
    d = (root or results_root()) / "reproduction" / run_id
    return d if d.is_dir() else None


def load_verification(run_id: str | None = None, root=None) -> dict | None:
    run_id = run_id or latest_run_id(root)
    d = run_dir_of(run_id, root) if run_id else None
    if d is None or not (d / "verification.json").is_file():
        return None
    v = json.loads((d / "verification.json").read_text())
    v["run_id"] = run_id
    return v


def function_location(dotted: str | None) -> dict | None:
    """Where the analysis function behind a claim lives, for the evidence panel."""
    if not dotted:
        return None
    import importlib, inspect
    if dotted.endswith(".py") or "/" in dotted:
        return dict(name=dotted, file=dotted, line=None)
    name = dotted.split(" via ")[0].strip()
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        try:
            for p in parts[i:]:
                obj = getattr(obj, p)
            file = pathlib.Path(inspect.getsourcefile(obj) or inspect.getfile(obj))
            return dict(name=name, file=str(file.relative_to(PKG)) if PKG in file.parents else str(file),
                        line=inspect.getsourcelines(obj)[1] if callable(obj) else None)
        except (AttributeError, OSError, TypeError, ValueError):
            break
    return dict(name=name, file=None, line=None)


def experiment_detail(exp_id: str, run_id: str | None = None, root=None) -> dict | None:
    manifest = pv.load_manifest()
    meta = (manifest.get("experiments") or {}).get(exp_id)
    if meta is None:
        return None
    v = load_verification(run_id, root)
    d = run_dir_of(v["run_id"], root) if v else None
    artifacts = {}
    for name in meta.get("artifacts", []):
        p = d / name if d else None
        if p and p.is_file() and name.endswith(".json"):
            artifacts[name] = json.loads(p.read_text())
        elif p and p.is_file():
            artifacts[name] = None            # a non-JSON artifact: listed, downloadable, not inlined
    claims = [r for r in (v["claims"] if v else []) if r["experiment"] == exp_id]
    return dict(id=exp_id, run_id=v["run_id"] if v else None, artifact_names=meta.get("artifacts", []),
                **{k: x for k, x in meta.items() if k != "artifacts"},
                function_location=function_location(meta.get("function")),
                status=(v.get("experiments", {}).get(exp_id, {}).get("status") if v else "NOT_RUN"),
                artifacts=artifacts, claims=claims)
