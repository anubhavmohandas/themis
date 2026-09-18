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

## Test suite state

- Backend: **87/87 → 102/102** passing (15 new tests across 4 files, one new
  file `tests/test_api_export.py`).
- Paper regression (`tests/test_paper_claims.py`): 42/42 → 47/47 passing.
- Frontend production build: clean (one pre-existing bundle-size advisory,
  not a defect — not touched).
- Live API smoke test: paper-reproduction workspace creation, address
  explain, CSV export, and both upload-rejection flows (non-crypto,
  unsupported-chain) plus a valid-Bitcoin control upload — all exercised
  against the actual running FastAPI backend over HTTP, not just unit tests.

## Explicitly not yet covered

External public dataset discovery/download and compatibility testing,
frontend browser-automation E2E, deeper taxonomy/polarity/hierarchy
adversarial tests, target-audit isolation stress tests beyond what code
reading confirmed, persistence/restart testing (the workspace store is
in-memory by design — already labeled with an `occam:` comment noting the
upgrade path, not a bug), per-source confidence-semantics research, and the
full malicious-input matrix (formula-injection *labels* at ingestion time
rather than export, HTML/JS strings, path-like strings, right-to-left text,
etc.) beyond what was spot-checked.
