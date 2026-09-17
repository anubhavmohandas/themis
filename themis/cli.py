"""THEMIS - Trust and Evidence-based Heuristic Method for Investigative Source
Assessment. Runs the attribution-reliability audit from the command line.
"""
from __future__ import annotations
import argparse, json, sys, textwrap
from .corpus import Corpus
from . import analysis, taxonomy, config_io, report as _report
from .ingest import pipeline as _ingest_pipeline

B, D, DIM = "\033[1m", "\033[0m", "\033[2m"
RED, GRN, YEL = "\033[31m", "\033[32m", "\033[33m"


def _c(s, col):
    return s if not sys.stdout.isatty() else f"{col}{s}{D}"


def load(args) -> Corpus:
    if getattr(args, "observations", None):
        return Corpus.from_file(args.observations)
    return Corpus.demo()


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
        for v, g in list(fd["groups"].items())[:12]:
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
    runs = [False, True] if args.both else [args.upper]
    out = {}
    for ub in runs:
        b = analysis.bootstrap(c, n_boot=args.n, upper_bound=ub)
        name = "upper bound (unresolved independent)" if ub else "lower bound (unresolved pooled)"
        out["upper" if ub else "lower"] = b
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
        deps = src.get("known_dependencies") or []
        if deps:
            print(f"    known dependencies {', '.join(deps)}")
    if args.json:
        json.dump(cfg.sources, open(args.json, "w"), indent=1)
        print(f"\nwritten {args.json}")


def cmd_ingest(args):
    """STEP 23 - new dataset mode: upload a previously unseen CSV."""
    reference = None
    if args.reference:
        reference = Corpus.from_file(args.reference)
    elif not args.no_reference:
        reference = Corpus.demo()

    override = {}
    for spec in args.map or []:
        if "=" not in spec:
            print(f"--map expects role=column, got: {spec}", file=sys.stderr)
            return 1
        role, col = spec.split("=", 1)
        override[role] = col

    r = _ingest_pipeline.ingest(args.file, args.source_id, mapping_override=override or None,
                                reference=reference)
    if r["stopped"]:
        rule("DATASET PRE-FLIGHT")
        print(_c(r["message"], YEL))
        print(f"\n  rows: {r['basic_quality']['rows']:,}   "
              f"columns: {', '.join(r['basic_quality']['columns'])}")
        if args.json:
            json.dump(r, open(args.json, "w"), indent=1)
        return 1

    d = r["detection"]
    rule("DATASET PRE-FLIGHT")
    print(f"  cryptocurrency attribution dataset: {_c(d['confidence'], GRN if d['confidence']=='HIGH' else YEL)}")
    print(f"  detected blockchain:  {d['blockchain']}")
    print(f"  address field:        {d['address_field']}  (sample hit rate "
          f"{100*d['sample_hit_rate']:.1f}% of {d['sampled']} sampled)")
    rule("SCHEMA MAPPING")
    for role, col in r["schema_mapping"].items():
        print(f"  {role:<12}{col or '(none found - override with --map)'}")
    rule("VALIDATION")
    v = r["validation"]
    print(f"  {v['n_input']:,} input rows -> {v['n_valid']:,} valid claims, "
          f"{v['n_rejected']:,} rejected")
    for reason, n in v["rejected_by_reason"].items():
        print(f"    {reason:<20}{n:>8,}")
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


def cmd_report(args):
    """STEP 27 - the canonical, single-object report every other surface
    (JSON export, future UI) reads from."""
    c = load(args)
    res = _report.build_corpus_report(c, include_bootstrap=args.bootstrap,
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


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="themis",
        description="THEMIS - Trust and Evidence-based Heuristic Method for "
                    "Investigative Source Assessment. Audits public Bitcoin "
                    "attribution labels: provenance, independence, currency, and "
                    "their effect on a forensic figure.")
    p.add_argument("--observations", help="full observations.csv(.gz); omit to use "
                                          "the bundled sample")
    p.add_argument("--json", help="also write the result to this JSON file")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audit", help="corroboration, agreement and independence").set_defaults(fn=cmd_audit)
    sub.add_parser("drift", help="the four trust conditions").set_defaults(fn=cmd_drift)
    sub.add_parser("taxonomy", help="print the classification rules").set_defaults(fn=cmd_taxonomy)

    e = sub.add_parser("explain", help="trace one address")
    e.add_argument("address")
    e.set_defaults(fn=cmd_explain)

    b = sub.add_parser("bootstrap", help="cluster-bootstrap confidence intervals")
    b.add_argument("-n", type=int, default=2000)
    b.add_argument("--upper", action="store_true", help="unresolved records independent")
    b.add_argument("--both", action="store_true", help="report both lineage bounds")
    b.set_defaults(fn=cmd_bootstrap)

    sub.add_parser("sources", help="print the source registry").set_defaults(fn=cmd_sources)

    r = sub.add_parser("report", help="canonical single-object report + audit trail")
    r.add_argument("--bootstrap", action="store_true", help="include cluster-bootstrap intervals")
    r.add_argument("--out", help="write the report JSON here (same as --json)")
    r.set_defaults(fn=cmd_report)

    ig = sub.add_parser("ingest", help="STEP 23: audit a previously unseen CSV")
    ig.add_argument("file", help="path to the CSV (or .csv.gz) to ingest")
    ig.add_argument("--source-id", default="uploaded", help="id to tag this dataset's claims with")
    ig.add_argument("--reference", help="compare against this observations file instead of the "
                                        "bundled sample")
    ig.add_argument("--no-reference", action="store_true", help="skip cross-source comparison entirely")
    ig.add_argument("--map", action="append",
                    help="override a schema role, e.g. --map address=btc_addr (repeatable)")
    ig.set_defaults(fn=cmd_ingest)

    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
