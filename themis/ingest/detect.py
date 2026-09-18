"""STEP 1 - is this even a cryptocurrency attribution dataset? Decided by
sampling every column against every registered chain adapter, never by
filename. THEMIS stops the forensic pipeline (but not basic data-quality
checks) when nothing looks like an address at a rate too high to be
coincidence.
"""
from __future__ import annotations
import re
from .. import chains

HIGH, MEDIUM, LOW, NONE = "HIGH", "MEDIUM", "LOW", "NONE"
ADDRESS_NAME_HINTS = ("address", "wallet", "addr", "acct", "account")

# No registered adapter validates these, but a chain we have no adapter for
# yet still produces opaque, fixed-shape identifier tokens - uniform length,
# a restricted alphabet, no whitespace or punctuation. This is a structural
# shape check only: it never names a specific chain, so it also never turns
# into per-dataset branching (see chains/base.py: "a new chain is a new
# adapter ... never a branch inside the analysis engine"). It exists so an
# unsupported-chain attribution file is told apart from data that just isn't
# address-shaped at all (Iris, Titanic, OHLC price rows, ...).
_OPAQUE_TOKEN_RE = re.compile(r"^[0-9a-zA-Z]+$")


def _looks_like_unrecognized_address(sample: list[str]) -> bool:
    if len(sample) < 3:
        return False
    lengths = {len(v) for v in sample}
    if len(lengths) > 2 or not all(18 <= len(v) <= 100 for v in sample):
        return False
    return all(_OPAQUE_TOKEN_RE.match(v) for v in sample)


def sample_values(rows: list[dict], field: str, limit: int) -> list[str]:
    out = []
    for r in rows:
        v = (r.get(field) or "").strip()
        if v:
            out.append(v)
            if len(out) >= limit:
                break
    return out


def _unsupported_chain_field(rows: list[dict], fieldnames: list[str], sample_size: int) -> str | None:
    """Only consulted once every registered adapter has already failed to
    match anything: is there still an address-named column of opaque,
    fixed-shape tokens THEMIS just has no adapter for?"""
    for field in fieldnames:
        if not any(h in field.lower() for h in ADDRESS_NAME_HINTS):
            continue
        sample = sample_values(rows, field, sample_size)
        if _looks_like_unrecognized_address(sample):
            return field
    return None


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
        unsupported = _unsupported_chain_field(rows, fieldnames, sample_size)
        return dict(confidence=NONE, blockchain=None, address_field=None,
                    unsupported_chain_field=unsupported,
                    sample_hit_rate=0.0, sampled=0, total_rows=len(rows), per_field={})

    rate = best["rate"]
    confidence = HIGH if rate >= 0.8 else MEDIUM if rate >= 0.3 else LOW if rate >= 0.05 else NONE
    unsupported = None if confidence != NONE else _unsupported_chain_field(rows, fieldnames, sample_size)
    return dict(confidence=confidence,
                blockchain=best["chain"] if confidence != NONE else None,
                address_field=best["field"] if confidence != NONE else None,
                unsupported_chain_field=unsupported,
                sample_hit_rate=rate, sampled=best["n_sampled"], total_rows=len(rows),
                per_field=per_field)
