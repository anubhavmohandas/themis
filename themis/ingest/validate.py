"""STEP 4 - input validation. Every rejected record is reported with a
reason and kept available for inspection; nothing is silently dropped.
"""
from __future__ import annotations
from .. import chains
from ..errors import InputError


def validate_rows(rows: list[dict], mapping: dict, chain_id: str | None, dedupe: bool = True) -> dict:
    """`chain_id` is required whenever an address column is mapped: an address
    is only valid on some chain, so there is no such thing as chain-less address
    validation. (The pre-flight settles the chain before this is ever called.)"""
    adapter = chains.get(chain_id) if chain_id else None
    addr_field = mapping.get("address")
    if addr_field and adapter is None:
        raise InputError("address validation needs a supported chain; none was given or detected")
    # a claim needs something claimed about the subject: a label, or failing that a category
    label_field = mapping.get("label") or mapping.get("category")

    valid_rows, rejected = [], []
    seen_rows, seen_claims = set(), set()
    n_checked = n_invalid = 0      # identifiers checked (after row-level dedupe) and how many failed

    for i, row in enumerate(rows):
        row_key = tuple(sorted(row.items()))
        if dedupe and row_key in seen_rows:
            rejected.append(dict(row=i, reason="duplicate row"))
            continue
        seen_rows.add(row_key)

        address = (row.get(addr_field) or "").strip() if addr_field else ""
        if not addr_field or not address:
            rejected.append(dict(row=i, reason="empty address"))
            continue
        n_checked += 1
        if not adapter.validate_address(address):
            n_invalid += 1
            rejected.append(dict(row=i, reason="invalid address", address=address))
            continue

        label = (row.get(label_field) or "").strip() if label_field else ""
        if label_field and not label:
            rejected.append(dict(row=i, reason="missing label", address=address))
            continue

        claim_key = (address, label)
        if dedupe and claim_key in seen_claims:
            rejected.append(dict(row=i, reason="duplicate claim", address=address))
            continue
        seen_claims.add(claim_key)
        valid_rows.append(row)

    by_reason = {}
    for r in rejected:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1

    return dict(valid_rows=valid_rows, rejected=rejected, rejected_by_reason=by_reason,
                n_input=len(rows), n_valid=len(valid_rows), n_rejected=len(rejected),
                n_identifiers_checked=n_checked, n_identifiers_invalid=n_invalid)
