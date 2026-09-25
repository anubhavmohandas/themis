"""STEP 4 - input validation. Every rejected record is counted with a reason
(and the first `rejected_examples` of them kept for inspection); nothing is
silently dropped.

A row's identifier is validated under ITS OWN chain: the per-row chain column
when the file has one, else the single chain the pre-flight settled on. The
same string on two chains is two subjects, so a claim is identified by
(chain, identifier, label, declared source).
"""
from __future__ import annotations
import hashlib, re
from .. import chains, config_io
from .claims import declared_source
from ..errors import InputError


def _digest(*parts) -> bytes:
    """A fixed-size key for a dedupe set, so ten million rows do not each keep a tuple alive.
    128 bits: an accidental collision is not a realistic event at any file size THEMIS accepts."""
    return hashlib.blake2b("\x1f".join(map(str, parts)).encode("utf-8", "surrogatepass"), digest_size=16).digest()


def split_label(cell: str, multi_label: dict | None) -> list[str]:
    """The tokens of a label cell IF the pre-flight established that this column holds token lists
    and the cell is one (every token well-formed). Anything else is one label, kept whole."""
    if not multi_label or multi_label.get("status") != "multi_label":
        return [cell]
    sep = multi_label["separator"]
    tok = re.compile(config_io.load().preflight["multi_label"]["token_pattern"])
    parts = cell.split(sep)
    return parts if len(parts) > 1 and all(tok.fullmatch(p) for p in parts) else [cell]


def validate_rows(rows: list[dict], mapping: dict, chain_id: str | None, dedupe: bool = True,
                  multi_label: dict | None = None) -> dict:
    """`chain_id` is the file's single chain, or None when the chain is stated per row
    (mapping["chain"]). An address is only valid on some chain, so there is no such thing as
    chain-less address validation: with neither, this refuses. (The pre-flight settles the
    chain before this is ever called.)

    Returns `valid_rows` with, aligned to it, `valid_chains` (each row's chain id) and
    `valid_labels` (the label tokens that became claims, or None when the row's own label is used)."""
    addr_field, chain_field = mapping.get("address"), mapping.get("chain")
    default_adapter = chains.get(chain_id) if chain_id else None
    if addr_field and default_adapter is None and not chain_field:
        raise InputError("address validation needs a supported chain; none was given or detected")
    # a claim needs something claimed about the subject: a category, or failing that a label. The
    # first non-empty one is the claim's label; an entity column is metadata, never required.
    label_fields = [f for f in (mapping.get("category"), mapping.get("label")) if f]
    keep_examples = config_io.load().preflight["rejected_examples"]

    valid_rows, valid_chains, valid_labels, rejected = [], [], [], []
    by_reason: dict[str, int] = {}
    per_chain: dict[str, dict] = {}
    checksums: dict[str, dict[str, int]] = {}
    seen_rows, seen_claims = set(), set()
    n_checked = n_invalid = n_trimmed = n_claims = 0

    def reject(i, reason, **extra):
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if len(rejected) < keep_examples:
            rejected.append(dict(row=i, reason=reason, **extra))

    for i, row in enumerate(rows):
        if dedupe:
            rk = _digest(*(f"{k}={v}" for k, v in row.items()))
            if rk in seen_rows:
                reject(i, "duplicate row")
                continue
            seen_rows.add(rk)

        raw = (row.get(addr_field) or "") if addr_field else ""
        address = raw.strip()
        if not addr_field or not address:
            reject(i, "empty address")
            continue

        row_chain = chain_id
        if chain_field:
            declared = (row.get(chain_field) or "").strip()
            # a blank chain value falls back to the file's chain; an explicit but unrecognised one is
            # never folded into it - it is a chain THEMIS cannot validate, and the row is rejected as such
            row_chain = chains.resolve_chain(declared) if declared else chain_id
        adapter = chains.get(row_chain) if row_chain else None
        if adapter is None:
            reject(i, "unresolved chain", address=address)
            continue

        n_checked += 1
        stats = per_chain.setdefault(row_chain, dict(checked=0, invalid=0, valid_rows=0))
        stats["checked"] += 1
        state_of = getattr(adapter, "checksum_state", None)
        state = state_of(address) if state_of else None
        if state_of:
            checksums.setdefault(row_chain, {}).setdefault(state or "not_an_address", 0)
            checksums[row_chain][state or "not_an_address"] += 1
        if not (state in ("not_encoded", "valid") if state_of else adapter.validate_address(address)):
            n_invalid += 1
            stats["invalid"] += 1
            reject(i, "invalid address", address=address, chain=row_chain)
            continue
        if address != raw:
            n_trimmed += 1      # outer whitespace only: counted and reported, the identifier itself is not edited
        subject = adapter.normalize_address(address)

        cell_field = next((f for f in label_fields if (row.get(f) or "").strip()), None)
        cell = (row.get(cell_field) or "").strip() if cell_field else ""
        if label_fields and not cell:
            reject(i, "missing label", address=address)
            continue
        tokens = split_label(cell, multi_label if cell_field == (multi_label or {}).get("column") else None)
        declared_src = declared_source(row, mapping)
        accepted = []
        for tok in tokens:
            claim_key = _digest(row_chain, subject, tok, declared_src)
            if dedupe and claim_key in seen_claims:
                continue
            seen_claims.add(claim_key)
            accepted.append(tok)
        if not accepted:
            reject(i, "duplicate claim", address=address)
            continue
        valid_rows.append(row)
        valid_chains.append(row_chain)
        valid_labels.append(accepted if len(tokens) > 1 else None)
        n_claims += len(accepted)
        stats["valid_rows"] += 1

    for st in per_chain.values():       # computed here, once, so no screen does arithmetic on a figure
        st["valid_share"] = (st["checked"] - st["invalid"]) / st["checked"] if st["checked"] else None
    return dict(valid_rows=valid_rows, valid_chains=valid_chains, valid_labels=valid_labels,
                rejected=rejected, rejected_by_reason=by_reason,
                n_input=len(rows), n_valid=len(valid_rows), n_rejected=len(rows) - len(valid_rows),
                n_claims=n_claims,
                n_identifiers_checked=n_checked, n_identifiers_invalid=n_invalid,
                n_identifiers_trimmed=n_trimmed,
                per_chain_checked={k: v["checked"] for k, v in per_chain.items()},
                per_chain_invalid={k: v["invalid"] for k, v in per_chain.items()},
                per_chain=per_chain, checksum_states=checksums)
