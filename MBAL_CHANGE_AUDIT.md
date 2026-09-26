# MBAL change-blast-radius audit

> **Historical record.** Commit hashes, test counts, file states and open decisions below describe the repository when this report was written (for example: `HEAD` `30ffd0b`, no `LICENSE`, `demo_data/` tracked, the earlier paper pin). They were resolved afterwards. The final state is the `v1.0-paper` tag, described by `README.md`, `REPRODUCE.md` and `THIRD_PARTY_DATA.md`.

Date: 2026-09-24. Scope: every file changed or untracked in the working tree when the MBAL work ended, audited before
anything is committed. This audit made no commit, no `git add`, no revert and no code change.

## 0. Read this first: the tree changed while the audit ran

| time (IST) | event |
|---|---|
| 15:56 | audit starts: HEAD `30ffd0b`, 39 modified + 6 untracked files, nothing staged |
| 15:57:59 | **another session** edits `.gitignore` (adds the MBAL reports, `mbal_testdata/`, `mbal_evidence/`, `mbal_*.csv`, `dataset_10m_ads*.csv`) and stages 42 files, splitting `themis/config/api.yml` by hunk |
| 15:58:22 | **commit `c718c4c`**, "Multi-chain ingestion: EVM chains, per-row chain, chain-aware subjects, honest pre-flight states": 42 files, +1,614 / -246, on top of `30ffd0b`. Author Anubhav Mohandas. The message has no `Co-Authored-By` or "Generated with" trailer (checked). Local only: `main` is 1 ahead of `origin/main` (`30ffd0b`). |

Not this session's doing: the session that ran this audit only ran read-only commands. `ListAgents` shows three peer
sessions (`themis-17` busy). I cannot tell whether the author or a peer session made the commit.

Consequence: the instruction "do not commit yet, avoid one 45-file commit" was overtaken. The MBAL work is now **one
42-file commit**. Because it is unpushed, it can be re-split with `git reset --soft 30ffd0b` (or `--mixed`) without
touching any remote. I did not do that: it rewrites a commit another actor made. Section 9 is the split I recommend.

Still uncommitted after `c718c4c`: `THEMIS_RELEASE_READINESS_REPORT.md` (modified), `themis/config/api.yml` (one hunk),
`THIRD_PARTY_DATA_REDISTRIBUTION.md` (untracked): all pre-MBAL work (section 3). The two MBAL reports are untracked
**and now git-ignored** by the peer's `.gitignore` edit, which contradicts "reports may be tracked": author call (section 8).

Baseline: `30ffd0b` (2026-09-24 06:02:32 +0530, "Report: drop trailing blank line"), the last commit before the MBAL work
(first MBAL file mtime 13:31). Every "baseline" number below comes from `git archive 30ffd0b`, never from the working tree.
(My first baseline copy was taken after the peer commit and was therefore identical to HEAD; I discarded it and redid it.)

## 1. Worktree record (Phase 1)

Original state: HEAD `30ffd0b`; 39 modified tracked files (`git diff --numstat`: 1,019 insertions, 248 deletions in total) and 6 untracked
files = **45 files**. The largest diffs are listed below.

| file | +/- at start |
|---|---|
| themis/ingest/preflight.py | 274/51 |
| themis/ingest/validate.py | 117/41 |
| themis/api.py | 65/28 |
| themis/views.py | 53/27 |
| themis/config/preflight.yml | 47/4 |
| themis/ingest/pipeline.py | 42/8 |
| THEMIS_RELEASE_READINESS_REPORT.md | 71/0 (pre-MBAL) |
| themis/ingest/detect.py | 32/5 |
| themis/ingest/claims.py | 31/7 |
| themis/target_audit.py | 30/13 |
| tests/e2e/e2e.mjs | 31/0 |
| frontend/src/pages/Overview.jsx | 20/5 |
| tests/test_target_audit.py | 20/0 |
| themis/ingest/gating.py | 20/6 |
| themis/chains/base.py | 18/1 |
| frontend/src/pages/Home.jsx | 16/3 |
| themis/corpus.py | 15/1 |
| frontend/src/components/Preflight.jsx | 14/1 |
| frontend/src/pages/Address.jsx | 13/4 |
| themis/provenance.py | 9/0 |
| (19 more files, 2-9 lines each) | |

Untracked at start: `MBAL_PREFLIGHT_DEFECT_REPORT.md`, `MBAL_VALIDATION_REPORT.md`, `THIRD_PARTY_DATA_REDISTRIBUTION.md`,
`tests/test_multichain_generalization.py`, `themis/chains/evm.py`, `themis/config/chains.yml`.

## 2. File-by-file change matrix (Phase 2)

Legend. **Pre?** = the file had pre-MBAL edits. **MBAL?** = changed by the MBAL work. **Gen?** G generic / D dataset-specific.
**Sci / API / FE / Paper** = does the change alter scientific behaviour / API behaviour / frontend behaviour / the
paper reproduction (Y/N; "upl" = only uploaded-dataset analyses, never the frozen corpus). **Decision**: Keep / Split /
Revert(hunk). **Cause codes** are the Phase 4 names (section 4). **Commit** = intended commit in the section 9 plan
(K1..K8; P = pre-existing release/licensing).

Every row was decided from the file's actual diff, not its name. No row is dataset-specific.

### 2.1 Production code

| File | Status now | Pre? | MBAL? | Reason changed (cause) | Gen? | Sci | API | FE | Paper | Tests covering it | Decision | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| themis/chains/evm.py | new, committed | N | Y | EVM adapter: strict `0x`+40 hex, EIP-55 reported apart from validity, stdlib Keccak-256 (MULTI-CHAIN SUPPORT) | G | Y upl | Y (chains list) | N | N | TestEvmIdentifiers | Keep | K1 |
| themis/config/chains.yml | new, committed | N | Y | the 4 EVM chains, aliases, `network_suffixes` (MULTI-CHAIN SUPPORT). Chain names are config, not code | G | Y upl | Y | N | N | TestChainNames | Keep | K1 |
| themis/chains/__init__.py | committed | N | Y | registers `evm`, exports `resolve_chain` (MULTI-CHAIN SUPPORT) | G | Y upl | N | N | N | TestChainNames, test_relational alias test | Keep | K1 |
| themis/chains/base.py | committed | N | Y | `resolve_chain`/`_normalize_chain_name`: generic chain-name resolution, never guesses, testnets never resolve (CHAIN-AWARE IDENTIFIER VALIDATION) | G | Y upl | N | N | N | TestChainNames | Keep | K1 |
| themis/config_io.py | committed | N | Y | loads `chains.yml` with the same custom-tree fallback as `api.yml` (MULTI-CHAIN SUPPORT) | G | N | N | N | N | every chain test (loads config) | Keep | K1 |
| themis/ingest/detect.py | committed | N | Y | seeded uniform sampling over the whole input instead of the first rows; `sample_pairs`, `paired_sample` (ROW-ORDER-ROBUST PROFILING) | G | Y upl | N | N | N | TestSamplingIsOrderIndependent | Keep | K2 |
| themis/ingest/preflight.py | committed | N | Y | **6 causes in one file**: order-robust profile (row-position sequence test); value validation of user mappings (MAPPING VALIDATION); per-row chain (MULTI-CHAIN SUPPORT); multi-label detection `_label_structure` (MULTI-LABEL CLAIM HANDLING); evidence-class source column (SOURCE/METHOD SEMANTICS); new dataset states `attribution_like_unresolved`/`mapping_unresolved` (OTHER: honest verdicts). Removed `_chain_aliases` (replaced by `chains.resolve_chain`) | G | Y upl | Y (`dataset_state`, `established`, `label_structure`, `per_row`) | Y (Preflight.jsx) | N | TestMappingsAreJudgedOnValues, TestChainPerRow, TestMultiLabelCells, TestHonestStates, TestInvalidUserMappingIsTheMappingsProblem, TestNoStateLeaksBetweenRequests, test_preflight | Keep, **Split by hunk if re-committing** | K2 |
| themis/config/preflight.yml | committed | N | Y | thresholds for all of the above live in config: `sample_seed`, `profile_rows`, `confidence_grades`, `strict_value_semantics`, `identifier_excluded_semantics`, `source_class_max_distinct`, `multi_label`, `chain_column_min_resolved`; `attribution_entity` semantic. `confidence_categorical_max_distinct` removed | G | Y upl | N | N | N | same as preflight.py | Keep | K2 |
| themis/ingest/gating.py | committed | N | Y | provenance state INSUFFICIENT_DATA when the declared-source column has <= 12 distinct values (SOURCE/METHOD SEMANTICS) | G | Y upl | Y (gating states) | N | N | test_a_three_value_source_column_is_a_class_of_evidence_not_provenance | Keep; **see finding F1 (inline `10 *`)** | K2 |
| themis/ingest/validate.py | committed | N | Y | per-row chain validation; claim key = (chain, address, label, source); label-token split; counts kept, only `rejected_examples` rows kept; blake2b digests replace stored tuples (CHAIN-AWARE SUBJECT IDENTITY, MULTI-LABEL, MULTI-CHAIN, scale) | G | Y upl | Y (`validation` shape) | Y (Overview) | N | TestChainPerRow, TestMultiLabelCells, TestIdentifierIntegrityIsReportedNotRepaired, test_ingest | Keep | K3 |
| themis/ingest/claims.py | committed | N | Y | claim carries `blockchain`, `entity`, `label_cell`; address canonicalised by the chain's adapter; category-first label; token claims (CHAIN-AWARE SUBJECT IDENTITY, MULTI-LABEL) | G | Y upl | Y | Y | N | TestMultiLabelCells, TestEvidenceEntityAndSourceAreNotTruth | Keep | K3 |
| themis/ingest/pipeline.py | committed | N | Y | passes per-row chains/labels; strips per-row lists from stored results (`_PER_ROW`); `_validation_limitations` reports what full validation found (SUMMARY PAYLOAD / SCALE FIX + MULTI-CHAIN) | G | Y upl | Y | Y | N | TestResponsesStayBoundedAtScale, TestIdentifierIntegrityIsReportedNotRepaired | Keep; **see F2 (EIP-55 wording in generic module)** | K3 |
| themis/ingest/relational.py | committed | N | Y | SQLite path uses `resolve_chain`, category-first label, chain-aware claim key (same causes as validate.py, kept in step) | G | Y upl | N | N | N | test_relational | Keep | K3 |
| themis/provenance.py | committed | N | Y | `subject_key(claim)` = `chain:address`, bare address when the claim has no chain (CHAIN-AWARE SUBJECT IDENTITY) | G | Y upl | N | N | **N** (corpus claims carry no `blockchain`) | TestChainPerRow, test_target_audit | Keep | K3 |
| themis/corpus.py | committed | N | Y | `chain_of`, `for_subject`: a reference source declaring another chain never matches by string; chain `None` = unfiltered as before (CHAIN-AWARE SUBJECT IDENTITY) | G | Y upl | N | N | **N** (no caller in the paper path) | test_a_reference_source_on_another_chain_never_matches_by_string | Keep | K3 |
| themis/trust/drift.py | committed | N | Y | `group_by_address` keys by `subject_key` (CHAIN-AWARE SUBJECT IDENTITY) | G | Y upl | N | N | **N** (verified byte-identical `themis drift`) | via views/trust tests | Keep | K3 |
| themis/trust/predicates.py | committed | N | Y | `_siblings` looks up by `subject_key` (same) | G | Y upl | N | N | **N** | same | Keep | K3 |
| themis/target_audit.py | committed | N | Y | (a) inheritance containment restricted to the reference source's declared chain; (b) `DISTINCT_PROVENANCE` and "confirmed independent multi-root" need a resolved root **of the target's own**: reference-vs-reference independence is no longer credited to the target (PROVENANCE / INDEPENDENCE FIX) | G | **Y upl (changes counts)** | Y (audit fields) | Y (Overview) | N (paper path never calls it) | TestReferenceIndependenceIsNotCreditedToTheTarget + existing target_audit tests | Keep | K4 |
| themis/views.py | committed | N | Y | subjects keyed by `chain:address`; `sorted_claims` and `count_subjects` cached per workspace; chain in conflicts rows/export (CHAIN-AWARE SUBJECT IDENTITY, SUMMARY PAYLOAD / SCALE FIX) | G | Y upl | Y (`chain` fields, extra CSV column) | Y | N | TestAddressInspectorKeepsChainsApart, test_api_views | Keep | K5 |
| themis/api.py | committed | N | Y | `_client_result` drops per-address maps from job/extract responses; `_present_result` drops them from `/summary`; streamed `analysis_summary.json`; `chain` on the address inspector; `browser_hash_max_bytes` on `/health`; chain columns in `normalized_claims.csv` (SUMMARY PAYLOAD / SCALE FIX, ADDRESS INSPECTOR FIX, CHAIN-AWARE SUBJECT IDENTITY) | G | N | Y | Y | N | TestResponsesStayBoundedAtScale, TestAddressInspectorKeepsChainsApart, test_api_views | Keep, **Revert 1 hunk: line 27, unused `provenance as _prov` alias (F3)** | K5 |
| themis/config/api.yml | **mixed**, MBAL hunk committed, other hunk still dirty | **Y (1 hunk)** | Y (1 hunk) | hunk A `max_bytes` 256 MiB -> 1 GiB = **pre-MBAL, uncommitted**; hunk B `browser_hash_max_bytes` = MBAL, committed (SUMMARY PAYLOAD / SCALE FIX) | G | N | Y | Y | N | test_api_security (limit is read from config), TestResponsesStayBoundedAtScale | **Split (already split by the peer)** | A -> P, B -> K5 |

### 2.2 Frontend

All seven files are unchanged in the working tree versus `c718c4c`; the committed frontend builds (section 7).

| File | Pre? | MBAL? | Reason changed (cause) | Gen? | Sci | API | FE | Paper | Tests | Decision | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frontend/src/pages/Overview.jsx | N | Y | crashed on any upload with a rejected row (`v.rejected` is not in the summary at `30ffd0b`: `pipeline.py` there dropped it) -> uses `rejected_examples`; per-chain validity table; claims-vs-rows wording (GUI REJECTED-ROW FIX) | G | N | N | Y | N | e2e H1 | Keep | K6 |
| frontend/src/pages/Home.jsx | N | Y | browser hashes only files under the server's `browser_hash_max_bytes`, else shows the server hash; "Reset to THEMIS's inferred mapping"; `e.target.value = ""` so the same file can be re-picked (SUMMARY PAYLOAD / SCALE FIX, MAPPING VALIDATION). The `value = ""` hunk has no defect of its own named in the MBAL notes (F4) | G | N | N | Y | N | e2e H1, H2 | Keep, F4 = author call | K6 |
| frontend/src/pages/Claims.jsx | N | Y | Chain and Entity columns, chain in the address link, claim's own category text (CHAIN-AWARE SUBJECT IDENTITY) | G | N | N | Y | N | e2e A2 | Keep | K6 |
| frontend/src/pages/Address.jsx | N | Y | `chain` query parameter, "on more than one chain: choose" panel (ADDRESS INSPECTOR FIX) | G | N | N | Y | N | e2e A3, TestAddressInspectorKeepsChainsApart | Keep | K6 |
| frontend/src/pages/Conflicts.jsx | N | Y | key and link include the chain (CHAIN-AWARE SUBJECT IDENTITY) | G | N | N | Y | N | e2e | Keep | K6 |
| frontend/src/components/Preflight.jsx | N | Y | shows what THEMIS established for an attribution-like file; no chain picker for `per_row` (OTHER: honest verdicts, MULTI-CHAIN) | G | N | N | Y | N | e2e H1/H2 | Keep | K6 |
| frontend/src/lib/api.js | N | Y | `address(id, addr, chain)` (ADDRESS INSPECTOR FIX) | G | N | N | Y | N | e2e A3 | Keep | K6 |

### 2.3 Tests, fixtures, examples

| File | Status now | Pre? | MBAL? | Reason | Gen? | Decision | Commit |
|---|---|---|---|---|---|---|---|
| tests/test_multichain_generalization.py | new, committed | N | Y | 540 lines, 52 tests, every fixture synthetic (checked: no path, dataset name or file read) | G | Keep | K7 (or split by class across K1-K5) |
| tests/test_target_audit.py | committed | N | Y | +1 class pinning the independence fix | G | Keep | K4 |
| tests/test_preflight.py | committed | N | Y | 2 hunks: forces the sample to be the file head (the real sample is now uniform); `chains` list now contains `ethereum` | G | Keep, Split by hunk | K2 / K1 |
| tests/test_ingest.py | committed | N | Y | Ethereum-shaped "unsupported chain" fixture -> Tron-shaped, because Ethereum is now supported | G | Keep | K1 |
| tests/test_api_export.py | committed | N | Y | same fixture change | G | Keep | K1 |
| tests/test_relational.py | committed | N | Y | Ethereum row -> Tron row (no adapter); alias test now checks `resolve_chain` since `_chain_aliases` was removed | G | Keep | K1 |
| tests/e2e/e2e.mjs, tests/e2e/make_fixtures.py | committed | N | Y | steps H1/H2 and a synthetic multi-chain fixture (checksummed Bitcoin, case-folded Bitcoin, EVM) | G | Keep | K7 |
| examples/example_unsupported_chain.csv | committed | N | Y | Ethereum addresses -> Tron-shaped ones: the file's purpose is an unsupported chain | G | Keep | K1 |

### 2.4 Documentation and repository files

| File | Status now | Pre? | MBAL? | Reason | Decision | Commit |
|---|---|---|---|---|---|---|
| README.md | committed | N | Y | input-class table: EVM chains supported, new "attribution-like, schema unresolved" row, Tron as the unsupported example | Keep | K8 |
| REPRODUCE.md | committed | N | Y | test counts 489/135 -> 542/135 and 618/6 -> 671/6 (measured: 671 passed, 6 skipped, section 7) | Keep | K8 |
| examples/README.md | committed | N | Y | Ethereum -> Tron in the table | Keep | K8 |
| tests/e2e/README.md | committed | N | Y | "Last run 16/16" -> 18/18 | Keep | K8 |
| .gitignore | committed (by peer) | N | not in the original 45 | ignores the MBAL reports and MBAL data patterns. Correct for the data patterns; **contradicts "reports may be tracked"** | Keep patterns; reports = author call (section 8) | K8 |
| MBAL_VALIDATION_REPORT.md | untracked, now ignored | N | Y | the MBAL record (no addresses; one SHA-256 only) | author call | K9 |
| MBAL_PREFLIGHT_DEFECT_REPORT.md | untracked, now ignored | N | Y | defect list (no addresses) | author call | K9 |
| **THEMIS_RELEASE_READINESS_REPORT.md** | modified, uncommitted | **Y** | **N** (mtime 06:22, before MBAL began at 13:31) | +71 lines: section 26, the third-party redistribution loop | **not MBAL; leave alone** | P |
| **THIRD_PARTY_DATA_REDISTRIBUTION.md** | untracked | **Y** | **N** (mtime 06:22) | 37 KB licensing investigation; its only "MBAL"-matching text is the word "Kaggle" for the Elliptic dataset | **not MBAL; leave alone** | P |

## 3. Pre-existing work, separated (Phase 3)

Method: the tree had no snapshot from before MBAL. I used (1) file mtimes: a file untouched since 06:22, before the first
MBAL edit at 13:31, is pre-MBAL; (2) the session memory, which records the pre-MBAL dirty set as "readiness report,
api.yml, THIRD_PARTY_DATA_REDISTRIBUTION.md"; (3) reading every hunk. All three agree.

| item | evidence | in `c718c4c`? |
|---|---|---|
| `THEMIS_RELEASE_READINESS_REPORT.md` (+71) | mtime 06:22; content is section 26 (redistribution) | no, still dirty |
| `THIRD_PARTY_DATA_REDISTRIBUTION.md` | mtime 06:22; licensing matrix | no, still untracked |
| `api.yml` hunk A, `max_bytes` 268435456 -> 1073741824 | pre-MBAL per memory and per this task's brief; no other file or doc supports 1 GiB | no, still dirty |
| `api.yml` hunk B, `browser_hash_max_bytes` | written by the MBAL work; the peer staged it alone | yes |

The only mixed file is `api.yml`, and the peer already separated it correctly. **Consistency warning about hunk A:**
committed `THEMIS_RELEASE_READINESS_REPORT.md` line 133 says `upload.max_bytes = 256 MiB`, and the tests' comments say
256 MiB, so the dirty 1 GiB value disagrees with committed documentation. It is also the value that makes the scale
limitation in section 5 reachable (a 1 GiB file needs about 33 GB of RAM). Whoever owns hunk A should decide it together
with section 5.

`.gitignore` had no pre-MBAL edit.

## 4. Production changes, classified by cause (Phase 4)

"Would this bug exist without MBAL?" The required answer for a retained change is *YES, reproducible with a generic
synthetic fixture*. Each answer names the fixture that shows it.

| cause | files | exists without MBAL? |
|---|---|---|
| MULTI-CHAIN SUPPORT | evm.py, chains.yml, chains/*, config_io, preflight (per-row chain), relational | **CAPABILITY, not a bug.** Ethereum-as-unsupported was documented behaviour that tests pinned; it has been deliberately reversed. Reproducible with any synthetic EVM file (TestEvmIdentifiers, TestChainPerRow). See F5: this is a scope change the author should confirm |
| CHAIN-AWARE IDENTIFIER VALIDATION | base.resolve_chain, evm.py, validate.py | YES. `"Polygon-Mainnet"` never resolved; an EVM address is valid on every EVM chain so it cannot be guessed. TestChainNames, TestEvmIdentifiers |
| ROW-ORDER-ROBUST PROFILING | detect.py, preflight.py `_Profile` | YES. A file sorted so that the first 500 rows are unusable concluded a single chain / no subject; the same rows reversed gave another answer. TestSamplingIsOrderIndependent (sorted, shuffled and reversed orders agree) |
| MAPPING VALIDATION | preflight.py `_column_record`, preflight.yml | YES. Choosing "address = market timestamp" was accepted; the old check waived value validation for user choices. TestMappingsAreJudgedOnValues |
| MULTI-LABEL CLAIM HANDLING | preflight `_label_structure`, validate `split_label`, claims | YES as a capability, with a safe default: nothing is split unless the column's own values show it is a token list. TestMultiLabelCells (incl. "a comma inside a literal is not a separator", "hierarchical-looking labels are not split") |
| SOURCE/METHOD SEMANTICS | gating.py, preflight `_source_class`, claims (entity as metadata) | YES. A 3-value column such as heuristic/external/ground_truth was ticked as a declared source and counted as provenance. TestEvidenceEntityAndSourceAreNotTruth |
| CHAIN-AWARE SUBJECT IDENTITY | provenance.subject_key, corpus.for_subject, validate/relational claim key, views, drift, predicates, target_audit | YES once a file has more than one chain: the same string on two chains was one subject. TestChainPerRow, TestAddressInspectorKeepsChainsApart |
| PROVENANCE / INDEPENDENCE FIX | target_audit.py | YES, and the only change here that alters a scientific figure for a chain-free file: an upload with unresolved provenance next to two reference roots was credited "confirmed independent". TestReferenceIndependenceIsNotCreditedToTheTarget (no MBAL data, no chain field) |
| SUMMARY PAYLOAD / SCALE FIX | api.py, pipeline `_PER_ROW`, views cache, api.yml hunk B, Home.jsx | YES at scale. `/summary` carried both per-address maps (1.5 GB at 10M rows), job status carried per-row lists, the browser hashed a whole file in memory. TestResponsesStayBoundedAtScale for the payload; the size claims (1.5 GB -> 32 KB) come from the recorded 10M run, not from a re-run |
| ADDRESS INSPECTOR FIX | api.py, Address.jsx, api.js | YES once chains exist. Note: the "inspector silently dropped its chain argument" defect noted in memory was in the MBAL work's own in-progress edit, not in `30ffd0b`; only the chain-aware inspector is retained |
| GUI REJECTED-ROW FIX | Overview.jsx | **YES, pre-existing bug at `30ffd0b`**: `pipeline.py` there removed `rejected` from the summary while `Overview.jsx` read `v.rejected.slice`, so any upload with a rejected row blanked the page. e2e H1 |
| OTHER: honest dataset states | preflight.py, Preflight.jsx | YES: a file with an attribution-shaped schema but unresolvable identifiers was labelled "not attribution data" |

**Nothing retained exists only because the dataset is MBAL.** No change is marked REVERT-OR-REDESIGN.

## 5. Production special-case search (Phase 5)

Searched `themis/` (`*.py`, `*.yml`) and `frontend/src/` for: `MBAL`, `dataset_10m_ads`, `ground_truth`, `heuristic`, `external`,
`ethereum_mainnet`, `bnb_chain_mainnet`, `polygon_mainnet`, `avalanche_c_chain`; and, repository-wide, `MBAL|dataset_10m|yidong|bcra|kaggle`.

| term | hits | verdict |
|---|---|---|
| `MBAL`, `dataset_10m_ads`, `yidong`, `bcra` | **0 in `themis/`, `frontend/`, `scripts/`, `run.py`, `pyproject.toml`**. Only `.gitignore` (the data-exclusion patterns) | clean |
| `kaggle` | `THIRD_PARTY_DATA_REDISTRIBUTION.md` (about Elliptic; pre-MBAL) | unrelated |
| `ethereum_mainnet`, `bnb_chain_mainnet`, `polygon_mainnet` | 0 | clean |
| `avalanche_c_chain` | `themis/config/chains.yml:25`, an alias in the generic chain config | legitimate: chain aliases belong in that file |
| `ground_truth` | `analysis.py:401,430`, `corpus.py:198`, `paper/experiments.py:416`, `paper/reproduce.py:67,80`: all the paper's `demo_data/ground_truth.csv` anchor set, unchanged | unrelated to MBAL's `source` values |
| `heuristic` | `taxonomy.py:95-149`, `claims.py:11,35,97` (the pre-existing `heuristic` claim field), `corpus.py:21`, `cli.py:1`; **added lines** `api.py:1128` (export column list) and `claims.py:267` (`default_heuristic` argument pass-through) | the field name, not the MBAL value "heuristic"; nothing interprets a source value of that name |
| `external` | `target_audit.py:235,246` (message text "no external public reference"), `trust/predicates.py:5` (comment) | unchanged prose |
| **MBAL-style values in code paths** | none. "heuristic / external / ground_truth" appear only as data in `tests/e2e/make_fixtures.py` (synthetic fixture rows) | fixtures, not logic |

Two genericity findings that are not MBAL names but do matter:

* **F1, an inline scientific constant** (violates the standing "no hardcoding, constants go in `config/*.yml`" rule):
  `themis/ingest/gating.py:44` and `themis/ingest/preflight.py:715` both hard-code `> 10 * distinct` (rows per distinct
  source value before a source column is "a class of evidence"). It also lives in **two places that must agree**. Fix: one
  key beside `source_class_max_distinct` in `preflight.yml`, read in both places. Not applied: it changes committed code.
* **F2:** `pipeline._validation_limitations` names "EIP-55" in a chain-agnostic module. It is keyed off the adapter's
  `checksum_state`, so it works, but a future chain with its own checksum would print EVM wording. Cosmetic.

## 6. Paper impact (Phase 6)

**Static reachability.** The frozen paper path (`themis drift|anchors|explain|bootstrap|audit`, `reproduce-paper`) reaches
changed code in only two places: `trust/drift.py::group_by_address` and `trust/predicates.py::_siblings`, both now keyed by
`provenance.subject_key`. Corpus claims have no `blockchain` field (`corpus.FIELDS` = address, source, raw_label, canon,
polarity, prov_family, lastmod, heuristic, subcat), so the key is the bare address exactly as before. Nothing under
`themis/paper/`, `cli.py` or `analysis.py` imports `ingest`, `views`, `api` or `target_audit`.

| question | answer |
|---|---|
| alter the seven-source corpus? | No: `scripts/build_corpus.py` and the adapters are untouched; corpus claim keys were never the upload key |
| alter claim identity? | Only in uploads: (chain, address, label, declared source). The frozen corpus never used that key |
| alter taxonomy? | No: `taxonomy.py`, `taxonomy.yml` untouched. Category-first label choice affects uploads only |
| alter provenance? | Uploads only (source-class gating). `provenance.resolve` and every `config/sources/*.yml` are untouched |
| alter independence? | Uploads only, and it lowers a previously over-credited figure (`target_audit`). Paper independence is `provenance.address_independence`, untouched |
| alter agreement/conflict? | Uploads only (subject key) |
| alter identifier validity? | Uploads only: EVM validity added; Bitcoin validation is unchanged |
| alter output ordering? | Uploads only (`claims` paging sorts by address, chain, source) |

**Measured.** Ran on `git archive 30ffd0b` (baseline) and on the current tree, same interpreter, same `demo_data/` sample:

| command | baseline `30ffd0b` vs current | vs `expected_output/` |
|---|---|---|
| `themis drift` | byte-identical | match |
| `themis anchors` | byte-identical | match |
| `themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7` | byte-identical | match |
| `themis bootstrap --both` | byte-identical | match |
| `themis audit` | byte-identical | **differs on line 1 (the `note:` sentence)**, same at baseline |
| `themis taxonomy` | byte-identical | match |
| `themis sources` | byte-identical | **differs at the Schnöring `citation` line**, same at baseline |
| `themis reproduce-paper` | identical verdicts: 20 PASS / 0 FAIL / 9 NOT REPRODUCED, Figure 1, Table 2, Figure 2 PASS, `PAPER ↔ THEMIS: BLOCKED` (exit 3) | n/a |

In the two `reproduce-paper` artifact directories all 39 numeric outputs (`paper_metrics.json`, `table1/2`, `drift`, `anchors`,
`bootstrap_*`, `overlap_matrix`, `currency`, `diagnostics`, `fig*_data`, ...) are byte-identical. The files that differ are
only run id, commit id, absolute paths, timings, and PDF-layer status (the baseline archive has no PDF, which is
gitignored): environment, not results.

**The pre-MBAL `expected_output/audit.txt` mismatch is separate and is not MBAL's.** `themis audit` prints
"...including the 15,400 multi-dataset addresses it held when it was drawn, before WatchYourBack's #-prefixed addresses
were joined..." while the frozen `expected_output/audit.txt` still has the older "...including every one of the 15,400
multi-dataset addresses..." sentence. It is the same at `30ffd0b` and `expected_output/` is unchanged since
`82883c7`. The Schnöring `citation` line in `themis sources` is a second stale frozen line of the same origin; it was not
mentioned in earlier notes. Neither is a paper number.

`BLOCKED` with a bundled sample is the documented pre-existing state (required corpus-wide input is not
redistributed), not a regression.

## 7. Verification on the committed tree (Phase 13)

| step | result |
|---|---|
| `python -m pytest` | **671 passed, 6 skipped, 2 warnings, 151 subtests passed** (132 s). Matches the `REPRODUCE.md` figure. It ran with the dirty `max_bytes = 1 GiB` hunk in place (no test depends on the value) |
| `npm ci` (frontend, clean copy of HEAD) | ok |
| `npm run build` | ok. Bundle 503.39 kB vs 499.56 kB at `30ffd0b` (+3.8 kB, +0.8%): the JS chunk crossed Vite's 500 kB warning; the warning is new, the size is trivial |
| `npm audit` | found 0 vulnerabilities |
| browser E2E (Playwright, API on :5001, `vite preview` on :4173, real Chromium) | **18/18** including H1 (multi-chain, rejected rows) and H2 (invalid mapping) |
| paper commands | section 6 |

Not verified: intermediate states of any re-split (section 9); I did not build the commits. Servers I started for E2E were
stopped afterwards. `reproduce-paper` wrote `results/reproduction/20260924T103309Z-c718c4c/` (gitignored).

## 8. Scale, memory, large queries, hygiene

### 8.1 Where the memory goes (Phase 7)

Measured with `tracemalloc` on a synthetic 200,000-row, 5-column file shaped like the MBAL run (chain, address,
categories, entity, source) and the bundled reference sample. Python-object bytes per input row:

| stage | bytes / row | at 10M rows | note |
|---|---|---|---|
| CSV parse into `list[dict]` | 461 | 4.6 GB | one dict per row |
| pre-flight | 4 | ~0 | samples 500 values per column |
| validation (retained) | 47 | 0.5 GB | `valid_rows` list, chain and label lists; **peak +235 B/row (2.3 GB)** while the blake2b dedupe sets exist, then released |
| canonical claims | **1,152** | **10.2 GB** (8.86M claims) | ~25 keys/claim, mostly unique strings (uuid `claim_id`, `raw_address` AND `address`, raw and canonical label) |
| reference comparison | 171 retained, **664 peak** | 1.5 GB / **5.9 GB** | per-subject comparability, resolution and independence rows; the reference sample itself is a fixed 288 MB (a full-corpus `THEMIS_OBSERVATIONS` reference adds its own multi-GB) |
| workspace caches (sorted claims, subject count, address index) | 10 | 0.1 GB | list of pointers only |
| serialization / frontend payload | n/a | 32 KB `/summary`, 295 KB job status (recorded) | bounded, not proportional to rows |
| exports | streaming | n/a | see 8.2 |

Sum of Python objects at the compare peak is roughly 20-22 GB; CPython allocator overhead and fragmentation take it to the
recorded **24.7 GB resident for 810.8 MB / 10,000,000 rows (about 2.5 KB per row, about 30 GB of RAM per GB of CSV)**.

* **Is 24.7 GB expected from the current architecture?** Yes. It is the in-memory design (`load_csv` returns every row as a
  dict, every claim is a dict, `WorkspaceStore` is an in-process dict). It is not a leak.
* **Avoidable duplication?** Some, all pre-existing, none introduced by MBAL: (a) `rows` and `valid_rows` stay alive
  through claim building and reference comparison although nothing reads them after `build_claims` (about 60% of the parse
  cost is freed by dropping them: 28 of 46 MB per 100k rows, roughly 2.8 GB of 24.7 GB, ~11%); (b) the upload's raw
  `bytes` (0.85 GB) stays referenced for the job because `_hash_bytes(data)` runs at the end; (c) repeated strings
  (`chain`, `source`, `canon`, `polarity`, label tokens) are separate objects per claim, not interned. Together perhaps
  15-25% of peak. MBAL's own changes added no full-size copy: the dedupe sets went from tuples to 16-byte digests (a
  saving), and `entity`/`label_cell` add two keys per claim.
* **Does `/summary` still materialize full claim structures?** No. `_present_result` drops `claims` and both per-address
  maps; recorded response 32 KB at 8.86M claims. `analysis_summary.json` does (8.2).
* **Could ordinary machines OOM before the 1 GiB limit?** **Yes, by a wide margin.** At about 30 GB RAM per GB of CSV,
  the committed 256 MiB limit corresponds to about 8 GB of RAM, a 16 GB machine is exhausted near 0.5 GB of input, and
  only about 1 GiB on a 32 GB machine. The uncommitted 1 GiB `max_bytes` bounds the file, not the memory. The bound is on
  rows, not bytes (short rows put more rows in a GB).

**No obvious redundant-copy defect was introduced by the MBAL work, so nothing was changed.** The available fixes ((a)
`del rows`/`valid_rows` after normalisation, (b) release `data`, (c) `sys.intern`) are optimisations of a pre-existing
design, worth ~15-25%, and would not change the conclusion. Freeing memory a caller still names is a real edit in
`pipeline.py`/`api.py`, which this audit did not start.

> **KNOWN SCALE LIMITATION.** THEMIS analyses an upload entirely in memory: about **2.5 KB of RAM per input row** (24.7 GB
> for 10,000,000 rows). Recommendation: keep `upload.max_bytes` at the committed 256 MiB (about 3.3 million rows of that shape,
> about 8 GB RAM) rather than 1 GiB; add a configurable `upload.max_rows` (not bytes) checked while the CSV is read, refused
> with a clear HTTP 413-style message; and show a warning above a smaller row count that states the estimate ("about N GB
> of RAM"). A disk-backed store (the `WorkspaceStore` note already says "swap for a persistent store") is the real fix and
> is not built.

### 8.2 Large queries and exports (Phase 8)

| observation | classification | reasoning |
|---|---|---|
| first Claims query ~37 s | **EXPECTED CURRENT ARCHITECTURE LIMITATION** (improved by MBAL: it was a 10-19 s re-sort on **every** page) | one-time sort of 8.86M claim dicts plus one pass for the distinct-subject count, then cached per workspace (1.8 ms after). Cheap improvement, not a bug: compute both at job completion instead of first request |
| first Trust query ~76 s | **EXPECTED CURRENT ARCHITECTURE LIMITATION, with a probable but unprofiled avoidable component** | `views._context` builds one list per subject and concatenates reference claims (`cs + list(ref.for_subject(...))`), then every rule runs a pass; 3.2 s afterwards. I did not profile the 76 s; do not call any part of it a defect without a profile |
| `analysis_summary.json` multi-GB | **BY DESIGN, and test-pinned; not a defect of the change** | see below |

**Should "summary" include every claim?** By the current contract, yes: `Export.jsx` describes it as "Meta, the canonical
result object and the audit trail: the same object every screen renders", and the pre-existing (unmodified by MBAL)
`test_api_views.py::test_stored_result_and_export_keep_the_claims` asserts `result.claims` is in the export.
`normalized_claims.csv` already gives every claim in a scalable format, so the JSON holds them a second time, plus both
per-address maps. **Recommendation, not applied:** keep the semantics (the export is a documented, tested contract); add a
lean variant (what `_present_result` returns, tens of KB) only if the author wants one, under a **new** name, and document
that the full export grows to gigabytes and streams. The MBAL change already stopped it being built as one string.

### 8.3 Data hygiene (Phase 9)

| check | result |
|---|---|
| `dataset_10m_ads.csv`, `mbal_100k_*.csv`, `mbal_edge_cases.csv`, `mbal_testdata/`, `mbal_evidence/` | none tracked; none in `c718c4c`. They live in `Claude outputs/mbal_testdata` and `mbal_evidence`, outside the repository, and are now excluded by `.gitignore` patterns |
| data-like files in `c718c4c` | exactly one: `examples/example_unsupported_chain.csv`, four Tron-shaped rows, synthetic |
| MBAL addresses in the commit | the 2 distinct `0x`+40-hex literals added by the commit were compared with all three local MBAL CSVs: **0 matches**. No Base58/bech32 literals were added |
| the two MBAL reports | no addresses; the only long hex string is a SHA-256; no absolute paths |
| screenshots, temporary JSON, full exports | none tracked (`mbal_evidence/` holds them, outside the repo) |
| local-only note | the Tron-shaped test and example addresses are well-known public addresses (e.g. a USDT contract), not MBAL rows; they replace Ethereum ones that were equally public |

### 8.4 Untracked files (Phase 10)

| file | necessary? | generic? | tested? | track? |
|---|---|---|---|---|
| themis/chains/evm.py | yes (the adapter) | yes | TestEvmIdentifiers (Keccak against published vectors, EIP-55) | tracked in `c718c4c` |
| themis/config/chains.yml | yes; also in `pyproject` package-data glob `config/*.yml` so it ships | yes | TestChainNames | tracked in `c718c4c` |
| tests/test_multichain_generalization.py | yes | yes, all fixtures synthetic | it is the tests | tracked in `c718c4c` |
| MBAL_VALIDATION_REPORT.md | documentation only | n/a | n/a | **author call**: the peer's `.gitignore` says no |
| MBAL_PREFLIGHT_DEFECT_REPORT.md | documentation only | n/a | n/a | **author call** |
| THIRD_PARTY_DATA_REDISTRIBUTION.md | pre-MBAL licensing work | n/a | n/a | not part of this audit |

Recommendation on the reports: both are safe to track (no rows, no addresses). If they are tracked, the four
patterns `mbal_testdata/`, `mbal_evidence/`, `mbal_*.csv`, `dataset_10m_ads*.csv` stay ignored and the two `/MBAL_*.md` lines are removed.

### 8.5 Accidental changes (Phase 11)

Reverted: **0**. I found one hunk that fails the "clear MBAL relationship" test and one that is arguable. Neither was
reverted: both are in a commit made by another actor, and reverting means a new commit or a history rewrite.

* **F3, revert candidate:** `themis/api.py:27` adds `provenance as _prov` to an import; `_prov` is referenced nowhere. Dead alias.
* **F4, author call:** `frontend/src/pages/Home.jsx` `e.target.value = ""` on the file input. Harmless and probably
  wanted (re-choosing the same file), but no MBAL defect names it.
* **F5, scope, not a hunk:** `themis/cli.py:534` still describes THEMIS as auditing "public Bitcoin attribution labels", while
  uploads now validate four EVM chains. The reference corpus and the paper stay Bitcoin-only, which is what the code does
  (a non-Bitcoin claim never matches a Bitcoin reference source). Wording and scope are the author's.

## 9. Proposed commit plan (Phase 12)

Reality first: everything is one commit (`c718c4c`), unpushed. To split it: `git reset --soft 30ffd0b`, then stage explicit
paths (never `git add -A`; a peer session shares the tree), one commit per row. Do not do this while another session is
mid-commit. I did not verify that each intermediate commit passes the test suite; run `pytest` at each step, or `git rebase
--exec`.

| # | commit | files | purpose | scientific effect | paper effect | tests |
|---|---|---|---|---|---|---|
| K1 | Chain adapters and generic chain-name resolution | `themis/chains/{__init__,base,evm}.py`, `themis/config/chains.yml`, `themis/config_io.py`; fixture updates in `tests/test_ingest.py`, `tests/test_api_export.py`, `tests/test_relational.py`, one hunk of `tests/test_preflight.py` (chains list), `examples/example_unsupported_chain.csv` | EVM identifiers validated strictly; chain names resolve without guessing | Ethereum-family uploads become analysable instead of "unsupported chain" | none | those test edits; `test_multichain_generalization` classes `TestEvmIdentifiers`, `TestChainNames` if split |
| K2 | Pre-flight: order-independent profiling, value-validated mappings, honest states | `themis/ingest/{detect,preflight,gating}.py`, `themis/config/preflight.yml`, other `tests/test_preflight.py` hunk | sample uniformly; a mapping cannot waive value checks; per-row chain; multi-label detection; evidence-class source; attribution-like verdict | uploads only: which columns are inferred, when analysis is blocked | none | `TestSamplingIsOrderIndependent`, `TestMappingsAreJudgedOnValues`, `TestHonestStates`, `TestInvalidUserMappingIsTheMappingsProblem`, `TestNoStateLeaksBetweenRequests`. `preflight.py` mixes six causes: use `git add -p` or accept one commit. **Fix F1 (`10 *` to config) here** |
| K3 | Chain-aware subject identity and claim construction | `themis/{provenance,corpus}.py`, `themis/trust/{drift,predicates}.py`, `themis/ingest/{validate,claims,pipeline,relational}.py` | (chain, address) subject; per-row chain validation; multi-label tokens; entity as metadata; bounded validation output | uploads only; frozen corpus keys unchanged | none: `drift`/`predicates` verified byte-identical | `TestChainPerRow`, `TestMultiLabelCells`, `TestEvidenceEntityAndSourceAreNotTruth`, `TestIdentifierIntegrityIsReportedNotRepaired`, `TestLogicalCsvRecords` |
| K4 | Independence fix | `themis/target_audit.py`, `tests/test_target_audit.py` | reference-vs-reference independence is not credited to a target with no resolved root of its own | **lowers a figure** for uploads that were over-credited; the only scientific-figure change | none (paper path never calls it) | `TestReferenceIndependenceIsNotCreditedToTheTarget` |
| K5 | Large-analysis API and view correctness | `themis/api.py` (minus the F3 alias), `themis/views.py`, `themis/config/api.yml` hunk B | bounded summary/job payloads, cached claims sort, streamed export, chain-aware inspector | none | none | `TestResponsesStayBoundedAtScale`, `TestAddressInspectorKeepsChainsApart` |
| K6 | Frontend | the 7 `frontend/src` files | reject-row crash fix, chain columns, chain-aware inspector, reset mapping, browser-hash limit | none | none | e2e |
| K7 | Generic regression and browser tests | `tests/test_multichain_generalization.py` (or split into K1-K5), `tests/e2e/{e2e.mjs,make_fixtures.py}` | pin every rule above with synthetic fixtures | none | none | itself |
| K8 | Docs and ignore rules | `README.md`, `REPRODUCE.md`, `examples/README.md`, `tests/e2e/README.md`, `.gitignore` | input-class table, test counts, e2e count, data-exclusion patterns | none | none | n/a |
| K9 | (optional) MBAL reports | the two MBAL reports | record | none | none | n/a. Needs the two `/MBAL_*.md` `.gitignore` lines removed |
| P | **Pre-existing, separately** | `THEMIS_RELEASE_READINESS_REPORT.md`, `THIRD_PARTY_DATA_REDISTRIBUTION.md`, `api.yml` hunk A | release/licensing record; upload limit | none | none | the `max_bytes` value needs the section 8.1 decision; commit it alone, or drop it back to 256 MiB |

Dependencies: K1 <- K2, K3; K2 <- K3 (the pipeline reads `pf["label_structure"]`, `validate` reads `preflight.multi_label`);
K3 <- K4, K5 (`subject_key`, `for_subject`); K5 <- K6 (fields the UI reads).

## 10. Findings needing an author decision

| id | finding | severity | proposed handling |
|---|---|---|---|
| **A1** | the MBAL work was committed as one 42-file commit by another actor while this audit ran | process | keep as is, or re-split (section 9) before pushing; it is not pushed |
| **A2** | `max_bytes` 1 GiB (uncommitted, pre-MBAL) contradicts the committed 256 MiB documentation and needs ~33 GB RAM | **high for anyone running the API on a normal machine** | keep 256 MiB; add `max_rows`; see 8.1 |
| **A3** | reports ignored vs tracked | low | author call |
| F1 | inline `10 *` scientific threshold in two places (`gating.py:44`, `preflight.py:715`) | medium (breaks the no-hardcoding rule; two copies) | move to `preflight.yml` |
| F3 | dead import alias `_prov` (`api.py:27`) | trivial | delete the alias |
| F5 | CLI/README wording says Bitcoin; scope now includes EVM uploads | low | wording call |
| — | `expected_output/audit.txt` and `sources.txt` stale frozen lines | pre-existing, **not MBAL** | separate |

## 11. Final counts

| measure | value |
|---|---|
| original changed-file count | **45** (39 modified tracked + 6 untracked) |
| files in commit `c718c4c` | **42** = 41 of the original 45 + `.gitignore` (added during the audit) |
| retained changed files | **43** MBAL-attributed original entries kept (41 committed + 2 MBAL reports, untracked and ignored) |
| reverted-file count | **0** (1 dead-alias hunk and 1 optional hunk flagged, none reverted) |
| pre-existing-file count | **2 whole files** (`THEMIS_RELEASE_READINESS_REPORT.md`, `THIRD_PARTY_DATA_REDISTRIBUTION.md`) **+ 1 hunk** (`api.yml` `max_bytes`) |
| MBAL production files | **21** in `themis/` (19 modified incl. the `api.yml` hunk, 2 new: `chains/evm.py`, `config/chains.yml`) **+ 7** frontend = 28 |
| MBAL test files | **8** (5 modified pytest files, `test_multichain_generalization.py`, `e2e.mjs`, `make_fixtures.py`) + the `examples/example_unsupported_chain.csv` fixture |
| documentation files | **6** MBAL (`README.md`, `REPRODUCE.md`, `examples/README.md`, `tests/e2e/README.md`, 2 MBAL reports) + 2 pre-existing |
| untracked files proposed for tracking | 3 already tracked by the peer commit (`evm.py`, `chains.yml`, the test file); 2 MBAL reports = author call; `THIRD_PARTY_DATA_REDISTRIBUTION.md` = not MBAL |
| paper regression status | **no regression**: 7 CLI outputs byte-identical to `30ffd0b`; 39 numeric `reproduce-paper` files identical; verdicts identical (BLOCKED with a bundled sample, as before). Pre-existing `audit.txt` and `sources.txt` differences vs `expected_output/` unchanged and not MBAL's |
| remaining scale limitations | **KNOWN SCALE LIMITATION**: ~2.5 KB RAM/row, 24.7 GB at 10M rows; first Claims 37 s and first Trust 76 s at 8.9M claims; `analysis_summary.json` is multi-GB by contract. No disk-backed store built |
| proposed commit sequence | K1 chains -> K2 pre-flight -> K3 identity/claims -> K4 independence -> K5 API/views -> K6 frontend -> K7 tests -> K8 docs -> K9 reports (optional); P pre-existing separately |
