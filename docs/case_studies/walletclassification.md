# Case study: WalletClassification

**Dataset role: UNRESOLVED-PROVENANCE CASE STUDY**

This is not one of THEMIS's seven reproducible corpus sources
(`themis/config/sources/*.yml`), and it never will be added as one from this
investigation. It is a worked example of what THEMIS does when a large
attribution dataset looks technically valid but its evidential provenance
cannot be established. No raw WalletClassification data ships with THEMIS or
this repository.

## Why this dataset stays a case study, not a source

- The local SQLite file THEMIS was given is truncated; only a partial
  recovery survives.
- The recovered addresses are technically valid Bitcoin addresses - address
  syntax validity was never in question.
- The label vocabulary strongly resembles BABD-13's.
- The recovered rows carry a `Source` field whose values include strings
  resembling WE (WalletExplorer), BABD, and Harvard.
- BABD-13's own documentation states that WalletExplorer is one of BABD-13's
  sources. That is a **documented dependency candidate**, not a verified
  exact lineage for this recovered file - THEMIS surfaces it as such (see
  `dependency_candidates` below) and never converts it into a fabricated
  independence count.
- Because of that documented dependency, WE / BABD / Harvard cannot be
  treated as three independent evidential roots just because they are three
  distinct strings in a `Source` column.
- Exact provenance semantics (what a `Source` value legally asserts about
  chain of custody) are not sufficiently documented for this recovered file
  to resolve any of the above.

Put together: **a dataset can contain valid identifiers, plausible labels,
and named source fields, and still not amount to forensically defensible
attribution.** That gap is the thing THEMIS exists to expose, and this case
study is the clearest example of it encountered so far.

## What THEMIS can establish

- SQLite file structure (tables, columns, keys) - `themis/ingest/sqlite_source.py`.
- Whether the file itself is intact - `sqlite_source.integrity_check()`.
- Recovered row count, for whatever subset of the file is readable.
- Bitcoin address syntax validity for every recovered row.
- The label/category vocabulary actually present in the recovered rows.
- Duplicate/conflicting-label structure *within* the recovered rows
  (`themis/ingest/relational.py:conflicts`).
- The presence of declared source-descriptor strings, and whether one
  declared-source string appears to textually cite another present in the
  same extraction (`relational.py:dependency_candidates`).

## What THEMIS cannot establish

- The full original corpus size - only the truncated file's own row count is
  ever reported; THEMIS never estimates or backfills an "original total."
- Complete dataset provenance - the recovery is partial and its chain of
  custody before reaching THEMIS is not documented.
- Independent source roots - a declared-source string is a claim, not a
  verified root (`relational.py:provenance_states`); WE/BABD/Harvard are
  DECLARED SOURCE DESCRIPTORS, not CONFIRMED PROVENANCE ROOTS.
- Verified label truth - a label is what the row says, not what was checked.
- Source accuracy - THEMIS has no independent means to verify a `Source`
  column's claims against reality.
- Investigative reliability as a single percentage - THEMIS deliberately
  never collapses this case into one number (see Phase 5's stopping rule
  against "0% reliable" / "unreliable dataset" framings; a rate would imply
  a denominator this case study does not have).

## Investigative interpretation

The dataset contains usable attribution records, but the evidence needed to
treat its source descriptors as independent forensic corroboration is not
established.

## How this shows up in THEMIS

- **Corrupt file, not yet recovered**: opening the original truncated file
  through the Database workflow fails `sqlite_source.integrity_check()`.
  `themis/ingest/relational.py:extract()` refuses to start analysis and
  returns `stopped=True` with a `database_corrupt` blocker before any table
  is even selected; the message is
  `preflight.yml: sqlite.integrity_gate_message`. THEMIS does not run
  `sqlite3 .recover` or any other automatic recovery.
- **Recovered subset, explicitly supplied**: once an analyst supplies an
  already-recovered, structurally valid SQLite file, extraction proceeds
  normally, but the analyst can attach free-text, caller-asserted context
  (never inferred by THEMIS) via `case_metadata` - see below. For this case
  study that context is, conceptually:

  | field | value |
  |---|---|
  | `analysis_origin` | `recovered_sqlite_subset` |
  | `integrity_status` | `source_file_truncated` |
  | `recovery_status` | `recovered_subset` |
  | `source_identity_status` | `partially_attributed` |
  | `provenance_resolution_status` | `unresolved` |
  | `limitations` | free text describing what was and wasn't recoverable |

  This is carried on `dataset_preflight.case_metadata` and rendered as a
  prominent "RECOVERED DATASET SUBSET - this analysis does not represent the
  complete original database" banner (`frontend/src/pages/Overview.jsx`).
- **Evidence profile**: the Overview page's "Evidence profile" section
  (populated for every relational/SQLite extraction, not only this case
  study) reports address validity, label coverage, provenance-state counts,
  whether independent corroboration is established, and any documented
  source-descriptor dependencies - reusing `relational_provenance`,
  `dependency_candidates`, and `dataset_profile`, all already generic,
  dataset-agnostic outputs.

## Generic support added for this case study

No WalletClassification-, BABD-, Harvard-, or WalletExplorer-specific logic
was added to production code. Two generic, dataset-agnostic mechanisms carry
this case study, and are equally usable by any future one:

1. **`themis/ingest/sqlite_source.py:integrity_check()` is now a gate, not
   just a display value.** `relational.extract()` calls it before doing any
   other work and refuses to start when the file is not `"ok"`.
2. **Optional case metadata**
   (`relational.py:CASE_METADATA_FIELDS`): `analysis_origin`,
   `integrity_status`, `recovery_status`, `source_identity_status`,
   `provenance_resolution_status`, `limitations`. An analyst may attach any
   subset of these (as free text, via the API's `case_metadata` form field
   or the Database page's "Case-study metadata (optional)" panel); THEMIS
   only carries and displays whatever is supplied - it never requires these
   fields for an ordinary CSV or SQLite analysis, never infers their values
   from data, and never scores them.

## Demo fixture

`scripts/generate_case_study_demo_db.py` builds a small SYNTHETIC SQLite
database reproducing the same pattern - valid addresses, multiple labels,
two declared-source strings where one textually names the other - without
redistributing any WalletClassification row. Run it and open the result
through the Database workflow to see the behavior above without needing the
real (and, in this case, truncated) file.

## Stopping rule

This case study is closed. No further recovery, disk-backed storage, or
provenance-root invention is planned for this dataset. If a clean,
authoritative copy of WalletClassification becomes available later, it
starts a new validation exercise from that raw source - it does not extend
this recovered-fragment analysis.
