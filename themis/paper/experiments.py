"""The paper's experiments, as functions of a corpus.

Each function turns a Corpus (and the existing analysis results) into one
generated result. Nothing here reads the paper's manifest or knows what the paper
says: the verifier compares these results with the manuscript's declared values
afterwards, never the other way round. The methodology itself is not
re-implemented - agreement, independence, drift and anchor validation are the
canonical functions in themis.analysis / themis.provenance; this module only
selects and arranges what they return so a table, a figure and the verifier all
read one object.
"""
from __future__ import annotations
import collections, datetime, hashlib, itertools

from .. import analysis, config_io, provenance
from ..corpus import data_dir

_cfg = config_io.load()

LIVE, FROZEN, SAMPLE_OBSERVED, UNAVAILABLE = "LIVE", "FROZEN_MANIFEST", "SAMPLE_OBSERVED", "UNAVAILABLE"


class Scope:
    """What the loaded corpus can reproduce live.

    A full build (`Corpus.full`) reproduces everything. The bundled reference
    sample holds every claim of its `complete_sources` and every multi-dataset
    address, so joins between datasets are exact, but a total that needs a
    sampled source's full size, or the whole corpus, is only a figure carried in
    the sample's manifest - a frozen artifact, not a recomputation.
    """

    def __init__(self, corpus):
        self.full = bool(corpus.full)
        s = corpus.manifest.get("sample", {})
        self.complete = set(corpus.src_addr) if self.full else set(s.get("complete_sources", []))
        self.sampled = set() if self.full else set(s.get("sampled_sources", []))
        self.has_manifest = bool(corpus.manifest.get("full_corpus"))

    @property
    def kind(self) -> str:
        return "FULL_CORPUS" if self.full else "BUNDLED_SAMPLE"

    def joins(self) -> str:
        """Cross-dataset joins: exact on the sample (every multi-dataset address is in it)."""
        return LIVE

    def source_total(self, *sources) -> str:
        if all(self.full or s in self.complete for s in sources):
            return LIVE
        return FROZEN if self.has_manifest else UNAVAILABLE

    def corpus_total(self) -> str:
        return LIVE if self.full else (FROZEN if self.has_manifest else UNAVAILABLE)

    def all_claims(self) -> str:
        """A statistic over every claim: a sample of the claims is not the corpus."""
        return LIVE if self.full else SAMPLE_OBSERVED


def source_claim_counts(corpus) -> dict:
    if corpus.full:
        return dict(collections.Counter(c["source"] for c in corpus.claims))
    per = corpus.manifest.get("full_corpus", {}).get("per_source", {})
    return {s: v["claims"] for s, v in per.items()}


class AnalysisBundle:
    """One corpus, each canonical analysis computed once and shared by every
    table, figure, metric and verifier that needs it."""

    def __init__(self, corpus, as_of=None, bootstrap: str = "both"):
        self.corpus = corpus
        self.scope = Scope(corpus)
        self.as_of = as_of or corpus.snapshot_date
        self.bootstrap_mode = bootstrap          # none | lower | both
        self._c: dict = {}

    def _get(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    @property
    def agreement(self):
        return self._get("agreement", lambda: analysis.agreement(self.corpus))

    @property
    def independence(self):
        return self._get("independence", lambda: analysis.independence(self.corpus))

    @property
    def kappa(self):
        return self._get("kappa", lambda: analysis.cohen_kappa(self.corpus))

    @property
    def drift_full(self):
        """analysis.drift with each policy's eligible claims kept, for the trace."""
        return self._get("drift", lambda: analysis.drift(self.corpus, keep_eligible=True))

    @property
    def drift(self):
        def strip():
            d = dict(self.drift_full)
            d["policies"] = {k: {a: b for a, b in v.items() if a != "_eligible"}
                             for k, v in d["policies"].items()}
            return d
        return self._get("drift_stripped", strip)

    @property
    def anchors(self):
        return self._get("anchors", lambda: analysis.anchor_validation(self.corpus))

    def bootstrap(self, upper: bool):
        return self._get(f"boot{upper}", lambda: analysis.bootstrap(self.corpus, upper_bound=upper))


# ------------------------------------------------------------------ Table 1
def table1(b: AnalysisBundle) -> dict:
    c, sc = b.corpus, b.scope
    sizes, claims_n = c.source_sizes(), source_claim_counts(c)
    by_src = collections.defaultdict(list)
    for x in c.claims:
        by_src[x["source"]].append(x)
    rows = []
    for s, n_addr in sizes.items():
        src_cfg = _cfg.sources.get(s, {})
        rows.append(dict(
            source=s, display_name=src_cfg.get("display_name", s),
            unique_addresses=n_addr, claims=claims_n.get(s),
            # a revision field exists if any of the source's claims carries a date
            revision_field=any((x.get("lastmod") or "").strip() for x in by_src[s]),
            provenance_mode=(src_cfg.get("provenance") or {}).get("mode", "none"),
            basis=sc.source_total(s)))
    cr = c.corpus_roots()
    return dict(rows=rows,
                total=dict(claims=c.n_claims, unique_addresses=c.n_addresses, basis=sc.corpus_total()),
                provenance_roots=dict(total=cr["total"], identified=cr["identified"],
                                      unresolved=None if cr["total"] is None else cr["total"] - cr["identified"],
                                      basis=sc.corpus_total()),
                sources=len(sizes))


# --------------------------------------------------------------- source depth
def source_depth(b: AnalysisBundle) -> dict:
    a = b.agreement
    total = a["n_addresses"]
    spa = a["sources_per_address"]
    buckets = collections.OrderedDict()
    for k in ("1", "2", "3", "4"):
        buckets[k] = spa.get(int(k), 0)
    buckets["5+"] = sum(v for k, v in spa.items() if k >= 5)
    return dict(
        denominator_addresses=total,
        by_dataset_count={k: dict(addresses=v, share=v / total if total else None) for k, v in buckets.items()},
        single_dataset=dict(addresses=a["single_source"], share=a["single_source"] / total if total else None),
        multi_dataset=dict(addresses=a["n_multi_source"], share=a["multi_source_rate"]),
        unit="distinct datasets per normalised address",
        interpretation="NO PUBLIC CROSS-SOURCE CORROBORATION AVAILABLE",
        not_interpreted_as="UNRELIABLE - a single-dataset address is not thereby wrong, only uncorroborated here",
        upper_bound_note="counts datasets, not independent sources; see the provenance experiments")


# --------------------------------------------------------------- overlap matrix
def overlap_matrix(b: AnalysisBundle) -> dict:
    c = b.corpus
    sa, sizes = c.src_addr, c.source_sizes()
    srcs = sorted(sa)
    pairs = []
    for x, y in itertools.combinations(srcs, 2):
        inter = len(sa[x] & sa[y])
        union = sizes[x] + sizes[y] - inter
        pairs.append(dict(source_a=x, source_b=y, intersection=inter,
                          share_of_a=inter / sizes[x] if sizes[x] else None,
                          share_of_b=inter / sizes[y] if sizes[y] else None,
                          jaccard=inter / union if union else None))
    by_src = {}
    for s in srcs:
        rest = set().union(*(sa[o] for o in srcs if o != s))
        covered = len(sa[s] & rest)
        shares = [p["intersection"] / sizes[s] for p in pairs
                  if s in (p["source_a"], p["source_b"]) and sizes[s]]
        by_src[s] = dict(size=sizes[s], addresses_in_any_other_source=covered,
                         share_in_any_other_source=covered / sizes[s] if sizes[s] else None,
                         share_with_no_public_cross_source_check=1 - covered / sizes[s] if sizes[s] else None,
                         max_pairwise_share=max(shares) if shares else None)
    # per-direction rows: a pair reads differently from each side
    directed = [dict(source=p["source_a"], other=p["source_b"], intersection=p["intersection"],
                     share_of_source=p["share_of_a"], share_of_other=p["share_of_b"], jaccard=p["jaccard"])
                for p in pairs] + \
               [dict(source=p["source_b"], other=p["source_a"], intersection=p["intersection"],
                     share_of_source=p["share_of_b"], share_of_other=p["share_of_a"], jaccard=p["jaccard"])
                for p in pairs]
    return dict(pairs=pairs, directed=directed, by_source=by_src, label="COVERAGE",
                not_interpreted_as="CORRECTNESS - overlap says how much of a source another source can check, "
                                   "not whether either is right")


# -------------------------------------------------- Rodwald provenance decode
def rodwald_containment(b: AnalysisBundle) -> dict:
    """Every (dataset, undocumented provenance field, candidate upstream source)
    discovered from source config, decoded by containment. Nothing names the
    dataset, the field or the candidate: they come from `discover_decodes`."""
    c = b.corpus
    out = []
    for fd in b.independence["field_decodes"]:
        ds, cand = fd["dataset"], fd["candidate"]
        thr = _cfg.thresholds
        inherited_share = thr.get("containment_inherited_share", 0.999)
        groups = []
        for code, g in fd["groups"].items():
            wellformed = code.isalpha()
            inside = wellformed and g["share_in_candidate"] > inherited_share
            groups.append(dict(code=code or "(blank)", size=g["n"], overlap_with_candidate=g["overlap"],
                               containment=g["share_in_candidate"], verdict=g["verdict"],
                               well_formed=wellformed, wholly_inside_candidate=inside,
                               examples=g["examples"]))
        inside_groups = [g for g in groups if g["wholly_inside_candidate"]]
        outside_groups = [g for g in groups if not g["wholly_inside_candidate"]]
        shared = len(c.src_addr[ds] & c.src_addr[cand])
        n_ds, n_cand = c.source_sizes().get(ds), c.source_sizes().get(cand)
        # the letter(s) every inherited code has and no independent code has
        inh = [set(g["code"]) for g in groups if g["verdict"] == "inherited"]
        ind = [set(g["code"]) for g in groups if g["verdict"] == "independent"]
        letters = sorted(set.intersection(*inh) - set().union(*ind)) if inh else []
        out.append(dict(
            dataset=ds, field=fd["field"], candidate=cand, clean_split=fd["clean_split"],
            decoded_letters=letters, groups=groups,
            well_formed_inside_candidate=dict(addresses=sum(g["overlap_with_candidate"] for g in inside_groups),
                                              groups=[g["code"] for g in inside_groups]),
            outside_candidate=dict(addresses=sum(g["size"] for g in outside_groups),
                                   overlap_with_candidate=sum(g["overlap_with_candidate"] for g in outside_groups),
                                   malformed_groups_overlapping=[g["code"] for g in outside_groups
                                                                 if not g["well_formed"] and g["overlap_with_candidate"]]),
            shared_addresses=shared,
            share_of_dataset=shared / n_ds if n_ds else None,
            share_of_candidate=shared / n_cand if n_cand else None,
            basis=b.scope.source_total(ds, cand),
            function="themis.provenance.decode_field"))
    return dict(decodes=out)


# ----------------------------------------------------------- Montreal recurrence
def montreal_recurrence(b: AnalysisBundle) -> dict:
    """How far each configured reference root's address list reappears in the
    other datasets (config/notable_roots.yml names the seed; nothing here does)."""
    out = []
    for p in b.independence["notable_root_propagation"]:
        size = p["size"]
        out.append(dict(root=p["root"], label=p["label"], seed_addresses=size,
                        recurrence=[dict(source=s, addresses=n, share=n / size if size else None)
                                    for s, n in sorted(p["propagation"].items(), key=lambda kv: -kv[1])],
                        basis=b.scope.joins(), function="themis.provenance.root_propagation"))
    return dict(roots=out, naming_residue=b.independence["naming_residues"])


# ---------------------------------------------------------------------- currency
def currency(b: AnalysisBundle) -> dict:
    c = b.corpus
    as_of = b.as_of
    by_src = collections.defaultdict(list)
    for x in c.claims:
        by_src[x["source"]].append(x)
    per = {}
    for s, cl in by_src.items():
        f = analysis.freshness(cl, as_of=as_of)
        dated = f["current"] + f["stale"]
        per[s] = dict(claims=f["n_claims"], with_revision=dated, without_revision=f["currency_unknown"],
                      stale=f["stale"], stale_share_of_dated=f["stale"] / dated if dated else None)
    tot = analysis.freshness(c.claims, as_of=as_of)
    return dict(
        analysis_as_of_date=str(as_of) if as_of else None,
        clock="declared analysis date, never the wall clock",
        staleness_years=_cfg.thresholds.get("staleness_years"),
        claims_analysed=tot["n_claims"],
        with_revision=tot["current"] + tot["stale"],
        without_revision=tot["currency_unknown"],
        without_revision_share=tot["currency_unknown_share"],
        by_source=per,
        scope=b.scope.kind,
        interpretation="METADATA LIMITATION - a claim with no revision field is currency-unknown, "
                       "not stale, and neither is evidence that a label is false")


# ------------------------------------------------------- unresolved provenance
def unresolved_provenance(b: AnalysisBundle) -> dict:
    c, sc = b.corpus, b.scope
    cr = c.corpus_roots()
    total_claims = sum(cr["root_claims"].values()) or None
    roots = [dict(root=r, claims=n, share_of_claims=n / total_claims if total_claims else None,
                  unresolved=provenance.is_unresolved(r))
             for r, n in sorted(cr["root_claims"].items(), key=lambda kv: -kv[1])]
    # per-source root shares, over addresses, for sources the loaded claims cover completely
    sizes = c.source_sizes()
    within = {}
    for s in sorted(c.src_addr):
        if not (sc.full or s in sc.complete):
            continue
        ra = collections.defaultdict(set)
        for x in c.claims:
            if x["source"] == s:
                ra[x["root"]].add(x["address"])
        within[s] = {r: dict(addresses=len(v), share=len(v) / sizes[s])
                     for r, v in sorted(ra.items(), key=lambda kv: -len(kv[1]))}
    return dict(
        addresses=cr["unresolved_addresses"], share=cr["unresolved_addr_share"],
        basis=sc.corpus_total(),
        roots=dict(total=cr["total"], identified=cr["identified"]),
        root_concentration=roots, within_source=within,
        treatment=dict(default="unresolved provenance stays unknown: never one shared root, never independent roots",
                       lower_independence="coarse assumption: unresolved blocks pooled",
                       upper_independence="fine assumption: each unresolved record independent"),
        function="themis.corpus.Corpus.corpus_roots")


# --------------------------------------------------------------- Table 2 / drift
def _pct_change(new, old):
    return new / old - 1 if old else None


def table2(b: AnalysisBundle) -> dict:
    d = b.drift
    conds = d["conditions"]
    rows = [dict(condition=k, label=v["label"], observations=v["observations"], addresses=v["addresses"],
                 revenue_usd=v["usd"], ratio_vs_B=v["ratio_vs_B"], coverage_vs_B=v["coverage_vs_B"])
            for k, v in conds.items()]
    A, B, C, D = (conds[k] for k in "ABCD")
    return dict(
        rows=rows,
        derived=dict(
            naive_inflation_vs_B=_pct_change(A["usd"], B["usd"]),
            addresses_removed_by_collapse=1 - C["addresses"] / B["addresses"] if B["addresses"] else None,
            value_removed_by_collapse=1 - C["usd"] / B["usd"] if B["usd"] else None,
            spread_B_over_D=d["spread_B_over_D"], spread_A_over_D=d["spread_A_over_D"],
            double_counted_addresses=d["shared_addresses"]),
        note="D retains a fraction of the addresses, so its figure is a lower bound at low "
             "coverage, not a corrected estimate",
        function="themis.analysis.drift")


# ------------------------------------------------------------- Condition D trace
def condition_d_trace(b: AnalysisBundle) -> dict:
    """Why each address in the highest-declared-confidence condition is eligible.
    The condition is the policy `policy_of_condition['D']`; the criteria it is
    declared to rest on are read from config/trust_rules.yml."""
    c = b.corpus
    d = b.drift_full
    pname = d["policy_of_condition"]["D"]
    policy_cfg = _cfg.trust_rules["policies"][pname]
    elig = d["policies"][pname]["_eligible"]
    retained = {x["address"] for x in elig}
    criteria = policy_cfg.get("declared_confidence_criteria", [])

    def meets(cl, crit):
        return cl["source"] == crit["source"] and str(cl.get(crit["field"], "")) == str(crit["equals"])

    crit_rows, matched_any = [], set()
    for crit in criteria:
        hits = {a for a in retained if any(meets(cl, crit) for cl in c.by_addr.get(a, []))}
        matched_any |= hits
        # the source's own vocabulary, kept apart from THEMIS evidence tiers
        native = collections.Counter(str(cl.get(crit["field"], "")) or "(blank)"
                                     for a in retained for cl in c.by_addr.get(a, [])
                                     if cl["source"] == crit["source"])
        crit_rows.append(dict(source=crit["source"], field=crit["field"], equals=crit["equals"],
                              meaning=crit.get("meaning"), addresses_meeting=len(hits),
                              share_of_retained=len(hits) / len(retained) if retained else None,
                              source_native_values_at_retained_addresses=dict(native.most_common(8))))

    root_conc = []
    for n in _cfg.notable_roots:
        carrying = sum(1 for a in retained if any(cl["root"] == n["root"] for cl in c.by_addr.get(a, [])))
        root_conc.append(dict(root=n["root"], label=n.get("label", n["root"]), addresses=carrying,
                              share_of_retained=carrying / len(retained) if retained else None))
    top_roots = collections.Counter(r for a in retained for r in {cl["root"] for cl in c.by_addr.get(a, [])})

    anchors_path = data_dir() / "verified_anchors.txt.gz"
    anchor_hash = hashlib.sha256(anchors_path.read_bytes()).hexdigest() if anchors_path.is_file() else None
    from ..trust import predicates
    rules = [dict(predicate=(p if isinstance(p, str) else next(iter(p))),
                  description=(predicates.REGISTRY[p if isinstance(p, str) else next(iter(p))].__doc__ or "")
                  .strip().split("\n\n")[0].replace("\n", " ")) for p in policy_cfg.get("eligibility", [])]
    top = sorted(({c_["address"]: c_["value_usd"] for c_ in elig}).items(), key=lambda kv: -kv[1])[:10]
    cond = d["conditions"]["D"]
    return dict(
        condition="D", policy=pname, label=policy_cfg.get("label"),
        eligibility_rule=rules,
        anchor_set=dict(file="verified_anchors.txt.gz", sha256=anchor_hash,
                        origin="assembled outside THEMIS; membership is not derived from the claims being scored"),
        retained_addresses=len(retained), observations=cond["observations"],
        coverage_vs_B=cond["coverage_vs_B"], revenue_usd=cond["usd"],
        declared_confidence_criteria=crit_rows,
        addresses_meeting_any_criterion=len(matched_any),
        addresses_meeting_no_criterion=len(retained - matched_any),
        provenance_concentration=root_conc,
        most_common_roots_at_retained_addresses=[dict(root=r, addresses=n) for r, n in top_roots.most_common(5)],
        top_addresses_by_revenue=[dict(address=a, usd=v) for a, v in top],
        interpretation="HIGHEST DECLARED CONFIDENCE: source-native declarations, not independently re-verified",
        not_interpreted_as="verified ground truth, or as GraphSense forensic = THEMIS VERIFIED; source-native "
                           "confidence ids are kept apart from THEMIS evidence tiers",
        function="themis.trust.predicates.anchor_membership via themis.analysis.drift")


# ------------------------------------------------------------------------ anchors
def anchors(b: AnalysisBundle) -> dict:
    r = b.anchors
    sizes = b.corpus.source_sizes()
    max_w = _cfg.thresholds.get("anchor_robust_max_ci_width", 0.2)
    reasons = []
    for s in sorted(sizes):
        v = r["per_source"].get(s)
        if v is None:
            reasons.append(dict(source=s, reason="never observed on a usable anchor"))
        elif not v["estimable"]:
            reasons.append(dict(source=s, reason=v["not_estimable_reason"]))
        elif v["ci_high"] - v["ci_low"] > max_w:
            reasons.append(dict(source=s, reason=f"interval [{v['ci_low']:.3f}, {v['ci_high']:.3f}] wider than "
                                                 f"{max_w:.2f} (anchor_robust_max_ci_width)"))
    gt_roots = sorted({root for _, root in b.corpus.ground_truth().values()})
    return dict(
        label="AGREEMENT WITH OPEN ANCHOR SET",
        not_interpreted_as="accuracy of a source",
        anchor_addresses=r["anchors_total"], usable_independent_anchors=r["usable_anchors"],
        same_root_exclusions=r["excluded_self_root_claims"],
        reference_roots=gt_roots, n_reference_roots=len(gt_roots),
        source_coverage={s: dict(n=v["n"]) for s, v in r["per_source"].items()},
        independent_provenance_roots=r["independent_provenance_roots"],
        agreement_outcomes=r["outcome_totals"],
        per_source={s: dict(n=v["n"], agreement=v["anchor_agreement"], independent_roots=v["independent_roots"],
                            ci_low=v["ci_low"], ci_high=v["ci_high"], estimable=v["estimable"],
                            not_estimable_reason=v["not_estimable_reason"]) for s, v in r["per_source"].items()},
        confidence_level=r["confidence_level"],
        source_accuracy_robustly_estimable=not reasons,
        not_robustly_estimable_because=reasons,
        limitations=r["limitations"],
        function="themis.analysis.anchor_validation")


# --------------------------------------------------------------- diagnostics
def diagnostics(b: AnalysisBundle) -> dict:
    """Taxonomy-sensitive agreement: regenerated, never a headline claim."""
    a, k = b.agreement, b.kappa
    return dict(label="DIAGNOSTIC / TAXONOMY-SENSITIVE",
                agreement_outcomes=a["outcomes"], n_multi_dataset=a["n_multi_source"],
                top_polarity_conflicts=a["top_polarity_conflicts"],
                kappa_pairs=k["n_pairs"], kappa_undefined=k["n_undefined"], kappa_substantial=k["substantial"],
                note="depends on the taxonomy parser; regenerated from the parser when the observation "
                     "table is rebuilt")


def bootstrap_results(b: AnalysisBundle) -> dict:
    out = {}
    if b.bootstrap_mode in ("lower", "both"):
        out["lower"] = b.bootstrap(False)
    if b.bootstrap_mode == "both":
        out["upper"] = b.bootstrap(True)
    for r in out.values():
        r["label"] = "REGENERATED DIAGNOSTIC"
    return out
