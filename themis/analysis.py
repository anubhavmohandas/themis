"""The four analyses: agreement, independence, drift, and the cluster bootstrap."""
from __future__ import annotations
import collections, random
from . import taxonomy, provenance


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
        sources_per_address=dict(sorted(collections.Counter(
            len({c["source"] for c in corpus.by_addr[a]}) for a in corpus.by_addr).items())),
    )


# ------------------------------------------------------------ E2 independence
def independence(corpus) -> dict:
    sa = corpus.src_addr
    cont = provenance.containment(sa)
    top = sorted(cont.items(), key=lambda kv: -kv[1]["share_of_a"])[:12]
    decode = provenance.decode_field(corpus.claims, "rodwald_ransom",
                                     "ransomwhere", sa.get("ransomwhere", set()))
    residue = provenance.naming_residue(corpus.claims, "rodwald_ransom")

    # how far one upstream set propagates
    montreal = {c["address"] for c in corpus.claims
                if c["source"] == "schnoering" and c.get("subcat") == "Montréal"}
    propagation = {s: len(montreal & sa[s]) for s in sa if s != "schnoering"}

    cr = corpus.corpus_roots()
    roots = collections.Counter(cr["root_claims"]) or corpus.roots()
    total_claims = sum(roots.values()) or len(corpus.claims)

    by_root = collections.Counter()
    for a in corpus.multi_source_addresses():
        by_root[len({c["root"] for c in corpus.by_addr[a]})] += 1

    return dict(
        containment_top=[dict(source=a, inside=b, **v) for (a, b), v in top],
        field_decode=decode,
        naming_residue=residue,
        montreal_set=dict(size=len(montreal), propagation=propagation),
        n_roots_total=cr["total"],
        n_roots_identified=cr["identified"],
        unresolved_addresses=cr["unresolved_addresses"],
        unresolved_addr_share=cr["unresolved_addr_share"],
        root_concentration=[dict(root=r, claims=n, share=n / total_claims)
                            for r, n in roots.most_common(8)],
        roots_per_multi_address=dict(sorted(by_root.items())),
    )


# ------------------------------------------------------------------ E3 drift
def drift(corpus, revenue_rows=None, anchors=None) -> dict:
    rows = revenue_rows if revenue_rows is not None else corpus.revenue_rows()
    anchors = anchors if anchors is not None else corpus.verified_anchors()

    rod, rw, meta = {}, {}, {}
    for r in rows:
        usd = float(r["usd"] or 0)
        if r["dataset"] == "rodwald_ransom":
            rod[r["address"]] = usd
            meta[r["address"]] = (r.get("family", ""), r.get("src_letters", ""))
        else:
            rw[r["address"]] = usd

    ded = dict(rod)
    for a, u in rw.items():
        ded[a] = max(ded.get(a, 0.0), u)

    def inherited(a):
        fam, letters = meta.get(a, ("", ""))
        return "R" in letters or fam.lower().startswith(
            tuple(p for p, _ in provenance.FAMILY_MARKERS))

    keep_c = {a: u for a, u in ded.items()
              if not (a in rod and inherited(a) and a not in rw)}
    keep_d = {a: u for a, u in ded.items() if a in anchors}

    base_usd = sum(ded.values())
    base_n = len(ded)
    conds = {
        "A": dict(label="naive union, sources summed as independent",
                  observations=len(rod) + len(rw), addresses=len(set(rod) | set(rw)),
                  usd=sum(rod.values()) + sum(rw.values())),
        "B": dict(label="address-level deduplication",
                  observations=base_n, addresses=base_n, usd=base_usd),
        "C": dict(label="circular inheritance collapsed to its root",
                  observations=len(keep_c), addresses=len(keep_c), usd=sum(keep_c.values())),
        "D": dict(label="highest-declared-confidence tier only",
                  observations=len(keep_d), addresses=len(keep_d), usd=sum(keep_d.values())),
    }
    for c in conds.values():
        c["ratio_vs_B"] = c["usd"] / base_usd if base_usd else None
        c["coverage_vs_B"] = c["observations"] / base_n if base_n else None
    return dict(conditions=conds,
                shared_addresses=len(set(rod) & set(rw)),
                spread_B_over_D=conds["B"]["usd"] / conds["D"]["usd"] if conds["D"]["usd"] else None,
                spread_A_over_D=conds["A"]["usd"] / conds["D"]["usd"] if conds["D"]["usd"] else None)


# ------------------------------------------------------- cluster bootstrap CIs
def bootstrap(corpus, n_boot=2000, seed=42, upper_bound=False) -> dict:
    """Resample provenance roots, not rows. `upper_bound` treats every
    unresolved-provenance address as its own root instead of pooling them.

    Rates whose denominator is the whole corpus (multi_source_rate) are only
    computed on a full build: on the bundled sample the denominator is the
    sample, not the corpus, so the figure would be meaningless. Rates
    conditional on being multi-dataset are unaffected, because every
    multi-dataset address is present in the sample.
    """
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

    try:
        import numpy as _np
    except ImportError:
        _np = None

    agg = {}
    for name, (num_f, den_f) in stats.items():
        cn = [sum(1 for i in clusters[k] if den_f(i) and num_f(i)) for k in keys]
        cd = [sum(1 for i in clusters[k] if den_f(i)) for k in keys]
        pt_n, pt_d = sum(cn), sum(cd)
        K = len(keys)
        if _np is not None:
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
        lo = vals[int(.025 * (len(vals) - 1))] if vals else None
        hi = vals[int(.975 * (len(vals) - 1))] if vals else None
        agg[name] = dict(point=pt_n / pt_d if pt_d else None, ci_low=lo, ci_high=hi)
    return dict(n_clusters=len(keys), upper_bound=upper_bound, stats=agg,
                corpus_wide_rates=corpus.full,
                note=None if corpus.full else
                "corpus-wide rates omitted on the bundled sample; conditional "
                "rates are exact. Use --observations with a full build to "
                "reproduce the paper's multi-dataset-rate interval.")


# --------------------------------------------------------- per-address report
def explain(corpus, address: str) -> dict:
    claims = corpus.by_addr.get(address)
    if not claims:
        return dict(address=address, found=False)
    roots = sorted({c["root"] for c in claims})
    srcs = sorted({c["source"] for c in claims})
    outcome = taxonomy.classify_address(claims) if len(srcs) >= 2 else "single-source"
    return dict(
        address=address, found=True,
        claims=[dict(source=c["source"], label=c["canon"], raw=c["raw_label"],
                     root=c["root"], tier=taxonomy.tier_of(c),
                     lastmod=c["lastmod"] or None,
                     flags=taxonomy.currency_flags(c)) for c in claims],
        datasets=srcs, roots=roots,
        apparent_corroboration=len(srcs),
        actual_corroboration=len(roots),
        circular=len(srcs) >= 2 and len(roots) < len(srcs),
        outcome=outcome,
        tier=taxonomy.best_tier(claims),
        flags=taxonomy.flags_for_address(claims),
    )
