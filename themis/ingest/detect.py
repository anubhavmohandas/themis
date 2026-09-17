"""STEP 1 - is this even a cryptocurrency attribution dataset? Decided by
sampling every column against every registered chain adapter, never by
filename. THEMIS stops the forensic pipeline (but not basic data-quality
checks) when nothing looks like an address at a rate too high to be
coincidence.
"""
from __future__ import annotations
from .. import chains

HIGH, MEDIUM, LOW, NONE = "HIGH", "MEDIUM", "LOW", "NONE"
ADDRESS_NAME_HINTS = ("address", "wallet", "addr", "acct", "account")


def sample_values(rows: list[dict], field: str, limit: int) -> list[str]:
    out = []
    for r in rows:
        v = (r.get(field) or "").strip()
        if v:
            out.append(v)
            if len(out) >= limit:
                break
    return out


def detect(rows: list[dict], fieldnames: list[str], sample_size: int = 500) -> dict:
    """Sample-based, so it stays fast on a large file; STEP 4 validation
    later checks every row exactly once a mapping is confirmed."""
    best = None
    per_field = {}
    for field in fieldnames:
        sample = sample_values(rows, field, sample_size)
        if not sample:
            continue
        for chain_id, adapter in chains.all_adapters().items():
            valid = sum(1 for v in sample if adapter.validate_address(v))
            rate = valid / len(sample)
            per_field[f"{field}:{chain_id}"] = dict(n_sampled=len(sample), n_valid=valid, rate=rate)
            score = rate + (0.05 if any(h in field.lower() for h in ADDRESS_NAME_HINTS) else 0.0)
            if best is None or score > best["score"]:
                best = dict(score=score, chain=chain_id, field=field, rate=rate, n_sampled=len(sample))

    if best is None:
        return dict(confidence=NONE, blockchain=None, address_field=None,
                    sample_hit_rate=0.0, sampled=0, total_rows=len(rows), per_field={})

    rate = best["rate"]
    confidence = HIGH if rate >= 0.8 else MEDIUM if rate >= 0.3 else LOW if rate >= 0.05 else NONE
    return dict(confidence=confidence,
                blockchain=best["chain"] if confidence != NONE else None,
                address_field=best["field"] if confidence != NONE else None,
                sample_hit_rate=rate, sampled=best["n_sampled"], total_rows=len(rows),
                per_field=per_field)
