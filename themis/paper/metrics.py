"""PaperMetrics: the one machine-readable object every paper-facing surface reads.

Assembled only from the experiment results in themis.paper.experiments (which
themselves call the canonical analysis functions). Nothing is recomputed here:
each metric is a lookup, tagged with the *basis* it rests on -

  LIVE             recomputed from the claims that were loaded
  FROZEN_MANIFEST  a corpus-wide figure carried in the bundled sample's manifest;
                   a frozen artifact, not a reproduction
  SAMPLE_OBSERVED  computed from a sample of the claims, so not the corpus's value
  UNAVAILABLE      not obtainable from the loaded input

so the verifier can refuse to call a frozen or sampled figure a reproduction.
"""
from __future__ import annotations
import dataclasses

from . import experiments as ex
from .experiments import LIVE, FROZEN, SAMPLE_OBSERVED, UNAVAILABLE   # noqa: F401


@dataclasses.dataclass
class PaperMetrics:
    values: dict = dataclasses.field(default_factory=dict)      # flat dotted key -> value
    basis: dict = dataclasses.field(default_factory=dict)       # flat dotted key -> LIVE | ...
    meta: dict = dataclasses.field(default_factory=dict)

    def put(self, key: str, value, basis: str = LIVE) -> None:
        self.values[key] = value
        self.basis[key] = basis if value is not None else UNAVAILABLE

    def tree(self) -> dict:
        out: dict = {}
        for k, v in self.values.items():
            node = out
            *head, last = k.split(".")
            for part in head:
                node = node.setdefault(part, {})
            node[last] = v
        return out

    def to_json(self) -> dict:
        return dict(meta=self.meta, metrics=self.tree(),
                    flat={k: dict(value=v, basis=self.basis[k]) for k, v in self.values.items()})

    @classmethod
    def from_json(cls, d: dict) -> "PaperMetrics":
        m = cls(meta=d.get("meta", {}))
        for k, v in d["flat"].items():
            m.values[k], m.basis[k] = v["value"], v["basis"]
        return m


def build(b: ex.AnalysisBundle) -> PaperMetrics:
    m, sc, c = PaperMetrics(), b.scope, b.corpus
    m.meta = dict(scope=sc.kind, analysis_as_of_date=str(b.as_of) if b.as_of else None,
                  complete_sources=sorted(sc.complete), sampled_sources=sorted(sc.sampled))

    # ---- corpus (Table 1)
    t1 = ex.table1(b)
    m.put("corpus.sources", len(c.src_addr))
    m.put("corpus.claims", t1["total"]["claims"], t1["total"]["basis"])
    m.put("corpus.addresses", t1["total"]["unique_addresses"], t1["total"]["basis"])
    pr = t1["provenance_roots"]
    m.put("corpus.provenance_roots", pr["total"], pr["basis"])
    m.put("corpus.identified_roots", pr["identified"], pr["basis"])
    m.put("corpus.unresolved_roots", pr["unresolved"], pr["basis"])
    m.put("corpus.provenance_descriptors", len({(x["source"], x["prov_family"]) for x in c.claims}),
          sc.all_claims())
    for r in t1["rows"]:
        s = r["source"]
        m.put(f"corpus.per_source.{s}.addresses", r["unique_addresses"], r["basis"])
        m.put(f"corpus.per_source.{s}.claims", r["claims"], r["basis"])
        # a date that exists proves the field exists even in a sample; its absence does not
        m.put(f"corpus.per_source.{s}.revision_field", r["revision_field"],
              LIVE if (r["revision_field"] or r["basis"] == LIVE) else SAMPLE_OBSERVED)

    # ---- coverage (RQ2: corroboration)
    sd = ex.source_depth(b)
    m.put("coverage.single_dataset_addresses", sd["single_dataset"]["addresses"], sc.corpus_total())
    m.put("coverage.single_dataset_share", sd["single_dataset"]["share"], sc.corpus_total())
    m.put("coverage.multi_dataset_addresses", sd["multi_dataset"]["addresses"], sc.joins())
    for k, v in sd["by_dataset_count"].items():
        if k == "1":
            continue
        m.put(f"coverage.multi_dataset_distribution.{k.replace('+', '_plus')}", v["addresses"], sc.joins())
    om = ex.overlap_matrix(b)
    for r in om["directed"]:
        base = f"coverage.overlap.{r['source']}.{r['other']}"
        m.put(f"{base}.intersection", r["intersection"], sc.joins())
        m.put(f"{base}.share_of_source", r["share_of_source"], sc.source_total(r["source"]))
    for s, v in om["by_source"].items():
        m.put(f"coverage.by_source.{s}.max_overlap_share", v["max_pairwise_share"], sc.source_total(s))
        m.put(f"coverage.by_source.{s}.no_cross_source_check_share",
              v["share_with_no_public_cross_source_check"], sc.source_total(s))

    # ---- currency
    cur = ex.currency(b)
    m.put("currency.claims_analysed", cur["claims_analysed"], sc.all_claims())
    m.put("currency.missing_revision_claims", cur["without_revision"], sc.all_claims())
    m.put("currency.missing_revision_share", cur["without_revision_share"], sc.all_claims())
    for s, v in cur["by_source"].items():
        m.put(f"currency.by_source.{s}.stale_share_of_dated", v["stale_share_of_dated"],
              LIVE if sc.full or s in sc.complete else SAMPLE_OBSERVED)

    # ---- circularity
    for d in ex.rodwald_containment(b)["decodes"]:
        base = f"circularity.{d['dataset']}.in.{d['candidate']}"
        m.put(f"{base}.shared_addresses", d["shared_addresses"], d["basis"])
        m.put(f"{base}.share_of_dataset", d["share_of_dataset"], d["basis"])
        m.put(f"{base}.share_of_candidate", d["share_of_candidate"], d["basis"])
        m.put(f"{base}.clean_split", d["clean_split"], d["basis"])
        m.put(f"{base}.well_formed_inside_addresses", d["well_formed_inside_candidate"]["addresses"], d["basis"])
        m.put(f"{base}.outside_addresses", d["outside_candidate"]["addresses"], d["basis"])
        m.put(f"{base}.outside_overlap_addresses", d["outside_candidate"]["overlap_with_candidate"], d["basis"])
        for g in d["groups"]:
            m.put(f"{base}.groups.{g['code']}.size", g["size"], d["basis"])
            m.put(f"{base}.groups.{g['code']}.overlap", g["overlap_with_candidate"], d["basis"])
    for r in b.independence["naming_residues"]:
        base = f"circularity.naming_residue.{r['dataset']}"
        m.put(f"{base}.total", r["total"], sc.source_total(r["dataset"]))
        m.put(f"{base}.attributed", r["attributed"], sc.source_total(r["dataset"]))
        m.put(f"{base}.share", r["share"], sc.source_total(r["dataset"]))
        for root, n in r["by_root"].items():
            m.put(f"{base}.by_root.{root}", n, sc.source_total(r["dataset"]))
    for rt in ex.montreal_recurrence(b)["roots"]:
        base = f"circularity.{rt['root']}"
        m.put(f"{base}.seed_addresses", rt["seed_addresses"], rt["basis"])
        for r in rt["recurrence"]:
            m.put(f"{base}.recurrence.{r['source']}.addresses", r["addresses"], rt["basis"])
            m.put(f"{base}.recurrence.{r['source']}.share", r["share"], rt["basis"])

    # ---- unresolved provenance
    up = ex.unresolved_provenance(b)
    m.put("unresolved_provenance.addresses", up["addresses"], up["basis"])
    m.put("unresolved_provenance.share", up["share"], up["basis"])
    for r in up["root_concentration"]:
        m.put(f"unresolved_provenance.root_share_of_claims.{r['root']}", r["share_of_claims"], up["basis"])
    for s, roots in up["within_source"].items():
        for root, v in roots.items():
            m.put(f"unresolved_provenance.within_source.{s}.{root}.share", v["share"], LIVE)

    # ---- drift (Table 2)
    t2 = ex.table2(b)
    for r in t2["rows"]:
        k = r["condition"]
        m.put(f"drift.{k}.observations", r["observations"])
        m.put(f"drift.{k}.addresses", r["addresses"])
        m.put(f"drift.{k}.revenue", r["revenue_usd"])
        m.put(f"drift.{k}.ratio_vs_B", r["ratio_vs_B"])
        m.put(f"drift.{k}.coverage_vs_B", r["coverage_vs_B"])
    for k, v in t2["derived"].items():
        m.put(f"drift.{k}", v)

    # ---- anchors (limitation, not an accuracy claim)
    an = ex.anchors(b)
    for k in ("anchor_addresses", "usable_independent_anchors", "same_root_exclusions",
              "n_reference_roots", "source_accuracy_robustly_estimable"):
        m.put(f"anchors.{k}", an[k])

    # ---- diagnostics (taxonomy-sensitive; never headline)
    dg = ex.diagnostics(b)
    for k, v in dg["agreement_outcomes"].items():
        m.put(f"diagnostics.agreement.{k}", v["n"])
    for which, r in ex.bootstrap_results(b).items():
        for k, s in r["stats"].items():
            m.put(f"diagnostics.bootstrap.{which}.{k}.point", s["point"])
            m.put(f"diagnostics.bootstrap.{which}.{k}.ci_low", s["ci_low"])
            m.put(f"diagnostics.bootstrap.{which}.{k}.ci_high", s["ci_high"])
    return m
