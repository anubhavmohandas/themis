"""THEMIS - Trust and Evidence-based Heuristic Method for Investigative Source
Assessment. Runs the attribution-reliability audit from the command line.
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys, textwrap
from .corpus import Corpus
from . import analysis, taxonomy, config_io, report as _report
from .ingest import pipeline as _ingest_pipeline

B, D, DIM = "\033[1m", "\033[0m", "\033[2m"
RED, GRN, YEL = "\033[31m", "\033[32m", "\033[33m"


def _c(s, col):
    return s if not sys.stdout.isatty() else f"{col}{s}{D}"


def load(args) -> Corpus:
    c = Corpus.from_file(args.observations) if getattr(args, "observations", None) else Corpus.demo()
    if getattr(args, "as_of", None):
        c.manifest["analysis_as_of_date"] = args.as_of   # Corpus.snapshot_date reads it
    return c


def rule(t=""):
    print(f"\n{_c('─' * 72, DIM)}")
    if t:
        print(_c(t, B))


# ------------------------------------------------------------------- commands
def cmd_audit(args):
    c = load(args)
    a = analysis.agreement(c)
    i = analysis.independence(c)
    kap = analysis.cohen_kappa(c)
    if c.sample_note:
        print(_c("note: " + c.sample_note, DIM))

    rule("CORPUS")
    print(f"  {a['n_claims'] if 'n_claims' in a else c.n_claims:,} claims over "
          f"{c.n_addresses:,} addresses, {i['n_roots_total']} distinct provenance "
          f"roots ({i['n_roots_identified']} identified, "
          f"{i['n_roots_total']-i['n_roots_identified']} unresolved)")
    for s, n in c.source_sizes().items():
        print(f"    {s:<18}{n:>10,}")

    rule("CORROBORATION  (RQ2)")
    print(f"  single-dataset       {a['single_source']:>10,}  "
          f"{100*(1-a['multi_source_rate']):6.2f}%")
    print(f"  two or more          {a['n_multi_source']:>10,}  "
          f"{100*a['multi_source_rate']:6.2f}%")
    print(_c("  counts datasets, not independent sources - see INDEPENDENCE below", DIM))

    rule("AGREEMENT  (among multi-dataset addresses)")
    for k, v in a["outcomes"].items():
        col = RED if "conflict" in k else None
        line = f"  {k:<26}{v['n']:>8,}  {100*v['share']:6.2f}%"
        print(_c(line, col) if col else line)
    print(_c(f"  chance-corrected: {kap['n_pairs']} overlapping pairs, "
             f"{kap['n_undefined']} undefined, {kap['n_zero']} at zero", DIM))
    for r in kap["substantial"]:
        print(f"    {r['pair']:<28}n={r['n']:>6,}  raw {100*r['percent_agreement']:5.1f}%"
              f"   kappa {r['cohen_kappa']:.3f}")
        ki = r["cohen_kappa_interpretable"]
        print(_c(f"      interpretable pairs only: n={r['n_interpretable']:>6,}  "
                 f"raw {100*r['percent_agreement_interpretable']:5.1f}%   kappa "
                 f"{'undefined' if ki is None else format(ki, '.3f')}"
                 f"   ({r['n_both_unknown']:,} both-unknown pairs counted as agreement above)", DIM))
    if a["top_polarity_conflicts"]:
        print(_c("  largest licit/illicit conflicts:", DIM))
        for p in a["top_polarity_conflicts"][:4]:
            print(f"    {p['n']:>5}  {p['source_a']}:{p['label_a']} "
                  f"vs {p['source_b']}:{p['label_b']}")

    rule("INDEPENDENCE  (RQ2)")
    for fd in i["field_decodes"]:
        verdict = "CLEAN SPLIT" if fd["clean_split"] else "inconclusive"
        print(f"  decoding {fd['dataset']}.{fd.get('field','source')} against {fd['candidate']}: "
              f"{_c(verdict, GRN if fd['clean_split'] else YEL)}")
        for v, g in list(fd["groups"].items())[:config_io.load().thresholds.get("decode_report_limit", 12)]:
            mark = "inherited" if g["verdict"] == "inherited" else g["verdict"]
            print(f"    group {v or '(blank)':<6} n={g['n']:>7,}  "
                  f"{100*g['share_in_candidate']:6.1f}% inside  {mark}")
        print(f"  -> {fd['inherited_addresses']:,} addresses inherited from {fd['candidate']}")
    for nr in i["naming_residues"]:
        print(f"  naming residue in {nr['dataset']}: {nr['attributed']:,} of {nr['total']:,} "
              f"({100*nr['share']:.2f}%) name their upstream study")
    for m in i["notable_root_propagation"]:
        print(f"  {m['label']} ({m['size']:,} addresses) also appears in:")
        for s, n in sorted(m["propagation"].items(), key=lambda kv: -kv[1]):
            if n:
                print(f"    {s:<18}{n:>7,}  {100*n/m['size']:6.2f}%" if m["size"] else f"    {s:<18}{n:>7,}")
    print(f"  unresolved provenance: {i['unresolved_addresses']:,} addresses "
          f"({100*i['unresolved_addr_share']:.1f}% of the corpus)")
    print(_c("  concentration:", DIM))
    for rc in i["root_concentration"][:3]:
        print(f"    {rc['root']:<34}{100*rc['share']:6.2f}% of all claims")
    print(_c("  unresolved is not 'shared' - see `themis bootstrap --both`", DIM))
    if args.json:
        json.dump(dict(agreement=a, independence=i, kappa=kap),
                  open(args.json, "w"), indent=1)
        print(f"\nwritten {args.json}")


def cmd_drift(args):
    c = load(args)
    d = analysis.drift(c)
    rule("CONCLUSION DRIFT  (RQ3)")
    print("  same corpus, same estimation procedure; only the trust rule changes\n")
    print(f"  {'':2}{'condition':<46}{'obs':>9}{'addresses':>11}{'revenue USD':>16}{'vs B':>7}")
    for k, v in d["conditions"].items():
        col = RED if k == "D" else None
        line = (f"  {k} {v['label']:<44}{v['observations']:>9,}{v['addresses']:>11,}"
                f"{v['usd']:>16,.0f}{v['ratio_vs_B']:>7.2f}")
        print(_c(line, col) if col else line)
    print(f"\n  {d['shared_addresses']:,} addresses are shared between the two sources "
          f"and counted twice in A")
    print(_c(f"  spread B/D = {d['spread_B_over_D']:.1f}x   A/D = {d['spread_A_over_D']:.1f}x", B))
    print(textwrap.fill(
        "D retains only %.1f%% of addresses, so its figure is a lower bound at low "
        "coverage, not a corrected estimate. The point is that the trust rule moves "
        "the answer by an order of magnitude." % (100 * d['conditions']['D']['coverage_vs_B']),
        76, initial_indent="  ", subsequent_indent="  "))
    if args.json:
        json.dump(d, open(args.json, "w"), indent=1)
        print(f"\nwritten {args.json}")


def cmd_explain(args):
    c = load(args)
    r = analysis.explain(c, args.address)
    if not r["found"]:
        print(f"address not present in this corpus: {args.address}")
        print(_c("the bundled sample holds every multi-dataset address plus a "
                 "random sample of single-dataset ones", DIM))
        return 1
    rule(f"ADDRESS  {r['address']}")
    print(f"  outcome            {r['outcome']}")
    print(f"  tier               {r['tier']}")
    print(f"  flags              {', '.join(r['flags']) or 'none'}")
    print(f"\n  apparent corroboration   {r['apparent_corroboration']} dataset(s)")
    line = f"  actual corroboration     {r['actual_corroboration']} provenance root(s)"
    print(_c(line, RED) if r["circular"] else _c(line, GRN))
    if r["circular"]:
        print(_c("  -> agreement here is circular: the datasets share an ancestor", RED))
    print("\n  claims:")
    for cl in r["claims"]:
        print(f"    {cl['source']:<16}{cl['label']:<18}root={cl['root']:<34}"
              f"{cl['tier']:<18}{','.join(cl['flags']) or ''}")
    if args.json:
        json.dump(r, open(args.json, "w"), indent=1)


def cmd_bootstrap(args):
    c = load(args)
    rule("CLUSTER BOOTSTRAP  (resampling unit = provenance root)")
    if args.fast:
        print(_c("  --fast: numpy RNG, exploratory only - endpoints will not match "
                  "the canonical (default) path or the paper", YEL))
    runs = [False, True] if args.both else [args.upper]
    out = {}
    for ub in runs:
        b = analysis.bootstrap(c, n_boot=args.n, upper_bound=ub, fast=args.fast)
        name = "upper bound (unresolved independent)" if ub else "lower bound (unresolved pooled)"
        out["upper" if ub else "lower"] = b
        if len(out) == 1:
            print(f"  {b['n_boot']:,} resamples, seed {b['seed']}, "
                  f"{100 * b['confidence_level']:.0f}% percentile interval, engine {b['engine']}")
        print(f"\n  {name}: {b['n_clusters']:,} clusters")
        if b.get("note"):
            print(_c("    " + b["note"], DIM))
        for k, v in b["stats"].items():
            print(f"    {k:<26}{100*v['point']:7.3f}%  "
                  f"[{100*v['ci_low']:6.3f}, {100*v['ci_high']:6.3f}]")
    print(_c("\n  a row-level bootstrap would report far tighter intervals and would be "
             "wrong to:\n  republished claims from one ancestor are not independent "
             "observations.", DIM))
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1)


def cmd_anchors(args):
    c = load(args)
    r = analysis.anchor_validation(c)
    rule("ANCHOR VALIDATION  (Sec 4.3/4.7 - open reference set, provenance-aware)")
    print(f"  {r['anchors_total']:,} anchors -> {r['usable_anchors']:,} usable "
          f"({100 * r['coverage']:.1f}% coverage)")
    print(f"  {r['excluded_self_root_claims']:,} claims excluded as self/same-root "
          f"(would overstate independent validation if matched by dataset name instead)")
    if r["uninterpretable_ground_truth_label"]:
        print(f"  {r['uninterpretable_ground_truth_label']:,} usable anchors have a "
              f"ground-truth label the taxonomy can't canonicalize")
    lvl = f"{100 * r['confidence_level']:.0f}%"
    print("\n  one decision per (source, address); 'agree' = exact agreement with the anchor's "
          "label,\n  NOT the source's accuracy. roots = independent resolved provenance roots "
          "behind the\n  decisions; top = share of decisions from the single largest root.")
    print(f"\n  {'source':<20}{'n':>6}{'exact':>7}{'agree':>8}{'roots':>7}{'top':>7}"
          f"{lvl + ' CI (roots resampled)':>30}")
    for src, v in sorted(r["per_source"].items(), key=lambda kv: -(kv[1]["n"] or 0)):
        if not v["estimable"]:
            why = v["not_estimable_reason"]
            head = (f"  {src:<20}{v['n']:>6,}{v['exact']:>7,}{100*v['anchor_agreement']:>7.1f}%"
                    f"{v['independent_roots']:>7}{100*v['largest_root_share']:>6.0f}%"
                    if v["n"] else f"  {src:<20}{0:>6}")
            print(f"{head}     not estimable: {why}")
            continue
        print(f"  {src:<20}{v['n']:>6,}{v['exact']:>7,}{100*v['anchor_agreement']:>7.1f}%"
              f"{v['independent_roots']:>7}{100*v['largest_root_share']:>6.0f}%"
              f"{'[' + format(100*v['ci_low'], '5.1f') + ', ' + format(100*v['ci_high'], '5.1f') + ']':>30}")
    if not r["estimable"]:
        print(_c("\n  no source is estimable: none has enough independent roots behind "
                 "its decisions on this anchor set", YEL))
    else:
        print(_c("\n  an estimable source is not a well-measured one: with this few "
                 "independent roots the\n  interval is wide by construction, and it "
                 "bounds only agreement with this anchor set.", YEL))
    print(textwrap.fill("\n" + r["limitations"], 76, subsequent_indent="  "))
    if args.json:
        json.dump(r, open(args.json, "w"), indent=1)
        print(f"\nwritten {args.json}")


def cmd_taxonomy(args):
    rule("RELIABILITY TAXONOMY")
    print("  tiers (ordered):")
    for t in taxonomy.TIER_ORDER:
        print(f"    {t}")
    print("\n  flags (orthogonal, downgrade within tier):")
    for f in ("currency-unknown", "stale", "conflicting", "circular"):
        print(f"    {f}")
    print(f"\n  stale threshold: {taxonomy.STALE_AFTER_YEARS} years since last revision")
    print("  a claim with no revision field is currency-unknown, never stale")
    print("\n  category polarities:")
    il = sorted(k for k, v in taxonomy.POLARITY.items() if v == "illicit")
    li = sorted(k for k, v in taxonomy.POLARITY.items() if v == "licit")
    print(textwrap.fill("illicit: " + ", ".join(il), 76, subsequent_indent="    "))
    print(textwrap.fill("licit:   " + ", ".join(li), 76, subsequent_indent="    "))
    print(f"\n  {len(taxonomy.ALIASES)} raw-label aliases declared "
          f"(config/taxonomy.yml) across {len(taxonomy.CATEGORIES)} categories")


def cmd_sources(args):
    """STEP 25 - the source registry, read straight from config/sources/."""
    cfg = config_io.load()
    rule("SOURCE REGISTRY")
    for sid, src in sorted(cfg.sources.items()):
        prov = src.get("provenance", {})
        print(f"\n  {_c(sid, B)}  ({src.get('display_name', sid)})")
        print(f"    chain              {src.get('chain', '?')}")
        print(f"    citation           {src.get('citation', '(none declared)')}")
        print(f"    confidence         {src.get('confidence_semantics', '(none declared)')}")
        print(f"    provenance mode    {prov.get('mode', '(none - resolves UNRESOLVED)')}")
        norm = src.get("address_normalization")
        if norm:
            print(f"    address normalize  strip {norm.get('strip_prefix')!r} (raw preserved as raw_address)")
        deps = src.get("known_dependencies") or []
        if deps:
            print(f"    known dependencies {', '.join(deps)}")
    if args.json:
        json.dump(cfg.sources, open(args.json, "w"), indent=1)
        print(f"\nwritten {args.json}")


def _print_preflight(pf: dict) -> None:
    """The pre-flight as a reviewable table: what each column was taken to mean, how sure, and what blocks analysis."""
    inp, ch = pf["input"], pf["chain"]
    rule("DATASET PRE-FLIGHT")
    print(f"  input:           {inp['filename']}  ({inp['type']}{', table ' + inp['table'] if inp.get('table') else ''}, "
          f"{inp['n_rows']:,} rows, {inp['n_columns']} columns)")
    print(f"  dataset type:    {pf['dataset_type']}")
    chain_txt = (f"{ch['value']}  ({ch['source']}, {100*(ch['confidence'] or 0):.0f}%)" if ch["value"]
                 else f"{ch['status']}" + ("  -> choose one with --chain" if ch["status"] in ("undetermined", "ambiguous") else ""))
    print(f"  blockchain:      {chain_txt}")
    if pf["currency_basis"]:
        print(f"  staleness rule:  {pf['currency_basis']['rule']}")
    rule("SCHEMA MAPPING")
    print(f"  {'column':<30}{'semantic field':<50}{'conf':>6}  status")
    for r in pf["columns"]:
        conf = "-" if r["confidence"] is None else f"{100*r['confidence']:.0f}%"
        color = {"ok": GRN, "review": YEL, "invalid": RED}.get(r["status"], DIM)
        print(f"  {r['column'][:29]:<30}{r['semantic_label'][:49]:<50}{conf:>6}  {_c(r['status'], color)}")
        for n in r["notes"]:
            print(_c(f"      {n}", DIM))
    for req in pf["required"]:
        mark = _c("OK ", GRN) if req["satisfied"] else _c("MISSING", RED)
        print(f"  required {req['name']:<20}{mark}  {req['column'] or ' / '.join(req['accepts'])}")
    for b in pf["blockers"]:
        print(_c(f"  blocked [{b['code']}]: {b['message']}", YEL))


def cmd_ingest(args):
    """STEP 23 - new dataset mode: upload a previously unseen CSV. The pre-flight
    runs first and decides whether any analysis may happen at all."""
    reference = None
    if args.reference:
        reference = Corpus.from_file(args.reference)
    elif not args.no_reference:
        try:
            reference = Corpus.demo()
        except FileNotFoundError as e:
            print(_c(f"note: no reference corpus, so no cross-source comparison ({e})", YEL), file=sys.stderr)

    override = {}
    for spec in args.map or []:
        if "=" not in spec:
            print(f"--map expects role=column, got: {spec}", file=sys.stderr)
            return 1
        role, col = spec.split("=", 1)
        override[role] = col

    try:
        r = _ingest_pipeline.ingest(args.file, args.source_id, mapping_override=override or None,
                                    reference=reference, chain=args.chain, confirmed=args.confirm)
    except ValueError as e:
        print(_c(f"error: {e}", RED), file=sys.stderr)
        return 2
    pf = r["dataset_preflight"]
    if args.preflight_json:
        json.dump(pf, open(args.preflight_json, "w"), indent=1, default=str)
    if r["stopped"]:
        _print_preflight(pf)
        rule("STOPPED AT PRE-FLIGHT")
        print(_c(r["message"], YEL))
        if args.json:
            out = dict(r)
            out.pop("claims", None)
            json.dump(out, open(args.json, "w"), indent=1, default=str)
        return 1

    _print_preflight(pf)
    rule("VALIDATION")
    v = r["validation"]
    print(f"  {v['n_input']:,} input rows -> {v['n_valid']:,} valid claims, "
          f"{v['n_rejected']:,} rejected")
    for reason, n in v["rejected_by_reason"].items():
        print(f"    {reason:<20}{n:>8,}")
    rule("ANALYSIS STATES")
    for name, st in r["analysis_states"].items():
        shown = st["state"] if st["state"] == "computed" else f"{st['state']} - {st['reason']}"
        print(f"  {name:<18}{_c(shown, GRN if st['state'] == 'computed' else YEL)}")
    rule("CAPABILITIES")
    for cap, ok in r["capabilities"].items():
        print(f"  {_c('OK ', GRN)} {cap}" if ok else f"  {_c('--', DIM)} {cap}")
    for lim in r["limitations"]:
        print(_c(f"  !  {lim}", YEL))
    rule("RELIABILITY PROFILE")
    for dim, block in r["reliability_profile"].items():
        if not block.get("available"):
            print(f"  {dim:<24}{_c('unavailable: ' + block['reason'], DIM)}")
        else:
            print(f"  {dim}")
            for k, v2 in block.items():
                if k == "available":
                    continue
                print(f"    {k:<26}{v2}")
    if args.json:
        out = dict(r)
        out["claims"] = len(r["claims"])   # the full claim list is large; keep the JSON small by default
        json.dump(out, open(args.json, "w"), indent=1, default=str)
        print(f"\nwritten {args.json}")


def cmd_preflight(args):
    """Inspect a CSV, or a table of a SQLite database, without analysing it. A
    SQLite file with no --table lists its tables and row counts; with --table it
    pre-flights that table on a spread-out sample (the database is opened
    read-only and never loaded)."""
    from .ingest import preflight as _pf, sqlite_source as _sq
    if _sq.is_sqlite_path(args.file):
        if not args.table:
            rule("SQLITE TABLES")
            for t in _sq.list_tables(args.file):
                n = f"{t['n_rows']:,}" if t["n_rows"] is not None else "? (count timed out)"
                print(f"  {t['table']:<40}{n:>16} rows  {t['n_columns']:>3} columns")
            print(_c("\n  choose one with --table NAME to pre-flight it", DIM))
            return 0
        sample, names = _sq.sample_rows(args.file, args.table, _pf.cfg()["sample_size"])
        with _sq.open_readonly(args.file) as con:
            total = _sq.count_rows(con, args.table, _sq.cfg()["count_timeout_seconds"])
        pf = _pf.run(sample, names, filename=os.path.basename(args.file), input_type="sqlite", table=args.table,
                     total_rows=total, overrides=_pf.overrides_from_roles(dict(m.split("=", 1) for m in args.map or []), names),
                     chain=args.chain, confirmed=args.confirm)
    else:
        rows, names = _ingest_pipeline.load_csv(args.file)
        pf = _pf.run(rows, names, filename=os.path.basename(args.file), sha256=_ingest_pipeline.sha256_file(args.file),
                     input_type=_ingest_pipeline.input_type_of(args.file),
                     overrides=_pf.overrides_from_roles(dict(m.split("=", 1) for m in args.map or []), names),
                     chain=args.chain, confirmed=args.confirm)
    _print_preflight(pf)
    if pf["message"]:
        rule("RESULT")
        print(_c(pf["message"], YEL))
    if args.json:
        json.dump(pf, open(args.json, "w"), indent=1, default=str)
    return 0 if pf["can_analyze"] else 1


def cmd_report(args):
    """STEP 27 - the canonical, single-object report every other surface
    (JSON export, future UI) reads from."""
    c = load(args)
    res = _report.build_corpus_report(c, include_bootstrap=args.bootstrap,
                                      include_anchors=args.anchors,
                                      input_path=args.observations)
    rule("THEMIS REPORT")
    ds = res["dataset_summary"]
    print(f"  {ds['n_claims']:,} claims over {ds['n_addresses']:,} addresses across "
          f"{len(ds['sources'])} sources")
    print(f"\n  audit trail")
    at = res["audit_trail"]
    print(f"    software version   {at['software_version']}")
    print(f"    config hash        {at['config_hash'][:16]}...")
    print(f"    timestamp          {at['analysis_timestamp']}")
    if res["limitations"]:
        print(_c("\n  limitations:", YEL))
        for lim in res["limitations"]:
            print(f"    - {lim}")
    path = args.json or args.out
    if path:
        _report.to_json(res, path)
        print(f"\nwritten {path}")


# ----------------------------------------------------- paper reproduction
_EXPERIMENTS = {   # `themis reproduce <name>` -> (function, what it writes beside its JSON)
    "table1": "table1", "source-depth": "source_depth", "overlap": "overlap_matrix",
    "rodwald-containment": "rodwald_containment", "montreal-recurrence": "montreal_recurrence",
    "currency": "currency", "unresolved-provenance": "unresolved_provenance", "anchors": "anchors",
    "table2": "table2", "condition-d": "condition_d_trace"}


def _paper_corpus(args):
    """The corpus for a paper command, or None after printing why there is none."""
    from .paper import reproduce as _rp
    try:
        return load(args)
    except FileNotFoundError as e:
        print(_rp.format_summary(dict(status="BLOCKED", blocked=dict(
            message=str(e), required=_rp.required_inputs()))))
        return None


def cmd_reproduce(args):
    from .paper import experiments as ex, figures
    c = _paper_corpus(args)
    if c is None:
        return 3
    b = ex.AnalysisBundle(c)
    res = getattr(ex, _EXPERIMENTS[args.experiment])(b)
    if args.experiment == "rodwald-containment":
        rule("RODWALD PROVENANCE DECODE  (group containment, derived - nothing names the candidate)")
        for d in res["decodes"]:
            print(f"  {d['dataset']}.{d['field']} against {d['candidate']}  decoded letters {d['decoded_letters']}"
                  f"  clean split: {d['clean_split']}")
            print(f"  {'group':<8}{'size':>9}{'inside':>9}{'containment':>13}  verdict")
            for g in d["groups"]:
                print(f"  {g['code']:<8}{g['size']:>9,}{g['overlap_with_candidate']:>9,}{100*g['containment']:>12.2f}%  {g['verdict']}")
            print(f"\n  shared addresses {d['shared_addresses']:,} = {100*d['share_of_dataset']:.2f}% of {d['dataset']}, "
                  f"{100*d['share_of_candidate']:.2f}% of {d['candidate']}")
    else:
        print(json.dumps(res, indent=1, default=str)[:20000])
    if args.out_dir:
        out = pathlib.Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
        (out / f"{_EXPERIMENTS[args.experiment]}.json").write_text(json.dumps(res, indent=1, default=str))
        if args.experiment == "rodwald-containment":
            figures.write_rows(figures.fig1a_rows(b), out / "fig1a_data")
        print(f"\nwritten {out}")


def cmd_figures(args):
    from .paper import experiments as ex, figures, reproduce as rp
    out = pathlib.Path(args.out_dir or rp.results_root() / "paper_proof")
    out.mkdir(parents=True, exist_ok=True)
    if args.from_data:   # redraw from artifacts already on disk: no corpus needed
        src = pathlib.Path(args.from_data)
        rows = {n: json.loads((src / f"{n}_data.json").read_text()) for n in ("fig1a", "fig1b", "fig2")}
        b = None
    else:
        c = _paper_corpus(args)
        if c is None:
            return 3
        b = ex.AnalysisBundle(c)
        rows = dict(fig1a=figures.fig1a_rows(b), fig1b=figures.fig1b_rows(b), fig2=figures.fig2_rows(b))
        for n, r in rows.items():
            figures.write_rows(r, out / f"{n}_data")
    if not figures.HAVE_MPL:
        print("matplotlib is not installed: data files written, figures not rendered "
              "(pip install -e '.[figures]')", file=sys.stderr)
        return 1
    meta = dict(software_version=rp.__version__, git_commit=rp.git_state()["commit"], config_hash=_report._hash_config())
    for n, f, fn in (("fig1a", figures.render_fig1a, "themis.provenance.decode_field"),
                     ("fig1b", figures.render_fig1b, "themis.provenance.root_propagation"),
                     ("fig2", figures.render_fig2, "themis.analysis.drift")):
        print(f"  {n}: " + ", ".join(f(rows[n], out, dict(meta, input_artifact=f"{n}_data.json", analysis_function=fn))))
    print(f"figures written to {out}")


def cmd_verify_paper(args):
    from .paper import experiments as ex, metrics as pm, verify as pv
    manifest = pv.load_manifest(args.claims)
    if args.metrics:
        m = pm.PaperMetrics.from_json(json.load(open(args.metrics)))
    else:
        c = _paper_corpus(args)
        if c is None:
            return 3
        m = pm.build(ex.AnalysisBundle(c, bootstrap="both" if args.with_bootstrap else "none"))
    res = pv.verify(m, manifest, pdf=args.paper)
    print(pv.format_console(res))
    if args.json:
        json.dump(res, open(args.json, "w"), indent=1, default=str)
    if args.claim_map:
        open(args.claim_map, "w").write(pv.claim_map_markdown(res))
        print(f"\nclaim map written to {args.claim_map}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 3}[res["status"]]


def cmd_reproduce_paper(args):
    from .paper import reproduce as rp
    out = rp.reproduce(observations=args.observations, as_of=args.as_of, bootstrap=args.bootstrap,
                       out_root=pathlib.Path(args.results_dir) if args.results_dir else None,
                       run_id=args.run_id, manifest_path=args.claims, pdf=args.paper,
                       with_rq1=not args.no_rq1, progress=None if args.quiet else
                       (lambda ev, st, *_: print(f"  {ev:<9}{st}", file=sys.stderr) if ev == "start" else None))
    print(rp.format_summary(out))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 3}[out["status"]]


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="themis",
        description="THEMIS - Trust and Evidence-based Heuristic Method for "
                    "Investigative Source Assessment. Audits public cryptocurrency "
                    "attribution labels: provenance, independence, currency, and "
                    "their effect on a forensic figure.")
    p.add_argument("--observations", help="full observations.csv(.gz) from scripts/build_corpus.py; "
                                          "omit to use the reference corpus in the data directory")
    p.add_argument("--data-dir", metavar="DIR",
                   help="directory holding the reference corpus and its task inputs (default: "
                        "$THEMIS_DATA_DIR, else demo_data/ in a development checkout - a release "
                        "does not ship it, see THIRD_PARTY_DATA.md)")
    p.add_argument("--as-of", metavar="YYYY-MM-DD",
                   help="the date staleness is judged against (default: the bundled sample's "
                        "declared analysis date; for --observations, the newest revision date in "
                        "the claims - pass the real retrieval date here)")
    p.add_argument("--json", help="also write the result to this JSON file")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audit", help="corroboration, agreement and independence").set_defaults(fn=cmd_audit)
    sub.add_parser("drift", help="the four trust conditions").set_defaults(fn=cmd_drift)
    sub.add_parser("taxonomy", help="print the classification rules").set_defaults(fn=cmd_taxonomy)

    e = sub.add_parser("explain", help="trace one address")
    e.add_argument("address")
    e.set_defaults(fn=cmd_explain)

    b = sub.add_parser("bootstrap", help="cluster-bootstrap confidence intervals")
    # default=None defers to config/thresholds.yml's bootstrap.iterations - a
    # hardcoded default here silently overrode the config on the CLI path
    b.add_argument("-n", type=int, default=None,
                   help="resamples (default: bootstrap.iterations in config/thresholds.yml)")
    b.add_argument("--upper", action="store_true", help="unresolved records independent")
    b.add_argument("--both", action="store_true", help="report both lineage bounds")
    b.add_argument("--fast", action="store_true",
                   help="numpy RNG for large K (requires numpy); exploratory only, "
                        "not the canonical/paper path")
    b.set_defaults(fn=cmd_bootstrap)

    sub.add_parser("anchors", help="provenance-aware validation against the open anchor set").set_defaults(fn=cmd_anchors)

    sub.add_parser("sources", help="print the source registry").set_defaults(fn=cmd_sources)

    r = sub.add_parser("report", help="canonical single-object report + audit trail")
    r.add_argument("--bootstrap", action="store_true", help="include cluster-bootstrap intervals")
    r.add_argument("--anchors", action="store_true", help="include anchor validation (Sec 4.3/4.7)")
    r.add_argument("--out", help="write the report JSON here (same as --json)")
    r.set_defaults(fn=cmd_report)

    ig = sub.add_parser("ingest", help="STEP 23: audit a previously unseen CSV")
    ig.add_argument("file", help="path to the CSV (or .csv.gz) to ingest")
    ig.add_argument("--source-id", default="uploaded", help="id to tag this dataset's claims with")
    ig.add_argument("--reference", help="compare against this observations file instead of the "
                                        "bundled sample")
    ig.add_argument("--no-reference", action="store_true", help="skip cross-source comparison entirely")
    ig.add_argument("--map", action="append",
                    help="override a schema role, e.g. --map address=btc_addr or "
                         "--map ts_attribution_last_updated=updated (repeatable); the pre-flight still validates it")
    ig.add_argument("--chain", help="the chain the identifiers belong to (required when it cannot be detected)")
    ig.add_argument("--confirm", action="store_true",
                    help="record that you reviewed low-confidence mappings (from `themis preflight`)")
    ig.add_argument("--preflight-json", help="write the pre-flight record (preflight.json) here")
    ig.set_defaults(fn=cmd_ingest)

    pfc = sub.add_parser("preflight", help="inspect a CSV or a SQLite table: column meanings, chain, blockers")
    pfc.add_argument("file", help="a .csv/.csv.gz file or a .db/.sqlite/.sqlite3 database")
    pfc.add_argument("--table", help="the SQLite table to pre-flight (omit to list tables)")
    pfc.add_argument("--map", action="append", help="role=column override (repeatable)")
    pfc.add_argument("--chain", help="the chain the identifiers belong to")
    pfc.add_argument("--confirm", action="store_true", help="record that low-confidence mappings were reviewed")
    pfc.set_defaults(fn=cmd_preflight)

    rp = sub.add_parser("reproduce-paper", help="run every paper experiment, write results/reproduction/<run>, "
                                                "and compare with the manuscript")
    rp.add_argument("--bootstrap", choices=["none", "lower", "both"], default="both",
                    help="provenance-bound bootstrap bounds to regenerate (default: both)")
    rp.add_argument("--results-dir", help="root for reproduction/ (default: $THEMIS_RESULTS_DIR or ./results)")
    rp.add_argument("--run-id")
    rp.add_argument("--claims", help="paper manifest (default: paper/paper_claims.yml)")
    rp.add_argument("--paper", help="the final PDF, for the secondary manuscript check")
    rp.add_argument("--no-rq1", action="store_true", help="skip running the RQ1 taxonomy tests")
    rp.add_argument("--quiet", action="store_true")
    rp.set_defaults(fn=cmd_reproduce_paper)

    vp = sub.add_parser("verify-paper", help="compare generated metrics with paper/paper_claims.yml and the PDF")
    vp.add_argument("--claims", help="paper manifest (default: paper/paper_claims.yml)")
    vp.add_argument("--paper", help="the final PDF text is checked against the manifest too")
    vp.add_argument("--metrics", help="verify a saved paper_metrics.json instead of recomputing")
    vp.add_argument("--with-bootstrap", action="store_true", help="also regenerate the bootstrap diagnostics")
    vp.add_argument("--claim-map", metavar="FILE", help="write PAPER_CLAIM_MAP.md here")
    vp.set_defaults(fn=cmd_verify_paper)

    fg = sub.add_parser("figures", help="regenerate Figures 1 and 2 (data + PNG/PDF/SVG) from generated results")
    fg.add_argument("--out-dir")
    fg.add_argument("--from-data", metavar="DIR", help="redraw from fig*_data.json in DIR; needs no corpus")
    fg.set_defaults(fn=cmd_figures)

    rx = sub.add_parser("reproduce", help="run one paper experiment on its own")
    rx.add_argument("experiment", choices=sorted(_EXPERIMENTS))
    rx.add_argument("--out-dir")
    rx.set_defaults(fn=cmd_reproduce)

    a = p.parse_args(argv)
    if a.data_dir:
        os.environ["THEMIS_DATA_DIR"] = a.data_dir      # corpus.data_dir() reads it at call time
    try:
        return a.fn(a) or 0
    except FileNotFoundError as e:
        # a missing corpus/anchor/revenue file is an operator problem with a known fix, not a crash
        print(f"themis: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
