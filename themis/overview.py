"""The Overview page's figures, each carried with the population it was counted over.

A corpus report mixes populations that the page must never blur: claims vs
addresses, raw address keys (the address column as built) vs normalized
addresses (after the source-specific rewrite, e.g. WatchYourBack's `#` marker,
which joins raw keys), and the bundled sample vs the full corpus. Each metric
here is one record

    value, numerator, denominator, share, unit, population, quality, analysis_as_of

with ONE unit and ONE population for numerator and denominator alike, so a
share can only be taken inside a single universe. Nothing is computed a second
way: every figure is read from the canonical analysis results or the corpus.

    population  normalized_full_corpus | raw_address_keys | claims_full_corpus | bundled_sample
    quality     live | manifest | sample_observed | unavailable

`live` is recomputed from the claims loaded (a full build); `manifest` is a
corpus-wide figure frozen in the bundled sample's manifest; `sample_observed`
is counted over the sample only, so it is never the corpus's value.
"""
from __future__ import annotations

from .paper.experiments import source_claim_counts

NORMALIZED, RAW_KEYS = "normalized_full_corpus", "raw_address_keys"
CLAIMS_FULL, SAMPLE = "claims_full_corpus", "bundled_sample"
LIVE, MANIFEST, SAMPLE_OBSERVED, UNAVAILABLE = "live", "manifest", "sample_observed", "unavailable"


def _metric(value, *, unit, population, quality, as_of, numerator=None, denominator=None, **extra) -> dict:
    """One metric record. A missing value is `unavailable`, never a silent zero."""
    share = numerator / denominator if numerator is not None and denominator else None
    return dict(value=value, numerator=numerator, denominator=denominator, share=share, unit=unit,
                population=population, quality=quality if value is not None else UNAVAILABLE,
                analysis_as_of=as_of, **extra)


def build(corpus, agreement: dict, independence: dict, fresh: dict, as_of) -> dict:
    full = corpus.full
    fc = corpus.manifest.get("full_corpus", {})
    asof = str(as_of) if as_of else None
    # a figure about the whole corpus: recomputed on a full build, frozen in the manifest on the sample
    corpus_q = LIVE if full else MANIFEST

    def M(value, **kw):
        return _metric(value, as_of=asof, **kw)

    n_claims = corpus.n_claims if (full or fc) else None
    n_norm = len(corpus.by_addr) if full else None
    n_raw = len({c["raw_address"] for c in corpus.claims}) if full else fc.get("addresses")
    n_multi = agreement["n_multi_source"]
    metrics = {}

    metrics["claims"] = M(n_claims, unit="claims", population=CLAIMS_FULL, quality=corpus_q,
                          sources=len(corpus.source_sizes()))
    metrics["normalized_addresses"] = M(n_norm, unit="addresses", population=NORMALIZED, quality=LIVE)
    metrics["raw_address_keys"] = M(n_raw, unit="addresses", population=RAW_KEYS, quality=corpus_q)

    # multi-dataset vs single-source share ONE denominator: the normalized addresses. On the sample that
    # universe is not loaded, so only the sample's own multi-dataset count exists (no share, no complement).
    if full:
        metrics["multi_dataset"] = M(n_multi, numerator=n_multi, denominator=n_norm, unit="addresses",
                                     population=NORMALIZED, quality=LIVE)
        metrics["single_source"] = M(n_norm - n_multi, numerator=n_norm - n_multi, denominator=n_norm,
                                     unit="addresses", population=NORMALIZED, quality=LIVE)
    else:
        metrics["multi_dataset"] = M(n_multi, unit="addresses", population=SAMPLE, quality=SAMPLE_OBSERVED)
        metrics["single_source"] = M(None, unit="addresses", population=NORMALIZED, quality=LIVE)
    depth = {k: v for k, v in agreement["sources_per_address"].items() if k >= 2}
    metrics["source_depth"] = M(n_multi, denominator=n_multi, unit="addresses",
                                population=metrics["multi_dataset"]["population"],
                                quality=metrics["multi_dataset"]["quality"],
                                parts=[dict(key=str(k), n=v, share=v / n_multi if n_multi else None)
                                       for k, v in sorted(depth.items())])

    # agreement outcomes exist only over multi-dataset addresses, so they carry that population
    metrics["agreement"] = M(n_multi, unit="addresses", population=metrics["multi_dataset"]["population"],
                             quality=metrics["multi_dataset"]["quality"], outcomes=agreement["outcomes"])

    # unresolved provenance: numerator and denominator from ONE address universe
    unres = independence["unresolved_addresses"]
    u_den, u_pop, u_q = (n_norm, NORMALIZED, LIVE) if full else (n_raw, RAW_KEYS, MANIFEST)
    metrics["unresolved_provenance"] = M(unres, numerator=unres, denominator=u_den, unit="addresses",
                                         population=u_pop, quality=u_q,
                                         resolved=u_den - unres if u_den is not None and unres is not None else None,
                                         resolved_share=(u_den - unres) / u_den if u_den and unres is not None else None)

    metrics["root_concentration"] = M(independence["n_roots_total"], denominator=n_claims, unit="claims",
                                      population=CLAIMS_FULL, quality=corpus_q,
                                      identified=independence["n_roots_identified"])

    per_source = source_claim_counts(corpus)
    metrics["source_contribution"] = M(
        sum(per_source.values()), denominator=n_claims, unit="claims", population=CLAIMS_FULL, quality=corpus_q,
        parts=[dict(key=s, n=n, share=n / n_claims if n_claims else None)
               for s, n in sorted(per_source.items(), key=lambda kv: -kv[1])])

    # currency is judged over the claims loaded: the whole corpus on a full build, the sample otherwise
    cur_pop, cur_q = (CLAIMS_FULL, LIVE) if full else (SAMPLE, SAMPLE_OBSERVED)
    metrics["currency"] = M(fresh["n_claims"], denominator=fresh["n_claims"], unit="claims",
                            population=cur_pop, quality=cur_q, corpus_n_claims=n_claims,
                            parts=[dict(key=k, n=fresh[k], share=fresh[f"{k}_share"])
                                   for k in ("current", "stale", "currency_unknown")])
    metrics["claims_without_revision"] = M(
        fresh["currency_unknown"] if full else None, numerator=fresh["currency_unknown"] if full else None,
        denominator=n_claims, unit="claims", population=CLAIMS_FULL, quality=LIVE)

    return dict(scope="FULL_CORPUS" if full else "BUNDLED_SAMPLE", analysis_as_of=asof, metrics=metrics)
