"""The four analyses: agreement, independence, drift, and the cluster bootstrap."""
from __future__ import annotations
import collections, random, statistics
from . import taxonomy, provenance, config_io
from .trust import policy as trust_policy, drift as trust_drift
from .tasks import ransomware_revenue as _revenue_task

_cfg = config_io.load()


def _sources_per_address(corpus, n_multi):
    d = collections.Counter(len({c["source"] for c in corpus.by_addr[a]})
                            for a in corpus.by_addr)
    d[1] = corpus.n_addresses - n_multi
    return dict(sorted(d.items()))


# --------------------------------------------------------------- E1 agreement
def agreement(corpus) -> dict:
    multi = corpus.multi_source_addresses()
    out = collections.Counter()
    pairs = collections.Counter()
    for a in multi:
        claims = corpus.by_addr[a]
        out[taxonomy.classify_address(claims)] += 1
        lab = {}
        for c in claims:
            if c["canon"] != "unknown":
                lab[c["source"]] = c["canon"]
        srcs = sorted(lab)
        for i, s1 in enumerate(srcs):
            for s2 in srcs[i + 1:]:
                c1, c2 = lab[s1], lab[s2]
                if c1 == c2:
                    continue
                p1 = taxonomy.POLARITY.get(c1, "unknown")
                p2 = taxonomy.POLARITY.get(c2, "unknown")
                if {c1, c2} & taxonomy.GENERIC and p1 == p2:
                    continue
                if p1 != p2:
                    pairs[(s1, c1, s2, c2)] += 1
    total = sum(out.values())
    return dict(
        n_multi_source=total,
        n_addresses=corpus.n_addresses,
        multi_source_rate=total / corpus.n_addresses if corpus.n_addresses else 0.0,
        single_source=corpus.n_addresses - total,
        outcomes={k: dict(n=out.get(k, 0), share=out.get(k, 0) / total if total else 0.0)
                  for k in taxonomy.OUTCOMES},
        top_polarity_conflicts=[dict(source_a=k[0], label_a=k[1], source_b=k[2],
                                     label_b=k[3], n=v)
                                for k, v in pairs.most_common(10)],
        # the 1-dataset bucket is corpus-wide, not sample-scoped: every
        # multi-dataset address is present in the sample, so only the singles
        # are undercounted there and the manifest carries the true total
        sources_per_address=_sources_per_address(corpus, total),
    )


# ------------------------------------------------- chance-corrected agreement
def cohen_kappa(corpus) -> dict:
    """Cohen's kappa for every pair of datasets that share addresses.

    Raw agreement flatters a corpus dominated by one category, so the paper
    reports kappa alongside it. Kappa is undefined when the shared region is
    effectively single-class, which is the common case here; those pairs are
    named rather than silently dropped.
    """
    # one label per (address, dataset): the modal canonical category, matching the
    # overlap counts reported in the containment table. `unknown` is a category
    # here, not a reason to drop the address - excluding it would silently change
    # the comparable set and with it the denominator.
    per = collections.defaultdict(dict)
    tmp = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for a, v in corpus.by_addr.items():
        for c in v:
            tmp[a][c["source"]][c["canon"]] += 1
    for a, d in tmp.items():
        for src, counts in d.items():
            per[a][src] = counts.most_common(1)[0][0]
    srcs = sorted(corpus.src_addr)
    out = []
    for i, s1 in enumerate(srcs):
        for s2 in srcs[i + 1:]:
            pairs = [(l[s1], l[s2]) for l in per.values() if s1 in l and s2 in l]
            n = len(pairs)
            if not n:
                continue
            agree = sum(1 for x, y in pairs if x == y) / n
            m1 = collections.Counter(x for x, _ in pairs)
            m2 = collections.Counter(y for _, y in pairs)
            pe = sum(m1[k] * m2[k] for k in set(m1) | set(m2)) / (n * n)
            if abs(1 - pe) < 1e-12:
                k, note = None, "undefined: shared region is single-class"
            else:
                k, note = (agree - pe) / (1 - pe), None
            out.append(dict(source_a=s1, source_b=s2, n=n,
                            percent_agreement=agree, cohen_kappa=k, note=note))
    out.sort(key=lambda r: -r["n"])
    kappa_threshold = _cfg.thresholds.get("kappa_substantial_threshold", 0.4)
    usable = [r for r in out if r["cohen_kappa"] is not None and r["cohen_kappa"] > kappa_threshold]
    return dict(pairs=out, n_pairs=len(out),
                n_undefined=sum(1 for r in out if r["cohen_kappa"] is None),
                n_zero=sum(1 for r in out if r["cohen_kappa"] is not None
                           and abs(r["cohen_kappa"]) < 1e-9),
                substantial=[dict(pair=f"{r['source_a']}-{r['source_b']}", n=r["n"],
                                  percent_agreement=r["percent_agreement"],
                                  cohen_kappa=r["cohen_kappa"]) for r in usable])


# ------------------------------------------------------------ E2 independence
def independence(corpus) -> dict:
    sa = corpus.src_addr
    cont = provenance.containment(sa)
    top = sorted(cont.items(), key=lambda kv: -kv[1]["share_of_a"])[:12]

    # STEP 8B - every (dataset, field, candidate) worth decoding, discovered
    # from config rather than named here; a source only appears if its
    # decoded root is natively owned by another source present in this corpus.
    decodes = [provenance.decode_field(corpus.claims, d["dataset"], d["field"],
                                       d["candidate"], sa.get(d["candidate"], set()))
               for d in provenance.discover_decodes()]

    # STEP 8C - every naming-residue check a source config declares.
    residues = [provenance.naming_residue(corpus.claims, r["dataset"], r["field"], r["prefix_map"])
                for r in provenance.discover_residue_checks()]

    # STEP 8 - how far each configured reference root's address list
    # propagates into every other source.
    propagations = [dict(root=n["root"], label=n.get("label", n["root"]),
                         **provenance.root_propagation(corpus.claims, sa, n["seed_source"],
                                                       n["seed_field"], n["seed_value"]))
                    for n in _cfg.notable_roots]

    cr = corpus.corpus_roots()
    limit = _cfg.thresholds.get("root_concentration_limit", 8)
    roots = collections.Counter(cr["root_claims"]) or corpus.roots()
    total_claims = sum(roots.values()) or len(corpus.claims)

    by_root = collections.Counter()
    for a in corpus.multi_source_addresses():
        by_root[len({c["root"] for c in corpus.by_addr[a]})] += 1

    return dict(
        containment_top=[dict(source=a, inside=b, **v) for (a, b), v in top],
        field_decodes=decodes,
        naming_residues=residues,
        notable_root_propagation=propagations,
        n_roots_total=cr["total"],
        n_roots_identified=cr["identified"],
        unresolved_addresses=cr["unresolved_addresses"],
        unresolved_addr_share=cr["unresolved_addr_share"],
        root_concentration=[dict(root=r, claims=n, share=n / total_claims)
                            for r, n in roots.most_common(limit)],
        roots_per_multi_address=dict(sorted(by_root.items())),
    )


# ------------------------------------------------------------------ E3 drift
#: generic policy name -> the paper's condition letter, purely for the
#: console/report labelling this function has always used.
_CONDITION_LETTER = {"naive_union": "A", "address_dedup": "B",
                     "inheritance_collapsed": "C", "verified_only": "D"}


def drift(corpus, revenue_rows=None, anchors=None, task=_revenue_task, as_of=None) -> dict:
    """STEP 20 - re-run `task`'s forensic aggregation under every configured
    trust-rule policy (config/trust_rules.yml). The eligibility logic lives
    in the generic policy engine (themis/trust/); this function only wires a
    task's claims and value field into it and relabels the result A-D to
    match the paper's condition names.

    `as_of` defaults to the corpus's own `snapshot_date` (same as
    `report.build_report`/`explain`) and is passed through to any
    date-sensitive predicate (e.g. `current_only`) via context - none of
    the four bundled paper conditions use one today, but a custom policy
    on an uploaded dataset can.
    """
    rows = revenue_rows if revenue_rows is not None else corpus.revenue_rows()
    anchors = anchors if anchors is not None else corpus.verified_anchors()
    as_of = as_of or getattr(corpus, "snapshot_date", None)

    claims = task.build_claims(rows)
    policies, baseline = trust_policy.load_policies(_cfg.trust_rules)
    result = trust_drift.run(claims, policies, baseline, task.aggregate,
                             context=dict(anchor_addresses=anchors, as_of=as_of))

    by_addr = collections.defaultdict(set)
    for c in claims:
        by_addr[c["address"]].add(c["source"])
    shared_addresses = sum(1 for srcs in by_addr.values() if len(srcs) >= 2)

    conds = {}
    for pname, r in result["results"].items():
        letter = _CONDITION_LETTER.get(pname, pname)
        conds[letter] = dict(label=r["label"], observations=r["observations"],
                             addresses=r["addresses"], usd=r["value"],
                             ratio_vs_B=r["ratio_vs_baseline"], coverage_vs_B=r["coverage_vs_baseline"])
    a_usd, b_usd, d_usd = conds["A"]["usd"], conds["B"]["usd"], conds["D"]["usd"]
    return dict(conditions=conds, shared_addresses=shared_addresses,
                spread_B_over_D=b_usd / d_usd if d_usd else None,
                spread_A_over_D=a_usd / d_usd if d_usd else None,
                policies=result["results"])


# ------------------------------------------------------- cluster bootstrap CIs
_BOOT_CFG = _cfg.thresholds.get("bootstrap", {})


def bootstrap(corpus, n_boot=None, seed=None, confidence_level=None, upper_bound=False,
              fast=False) -> dict:
    """Resample provenance roots, not rows. `upper_bound` treats every
    unresolved-provenance address as its own root instead of pooling them.

    Rates whose denominator is the whole corpus (multi_source_rate) are only
    computed on a full build: on the bundled sample the denominator is the
    sample, not the corpus, so the figure would be meaningless. Rates
    conditional on being multi-dataset are unaffected, because every
    multi-dataset address is present in the sample.

    n_boot/seed/confidence_level default to config/thresholds.yml's
    `bootstrap` block (STEP 14/15) - paper reproduction uses those defaults
    unchanged; a live audit can override any of the three per run.

    The canonical path (`fast=False`, the default) always resamples with the
    stdlib `random.Random`, whether or not numpy happens to be installed -
    numpy's `default_rng` is a different algorithm, so the same seed produces
    different CI endpoints under it (point estimates are unaffected; only the
    resampled interval is). A reviewer must get the same interval regardless
    of their environment, so paper reproduction never switches RNG based on
    what's importable. `fast=True` opts into the numpy path for large `K`
    (e.g. a full-corpus upper-bound run) where the stdlib loop is slow; it
    requires numpy and its result is explicitly marked non-canonical.
    """
    if fast:
        try:
            import numpy as _np
        except ImportError:
            raise ImportError(
                "bootstrap(fast=True) requires numpy; install it, or omit "
                "fast= for the canonical reproducible path (no dependency needed)")
    else:
        _np = None
    n_boot = _BOOT_CFG.get("iterations", 2000) if n_boot is None else n_boot
    seed = _BOOT_CFG.get("seed", 42) if seed is None else seed
    confidence_level = (_BOOT_CFG.get("confidence_level", 0.95)
                        if confidence_level is None else confidence_level)
    tail = (1 - confidence_level) / 2
    rng = random.Random(seed)
    addrs = list(corpus.by_addr)
    dom, multi, outcome = [], [], []
    for a in addrs:
        cs = corpus.by_addr[a]
        r = collections.Counter(c["root"] for c in cs).most_common(1)[0][0]
        dom.append(r)
        m = len({c["source"] for c in cs}) >= 2
        multi.append(m)
        outcome.append(taxonomy.classify_address(cs) if m else None)

    clusters = collections.defaultdict(list)
    for i, r in enumerate(dom):
        key = f"u{i}" if (upper_bound and provenance.is_unresolved(r)) else r
        clusters[key].append(i)
    keys = list(clusters)

    stats = {}
    if corpus.full:
        stats["multi_source_rate"] = (lambda i: multi[i], lambda i: True)
    for name in ("exact", "hierarchical refinement", "licit/illicit conflict"):
        stats[name] = ((lambda n: (lambda i: outcome[i] == n))(name),
                       (lambda i: multi[i]))

    agg = {}
    for name, (num_f, den_f) in stats.items():
        cn = [sum(1 for i in clusters[k] if den_f(i) and num_f(i)) for k in keys]
        cd = [sum(1 for i in clusters[k] if den_f(i)) for k in keys]
        pt_n, pt_d = sum(cn), sum(cd)
        K = len(keys)
        if K == 0:
            # nothing to resample (an empty corpus/cluster set) - every
            # resample would have an empty denominator anyway, so this
            # just states that directly instead of computing multinomial
            # weights over zero clusters, which is a ZeroDivisionError
            # (1.0 / K) rather than the empty-`vals` result the pure-Python
            # path already reaches here by the loop over `range(K)` never
            # running.
            vals = []
        elif _np is not None:
            # multinomial cluster weights: same estimator, no index materialising,
            # which keeps the upper bound (hundreds of thousands of clusters) fast
            rs = _np.random.default_rng(seed)
            acn, acd = _np.array(cn, float), _np.array(cd, float)
            p = _np.full(K, 1.0 / K)
            batch = max(1, int(1.5e7 // max(K, 1)))
            vals = []
            done = 0
            while done < n_boot:
                b = min(batch, n_boot - done)
                w = rs.multinomial(K, p, size=b).astype(float)
                n_, d_ = w @ acn, w @ acd
                ok = d_ > 0
                vals.extend((n_[ok] / d_[ok]).tolist())
                done += b
        else:
            vals = []
            for _ in range(n_boot):
                pick = [rng.randrange(K) for _ in range(K)]
                n_ = sum(cn[j] for j in pick)
                d_ = sum(cd[j] for j in pick)
                if d_:
                    vals.append(n_ / d_)
        vals.sort()
        lo = vals[int(tail * (len(vals) - 1))] if vals else None
        hi = vals[int((1 - tail) * (len(vals) - 1))] if vals else None
        agg[name] = dict(point=pt_n / pt_d if pt_d else None, ci_low=lo, ci_high=hi)
    return dict(n_clusters=len(keys), upper_bound=upper_bound, stats=agg,
                confidence_level=confidence_level, n_boot=n_boot, seed=seed,
                corpus_wide_rates=corpus.full,
                engine="numpy_fast_exploratory" if fast else "python_canonical",
                note=None if corpus.full else
                "corpus-wide rates omitted on the bundled sample; conditional "
                "rates are exact. Use --observations with a full build to "
                "reproduce the paper's multi-dataset-rate interval.")


def _wilson_interval(successes: int, n: int, confidence_level: float) -> tuple[float, float]:
    """Wilson score interval - defensible at any n (including the very small
    per-source n an anchor set like this produces), unlike a normal
    approximation. `z` is derived from `confidence_level` via the standard
    normal quantile rather than a hardcoded 1.96, so a config change to the
    confidence level doesn't require a matching code change."""
    z = statistics.NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _modal_claim(claims: list[dict]) -> tuple[str, str]:
    """One decision per (source, address): the most common canonical label
    among that source's interpretable claims, ties broken by label then root
    name so the result never depends on claim order. Returns (canon, root of
    the claim(s) that carried it)."""
    cnt = collections.Counter(c["canon"] for c in claims)
    canon = min(cnt, key=lambda k: (-cnt[k], k))
    return canon, min(c["root"] for c in claims if c["canon"] == canon)


def _root_cluster_ci(per_root: dict, n_boot: int, seed: int,
                     confidence_level: float) -> tuple[float | None, float | None]:
    """Percentile interval for a pooled ratio, resampling provenance roots
    (each root's (successes, n) is one cluster) - the same unit `bootstrap()`
    resamples, for the same reason: evaluations that descend from one root
    are not independent observations, so a Wilson interval over addresses
    would report far more certainty than the evidence supports."""
    keys = sorted(per_root)
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        d_ = sum(per_root[k][1] for k in pick)
        if d_:
            vals.append(sum(per_root[k][0] for k in pick) / d_)
    vals.sort()
    tail = (1 - confidence_level) / 2
    return ((vals[int(tail * (len(vals) - 1))], vals[int((1 - tail) * (len(vals) - 1))])
            if vals else (None, None))


def anchor_validation(corpus, anchors=None, confidence_level=None) -> dict:
    """Provenance-aware validation against the paper's open-anchor reference
    set (Sec 4.3/4.7: `demo_data/ground_truth.csv`) - operationalizes what
    that section previously only argued qualitatively.

    `ground_truth_source` in that file records a provenance ROOT
    (`ofac_sdn`, `watchyourback_manual`), not a corpus source id. A claim
    can only validate an anchor if its own resolved root differs from the
    anchor's declared root - matching by root, not by dataset name, is what
    correctly excludes both literal self-validation (the same source that
    produced the anchor) and same-root validation (a different-named source
    whose claim descends from the same root the anchor came from, e.g. a
    schnoering claim inherited from `ofac_sdn` "confirming" an OFAC anchor).
    A naive name-based check misses the second case entirely.

    The unit of evaluation is one decision per (source, address), the
    source's modal interpretable label (Sec 4.2: "the unit must be the
    address rather than the claim") - a source that repeats itself on an
    anchor must not be counted as several confirmations. A source with no
    interpretable claim at an anchor (canon == "unknown", same rule as
    `taxonomy.classify_address`) contributes an `incomparable`, not a miss.

    What is reported is AGREEMENT WITH THE ANCHOR SET, not source accuracy:
    the reference set is small, non-random, and concentrated in a few roots.
    Each source therefore also carries the number of independent resolved
    roots its evaluated decisions come from and the share held by its
    largest root; the interval is a root-cluster bootstrap (not Wilson over
    addresses, kept alongside as `wilson_low/high` for comparison only) and
    a source below `anchor_min_independent_roots` is not estimable at all -
    with one root there is no between-root variance to resample.
    """
    anchors = anchors if anchors is not None else corpus.ground_truth()
    confidence_level = (_BOOT_CFG.get("confidence_level", 0.95)
                        if confidence_level is None else confidence_level)
    n_boot = _BOOT_CFG.get("iterations", 2000)
    seed = _BOOT_CFG.get("seed", 42)
    min_roots = _cfg.thresholds.get("anchor_min_independent_roots", 2)

    usable_anchors = excluded_self_root_claims = uninterpretable_ground_truth = 0
    root_counts = []
    outcome_totals = collections.Counter()
    per_source = collections.defaultdict(collections.Counter)
    evaluated = collections.defaultdict(list)     # source -> [(root, outcome)]

    for addr, (label, anchor_root) in anchors.items():
        claims = corpus.by_addr.get(addr, [])
        self_claims = [c for c in claims if c["root"] == anchor_root]
        indep_claims = [c for c in claims if c["root"] != anchor_root]
        excluded_self_root_claims += len(self_claims)
        if not indep_claims:
            continue
        usable_anchors += 1
        root_counts.append(len({c["root"] for c in indep_claims
                                if not provenance.is_unresolved(c["root"])}))

        gt_canon = taxonomy.canonicalize_category(label)
        if gt_canon is None:
            uninterpretable_ground_truth += 1
            continue
        anchor_claim = dict(source="__anchor__", canon=gt_canon)
        by_source = collections.defaultdict(list)
        for c in indep_claims:
            by_source[c["source"]].append(c)
        for src, group in by_source.items():
            interpretable = [c for c in group if c["canon"] != "unknown"]
            if not interpretable:
                per_source[src]["incomparable"] += 1
                outcome_totals["incomparable"] += 1
                continue
            canon, root = _modal_claim(interpretable)
            outcome = taxonomy.classify_address(
                [anchor_claim, dict(source=src, canon=canon)])
            outcome_totals[outcome] += 1
            per_source[src]["n"] += 1
            per_source[src][outcome] += 1
            evaluated[src].append((root, outcome))

    per_source_report = {}
    for src, counts in per_source.items():
        n = counts["n"]
        if n == 0:
            per_source_report[src] = dict(
                n=0, incomparable=counts["incomparable"], independent_roots=0,
                anchor_agreement=None, ci_low=None, ci_high=None,
                wilson_low=None, wilson_high=None, estimable=False,
                not_estimable_reason="no interpretable claim on any usable anchor")
            continue
        exact = counts["exact"]
        per_root = collections.defaultdict(lambda: [0, 0])
        for root, outcome in evaluated[src]:
            per_root[root][1] += 1
            per_root[root][0] += outcome == "exact"
        roots = len({r for r in per_root if not provenance.is_unresolved(r)})
        estimable = roots >= min_roots
        ci_low, ci_high = (_root_cluster_ci(per_root, n_boot, seed, confidence_level)
                           if estimable else (None, None))
        w_low, w_high = _wilson_interval(exact, n, confidence_level)
        per_source_report[src] = dict(
            n=n, exact=exact,
            hierarchical=counts["hierarchical refinement"],
            conflicting=counts["entity-type conflict"] + counts["licit/illicit conflict"],
            incomparable=counts["incomparable"],
            anchor_agreement=exact / n,
            independent_roots=roots,
            largest_root_share=max(v[1] for v in per_root.values()) / n,
            ci_low=ci_low, ci_high=ci_high, ci_method="root_cluster_bootstrap",
            wilson_low=w_low, wilson_high=w_high, estimable=estimable,
            not_estimable_reason=None if estimable else (
                f"{roots} independent root(s), need {min_roots}+"))

    return dict(
        anchors_total=len(anchors),
        usable_anchors=usable_anchors,
        coverage=usable_anchors / len(anchors) if anchors else None,
        excluded_self_root_claims=excluded_self_root_claims,
        uninterpretable_ground_truth_label=uninterpretable_ground_truth,
        independent_provenance_roots=dict(sorted(collections.Counter(root_counts).items())),
        outcome_totals=dict(outcome_totals),
        per_source=per_source_report,
        confidence_level=confidence_level,
        min_independent_roots=min_roots,
        estimable=any(v["estimable"] for v in per_source_report.values()),
        limitations=(
            "This reference set is small (see anchors_total) and concentrated in a "
            "few sources; a per-source figure here measures agreement with this "
            "open anchor set, not verified accuracy against ground truth for the "
            "corpus as a whole. One decision is counted per (source, address); a "
            "source whose decisions come from few independent roots is not "
            "estimable, and where it is the interval resamples roots, so few "
            "roots means a wide interval - read it as a bound on what this "
            "reference set can say, not as a measurement. estimable=False means "
            "either too few independent roots, or the source was never seen on a "
            "usable anchor, or every claim it made there never canonicalized - "
            "none of these is an agreement of zero. Root resolution can only be "
            "as correct as the source registry's declared provenance - see "
            "config/sources/watchyourback.yml's confidence_semantics for a known "
            "case where a source's declared root may itself be too coarse."))


# ------------------------------------------------------------- STEP 13 freshness
def freshness(claims: list[dict], as_of=None) -> dict:
    """CURRENT / STALE / CURRENCY_UNKNOWN over a flat claim list. A claim
    with no revision date is always CURRENCY_UNKNOWN, never STALE - see
    taxonomy.currency_flags.

    `as_of` (Loop 2 STEP 16) fixes "today" for this computation: a live
    audit defaults to the real current date, but a paper-reproduction run
    passes its snapshot date so the same archived corpus doesn't drift more
    "stale" every year it's re-run.
    """
    current = stale = unknown = 0
    for c in claims:
        flags = taxonomy.currency_flags(c, today=as_of)
        if "stale" in flags:
            stale += 1
        elif "currency-unknown" in flags:
            unknown += 1
        else:
            current += 1
    total = len(claims) or 1
    return dict(current=current, stale=stale, currency_unknown=unknown,
                current_share=current / total, stale_share=stale / total,
                currency_unknown_share=unknown / total)


# --------------------------------------------------------- per-address report
def explain(corpus, address: str, as_of=None) -> dict:
    """`as_of` (Loop 2 STEP 16) defaults to the corpus's own `snapshot_date`,
    same as `report.build_report` - a single address's stale/currency-unknown
    flags must agree with the corpus-wide freshness figures for the same
    archived corpus, not drift against them because this view recomputed
    against the live wall clock instead of the frozen snapshot."""
    as_of = as_of or getattr(corpus, "snapshot_date", None)
    claims = corpus.by_addr.get(address)
    if not claims:
        return dict(address=address, found=False)
    roots = sorted({c["root"] for c in claims})
    srcs = sorted({c["source"] for c in claims})
    outcome = taxonomy.classify_address(claims) if len(srcs) >= 2 else "single-source"
    indep = provenance.address_independence(claims)
    return dict(
        address=address, found=True,
        claims=[dict(source=c["source"], label=c["canon"], raw=c["raw_label"],
                     root=c["root"], root_kind=c.get("prov_kind", "UNKNOWN"),
                     tier=taxonomy.tier_of(c),
                     lastmod=c["lastmod"] or None,
                     flags=taxonomy.currency_flags(c, today=as_of)) for c in claims],
        datasets=srcs, roots=roots,
        # apparent = distinct datasets; actual/confirmed = distinct *resolved*
        # roots only - an unresolved root is an unknown relationship, never a
        # confirmed independent one (see provenance.address_independence)
        apparent_corroboration=indep["apparent_dataset_count"],
        actual_corroboration=indep["confirmed_independent_root_count"],
        circular=indep["circular"],
        independence=indep,
        outcome=outcome,
        tier=taxonomy.best_tier(claims),
        flags=taxonomy.flags_for_address(claims, today=as_of),
    )
