# THEMIS hardening log

Running record of the paper-vs-implementation audit and bug-fix loop against
`ICISHCT2026_Final_8_Section_Paper.pdf` (the most recently modified of
several paper drafts in the parent folder — treated as canonical over
`ICISHCT2026_Submission.pdf`, an earlier draft).

## Baseline (2026-09-18)

- `pytest` and `httpx` were not installed in the project's own `.venv`;
  installed both (`httpx` added to a new `test` extra in `pyproject.toml`).
- Backend suite before any changes: **87/87 passing**.
- `numpy` is absent, so `themis bootstrap` only ever exercised the
  pure-Python fallback path in this environment — not cross-checked against
  a numpy run.

## Paper reproduction

Reproduced via `themis audit`, `themis drift`, `themis explain`,
`themis bootstrap --both` against the bundled corpus. Exact matches:
corpus size (1,545,710 claims / 1,497,191 addresses), per-source counts,
corroboration (15,400 multi-dataset / 1.03%), agreement outcomes
(13,673 exact / 1,253 hierarchical / 342 entity-type / 109 licit-illicit),
Rodwald↔Ransomwhere circularity (7,508 addresses, 67.12% / 14.92%),
Montréal four-corpus reappearance (7,222 → 7,208 / 7,208 / 7,122), and
unresolved provenance (853,583 addresses, 57.0%).

One known, non-bug discrepancy: the ransomware-revenue drift table (A–D)
comes out $1–3 off Table 2 on totals around $1B–$1.4B. Verified independently
with Decimal summation that this is not a floating-point bug (Decimal and
float agree exactly on the bundled `revenue.csv.gz`); it's a pre-existing gap
between that bundled snapshot and whatever generated the paper's table,
present since the repo's first commit. Already covered by
`tests/test_paper_claims.py`'s `assertAlmostEqual(..., delta=5)` with a
"cent-level tolerance" comment.

## Bugs found and fixed

Each entry: root cause → fix → regression test. All fixes keep every
numeric constant that affects a scientific result in `themis/config/*.yml`;
none are hardcoded in analysis code.

### 1. Provenance independence silently dropped a source's second claim
**File:** `themis/provenance.py` (`address_independence`)
**Root cause:** roots were collected into `by_source: dict[str, str]` keyed
only by dataset name. When one dataset asserts two claims about the same
address that resolve to *different* roots (real and common — e.g. two
TagPack records from different creators), the second claim silently
overwrote the first, dropping a confirmed root.
**Impact:** 7,508 of 17,303 multi-claim addresses in the bundled corpus were
affected, including the exact address the README uses as its worked example
(`14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7`, documented as "4 datasets, 3 roots" —
the code produced 2). Fed into `target_audit.py`'s `confirmed_multi` /
`DISTINCT_PROVENANCE` classification and `taxonomy.py`'s `circular` flag.
Corpus-wide headline stats in `themis audit`/`drift` were *not* affected —
verified byte-identical before/after.
**Fix:** collect distinct `(source, root)` pairs instead of one root per
source.
**Test:** `tests/test_independence.py::test_one_source_two_claims_different_roots_both_count`

### 2. Unsupported-chain data was indistinguishable from non-crypto data
**Files:** `themis/ingest/detect.py`, `themis/ingest/pipeline.py`
**Root cause:** `detect()` only ever checked sampled values against
*registered* chain adapters (Bitcoin only in V1). An Ethereum attribution
CSV got `confidence=NONE`, identical to Iris/Titanic, and the pipeline
printed "This dataset does not appear to contain cryptocurrency attribution
data" for both.
**Fix:** added a chain-agnostic structural fallback
(`_looks_like_unrecognized_address`) that recognizes opaque, fixed-shape,
address-named tokens no adapter validates, without naming any specific
chain (no per-dataset branching — matches the existing "a new chain is a
new adapter" architecture). Wired a distinct
`UNSUPPORTED_CHAIN_MESSAGE` in the pipeline.
**Verified no false positives on:** Iris, Bitcoin OHLC price data, a
security log with 40-char hex hashes (column not address-named), and a
short `account_id`-style column (length gate excludes it).
**Tests:** `tests/test_ingest.py::test_unsupported_chain_address_shape_is_flagged_not_treated_as_non_crypto`,
`test_short_account_ids_are_not_mistaken_for_an_unsupported_chain`,
`test_unsupported_chain_file_gets_a_distinct_message_from_non_crypto`

### 3. Severe: every rejected upload 500'd via the web API
**File:** `themis/api.py` (`create_analysis`)
**Root cause:** `result["schema_mapping"]` (bracket access) on a pipeline
result that has no such key when ingestion stops early (non-crypto or, after
fix #2, unsupported-chain data) — `KeyError` inside the request handler.
**Impact:** the actual `/api/analysis` upload endpoint crashed with a 500 on
its two most basic guard-rail cases, even though the frontend
(`Upload.jsx`) already had correct handling for `preflight.stopped` and the
CLI/pipeline layer worked fine. Confirmed by starting the real backend and
uploading fixtures over HTTP before and after the fix.
**Fix:** `result.get("schema_mapping")`.
**Test:** `tests/test_api_export.py::TestUploadStoppedIngestDoesNotCrash` (three
cases: non-crypto, unsupported-chain, and a control valid-Bitcoin upload
that must keep succeeding) — first FastAPI `TestClient`-based test in the
suite.

### 4. Per-address currency flags used the live clock, not the frozen snapshot
**Files:** `themis/analysis.py` (`explain`), `themis/api.py`
(`_explain_in_workspace`, `analysis_address`)
**Root cause:** every corpus-wide freshness statistic correctly freezes
"today" to the corpus's `snapshot_date` (`report.build_report`), but the
per-address `explain()` path (CLI `themis explain`, and both API address
routes) never accepted or threaded an `as_of` parameter, so it always used
`datetime.date.today()`.
**Impact:** non-deterministic paper reproduction (the same archived corpus
could report an address as "stale" differently depending on when you ran
the command), and, in the product, the Address Inspector page could disagree
with the Corpus Audit summary of the same analysis if viewed on a later
date than the analysis was created.
**Fix:** `analysis.explain()` now accepts `as_of`, defaulting to
`corpus.snapshot_date`. API routes thread `ws.analysis_as_of_date` (the date
already stored on the workspace at analysis-creation time) through both
explain paths via a new `_as_of_date()` helper.
**Tests:** `tests/test_paper_claims.py::TestAsOfDate::test_explain_freezes_currency_flags_to_snapshot_date_by_default`,
`test_explain_honors_an_explicit_as_of_override`

### 5. CSV export had no formula/DDE-injection guard
**File:** `themis/api.py` (`_csv_response`)
**Root cause:** `normalized_claims.csv` writes `raw_label` and other fields
straight from attacker-controllable upload content (correct — STEP 23
preserves raw evidence verbatim internally), but the CSV writer emitted
those values unescaped. A label like `=SUM(A1:A10)` or `+CMD|'/C calc'!A0`
would open as a live formula in Excel/Sheets.
**Fix:** `_csv_safe_cell()` prefixes any cell starting with `=`, `+`, `-`,
`@`, tab, or CR with a single quote (standard OWASP CSV-injection
mitigation), applied once in the shared `_csv_response` writer.
**Test:** `tests/test_api_export.py::TestCsvExportInjectionGuard` (3 cases).

### 6. Hidden hardcoding: kappa threshold ignored its own config value
**File:** `themis/analysis.py` (`cohen_kappa`)
**Root cause:** `themis/config/thresholds.yml` already declares
`kappa_substantial_threshold: 0.4` with a docstring saying it drives which
pairs are reported as "substantial agreement" — but the code compared
against a hardcoded literal `0.4` instead of reading the config value, so
editing the config would silently do nothing.
**Fix:** read `_cfg.thresholds.get("kappa_substantial_threshold", 0.4)`.
**Test:** `tests/test_paper_claims.py::TestKappa::test_substantial_threshold_is_read_from_config_not_hardcoded`
(monkeypatches the threshold to 0.6 and confirms the reported pair set
actually changes).

### 7. UTF-8 BOM leaked into the address column name
**Files:** `themis/ingest/pipeline.py` (`load_csv`), `themis/corpus.py`
(`_open`)
**Root cause:** files were opened with the platform default encoding; a
leading UTF-8 BOM (common in Excel-exported CSVs) survived as part of the
*first column's name* (`"﻿address"` instead of `"address"`), which
still detects by luck (substring hint match) but silently breaks any
exact-name match — a `--map` override, a mapping echoed back to a caller.
**Fix:** open with `encoding="utf-8-sig"` (strips a BOM if present,
identical to utf-8 otherwise) in both the ingest loader and the corpus
loader.
**Test:** `tests/test_ingest.py::test_utf8_bom_does_not_leak_into_the_address_column_name`

### 8. Target-vs-reference audit mislabeled a directly-confirmed shared root as "unresolved"
**File:** `themis/target_audit.py` (`_address_status`)
**Root cause:** the per-address comparability status only ever assigned
`SAME_PROVENANCE` when the *corpus-wide containment heuristic*
(`discover_inheritance_candidates`) flagged every reference source as
`INFERRED` — a coarse signal that needs a large enough address overlap to
fire at all. It never checked whether the target's claim and the
reference's claim resolve to the identical *declared* root directly (e.g.
both configured as the same `fixed_root`), which `provenance.resolve()`
already establishes per claim with full confidence. A single shared address
with a directly-confirmed common root fell all the way through to
`RELATIONSHIP_UNRESOLVED` — actively misrepresenting a *known* relationship
as unknown.
**Impact:** Part P's canonical case "A → Root X, B → Root X" (apparent=2,
confirmed roots=1) produced the correct aggregate independence counters
(`shared_or_inherited_only`) but the wrong per-address status label,
which is what the Address Inspector / provenance UI actually shows.
**Fix:** added a direct root-intersection check —
`target_roots & ref_roots` minus unresolved roots — before falling through
to the distinct/unresolved branches. Deliberately *not* implemented via
`address_independence()`'s combined `circular`/`shared_root_count` fields:
those mix target-internal root sharing (the target asserting two claims
that happen to share a root, with no reference relationship at all) with
target↔reference sharing; a synthetic test confirms the chosen fix
correctly ignores target-internal-only sharing while the naive
`combo_indep["circular"]` approach would have false-positived on it.
**Tests:** `tests/test_target_audit.py::TestProvenanceIndependenceCases` — the
four canonical Part P cases (same root / different roots / one unresolved /
both unresolved) plus the target-internal-sharing false-positive guard,
run through the real `audit_target_against_reference()` using synthetic
`fixed_root` sources patched into both `provenance._cfg.sources` and the
derived `_EXACT_ROOTS`/`_PREFIX_ROOTS` ledger (patching the config dict
alone is not enough — `is_unresolved()`'s ledger is built once at import
time and does not observe later config changes; harmless in production
since config never changes post-startup, but a real trap for tests).

### Also: generic multi-level taxonomy hierarchy walk had no adversarial coverage
`themis/taxonomy.py`'s `classify_address`/`ancestors()` is written to walk
an arbitrary-depth category tree, but the bundled `taxonomy.yml` is only
ever 2 levels deep, so that code path was only ever exercised by the
incidental 2-level case. Added `tests/test_paper_claims.py::TestHierarchyAdversarial`
with a synthetic 3-level tree (monkeypatching `CATEGORIES`/`POLARITY`/`GENERIC`
together) proving: a genuine grandparent/grandchild pair reads as
refinement, but siblings under a shared non-root parent, and categories in
unrelated branches, do not — the check is structural (via `parent:` links)
rather than name-based. No code change was needed; this was a coverage gap,
not a bug.

### 9. `current_only` trust-rule predicate had the same wall-clock bug as #4
**Files:** `themis/trust/predicates.py` (`current_only`), `themis/analysis.py`
(`drift`)
**Root cause:** `current_only(claim, context)` called
`taxonomy.currency_flags(claim)` with no `today`, so it always used the live
wall clock rather than the corpus's frozen snapshot date — same bug class
as #4, in a different module. None of the four bundled paper-reproduction
trust-rule policies (`naive_union`/`address_dedup`/`inheritance_collapsed`/
`verified_only`) use `current_only`, so the paper's RQ3 drift table is
unaffected today, but the predicate is registered and available to any
custom policy on an uploaded dataset (matching PART X's "current only" test
category), and would have silently drifted for one.
**Fix:** `current_only` now reads `context.get("as_of")`;
`analysis.drift()` gained an `as_of` parameter (defaulting to
`corpus.snapshot_date`, same pattern as `explain()`) and threads it into
the policy-engine context.
**Tests:** `tests/test_trust_engine.py::TestCurrentOnlyIsDeterministic` (direct,
discriminating - dated claim, two different `as_of` values, opposite
results), `tests/test_paper_claims.py::TestAsOfDate::test_drift_threads_snapshot_date_into_a_current_only_policy`
(integration-level wiring check — the bundled revenue task's own claims
have no `lastmod` field, so this one can't discriminate the date value
itself, only that the parameter reaches the policy context without
raising).

## Test suite state

- Backend: **87/87 → 122/122** passing (35 new tests across 7 files, one new
  file `tests/test_api_export.py`). `numpy` is now installed in the venv,
  so this count includes the bootstrap suite running against both backends.
- Paper regression (`tests/test_paper_claims.py`): 42/42 → 49/49 passing.
- `tests/test_target_audit.py`: 2/2 → 7/7 passing.
- `tests/test_trust_engine.py`: 9/9 → 11/11 passing.
- Frontend production build: clean (one pre-existing bundle-size advisory,
  not a defect — not touched).
- Live API smoke test: paper-reproduction workspace creation, address
  explain, CSV export, and both upload-rejection flows (non-crypto,
  unsupported-chain) plus a valid-Bitcoin control upload — all exercised
  against the actual running FastAPI backend over HTTP, not just unit tests.

### 10. Malformed `mapping` JSON crashed the upload endpoint
**File:** `themis/api.py` (`create_analysis`)
**Root cause:** `json.loads(mapping)` on the optional schema-mapping-override
form field was uncaught. A request with invalid JSON, or valid JSON that
wasn't an object (e.g. a bare array), raised an unhandled
`JSONDecodeError`/`AttributeError` inside the request handler → 500.
**Fix:** wrapped in try/except, `HTTPException(400, ...)` for invalid JSON
and for JSON that isn't an object.
**Tests:** `tests/test_api_export.py::TestUploadInputValidation::test_malformed_mapping_json_is_a_clean_400`,
`test_mapping_that_is_not_a_json_object_is_a_clean_400`

### 11. Non-UTF-8 upload crashed the ingest pipeline
**File:** `themis/ingest/pipeline.py` (`load_csv`)
**Root cause:** the CSV loader opened files with a fixed `utf-8-sig`
encoding and no error handling; a file containing invalid UTF-8 byte
sequences (binary content, or genuinely non-UTF-8 text) raised an
unhandled `UnicodeDecodeError` deep inside `csv.DictReader` iteration —
uncaught all the way to a 500 via the web API, and an unhandled traceback
via the CLI.
**Fix:** added `errors="replace"` — invalid bytes decode to U+FFFD instead
of raising, so ingestion degrades to "no usable address column found"
(correctly reported as such) instead of crashing outright.
**Tests:** `tests/test_api_export.py::TestUploadInputValidation::test_non_utf8_upload_does_not_crash`,
`test_zero_byte_upload_does_not_crash` (already worked, confirmed no
regression)

### 12. Cluster bootstrap crashed on an empty corpus when numpy is installed
**File:** `themis/analysis.py` (`bootstrap`)
**Root cause:** with zero clusters (`K=0`, e.g. an empty corpus), the numpy
path computed `p = _np.full(K, 1.0 / K)` — a plain Python `1.0 / 0`,
`ZeroDivisionError`, before any numpy call. The pure-Python fallback path
avoided this *by accident*: `for _ in range(K)` with `K=0` never executes,
so `rng.randrange(K)` is never called and `vals` ends up correctly empty.
Two backends of the same function silently disagreed on whether this
crashes.
**How found:** numpy was not installed anywhere in this environment for
the whole session up to this point (`themis bootstrap` had only ever been
exercised via the pure-Python fallback), which is itself a gap worth
recording — installed it specifically to cross-check the bootstrap
implementation, and this is what that check turned up.
**Fix:** explicit `if K == 0: vals = []` guard ahead of the numpy/no-numpy
branch, stating directly what the no-numpy path already did implicitly.
**Test:** `tests/test_paper_claims.py::TestBootstrap::test_empty_corpus_does_not_crash_with_or_without_numpy`
**Also confirmed (not a bug, but worth recording):** with numpy now
installed, re-ran `themis bootstrap --both` and the full suite — every
existing bootstrap test passes against the numpy-accelerated path too.
Point estimates (deterministic) match the pure-Python run exactly;
confidence intervals differ slightly between backends even with the same
`seed=42`, because `random.Random` (Mersenne Twister) and
`numpy.random.default_rng` (PCG64) are different PRNG algorithms — seeding
only guarantees reproducibility *within* one backend, not bit-identical
results across both. Both intervals bracket the point estimate sensibly
and both show the upper bound's interval narrower than the lower bound's,
as the paper's methodology requires.

## API hardening sweep (also confirmed correct, no fix needed)

Invalid/unknown `analysis_id` returns a clean 404 with no stack trace on
every route that takes one (get, summary, address, export). Path-traversal
strings in `analysis_id` and export filenames (`../../etc/passwd`,
URL-encoded equivalents) 404 cleanly — Starlette's own path-segment routing
rejects them before any handler runs, and the export endpoint never touches
the filesystem based on the `name` parameter (it's compared against three
literal constants). An invalid `use_reference` form value gets FastAPI's
own built-in 422 validation error, not a crash. Tests:
`tests/test_api_export.py::TestUploadInputValidation::test_unknown_export_name_is_a_clean_404`,
`test_unknown_analysis_id_is_a_clean_404_everywhere`.

## Frontend / address-validation confirmations (no fix needed)

- Grepped the entire frontend for `dangerouslySetInnerHTML`/`innerHTML`/`eval`:
  none exist. Every attacker-controllable field (raw labels, etc.) renders
  through ordinary JSX text interpolation, which React auto-escapes — no
  XSS path found.
- Bech32 case handling (`themis/chains/bitcoin.py`) already correctly
  accepts all-lowercase and all-uppercase addresses and rejects mixed-case
  per BIP-173, but had no test for either — added
  `tests/test_bitcoin_adapter.py::test_all_uppercase_segwit_accepted` and
  `test_mixed_case_segwit_rejected`.

## Notable non-bug finding

The trust-policy engine (`themis/trust/`) is generic and fully tested in
isolation, but `analysis.drift()` — reproducing the paper's four
ransomware-revenue conditions — is currently its *only* real caller
anywhere in the codebase. PART X's "for arbitrary uploads: report surviving
claims and coverage" (applying a trust-rule policy to any ingested
dataset, not just the bundled revenue task) is not wired up yet. Not a bug
— the engine was clearly built generic on purpose (STEP 20/21's docstrings
say as much) — but a real gap between what the architecture supports and
what's reachable today.

## Explicitly not yet covered

External public dataset discovery/download and compatibility testing,
frontend browser-automation E2E, target-audit isolation stress tests beyond
what code reading and the Part P cases confirmed, persistence/restart
testing (the workspace store is in-memory by design — already labeled with
an `occam:` comment noting the upgrade path, not a bug), per-source
confidence-semantics research, and the full malicious-input matrix
(formula-injection *labels* at ingestion time rather than export, HTML/JS
strings, path-like strings, right-to-left text, etc.) beyond what was
spot-checked.
