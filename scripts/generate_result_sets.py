"""Phase 4 - generate one result set from the bundled corpus.

    python scripts/generate_result_sets.py --mode frozen    --out DIR
    python scripts/generate_result_sets.py --mode candidate --out DIR

mode=frozen     the bundled snapshot exactly as shipped (canon pre-baked by the
                paper's pipeline) - what the current code reproduces.
mode=candidate  the same snapshot with every claim whose frozen canon is
                `unknown` re-derived through the current taxonomy + structured-
                label parser; claims with a known canon are NOT touched (their
                canon came from source-specific adapters, not from aliases).
Writes one JSON per analysis plus metrics.json, a flat key->value map that the
reconciliation and verification tables read.
"""
import argparse, collections, json, pathlib, datetime, hashlib
from themis import corpus as C, analysis, taxonomy, provenance, report, config_io

ap = argparse.ArgumentParser(); ap.add_argument("--mode", choices=["frozen", "candidate"], required=True)
ap.add_argument("--out", required=True); args = ap.parse_args()
out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
K = C.Corpus.demo()

recanon = collections.Counter(); recanon_ex = collections.Counter()
if args.mode == "candidate":
    for c in K.claims:
        if c["canon"] == "unknown":
            n = taxonomy.canonicalize_category(c["raw_label"])
            if n:
                recanon[(c["source"], n)] += 1; recanon_ex[(c["source"], c["raw_label"], n)] += 1
                c["canon"], c["polarity"] = n, taxonomy.POLARITY[n]

m = {}                      # flat metrics
def put(k, v): m[k] = v
def dump(name, obj): json.dump(obj, open(out / f"{name}.json", "w"), indent=1, default=str)

man = K.manifest["full_corpus"]
# ---- corpus
put("corpus.claims", K.n_claims); put("corpus.addresses", K.n_addresses)
put("corpus.sources", len(man["per_source"]))
for s, v in man["per_source"].items():
    put(f"source.{s}.addresses", v["addresses"]); put(f"source.{s}.claims", v["claims"])
put("corpus.roots_total", man["roots_total"]); put("corpus.roots_identified", man["roots_identified"])
put("corpus.roots_unresolved", man["roots_total"] - man["roots_identified"])
put("corpus.provenance_families_in_sample", len({c["prov_family"] for c in K.claims}))
put("corpus.sample.claims", len(K.claims)); put("corpus.sample.addresses", len(K.by_addr))
tiers = collections.defaultdict(collections.Counter)
for c in K.claims: tiers[c["source"]][taxonomy.tier_of(c)] += 1
dump("tiers_by_source", tiers)
dump("corpus_summary", dict(claims=K.n_claims, addresses=K.n_addresses, per_source=man["per_source"],
     roots_total=man["roots_total"], roots_identified=man["roots_identified"], sample=K.manifest["sample"],
     sample_claims_by_source=collections.Counter(c["source"] for c in K.claims)))
# ---- corroboration / agreement
ag = analysis.agreement(K); dump("agreement", ag)
put("corro.single_dataset", ag["single_source"]); put("corro.multi_dataset", ag["n_multi_source"])
put("corro.single_share", ag["single_source"] / K.n_addresses); put("corro.multi_share", ag["multi_source_rate"])
spa = ag["sources_per_address"]
for k, v in spa.items(): put(f"corro.sources_per_address.{k}", v)
put("corro.sources_per_address.5plus", sum(v for k, v in spa.items() if int(k) >= 5))
for k in taxonomy.OUTCOMES:
    put(f"agree.{k}.n", ag["outcomes"][k]["n"]); put(f"agree.{k}.share", ag["outcomes"][k]["share"])
put("agree.total", ag["n_multi_source"])
for t in ag["top_polarity_conflicts"][:5]:
    put(f"conflict.{t['source_a']}:{t['label_a']}|{t['source_b']}:{t['label_b']}", t["n"])
# ---- overlap / containment (exact on the sample: every multi-dataset address is in it)
sa = K.src_addr; ov = {}
srcs = sorted(sa)
for i, a in enumerate(srcs):
    for b in srcs[i + 1:]:
        n = len(sa[a] & sa[b])
        if n: ov[f"{a}&{b}"] = n; put(f"overlap.{a}&{b}", n)
dump("overlap", ov)
full = {s: v["addresses"] for s, v in man["per_source"].items()}
put("overlap.ellipticpp_share", len(sa["ellipticpp"] & sa["schnoering"]) / full["ellipticpp"])
put("overlap.ellipticpp_any_share_max", max(len(sa["ellipticpp"] & sa[o]) for o in srcs if o != "ellipticpp") / full["ellipticpp"])
elp_any = len(sa["ellipticpp"] & set().union(*[sa[o] for o in srcs if o != "ellipticpp"])) / full["ellipticpp"]
put("overlap.ellipticpp_share_with_any_other", elp_any)
for o in ("rodwald_ransom", "tagpack", "schnoering"):
    put(f"containment.ransomwhere_in_{o}", len(sa["ransomwhere"] & sa[o]) / len(sa["ransomwhere"]))
# ---- kappa
kp = analysis.cohen_kappa(K); dump("kappa", kp)
put("kappa.n_pairs", kp["n_pairs"]); put("kappa.n_undefined", kp["n_undefined"]); put("kappa.n_zero", kp["n_zero"])
put("kappa.n_substantial", len(kp["substantial"]))
for r in kp["pairs"]:
    k = f"kappa.{r['source_a']}-{r['source_b']}"
    put(k + ".n", r["n"]); put(k + ".raw", r["percent_agreement"]); put(k + ".kappa", r["cohen_kappa"])
    put(k + ".n_interpretable", r["n_interpretable"]); put(k + ".raw_interpretable", r["percent_agreement_interpretable"])
    put(k + ".kappa_interpretable", r["cohen_kappa_interpretable"]); put(k + ".n_both_unknown", r["n_both_unknown"])
# ---- independence / circularity
ind = analysis.independence(K); dump("independence", ind)
put("indep.unresolved_addresses", ind["unresolved_addresses"]); put("indep.unresolved_share", ind["unresolved_addr_share"])
for r in ind["root_concentration"][:3]:
    put(f"indep.root_share.{r['root']}", r["share"])
d = ind["field_decodes"][0]
put("decode.clean_split", d["clean_split"]); put("decode.inherited_addresses", d["inherited_addresses"])
for g, r in d["groups"].items(): put(f"decode.group.{g}", r["n"]); put(f"decode.group.{g}.verdict", r["verdict"])
put("decode.n_code_strings", len(d["groups"]))
put("decode.inherited_group_sum", sum(r["n"] for g, r in d["groups"].items() if r["verdict"] == "inherited"))
put("circ.rodwald_ransom_in_ransomwhere", len(sa["rodwald_ransom"] & sa["ransomwhere"]))
put("circ.share_of_rodwald_ransom", len(sa["rodwald_ransom"] & sa["ransomwhere"]) / len(sa["rodwald_ransom"]))
put("circ.share_of_ransomwhere", len(sa["rodwald_ransom"] & sa["ransomwhere"]) / len(sa["ransomwhere"]))
nr = ind["naming_residues"][0]; put("residue.attributed", nr["attributed"]); put("residue.total", nr["total"]); put("residue.share", nr["share"])
for k, v in nr["by_root"].items(): put(f"residue.{k}", v)
mp = ind["notable_root_propagation"][0]; put("montreal.seed", mp["size"])
for k, v in mp["propagation"].items(): put(f"montreal.{k}", v); put(f"montreal.{k}.share", v / mp["size"])
schn = collections.Counter(c["subcat"] for c in K.claims if c["source"] == "schnoering")
put("schnoering.share_bitcointalk", sum(v for k, v in schn.items() if "bitcointalk" in k.lower()) / sum(schn.values()))
put("schnoering.share_ofac", schn.get("SDN", 0) / sum(schn.values()))
put("tagpack.share_graphsense_core_root_of_all_claims", man["root_claims"]["tagpack_GraphSense Core Team"] / K.n_claims)
# circular addresses: apparent multi-dataset corroboration with a shared resolved root
circ = sum(1 for a in K.multi_source_addresses() if provenance.address_independence(K.by_addr[a])["circular"])
put("circ.multi_dataset_addresses_flagged_circular", circ)
# ---- freshness (corpus-wide figure needs the full corpus; report what the manifest + Table-1 revision declarations give)
SD = K.snapshot_date   # a property that scans every claim - evaluate once, not per claim
fr = analysis.freshness(K.claims, as_of=SD); dump("freshness_sample", fr)
tp = [c for c in K.claims if c["source"] == "tagpack" and (c["lastmod"] or "").strip()]
put("fresh.tagpack_dated_in_sample", len(tp))
put("fresh.tagpack_dated_older_than_3y_share", sum(1 for c in tp if "stale" in taxonomy.currency_flags(c, today=SD)) / len(tp))
put("fresh.snapshot_date", str(SD))
no_rev = sum(v["claims"] for s, v in man["per_source"].items() if s in ("ellipticpp", "schnoering", "rodwald_mixers", "rodwald_ransom", "watchyourback"))
put("fresh.no_revision_claims_lower_bound", no_rev); put("fresh.no_revision_share_lower_bound", no_rev / K.n_claims)
# ---- anchors / bootstrap / drift
an = analysis.anchor_validation(K); dump("anchors", an)
put("anchor.total", an["anchors_total"]); put("anchor.usable", an["usable_anchors"]); put("anchor.excluded_self_root", an["excluded_self_root_claims"])
for s, v in an["per_source"].items():
    put(f"anchor.{s}.n", v["n"]); put(f"anchor.{s}.roots", v["independent_roots"]); put(f"anchor.{s}.estimable", v["estimable"])
    if v["n"]:
        put(f"anchor.{s}.exact", v["exact"]); put(f"anchor.{s}.agreement", v["anchor_agreement"])
        put(f"anchor.{s}.ci_low", v["ci_low"]); put(f"anchor.{s}.ci_high", v["ci_high"])
put("anchor.n_estimable_sources", sum(1 for v in an["per_source"].values() if v["estimable"]))
lo = analysis.bootstrap(K); up = analysis.bootstrap(K, upper_bound=True)
dump("bootstrap_lower", lo); dump("bootstrap_upper", up)
for tag, b in (("lower", lo), ("upper", up)):
    put(f"boot.{tag}.clusters", b["n_clusters"])
    for k, v in b["stats"].items(): put(f"boot.{tag}.{k}.point", v["point"]); put(f"boot.{tag}.{k}.ci_low", v["ci_low"]); put(f"boot.{tag}.{k}.ci_high", v["ci_high"])
put("boot.n_boot", lo["n_boot"]); put("boot.seed", lo["seed"]); put("boot.confidence", lo["confidence_level"])
dr = analysis.drift(K); dump("drift", dr)
for L, c in dr["conditions"].items():
    put(f"drift.{L}.observations", c["observations"]); put(f"drift.{L}.addresses", c["addresses"]); put(f"drift.{L}.usd", c["usd"])
    put(f"drift.{L}.ratio_vs_B", c["ratio_vs_B"]); put(f"drift.{L}.coverage_vs_B", c["coverage_vs_B"])
put("drift.shared_addresses", dr["shared_addresses"]); put("drift.spread_B_over_D", dr["spread_B_over_D"]); put("drift.spread_A_over_D", dr["spread_A_over_D"])
c = dr["conditions"]
put("drift.A_inflation_vs_B", c["A"]["usd"] / c["B"]["usd"] - 1)
put("drift.C_addresses_removed_share", 1 - c["C"]["addresses"] / c["B"]["addresses"])
put("drift.C_value_removed_share", 1 - c["C"]["usd"] / c["B"]["usd"])
# ---- what condition D is made of (Phase 2A)
rev = K.revenue_rows(); anchors = K.verified_anchors()
best = {}
for r in rev:
    a, u = r["address"], float(r["usd"] or 0)
    if a not in best or u > best[a]: best[a] = u
dset = {a for a in best if a in anchors}
tpconf = collections.Counter()
mont = 0
for a in dset:
    confs = {x["subcat"] for x in K.by_addr.get(a, []) if x["source"] == "tagpack"}
    tpconf["forensic" if "forensic" in confs else "other/none"] += 1
    if any(x["root"] == "montreal_paquet_clouston_2019" for x in K.by_addr.get(a, [])): mont += 1
put("D.addresses", len(dset)); put("D.with_tagpack_forensic", tpconf["forensic"])
put("D.with_montreal_rooted_claim", mont); put("D.share_with_montreal_rooted_claim", mont / len(dset))
put("D.wyb_ransomware_only_addresses", len({a for a in dset if any(x["source"] == "watchyourback" and x["raw_label"].split(":")[0] == "ransomware" for x in K.by_addr.get(a, []))}))
# ---- structured-label impact / WYB provenance impact
if args.mode == "candidate":
    dump("structured_label_impact", dict(
        claims_rederived=sum(recanon.values()), by_source_and_category={f"{k[0]}->{k[1]}": v for k, v in recanon.items()},
        examples=[dict(source=k[0], raw_label=k[1], canon=k[2], n=v) for k, v in recanon_ex.most_common()]))
    put("structured.claims_rederived", sum(recanon.values()))
wyb = [x for x in K.claims if x["source"] == "watchyourback" and x["root"] == "ofac_sdn"]
before = after = 0
for x in wyb:
    cl = K.by_addr[x["address"]]
    old = [dict(y, root=("watchyourback_manual" if y is x else y["root"])) for y in cl]
    if provenance.address_independence(old)["circular"]: before += 1
    if provenance.address_independence(cl)["circular"]: after += 1
put("wyb.rerooted_claims", len(wyb)); put("wyb.rerooted_addresses_circular_before", before); put("wyb.rerooted_addresses_circular_after", after)
put("meta.mode", args.mode); put("meta.config_hash", report._hash_config())
dump("metrics", dict(sorted(m.items())))
print(args.mode, "->", out, len(m), "metrics")
