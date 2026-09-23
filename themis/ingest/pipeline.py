"""STEP 23 - new dataset mode: upload -> crypto detection -> schema mapping
-> address validation -> claim normalization -> provenance extraction ->
reference-source comparison -> overlap/agreement/independence ->
freshness -> reliability profile.

Every stage that could not run says so explicitly (STEP 23's "impossible,
because ..."); nothing here fabricates a result for a dataset that lacks the
evidence to support it. An unrecognized `source_id` gets no provenance rule
from config/sources/ and therefore resolves UNRESOLVED by construction
(themis.provenance.resolve) - a brand-new dataset is never silently assumed
either identified or independent.

Loop 2 STEP 3: cross-source comparison is computed by `target_audit`, never
by unioning the target's claims into the reference corpus and re-running the
corpus-wide agreement/independence analyses - that would let reference-
reference relationships the target never touched leak into its numbers.
"""
from __future__ import annotations
import csv, gzip, hashlib

from .. import corpus as _corpus, analysis, target_audit, chains, config_io
from ..errors import InputError
from . import gating as _gating, preflight as _preflight, validate as _validate, claims as _claims

# The user-facing stop messages live with the pre-flight that decides them;
# re-exported so existing callers keep importing them from here.
NOT_CRYPTO_MESSAGE = _preflight.NOT_CRYPTO_MESSAGE
UNSUPPORTED_CHAIN_MESSAGE = _preflight.UNSUPPORTED_CHAIN_MESSAGE
CRYPTO_NON_ATTRIBUTION_MESSAGE = _preflight.CRYPTO_NON_ATTRIBUTION_MESSAGE


def load_csv(path: str) -> tuple[list[dict], list[str]]:
    # utf-8-sig strips a leading UTF-8 BOM if present (common from
    # Excel-exported CSVs) and is otherwise identical to utf-8, so a
    # BOM-free file is unaffected; without it the BOM survives as part of
    # the first column's *name* (e.g. "﻿address"), breaking any exact
    # match against it (a --map override, a later schema round-trip).
    # errors="replace" turns a genuinely non-UTF-8 upload (binary content,
    # another encoding entirely) into a readable-if-garbled file instead of
    # an unhandled UnicodeDecodeError - detection then correctly reports no
    # usable address column rather than the request crashing outright.
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def input_type_of(path: str) -> str:
    return "csv.gz" if str(path).endswith(".gz") else "csv"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stopped(source_id: str, pf: dict, rows: list, fieldnames: list, validation: dict | None = None) -> dict:
    """The result for a dataset that must not be analysed: no claims exist."""
    return dict(source_id=source_id, stopped=True, message=pf["message"], detection=pf["detection"],
                dataset_preflight=pf, analysis_states=_gating.blocked(pf), claims=[],
                validation=validation,
                basic_quality=dict(rows=len(rows), columns=fieldnames,
                                   empty_rows=sum(1 for r in rows if not any(r.values()))))


def ingest(path: str, source_id: str, mapping_override: dict | None = None,
          reference: "_corpus.Corpus | None" = None, sample_size: int | None = None,
          analysis_as_of_date=None, progress=None, *, semantics: dict | None = None,
          chain: str | None = None, confirmed: bool = False, original_filename: str | None = None) -> dict:
    """`mapping_override` is {role: column} (CLI `--map`, semantic ids or the
    legacy role names) and `semantics` is {column: semantic type} (the mapping
    screen). Either way the pre-flight re-validates the choice: a mapping can
    select columns, it can never waive validation. `chain` is a user-selected
    chain id; `confirmed` records that the user reviewed low-confidence mappings.

    `progress`, when given, is called as progress("start"|"complete", stage_id,
    detail) around each real stage so a caller (the API's job runner) can
    report genuine pipeline state. It changes nothing about the result."""
    def _p(event, stage, detail=None):
        if progress is not None:
            progress(event, stage, detail)

    if source_id in config_io.load().sources:
        # such an id would hand this upload the bundled source's provenance rule
        raise InputError(f"source id {source_id!r} is a bundled THEMIS reference source; choose another "
                         "id so the uploaded file is not given that source's provenance")

    _p("start", "parse")
    rows, fieldnames = load_csv(path)
    _p("complete", "parse", f"{len(rows):,} rows \u00b7 {len(fieldnames)} columns")

    _p("start", "detect")
    overrides = _preflight.overrides_from_roles(mapping_override, fieldnames)
    overrides.update(semantics or {})
    pf = _preflight.run(rows, fieldnames, filename=original_filename or str(path).rsplit("/", 1)[-1],
                        sha256=sha256_file(path), input_type=input_type_of(path), overrides=overrides,
                        chain=chain, confirmed=confirmed, sample_size=sample_size)
    detection = pf["detection"]
    _p("complete", "detect", f"{pf['dataset_type']} \u00b7 {pf['chain']['value'] or 'no chain'} \u00b7 {pf['status']}")
    if not pf["can_analyze"]:
        return _stopped(source_id, pf, rows, fieldnames)

    mapping, chain_id = pf["mapping"], pf["chain"]["value"]
    _p("start", "validate")
    validation = _validate.validate_rows(rows, mapping, chain_id)
    _p("complete", "validate", f"{len(validation['valid_rows']):,} of {len(rows):,} rows have a valid address")
    # the sample said the subject looked valid; every row is now checked. A file whose
    # identifiers mostly fail is not an attribution dataset, whatever its first rows held.
    floor = _preflight.cfg()["min_identifier_valid_rate"]
    n_chk, n_bad = validation["n_identifiers_checked"], validation["n_identifiers_invalid"]
    if not n_chk or (n_chk - n_bad) / n_chk < floor:
        pf["blockers"].append(dict(code="subject_invalid_full", message=(
            f"Only {n_chk - n_bad:,} of {n_chk:,} values in '{mapping['address']}' are valid {chain_id} identifiers "
            f"(minimum {floor:.0%}); no claims were created.")))
        pf.update(status="blocked", can_analyze=False, message=_preflight._message("blocked", "attribution_claims",
                                                                                   pf["blockers"], detection))
        return _stopped(source_id, pf, rows, fieldnames,
                        {k: v for k, v in validation.items() if k != "valid_rows"})
    _p("start", "normalize")
    claims = _claims.build_claims(validation["valid_rows"], mapping, source_id, blockchain=chain_id)
    _p("complete", "normalize", f"{len(claims):,} claims")

    capabilities = {"address_validation": True, "claim_normalization": True,
                    "internal_consistency": True}
    limitations = []

    basis = pf["currency_basis"]
    if basis is None:
        limitations.append("Staleness / currency not computed: no attribution timestamp (last updated or last "
                           "verified) is mapped. Other date columns are never used for it.")
    else:
        capabilities["freshness"] = True

    target_result = None
    _p("start", "compare")
    if reference is not None and claims:
        target_result = target_audit.audit_target_against_reference(
            claims, reference, analysis_as_of_date=analysis_as_of_date)
        capabilities["cross_source_comparison"] = True
        capabilities["provenance_extraction"] = True
        limitations.extend(target_result["limitations"])
        if getattr(reference, "sample_note", None):
            limitations.append("Reference corpus is a bundled sample, not the full published "
                               "corpus: cross-source figures above cover only what the sample "
                               "contains.")
    else:
        limitations.append("Cross-source comparison unavailable: no reference corpus was supplied.")
        limitations.append("Provenance extraction limited: this source has no declared "
                           "provenance rule, so every claim's root is UNRESOLVED by default.")
        fresh = analysis.freshness(claims, as_of=analysis_as_of_date) if basis else None
        target_result = dict(
            n_target_addresses=len({c["address"] for c in claims}), n_target_claims=len(claims),
            address_comparability={}, address_resolution={},
            profile=dict(
                data_quality=dict(available=True, target_addresses=len({c["address"] for c in claims}),
                                  target_claims=len(claims)),
                reference_comparability=_unavailable_dim("no reference corpus was supplied"),
                agreement=_unavailable_dim("no reference corpus was supplied"),
                provenance=_unavailable_dim("no reference corpus was supplied"),
                independence=_unavailable_dim("no reference corpus was supplied"),
                currency=(dict(available=True, **fresh) if fresh is not None
                         else _unavailable_dim("no attribution timestamp (last updated / last verified) is mapped")),
                evidence_class=target_audit.evidence_class_tally(claims),
            ),
            limitations=[], inheritance_candidates=[],
        )

    states = _gating.evaluate(pf, claims, target_result, reference)
    if basis is None:
        # every claim would be "currency-unknown": that is the absence of a figure, not a finding
        target_result["profile"]["currency"] = dict(available=False, state=states["staleness"]["state"],
                                                    reason=states["staleness"]["reason"])
    else:
        currency = target_result["profile"]["currency"]
        currency.update(state=states["staleness"]["state"], basis=basis)   # which field and rule produced these counts
    if states["conflicts"]["state"] != _gating.COMPUTED:
        target_result["profile"]["agreement"]["state"] = states["conflicts"]["state"]

    _p("complete", "compare",
       "provenance, reference comparison, independence and currency" if reference is not None
       else "internal checks only (no reference corpus)")
    summary = {k: v for k, v in validation.items() if k not in ("valid_rows", "rejected")}
    summary["rejected_examples"] = validation["rejected"][:_preflight.cfg()["rejected_examples"]]
    pf["validation"] = summary
    pf["analysis_states"] = states
    return dict(
        source_id=source_id, stopped=False,
        detection=detection, schema_mapping=mapping, dataset_preflight=pf, analysis_states=states,
        validation=summary,
        claims=claims, capabilities=capabilities, limitations=limitations,
        target_audit=target_result, reliability_profile=target_result["profile"],
    )


def _unavailable_dim(reason: str) -> dict:
    return dict(available=False, reason=reason)
