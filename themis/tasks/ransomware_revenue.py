"""STEP 20/22 - the paper's forensic task: ransomware revenue estimation.

This is the one module allowed to know that the figure being estimated is a
USD sum per address. It turns raw revenue rows into claims the generic trust
engine can score - resolving each one's provenance through the same
config-driven resolver as every other claim, so the eligibility policies in
config/trust_rules.yml (in particular `root_independent_or_native`, STEP 12)
apply to this task exactly as they do to the main corpus, with no separate
"is this row inherited" logic re-implemented here.

A future task (sanctions exposure, entity counts, ...) is a new module in
this shape, not a new branch in the trust engine.
"""
from __future__ import annotations
from .. import provenance


def build_claims(revenue_rows: list[dict]) -> list[dict]:
    claims = []
    for r in revenue_rows:
        source = r["dataset"]
        c = {
            "source": source,
            "address": r["address"],
            "value_usd": float(r["usd"] or 0),
            # only the suffix after ':' is ever read by the resolver; using
            # the row's own declared source as the prefix keeps this claim
            # self-describing without assuming a naming convention.
            "prov_family": f"{source}:{r.get('src_letters', '') or ''}",
            "subcat": r.get("family", "") or "",
        }
        res = provenance.resolve(c)
        c["root"], c["prov_resolved"] = res["root"], res["resolved"]
        c["prov_native"], c["prov_verified"] = res["native"], res["verified"]
        claims.append(c)
    return claims


def aggregate(claims: list[dict], mode: str) -> dict:
    if mode == "raw_sum":
        return dict(observations=len(claims),
                    addresses=len({c["address"] for c in claims}),
                    value=sum(c["value_usd"] for c in claims))
    if mode == "dedup_max_per_address":
        best: dict[str, float] = {}
        for c in claims:
            a, v = c["address"], c["value_usd"]
            if a not in best or v > best[a]:
                best[a] = v
        return dict(observations=len(best), addresses=len(best), value=sum(best.values()))
    raise ValueError(f"unknown aggregation mode: {mode!r}")
