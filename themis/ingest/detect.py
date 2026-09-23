"""STEP 1 - is this even a cryptocurrency attribution dataset? Decided by
sampling every column against every registered chain adapter, never by
filename. THEMIS stops the forensic pipeline (but not basic data-quality
checks) when nothing looks like an address at a rate too high to be
coincidence.
"""
from __future__ import annotations
import re
from .. import chains, config_io

HIGH, MEDIUM, LOW, NONE = "HIGH", "MEDIUM", "LOW", "NONE"


def cfg() -> dict:
    return config_io.load().preflight
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

# Distinguishes "crypto data, but not an attribution dataset" (a price/
# market-data column that names a known chain, e.g. Symbol="BTC-USD") from
# "no crypto signal at all" (Iris, Titanic, a bare Date/Price series with no
# asset identity anywhere in it - see external_data/non_crypto/btc_ohlc_real.csv,
# which THEMIS correctly still can't call crypto: no column states what asset
# it is). Content-gated on each adapter's own `symbol_aliases`, never on
# filename - adding a chain only ever means adding an adapter (base.py).
ASSET_NAME_HINTS = ("symbol", "ticker", "pair", "coin", "currency", "asset", "market")
_ASSET_TOKEN_RE = re.compile(r"[a-zA-Z]+")


def _known_symbol_aliases() -> set[str]:
    return {a.lower() for adapter in chains.all_adapters().values() for a in adapter.symbol_aliases}


def _crypto_asset_field(rows: list[dict], fieldnames: list[str], sample_size: int) -> str | None:
    """Only consulted once every adapter and the unsupported-chain fallback
    have both already failed to find any address-shaped column."""
    aliases = _known_symbol_aliases()
    if not aliases:
        return None
    for field in fieldnames:
        if not any(h in field.lower() for h in ASSET_NAME_HINTS):
            continue
        sample = sample_values(rows, field, sample_size)
        tokens = {t.lower() for v in sample for t in _ASSET_TOKEN_RE.findall(v)}
        if tokens & aliases:
            return field
    return None


def _looks_like_unrecognized_address(sample: list[str]) -> bool:
    if len(sample) < 3:
        return False
    shape = cfg()["detect"]["unsupported_chain_shape"]
    lengths = {len(v) for v in sample}
    if len(lengths) > shape["max_distinct_lengths"] or not all(shape["min_len"] <= len(v) <= shape["max_len"] for v in sample):
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


def confidence_of(rate: float) -> str:
    """The share of sampled values that validate -> HIGH / MEDIUM / LOW / NONE.
    MEDIUM reuses `min_identifier_valid_rate` (the same floor the pre-flight
    gate blocks analysis below) rather than its own copy of that number -
    see that key's comment in preflight.yml."""
    c = cfg()
    d = c["detect"]
    return (HIGH if rate >= d["confidence_high"] else
            MEDIUM if rate >= c["min_identifier_valid_rate"] else
            LOW if rate >= d["confidence_low"] else NONE)


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
            score = rate + (cfg()["detect"]["address_name_hint_bonus"]
                           if any(h in field.lower() for h in ADDRESS_NAME_HINTS) else 0.0)
            if best is None or score > best["score"]:
                best = dict(score=score, chain=chain_id, field=field, rate=rate, n_sampled=len(sample))

    if best is None:
        unsupported = _unsupported_chain_field(rows, fieldnames, sample_size)
        crypto_asset = None if unsupported else _crypto_asset_field(rows, fieldnames, sample_size)
        return dict(confidence=NONE, blockchain=None, address_field=None,
                    unsupported_chain_field=unsupported, crypto_asset_field=crypto_asset,
                    sample_hit_rate=0.0, sampled=0, total_rows=len(rows), per_field={})

    rate = best["rate"]
    confidence = confidence_of(rate)
    unsupported = None if confidence != NONE else _unsupported_chain_field(rows, fieldnames, sample_size)
    crypto_asset = (None if (confidence != NONE or unsupported)
                    else _crypto_asset_field(rows, fieldnames, sample_size))
    return dict(confidence=confidence,
                blockchain=best["chain"] if confidence != NONE else None,
                address_field=best["field"] if confidence != NONE else None,
                unsupported_chain_field=unsupported, crypto_asset_field=crypto_asset,
                sample_hit_rate=rate, sampled=best["n_sampled"], total_rows=len(rows),
                per_field=per_field)
