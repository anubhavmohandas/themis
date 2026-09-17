"""STEP 20 - re-run a forensic calculation under every configured trust-rule
policy and report the result together with its coverage against a baseline.
Generic over the task: the caller supplies the claims (each needs at least
`address`, `root`, `prov_resolved`, `prov_native`) and an aggregation
function keyed by the policy's declared `aggregation` mode. This module
never sees "ransomware" or "revenue" - see themis/tasks/ for that.
"""
from __future__ import annotations
import collections


def group_by_address(claims: list[dict]) -> dict:
    out = collections.defaultdict(list)
    for c in claims:
        out[c["address"]].append(c)
    return dict(out)


def run(claims: list[dict], policies: dict, baseline: str, aggregate_fn, context: dict | None = None) -> dict:
    """`aggregate_fn(eligible_claims, mode) -> {observations, addresses, value}`."""
    ctx = dict(context or {})
    ctx.setdefault("claims_by_address", group_by_address(claims))

    results = {}
    for name, policy in policies.items():
        eligible = policy.eligible(claims, ctx)
        agg = aggregate_fn(eligible, policy.aggregation)
        results[name] = dict(label=policy.label, aggregation=policy.aggregation, **agg)

    if baseline not in results:
        raise KeyError(f"baseline policy {baseline!r} is not among the loaded policies")
    base = results[baseline]
    for r in results.values():
        r["ratio_vs_baseline"] = r["value"] / base["value"] if base["value"] else None
        r["coverage_vs_baseline"] = (r["observations"] / base["observations"]
                                     if base["observations"] else None)
    return dict(baseline=baseline, results=results)
