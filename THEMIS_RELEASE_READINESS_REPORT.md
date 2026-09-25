# THEMIS release-readiness, security and scientific-integrity closure report

Date: 2026-09-24. Scope: one repository-wide closure pass. This file is tracked on purpose: the release state
must not depend on the gitignored `HARDENING_LOG.md`. Statements are labelled **OBSERVED** (seen in this
run), **INFERRED**, **DOCUMENTED BY SOURCE** (a source's own documentation) or **CONFIRMED BY THEMIS** (established
by a THEMIS check) where the distinction matters.

**Verdict: CONDITIONALLY READY — EXTERNAL CHECKS BLOCKED.** No avoidable implementation defect found in this
loop remains open. Three things cannot be closed from inside the repository (section 23).

---

## 1. Baseline (recorded before any change)

| item | value |
|---|---|
| HEAD | `33d9aba7f74d339b998b950613aeadb130bccd37` ("run themis"), equal to `origin/main` |
| `git status --short`, `git diff --stat`, `git diff` | all empty: clean tree |
| last commits | 33d9aba run themis · 2199296 provenance integrity gate + case-study metadata · 67fa669 tighten .gitignore · 554a7d4 relational SQLite ingestion · a7fe5e0 pre-flight gate tests/docs · 83cbc3c frontend schema mapping · 540094b pre-flight gate · a7ee979 css · 4c690e3 REPRODUCE test counts · 1e2039b overview populations |
| Python | 3.14.6 (project `.venv`), pip 26.1.2 at baseline |
| Node / npm | v26.8.2 / 11.19.1 |
| `frontend/package-lock.json` sha256 | `9586d4b7471da720fb789e96d5bacca491d5fab4645e1e9ad3a8d673b1318d9d` (unchanged at the end) |
| config sha256 (baseline) | notable_roots `586a4d1e…`, preflight `648cc603…`, taxonomy `1cb2f8e3…`, thresholds `acfd5016…`, trust_rules `b0d18ce9…` |
| ignored local files | HARDENING_LOG.md, RECONCILIATION_REPORT.md, WALLETCLASSIFICATION_CASE_STUDY_REPORT.md, provenance_register.html, results/, external_data/, release/, paper/manuscript/, .venv, node_modules, dist |
| baseline suite | 467 passed, 6 skipped |

State layers: (1) **committed baseline** = 33d9aba, which already contains the WalletClassification integration
(554a7d4, 2199296) and the earlier security/hardening work; (2) **changes introduced by this loop** = commits
48101d2, f3b0d94, be42d24, de14716, a5fc145, 9a9e9fe and the commit adding this report.

## 2. Scope

Phases 1–26 of the closure brief. Not done, by rule: no WalletClassification recovery, no new corpus source, no
paper or corpus edit, no data deleted, no disk-backed storage, no authentication added.

## 3. Changes made

| commit | what |
|---|---|
| 48101d2 | CORS allowlist + cross-origin write refusal, byte-exact upload cap (wire + per-file + gzip expansion), error sanitization, NUL-in-path fix, `run_dir_of` fix, `api.yml`, `errors.py` |
| f3b0d94 | every relational SQL identifier quoted, alias collision refused, SQLite URI percent-encoded, `sqlite*` tables no longer hidden, dependency candidates no longer promote claims, `case_metadata` validated, literals moved to `preflight.yml`, and 101 new tests (41 more are in 48101d2) |
| be42d24 | UI overclaim fixes, case-metadata rendering, dependency panel, neutral placeholder, case-study wording |
| de14716, a5fc145, 9a9e9fe | REPRODUCE counts; optional browser harness `tests/e2e/` |

Production diff vs baseline: 17 files, +365/−108 (`themis/`, `frontend/src`); tests +1,959 lines in 10 files.
`git diff --check`: clean.

## 4. Scientific integrity audit — defects found and fixed

Every item has a test that fails on the old behaviour (mutation-checked where noted).

| # | defect | effect | fix | test |
|---|---|---|---|---|
| S1 | `relational.provenance_states` moved a claim from `unresolved` to `inherited` because one declared-source string textually contained another (an unverified **dependency candidate**) | a candidate was presented as a lineage; contradicted the docs' "never changes a provenance count" | claims stay in their state; candidates counted separately as `dependency_candidate_claims`; `inherited` is 0 for a database extraction (no confirmed lineage exists there) | `test_evidence_invariants::test_E_extraction_…` |
| S2 | Overview showed **"Independent corroboration: established"** whenever the reference comparison merely ran (`ind.available`), even with 0 confirmed independent roots | overclaim | established only when confirmed independent multi-root addresses > 0; interpretation paragraph tied to `resolved == 0` | browser E (see §16) |
| S3 | the "RECOVERED DATASET SUBSET" banner fired for any non-empty `analysis_origin`/`recovery_status`, including "original_full_database" | a false statement of what the data is | fires only when the declaration mentions recovery (errs toward warning); metadata rendered as one row per field, labelled "declared by the analyst … not verified" | browser D, D2 |
| S4 | "rows valid" beside the claim count read as verification | overclaim | "rows became claims (address syntax checked; not a verification)" | — |

Verified **not** defects (tested, no change): unresolved roots never count as confirmed; a bundled source name in a
declared-source column resolves nothing; a CSV cannot declare itself verified/derived; unknown labels stay
`unknown` and never form agreement; one source disagreeing with itself is `incomparable`; Elliptic class aliases
apply only to fresh ingestion and read-only to frozen claims.

## 5. WalletClassification closure

Final role: **UNRESOLVED-PROVENANCE CASE STUDY** (unchanged). Core conclusion: technically valid data ≠
forensically defensible attribution.

* Wording (tracked `docs/case_studies/walletclassification.md`, local report, guard test `TestCaseStudyWording`):
  **INDEPENDENCE NOT ESTABLISHED**; separately, **a documented dependency exists between at least one pair of
  declared source descriptors: BABD / WalletExplorer** (DOCUMENTED BY SOURCE; applying it to the recovered rows is
  INFERRED). The phrase "independence is contradicted" and the sentence inferring an original table "likely tens of
  millions of rows" from a maximum rowid were removed. Observed values (1,032,288 recovered rows; 1,632,364
  index-fragment pairs; largest rowid 37,464,413) are kept as observations only, with
  "**the full original corpus size cannot be established from the recovered subset**".
* No "0% reliable / unreliable / invalid attribution" language exists (guard test).
* No further recovery was attempted; the raw file is not in the repository and was not touched.

## 6. Genericity audit (Phase 3)

Search for `WalletClassification`, `BABD`, `Harvard`, `WalletExplorer`, standalone `WE` (case-insensitive too)
over `themis/` and `frontend/src/` (plus `scripts/`, `run.py`):

| hit | class |
|---|---|
| `themis/config/sources/rodwald_mixers.yml:11,20,23` "walletexplorer" | PRE-EXISTING seven-source config data/comment (a dependency Rodwald's own source documents); not a branch |
| `frontend/src/pages/Database.jsx:104` placeholder `WalletClassification.db` | UI TEXT → **replaced** by `dataset.sqlite` |
| `scripts/generate_case_study_demo_db.py:3,34` | GENERIC DEMO SUPPORT (synthetic; a comment names the real pattern) |
| standalone `WE` | none |

**Result: zero WalletClassification-specific scientific branches.** The dependency test uses no dataset name; the
synthetic demo uses "DemoCorpus-13 (labels via DemoExplorer)". Source-name aliases in the taxonomy: none (test).

## 7. Hardcoding audit (Phase 4)

Method: AST scan of every numeric literal in `themis/**/*.py` (195 non-trivial) plus a frontend sweep.

Genuine scientific/method parameters that were literals — now config (`preflight.yml`), each with a test that
flips the value: `review_confidence` (a literal `0.5` duplicated it), `min_sequence_sample` (3),
`detect.unsupported_chain_shape.min_sample` (3), `target_audit.min_source_name_length` (was `> 3`; now `>= 4`,
same behaviour), `sqlite.dependency_min_descriptor_length` (3), `sqlite.lookup_role_confidence` (0.5),
`sqlite.inferred_relationship_confidence` (0.6), `sqlite.unindexed_join_warn_rows` (1000),
`sqlite.case_metadata_max_chars` (4000). Also fixed: `thresholds.yml: decode_report_limit` was **documented but never
read** while `cli.py` printed a literal 12. A `… or 0.6` fallback that turned a zero table-role confidence into 0.6
was replaced by `or 0.0`.

Left in code, classified:

* MATHEMATICALLY INHERENT: `1e-12`/`1e-9` float tolerances in kappa, `365.25` days/year, Wilson `z*z/(4n²)`,
  bitcoin checksum/bech32 constants.
* SOFTWARE/API: HTTP status codes, `1<<20` read chunk, SQLite progress-handler interval, `_MAX_JOBS = 50`, batch size
  `1.5e7`.
* DISPLAY: `[:5]`, `[:10]`, `[:12]` (containment table), `[:20]` examples, console widths, `most_common(10/20)`,
  frontend `PAGE = 100`, "show 10 rejected", `>6` pairs toggle.
* Config with an in-code fallback equal to the shipped value (`kappa 0.4`, bootstrap 2000/42/0.95,
  `staleness_years 3.0`, `root_concentration_limit 8`, `containment_*`): config-driven; the duplicate default is
  only reached for a custom `THEMIS_CONFIG_DIR` lacking the key (KNOWN LIMITATION, cosmetic).
* Frontend: no scientific threshold; all percentages/`toFixed` are formatting of server values.

Deliberately **not** added to `thresholds.yml`: its hash is recorded in every paper-reproduction run.
Re-audited classes (kappa, `confidence_of`, preflight thresholds, currency/staleness, bootstrap, taxonomy walk, trust
predicates, target/reference independence): no further hardcoding found.

## 8. API security audit (Phases 5–7, 13, 14)

Threat model (also in `themis/config/api.yml`): local single-user tool, binds 127.0.0.1, no authentication.
Realistic attacker: any web page open in the same browser.

| control | result |
|---|---|
| CORS | `allow_origins=["*"]` → allowlist `localhost/127.0.0.1` × `5173/4173` (config). Allowed origin: header present; unknown origin (incl. `null`, wrong port, look-alike host): absent; no `Origin`: unchanged |
| blind cross-origin write | a "simple" multipart POST is still *processed* by a page that cannot read the reply. `_RequestGuard` returns 403 for any non-GET request whose `Origin` is present and not allowed; verified in a real browser (§16 G): read blocked, no analysis created |
| upload size | `upload.max_bytes = 256 MiB` (config). Three layers: declared `Content-Length` early refusal; body bytes counted **as read** (endless-body test: stops at the limit, does not consume); exact per-file check; a `.gz` is also refused if it **decompresses** past the limit. Same code for `/api/preflight`, `/api/analysis`, `/api/jobs/analysis`. Clean 413, no traceback, no analysis or job created |
| error disclosure | only `InputError` text (raised deliberately for the caller) is shown; every other failure → `Analysis task failed.` with the real exception and traceback in the server log (`themis.api` logger). Server paths removed from the missing-reference-corpus message; SQLite library text no longer echoed |
| paging | server cap `paging.claims_max_page = 500`; partition test over limits 1…261 finds no duplicate/gap; empty page, invalid limits/offsets (clamped or 422), filters compose, tiers partition the claims |
| other | `db` with NUL byte 500'd → 400; `paper run_id` `.`/`..` accepted by the regex → rejected |

Trust-engine reachability (Phase 13): **IMPLEMENTED AND REACHABLE** — paper trust-rule sensitivity (`/drift`, Trust
page) and, for any uploaded dataset, evidence retention under chosen trust predicates (`/trust-coverage`, Trust page).
**IMPLEMENTED BUT NOT EXPOSED** — running a user's own downstream task under alternative trust rules on an arbitrary
upload (the engine is generic; the only task is ransomware revenue, CLI/paper mode). **NOT IMPLEMENTED** — user-defined
rules in the UI (config only). Docs already say "paper mode only"; no claim needed correcting.

Residual (author decision): **DNS rebinding** and other local processes are not covered; a `Host`-header allowlist would
close the former (about 3 lines) but every existing test client uses host `testserver`.

## 9. SQLite hardening (Phase 8)

28 tests (+45 subtests) on synthetic databases: bad magic, truncations, random bytes of 1…70,000 B, zero-byte and empty
files, 22 hostile table names (quotes, SQL text, Unicode, emoji, reserved words, 5,000 characters, newlines, `sqlite*`),
hostile/empty/duplicate-alias column names, FKs to missing tables/columns, cycles, self-join, orphans, duplicate and
conflicting claims, NULL/empty/huge sources, two address-like columns, traversal/absolute/symlink/URI-metacharacter paths.
Real defects found and fixed: unquoted column identifiers and aliases (**SQL quote injection**; mutation-verified),
unescaped `LIKE 'sqlite_%'`, raw-path SQLite URI (`?`, `#`, `%`), NUL path 500, silent alias overwrite.
Guarantees: read-only open, file bytes unchanged, no journal, **no `.recover`, no subprocess anywhere** (static test),
corrupt file → `stopped`, no claims.

## 10. CSV / general ingest hardening (Phase 9)

16 tests (+44 subtests): 20 filenames (traversal, control characters, 10,000 characters), 22 header shapes (BOM, empty,
duplicate, SQL/script/formula, 10,000 characters), hostile values (HTML/JS/SQL/formula/CRLF/NUL/100,000-character/empty/
unknown). No path use of filenames, no crash, unknown stays `unknown` (raw kept verbatim), formula-leading cells
(`= + - @ \t \r`) neutralised in **every** CSV export including headers and `source_id`, nothing promotes tier or provenance.
No defect found beyond §9.

## 11. Frontend security (Phase 15)

`dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, `new Function`, `document.write`,
`srcdoc`, `javascript:`: **none** in `src/` or `legacy/`. The only dynamic `href`s are two API URLs built from server-side
names. In a real browser, `<script>` and `<img onerror>` in labels, sources, column names, table names and an error
message rendered as text; `window.__xss` never set; no dialog, page error or console error.

## 12. Dependency and secret audit (Phase 17)

| tool | result | class |
|---|---|---|
| `pip-audit` | baseline: `pip 26.1.2` PYSEC-2026-3721 (fix 26.2). Upgraded the venv's pip to 26.2.1 → **no known vulnerabilities** | packaging-tool/environment (not a runtime dependency) |
| `npm audit` | 0 vulnerabilities | — |
| runtime deps | pyyaml, fastapi, uvicorn, python-multipart, react, react-router-dom, reactflow: clean | — |
| secret scan | 147 tracked files + history names: no private keys, cloud/GitHub/Slack/Google tokens, JWTs, credential URLs, `.env`, assignments to key/password/secret/token. **No false positives to report** | — |

`themis` itself is "not on PyPI" to `pip-audit` (expected).

## 13. Third-party data and license audit (Phase 21)

**OBSERVED:** the repository is public (`private:false`, unauthenticated API, 2026-09-24) and **tracks** `demo_data/`
(5 files: `observations_sample.csv.gz` 6.7 MB, `revenue.csv.gz`, `verified_anchors.txt.gz`, `ground_truth.csv`,
`manifest.json`) — records **derived** from all seven sources. No raw source file, no transaction graph. Other tracked
address-shaped strings are test/example fixtures. No WalletClassification, BABD or recovered-database content is tracked.

| source | derived records tracked | license state |
|---|---|---|
| GraphSense TagPack | 25,362 sampled claims + `forensic` half of the anchor set | **CONFIRMED** (MIT) |
| Schnöring et al. | complete | **CONFIRMED** (CC BY 4.0) |
| Ransomwhere | 11,186 claims + revenue | **CONFIRMED** (CC BY 4.0, Zenodo) |
| OFAC SDN | 185 anchors | **CONFIRMED** (public domain) |
| Elliptic++ | 20,083 sampled claims (53.24% of corpus claims) | **UNCONFIRMED** (no license stated) |
| Rodwald ransomware / mixers | 50,322 / 57,817 claims + revenue | **UNCONFIRMED** (no terms) |
| WatchYourBack | 309 claims | **PARTIAL / CODE-ONLY** (GPL-3.0 for the repository; data extent unstated) |

60.24% of corpus claims derive from UNCONFIRMED sources (per `THIRD_PARTY_DATA.md`, re-read). **Flagged, prominently:**
this is the top unresolved release question. Nothing was deleted, untracked or rewritten. The release ZIP builder already
excludes `demo_data/`; the git repository does not. THEMIS's own code has **no LICENSE file**.

## 14. Clean-install verification (Phase 18)

| step | result |
|---|---|
| `python -m pytest` | **609 passed, 6 skipped**, 2 warnings, 132 subtests (with the bundled sample). Release mode (`THEMIS_DATA_DIR` empty): 480 passed, 135 skipped |
| skips | 6 × full-corpus Overview figures (need `THEMIS_OBSERVATIONS`); release mode adds the corpus-dependent tests, each with its stated reason |
| `rm -rf node_modules && npm ci` | 121 packages, lockfile hash unchanged, 0 vulnerabilities |
| `npm run build` | vite 6.4.3, 228 modules, 0 errors, 0 build warnings |
| `npm audit` | 0 vulnerabilities |

Warnings: `StarletteDeprecationWarning` (httpx test client) and `anyio BlockingPortal` alias — UPSTREAM/DEPRECATION, not
actionable here. npm "install-scripts … esbuild, fsevents not yet covered by allowScripts" — UPSTREAM (npm policy notice;
the build works). ACTIONABLE: none. HARMLESS: `Failed to load resource` console lines on deliberate 4xx refusal paths.

Final verification (all code frozen, HEAD 9a9e9fe): pytest 609 passed / 6 skipped; clean `npm ci` + build + audit as above; `pip-audit` clean; default `reproduce-paper` BLOCKED (exit 3); retained-table run PASS; synthetic demo: 200 claims, provenance 0 resolved / 0 inherited / 0 inferred / 200 unresolved, 100 dependency-candidate claims, 1 candidate (`DemoCorpus-13 (labels via DemoExplorer)` → `DemoCorpus-13`), independence not available, 0 verified.

## 15. Complete test results

Baseline 467 → **609** (+142 tests). New files: `test_api_security` 41, `test_sqlite_adversarial` 28,
`test_evidence_invariants` 27, `test_case_metadata_hardening` 18, `test_csv_adversarial` 16,
`test_config_driven_parameters` 10; `test_case_study_metadata` 12 → 14. Related existing files all pass:
relational 26, sqlite_source 13, ingest 33, preflight 35, independence 7, rq1_taxonomy 22, target_audit 10,
api_views 30, trust_engine 11. Mutation checks (guard removed → a test fails): wire counter, origin refusal, per-file
limit, wildcard CORS, error text, identifier quoting.

## 16. Browser E2E (Phase 16)

**Executed** (not substituted by API tests): headless Chromium 151 driven by `playwright-core` 1.63.0 against the
production build (`vite preview :4173`) and the API (`:5001`, `THEMIS_DB_DIR` set). **16/16 steps passed**
(`tests/e2e/`, optional, not part of pytest):

A normal CSV upload → pre-flight → analysis → overview → claims (40 of 40, server-paged) → address → provenance → export
(`normalized_claims.csv`, 41 lines) · B healthy SQLite inspect → select → 2 joins → pre-flight → extract → overview ·
C corrupt SQLite shows "DATABASE INTEGRITY CHECK FAILED / Analysis has not started.", no table selection, and the server
independently refuses (`stopped`, 0 claims, `/claims` → 409) · D recovered subset shows "RECOVERED DATASET SUBSET / This
analysis does not represent the complete original database." in the alert region; a value containing a newline and
"provenance resolution status:" cannot forge a second row; an "original_full_database" declaration raises no banner ·
E dependent-source demo shows DECLARED SOURCE DESCRIPTOR and POTENTIAL / DOCUMENTED DEPENDENCY, "Independent corroboration:
not established", confirmed independent roots 0, provenance `resolved 0 · inherited 0 · inferred 0 · unresolved 200`, 100
candidate claims listed separately · F1–F4 hostile CSV / SQLite / error text render as text, no execution, no dialog ·
G a page on another origin cannot read the API and its blind upload created nothing.
Limits: one browser engine (Chromium), production build only, headless.

## 17. Paper reproduction (Phase 19)

| run | input | result |
|---|---|---|
| `themis reproduce-paper` (repository as shipped) | bundled sample | **`PAPER ↔ THEMIS: BLOCKED`**, exit 3; 20 PASS / 0 FAIL / 9 NOT_REPRODUCED; 27 claim ids blocked. **Missing prerequisite:** the full normalized observation table (`THEMIS_OBSERVATIONS`, built by `scripts/build_corpus.py` from the seven raw sources, which are not in this environment) |
| same command, retained full table `results/reproduction_closure/full_build/observations.csv.gz` (sha256 `e65bf05a…029acd`, 1,545,710 claims, built 2026-09-20; ground truth copied from `demo_data`), `--as-of 2026-09-15` | FULL_CORPUS | **`PAPER ↔ THEMIS: PASS`**, 29 headline PASS / 0 FAIL / 0 NOT_REPRODUCED. Run twice: once mid-loop (dirty tree on 33d9aba) and again in the final verification on clean commit 9a9e9fe (run `20260923T232302Z-9a9e9fe`); both PASS |

Reading: the BLOCKED result is the current, honest result of the command as shipped and is **not** described as a PASS.
The second run is a separate, current execution that reaches PASS on a locally retained table whose derivation from raw
sources could not be re-verified in this run (per-source claim counts in its manifest sum to the paper's 1,545,710).
Historical certified PASS (tag `v1.0-paper`) is not counted here.
Independently verified: `git diff` of `paper/`, `themis/config/sources/`, `taxonomy.yml`, `thresholds.yml`,
`trust_rules.yml`, `notable_roots.yml` against HEAD is empty; WalletClassification is absent from
`reproduce.required_inputs()`; the seven-source list is unchanged; no paper/config file is touched by the WalletClassification
commits; no paper code mentions `case_metadata` or the case study (test); the demo generator is not imported by production
code. One paper-harness file changed: `themis/paper/reproduce.py::run_dir_of` (name validation only; results unchanged, as
the PASS above shows).

## 18. Paper-vs-implementation discrepancy register (Phase 20)

| item | class | status |
|---|---|---|
| "Exact agreement" counted one source's opinion as two agreeing (published draft 13,673 / 1,253 / 342 / 109 / 23; THEMIS 10,515 / 1,253 / 340 / 108 / 3,184) | CODE BUG — FIXED | fixed in `classify_address`; the paper's declared values are the author's; manuscript is not in the repository and not compared here |
| TagPack per-tag confidence flattened to one `curated` tier | METHODOLOGY ISSUE — AUTHOR REVIEW REQUIRED | unchanged, by decision; `subcat` carries the raw id |
| WatchYourBack `#`-prefixed addresses (87) | CODE BUG — FIXED (address key: `strip_prefix`; 71 hydra-market re-rooted to `ofac_sdn`) / METHODOLOGY ISSUE — AUTHOR REVIEW REQUIRED (16 remaining records) | manifest now expects 15,413 multi-dataset addresses |
| Elliptic++ licensing | LICENSE / REDISTRIBUTION ISSUE | unresolved (§13) |
| Rodwald licensing | LICENSE / REDISTRIBUTION ISSUE | unresolved |
| WatchYourBack GPL-3.0 reach over the data | LICENSE / REDISTRIBUTION ISSUE | unresolved |
| Revenue table off by $1–3 | DATA SNAPSHOT DIFFERENCE in the first log entry; root cause later found and **CODE BUG — FIXED** (cent rounding in `build_corpus.py`) | Table 2 PASS in both runs |
| Elliptic `class_1/2` alias | NO LONGER APPLICABLE (verified zero effect; fresh ingestion only) | — |
| Staleness judged by wall clock / newest date | CODE BUG — FIXED | analysis date pinned |
| Bundled sample reproduces only 20/29 headline claims | KNOWN LIMITATION | needs the full table |
| Dedupe key `(address, label)` ignores the declared source, so a second descriptor for an identical claim is dropped and counted as "duplicate claim" | KNOWN LIMITATION (new, this loop) | reported not silent; changing it alters ingestion counts: author decision |
| THEMIS code has no LICENSE file | LICENSE / REDISTRIBUTION ISSUE | author decision |
| "Openly redistributable" wording for Elliptic++/Rodwald | LICENSE / REDISTRIBUTION ISSUE | author decision |

The paper was not edited.

## 19. Repository hygiene (Phase 22)

Tracked files: 147 at baseline. No `.db/.sqlite`, recovery fragment, `node_modules`, `.venv`, `.env`, credential, `dist`,
zip or temp result folder is tracked (the only name match, `docs/case_studies/walletclassification.md`, is a document).
Ignored as intended: HARDENING_LOG.md, RECONCILIATION_REPORT.md, the WalletClassification working report,
`results/`, `external_data/`, `release/`, `paper/manuscript/`, `*.db`, `*.sqlite`. `HARDENING_LOG.md` being ignored is a
deliberate `.gitignore` entry ("local working material"); its permanent content that matters is in §4, §18 and this file.
All test databases are built in temp directories; no test artifact was left behind.

## 20. Unresolved limitations

1. DNS rebinding and other local processes are outside the CORS/Origin model (§8).
2. Deduplication ignores the declared source (§18).
3. A database view that never terminates would make an extraction run unbounded (a hostile local file; not addressed).
4. Extraction holds all valid claims in memory (existing, documented `occam:` ceiling).
5. `allowed_origins` is read once at import; changing it needs a restart.
6. E2E covered Chromium only.
7. The unverified `ValueError`s raised by library code are now internal errors (generic message): a caller who relied on
   seeing their text will see the generic one.

## 21. Author decisions still required

1. Whether `demo_data/` stays tracked in a **public** repository given the unconfirmed Elliptic++ and Rodwald terms
   (confirm with the authors, or untrack / replace with a synthetic sample). Nothing was changed.
2. A LICENSE for THEMIS's own code.
3. Whether to accept the retained full observation table as the authoritative reproduction input, or rebuild it from
   freshly fetched raw sources.
4. TagPack tiering; the 16 unreassigned WatchYourBack records.
5. Whether the declared source should be part of the duplicate-claim key.
6. Whether to add a `Host` allowlist (DNS rebinding).

## 22. Final acceptance matrix

| # | requirement | status | evidence |
|---|---|---|---|
| 1 | Python full suite | PASS | `python -m pytest`: 609 passed, 6 skipped (six full-corpus tests, stated reason) |
| 2 | case-study tests | PASS | `test_case_study_metadata` 14, `test_case_metadata_hardening` 18 |
| 3 | relational SQLite tests | PASS | `test_relational` 26, `test_sqlite_source` 13 |
| 4 | adversarial SQLite tests | PASS | `test_sqlite_adversarial` 28 (+45 subtests) |
| 5 | CSV ingest tests | PASS | `test_csv_adversarial` 16, `test_ingest` 33, `test_preflight` 35 |
| 6 | taxonomy invariants | PASS | `test_evidence_invariants::TestTaxonomyInvariants`, `test_rq1_taxonomy` 22 |
| 7 | provenance invariants | PASS | `test_evidence_invariants` cases A–F + extraction cases (27) |
| 8 | independence invariants | PASS | `test_independence` 7, `test_target_audit` 10, cases A–F |
| 9 | API security | PASS | `test_api_security` 41 |
| 10 | CORS | PASS | allowed/unknown/absent origin, preflight, blind POST 403; browser G |
| 11 | upload-size enforcement | PASS | 8 required cases + endless body + gzip expansion, three routes |
| 12 | error sanitization | PASS | 500/job/task/sqlite/reference-path tests; server log captured |
| 13 | path traversal | PASS | filenames (20), `db` parameter (15 shapes, symlink, NUL), `run_id` |
| 14 | SQL injection | PASS | 22 table names, 8 column names, hostile values, catalogue lookup; mutation-verified |
| 15 | XSS | PASS | source scan + browser F1–F3, `window.__xss` never set |
| 16 | CSV formula injection | PASS | every export, headers, `source_id`, six lead characters |
| 17 | claims pagination | PASS | partition over limits 1…261, cap, empty page, filters, tiers |
| 18 | frontend clean install | PASS | `rm -rf node_modules && npm ci`, 121 packages, lockfile unchanged |
| 19 | frontend production build | PASS | vite build, 228 modules |
| 20 | npm audit | PASS | 0 vulnerabilities |
| 21 | pip audit | PASS | none after pip 26.1.2 → 26.2.1 (environment tool) |
| 22 | secret scan | PASS | §12 |
| 23 | browser E2E | PASS | 16/16, Chromium 151 (`tests/e2e`) |
| 24 | WalletClassification special-case grep | PASS | §6, zero scientific branches |
| 25 | synthetic demo | PASS | `test_E_…` and browser E: 200 claims, 0/0/0/200, 1 dependency, independence not available |
| 26 | third-party data hygiene | BLOCKED | derived records of 7 sources tracked in a public repo; 60.24% unconfirmed. Needs the Elliptic++ / Rodwald authors' answer or the author's decision (§13, §21.1) |
| 27 | paper files unchanged | PASS | `git diff HEAD -- paper` empty |
| 28 | seven-source corpus unchanged | PASS | `git diff -- themis/config/sources` empty; `required_inputs()` scan |
| 29 | paper reproduction (`themis reproduce-paper`, as shipped) | BLOCKED | full observation table absent from the repository/environment default; 20 PASS / 0 FAIL / 9 NOT_REPRODUCED |
| 29b | paper reproduction, retained full table | PASS | 29/29 headline; input provenance not re-derivable here (§17) |
| 30 | repository hygiene | PASS | §19 |
| 31 | scientific wording audit | PASS | §4 S2–S4 fixed; docs/back-end audit clean; guard tests |
| 32 | unresolved author-review issues | BLOCKED | §21 (author decisions) |
| 33 | licensing unresolved items | BLOCKED | Elliptic++, Rodwald, WatchYourBack confirmations from outside the repository |
| 34 | final WalletClassification role | PASS | UNRESOLVED-PROVENANCE CASE STUDY |

## 23. Final release recommendation

**CONDITIONALLY READY — EXTERNAL CHECKS BLOCKED.** Every code, security, scientific-wording and test item is PASS. Rows
26, 29, 32 and 33 are BLOCKED on inputs only the author or outside parties can give. Do not publish the repository or a
release as "release ready" until row 26 (what `demo_data/` may contain in a public repository) is decided.
`PAPER ↔ THEMIS` remains **BLOCKED** for the command as shipped; it is PASS only with the retained full table.

## 24. Exact git diff / status summary

Baseline `33d9aba`; commits by this loop: 48101d2, f3b0d94, be42d24, de14716, a5fc145, 9a9e9fe, plus the commit adding this
report. Working tree clean after the final commit. Files changed vs baseline: 30 (+2,397 / −121), of which production
`themis/` + `frontend/src` 17 files (+365 / −108), tests 10 files (+1,959), docs (README, REPRODUCE, case study, this
report), `themis/config/api.yml` and `themis/errors.py` new. No paper, corpus, source-config, taxonomy, threshold or
trust-rule file changed. Change review: no change alters a scientific result of the paper pipeline (§17 proves it), none
introduces source-specific behaviour, none weakens an existing guard; the one intentional interpretation change is S1
(a candidate no longer changes a provenance state). The new surfaces are the request guard and the config-driven allowlist,
both tested.


---

## 25. AUTHOR / RELEASE DECISIONS

Date: 2026-09-24, after commits 6c8895a (Host allowlist), e6a71f6 (claim identity) and 9176869 (data matrix, retained-table
record). Historical sections above are unchanged; where they are now out of date this section says so: **§8 residual
(DNS rebinding), §18 row "Dedupe key ignores the declared source", §20 items 1-2, §21 items 3-6 are superseded by the table below.**
Nothing in the frozen corpus, `paper/`, `themis/config/` or the manuscript was edited in this loop.

### 25.1 Summary

| # | issue | decision | status |
|---|---|---|---|
| 1 | public `demo_data/` redistribution | matrix built; **release policy not chosen** (rule: author selects); nothing removed | EXTERNAL CONFIRMATION REQUIRED |
| 2 | software LICENSE | ownership unresolved; options presented; **no LICENSE added** | EXTERNAL CONFIRMATION REQUIRED |
| 3 | authoritative reproduction input | fresh raw-source rebuild is authoritative; retained table = certified regression artifact; statements kept separate | RESOLVED |
| 4A | TagPack tiering | unchanged; current interpretation classified | DEFERRED WITH DOCUMENTED LIMITATION |
| 4B | 16 remaining WatchYourBack `#` records | classified COMMENT by upstream's own parser; frozen corpus **not** changed; paper impact measured | DEFERRED WITH DOCUMENTED LIMITATION |
| 4C | duplicate-claim identity | claim = (address, label, declared source); implemented and tested; frozen paper unaffected | RESOLVED |
| 4D | Host / DNS rebinding | Host allowlist implemented and tested | RESOLVED |

### 25.2 Decision 1 - `demo_data/` redistribution

* **Decision.** Build the matrix (`THIRD_PARTY_DATA.md`, "Redistribution matrix"); apply `UNCONFIRMED != PERMITTED`; do not remove
  anything until the author selects a policy.
* **Rationale / evidence (OBSERVED 2026-09-24).** TagPack MIT (`LICENSE` fetched), Schnöring CC BY 4.0 (figshare API), OFAC US government
  work: CONFIRMED REDISTRIBUTABLE. Elliptic++: GitHub `license: null`, no LICENSE file, README asks for citation only. Rodwald (both): page
  text has no license or terms. WatchYourBack: GPL-3.0 `LICENCE` for the repository; its reach over `btc_resolv.csv` is unstated and
  share-alike would apply if it does. **Ransomwhere was downgraded from CONFIRMED to UNCONFIRMED**: the CC BY 4.0 record is the Zenodo
  v1.1.0 deposit (2024-10-27); the corpus uses the live export retrieved 2026-09-20, whose terms could not be read.
  Every `demo_data/` file except `manifest.json` (aggregates) carries UNCONFIRMED records: observations sample (Elliptic++ 20,083,
  Rodwald 108,139, Ransomwhere 11,186, WatchYourBack 309 rows), revenue (Rodwald + Ransomwhere), anchors and ground truth (WatchYourBack half).
* **Git history (OBSERVED).** The repository is public (created 2026-09-16; 0 forks, stars, watchers, releases on 2026-09-24; only `main`
  pushed; `v1.0-paper*` tags local). The five files exist as 10 blob versions across 6 of 89 commits, from the first commit. `git rm`
  alone leaves all of it retrievable. Removal from history needs `git filter-repo --path demo_data --invert-paths` (not installed here) or
  BFG: every commit hash changes, force-push to `main`, local tags and the recorded release-ZIP hashes become stale, and cloned or
  GitHub-cached copies persist (purge only via GitHub Support). **No rewrite was performed or prepared.**
* **Implementation impact.** None (documentation only). **Paper impact.** The paper's Ethics statement still says the datasets are
  "openly redistributable"; that is not supported for Elliptic++, Rodwald or the Ransomwhere live export. Author wording change; paper untouched.
  **Release impact.** A release build already excludes all `demo_data/` files (`scripts/make_release.py`); the public development repository
  does not.
* **Status.** EXTERNAL CONFIRMATION REQUIRED (Elliptic++ / Rodwald / ransomwhe.re / WatchYourBack authors) plus the author's choice among:
  confirm and keep; `git rm --cached` going forward only; untrack and rewrite history; replace with a synthetic sample.

### 25.3 Decision 2 - software license

* **Decision.** None. No `LICENSE` file, no `pyproject.toml` license field, no header added.
* **Ownership evidence (OBSERVED).** 89 commits, all by one author identity; the paper lists one author affiliated with *Digital Forensics and
  Cyber Security, Institute of Advanced Research, Gandhinagar*, corresponding e-mail on the institute's domain (`mscdfcs` local part), and
  declares "No funding was received". Whether IAR holds rights in the work (student/thesis work, use of institute resources, an IP policy) is
  **not determinable from the repository**. That is the blocking fact; the author must ask the institute.
* **Separation.** A software license does not grant rights in third-party data (§25.2) and the data licenses do not license this code.
  If WatchYourBack's GPL-3.0 were held to cover the rows in `demo_data/`, shipping them in a repository under MIT or Apache-2.0 would conflict;
  with demo data untracked the question does not arise.
* **Options (not selected).** Dependencies are all permissive (PyYAML MIT; FastAPI MIT; uvicorn, starlette, httpx BSD-3; python-multipart
  Apache-2.0; React, Vite MIT), so none of the three is blocked by them.

| license | what it means in practice |
|---|---|
| MIT | shortest text; anyone may use, modify, relicense and sell it, keeping the notice; no patent grant; no warranty |
| Apache-2.0 | same freedoms plus an explicit patent grant and a NOTICE convention; longer; compatible with GPL-3.0 (one-way) |
| GPL-3.0 | derivatives and redistributed copies must stay GPL-3.0; discourages proprietary reuse; forecloses embedding in permissively licensed tools |

* **Impact.** Implementation none; paper none (its code-availability sentence says the code is "released"); release: a public release without a
  license is "all rights reserved" by default, so a reviewer may read but not reuse it. **Status.** EXTERNAL CONFIRMATION REQUIRED, then author choice.

### 25.4 Decision 3 - authoritative paper-reproduction input

* **Decision.** The fresh raw-source rebuild is the authoritative path. The retained observation table is a *certified retained reproduction
  artifact*, and its PASS is reported only as **REGRESSION VERIFICATION USING RETAINED FULL OBSERVATION TABLE**. The statements are never merged
  (`REPRODUCE.md`, "Two reproduction statements").
* **Evidence (OBSERVED 2026-09-24).** Retained table sha256 `e65bf05a…029acd`, 1,545,710 rows, columns `address, source, raw_label, canon,
  polarity, prov_family, lastmod, heuristic, subcat`, all seven sources (Elliptic++ 822,937; TagPack 499,327; Schnöring 103,812; Rodwald 57,817 +
  50,322; Ransomwhere 11,186; WatchYourBack 309). The six retained raw files hash exactly as its build manifest records; running
  `scripts/build_corpus.py` (unchanged since 6245e0c) on them reproduced `observations.csv.gz`, `revenue.csv.gz`, `verified_anchors.txt.gz` and
  `build_manifest.json` **byte-identically**. The manifest is now tracked as `expected_output/retained_table_build_manifest.json`.
* **What is not established.** It is a *reconstruction* built 2026-09-20 from a live Ransomwhere export and a moving TagPack branch (commit
  7f9a5d1, 2026-09-11), after the paper's data were collected; it reproduces the paper's per-source counts and all 29 headline claims but is not
  shown to be the identical working file. The raw files were not re-fetched today, so upstream drift since 2026-09-20 is unmeasured.
* **Results, kept apart.** `themis reproduce-paper` as shipped (sample only): **`PAPER ↔ THEMIS: BLOCKED`**, 20 PASS / 0 FAIL / 9 NOT_REPRODUCED.
  Retained table (`--observations`, `--data-dir`, `--as-of 2026-09-15`): 29 PASS / 0 FAIL / 0 blocked, **REGRESSION VERIFICATION USING RETAINED FULL
  OBSERVATION TABLE: PASS**.
* **Impact.** Implementation none; paper none; release: the shipped command stays BLOCKED, honestly. **Status.** RESOLVED.

### 25.5 Decision 4A - TagPack confidence

* **Upstream documentation (fetched 2026-09-24).** `graphsense-tagpack-tool`: `tagpack_schema.yaml` declares `confidence` (`taxonomy: confidence`,
  mandatory); `db/confidence.csv` defines each id by how the *creator* obtained the data, with a numeric `level`: forensic_investigation 70,
  authority_data 60, forensic / service_data / trusted_provider 50, untrusted_transaction 40, web_crawl 20, heuristic 10, unknown 5; `forensic` is
  "Forensic reports - Creator retrieved data attribution data from somehow trusted reports (e.g. academic papers)".
* **Classification of the current THEMIS interpretation.**

| interpretation | classification |
|---|---|
| raw id preserved verbatim in `subcat`; no `confidence_normalized` | SUPPORTED |
| every TagPack claim tiered DERIVED, no id mapped to the verified tier | SUPPORTED (upstream's ids describe a creator's acquisition class, not re-checkable verification) |
| Condition D "highest declared confidence" = `forensic` ∪ WatchYourBack ransomware | PARTIALLY SUPPORTED: `forensic` is level 50, equal to `service_data` and below `authority_data` (60) and `forensic_investigation` (70); "highest" holds only among the ids present at ransomware-revenue addresses. **AUTHOR REVIEW REQUIRED** on the wording |

* Full-corpus id distribution over the 499,327 TagPack claims (OBSERVED): service_data 67.51%, forensic 32.10%, blank 0.19%, web_crawl 0.13%,
  authority_data 0.07%, untrusted_transaction 13 claims. (The source config quotes the bundled sample's shares, 69.9% forensic; they differ.)
* **Impact.** Implementation none (tiers not changed to raise apparent confidence); paper none; release: the uncertainty is documented in
  `themis/config/sources/tagpack.yml` and here and does not masquerade as established truth. **Status.** DEFERRED WITH DOCUMENTED LIMITATION.

### 25.6 Decision 4B - the 16 remaining WatchYourBack records

* **Which.** Of the 87 `#`-prefixed lines in upstream `btc_resolv.csv`, 71 (hydra-market) were re-rooted to `ofac_sdn` earlier; the other 16 are 14
  `apt29` (`us-gov-sanctioned`) and 2 `mrpr0gr4mmer` (sextortion, clipper).
* **Upstream evidence (OBSERVED).** The README documents the tag-file format (six columns, no header) and no comment syntax. Upstream's own loader,
  `code/lib/tags.py`, reads this very file with `pd.read_csv(f, names=names, na_filter=False, comment='#')`: a line **beginning with `#` is
  ignored entirely by WatchYourBack itself**.
* **Classification.** All 16 (and the other 71) are **COMMENT** under upstream's parser. Syntax is resolved; the maintainers' *intent* (disabled,
  superseded, or noted elsewhere) is not, and is not needed for the classification. The earlier THEMIS rule (`strip_prefix: "#"`, "WatchYourBack's own
  convention") was made to fix cross-source address matching and treated the prefix as data formatting; upstream's code does not support that reading.
* **Paper impact of excluding them (MEASURED by full `reproduce-paper` runs on rebuilt tables).** Both exclusions give `PAPER ↔ THEMIS: FAIL` with the
  same 8 failing statements, 2 of them headline: `corpus.claims` (16 -> 1,545,694; 87 -> 1,545,623), WatchYourBack addresses/claims (293 / 222 vs 309),
  `coverage.multi_dataset_addresses` (15,413 -> 15,400 either way), the 2- and 3-dataset distribution cells, Elliptic++ ∩ WatchYourBack (8 -> 7), and
  `currency.missing_revision_claims` (1,035,420 -> 1,035,404 / 1,035,333). Every other statement stays PASS.
* **Decision.** The frozen corpus is **not** changed here: it would reverse an established, tested rule and move published numbers, and the intent question
  is open. Until the author decides, the records remain in the corpus and this section is the visible limitation. Not included to enlarge the corpus, not
  excluded to protect paper numbers: the cost of excluding is stated above. Decision needed: exclude (config `strip_prefix` removed / adapter skips `#`
  lines; paper numbers above change) or keep with the wording that they are lines upstream ignores.
* **Status.** DEFERRED WITH DOCUMENTED LIMITATION (AUTHOR DECISION; the 71 hydra records share the same evidence).

### 25.7 Decision 4C - duplicate-claim identity

* **Where the key lives.** Only the *upload* path (`ingest/validate.py`, streaming `ingest/relational.py`). The frozen seven-source corpus is built by
  `scripts/build_corpus.py`, which never called it, so **no paper number can move through this change**.
* **Change.** Claim identity is `(address, label, declared source)`; the same claim from a second declared source is kept, only a repeat from the
  same declared source (whitespace-normalised) collapses; without a mapped source column behaviour is unchanged. Row-level duplicates still collapse.
  Shared helper `claims.declared_source`, used by both paths and `build_claim`.
* **Quantified on the retained full table** (MEASURED with THEMIS's own `agreement`, `cohen_kappa`, `independence`, `corpus_roots`,
  `anchor_validation`; V0 = frozen as is; V1 = old key; V2 = new key):

| variant | claims | dropped | fields changed vs V0 (of 152 compared) |
|---|---|---|---|
| V0 frozen | 1,545,710 | - | - |
| V2 new key | 1,543,338 | 2,372 (all Schnöring repeats from the *same* declared source) | 9: claim totals, 3 root claim counts, unresolved addresses (853,583 -> 853,769), one anchor self-root count. Agreement outcomes, conflicts, kappa, roots-per-address, independence, anchor validation identical |
| V1 old key | 1,527,623 | 18,087 (TagPack 15,676, every one with a **distinct** declared source; Schnöring 2,411, of which 39 had distinct declared sources) | 33: e.g. multi-source addresses on 3 roots 7,432 -> 399; anchors exact 203 -> 201, licit/illicit conflict 25 -> 27; Schnöring anchor agreement 0.941 -> 0.882 |

  So the old key would have erased 15,715 groups of multi-source corroboration if the corpus had been ingested through it, and moved anchor results.
* **Independence is not implied.** A test uploads one claim under two declared sources: two claims kept, one **unresolved** root, no confirmed
  independent share. (In the frozen corpus TagPack creators are identified roots *by source config*, unchanged; that rule is the author's.)
* **Tests.** `test_ingest` (same source collapses; different sources kept, whitespace-insensitive; no source column unchanged), `test_evidence_invariants`
  (kept but still unresolved / no independence), `test_sqlite_adversarial` (relational path; the old assertion encoded the old key and was rewritten).
* **Impact.** Implementation: 3 source files, +4 tests, 1 rewritten. Paper: **none** (structural, and measured above). Release: uploads with several
  declared sources now report more claims and fewer "duplicate claim" rejections. **Status.** RESOLVED.

### 25.8 Decision 4D - Host / DNS rebinding

* **Decision.** Starlette `TrustedHostMiddleware` (installed dependency), outermost, hostnames from `themis/config/api.yml` `hosts.allowed`
  (`localhost`, `127.0.0.1`); port ignored, so no deployment port is hardcoded; wildcard forbidden by test; the server still binds `127.0.0.1` only.
* **Evidence.** New `TestHostAllowlist` (5 tests): localhost and loopback accepted on any port; `evil.example`, look-alikes
  (`localhost.evil.example`, `127.0.0.1.evil.example`, `localhost@evil.example`), other IPs, `0.0.0.0`, empty Host refused with 400 on GET and on upload
  routes, nothing stored; a refused host leaks no detail. Live check against a running server: `Host: 127.0.0.1:5001` 200, `Host: evil.example` 400.
  Browser E2E after the change: **16/16**.
* **Cost.** 14 test files construct their client with `base_url="http://localhost"` (Starlette's default host `testserver` is now refused).
* **Impact.** Implementation: 2 files + tests; paper none; release: `python -m themis.api` clients must send a local Host (browsers and curl do).
  **Status.** RESOLVED. Residual: other local processes (no authentication), as before.

### 25.9 Final verification (this loop)

| check | result |
|---|---|
| `python -m pytest` (corpus present) | **618 passed, 6 skipped** (was 609 / 6) |
| no reference corpus (`THEMIS_DATA_DIR` empty) | 489 passed, 135 skipped |
| `rm -rf frontend/node_modules; npm ci; npm run build; npm audit` | ci OK (postinstall scripts not approved by npm; build unaffected), build OK, **0 vulnerabilities** |
| `pip-audit` | no known vulnerabilities (the local `themis` package itself is skipped: not on PyPI) |
| browser E2E (Chromium, scratch Playwright) | **16/16** |
| `themis reproduce-paper` (shipped) | **`PAPER ↔ THEMIS: BLOCKED`** (20 PASS / 0 FAIL / 9 NOT_REPRODUCED) |
| retained-table regression | **`REGRESSION VERIFICATION USING RETAINED FULL OBSERVATION TABLE: PASS`** (29 / 29) |
| retained table rebuilt from retained raw files | byte-identical outputs |

### 25.10 Final status

**CONDITIONALLY READY — EXTERNAL CONFIRMATION REQUIRED.** Not `RELEASE READY`: unresolved redistribution rights (Elliptic++, Rodwald, the Ransomwhere
live export, WatchYourBack's GPL reach) could make the public repository inappropriate to distribute, and copyright ownership for the software
license is unconfirmed. Author actions, in order: (1) choose the `demo_data/` policy (§25.2); (2) ask IAR about IP, then pick a license; (3) decide
the 87 `#` WatchYourBack records (§25.6); (4) fix the paper's "openly redistributable" sentence and the "highest declared confidence" wording. The
artifact is otherwise frozen: no further engineering work is open.

## 26. THIRD-PARTY DATA REDISTRIBUTION DECISION LOOP (licensing investigation only)

Date: 2026-09-24. Full record: `THIRD_PARTY_DATA_REDISTRIBUTION.md` (inventory, per-source evidence with URLs, the
matrix, git impact, options, recommendation). Nothing in `demo_data/`, git history, the paper, the corpus, the code or
the licence state was changed. Sections above are historical; where §13 and §25.2 differ from this section, this section
is current: §13's "60.24% unconfirmed" predates the Ransomwhere downgrade (**60.98%** of corpus claims is now unconfirmed;
39.02% confirmed), and §25.2's "89 commits" is now 92.

### 26.1 What is redistributed (OBSERVED)

`demo_data/` tracks 5 files, all `NORMALIZED`/`DERIVED`/`AGGREGATED` (none verbatim, none synthetic):
`observations_sample.csv.gz` (268,891 normalized claims), `revenue.csv.gz` (61,508 per-address USD totals),
`verified_anchors.txt.gz` (146,243 bare addresses), `ground_truth.csv` (289 addresses: OFAC 185 + WatchYourBack 104),
`manifest.json` (counts only). 139,717 of the 268,891 sample rows (51.96%) come from sources with no confirmed
redistribution permission. Every file except `manifest.json` mixes confirmed and unconfirmed sources.

### 26.2 Source-by-source status (OBSERVED 2026-09-24)

| source | exact artifact | licence found | status |
|---|---|---|---|
| GraphSense TagPack | git clone `7f9a5d1` | MIT (`LICENSE`, © Iknaio, © AIT); the repository is the data | **CONFIRMED REDISTRIBUTABLE** |
| Schnöring et al. (the seventh corpus source) | figshare v3 `addresses.csv` | CC BY 4.0 (figshare API, v3) | **CONFIRMED REDISTRIBUTABLE** |
| OFAC SDN (ground truth only; not a corpus source) | `sdn_advanced.xml` | none published; 17 U.S.C. § 105(a) (US Government work) | **CONFIRMED REDISTRIBUTABLE** (statutory basis only) |
| Elliptic++ | `wallets_classes.csv`, authors' Drive | none: GitHub `license: null`, no LICENSE file, README/paper/issue #4 searched; Drive listing not enumerable | **UNCONFIRMED** |
| Rodwald ransomware / mixers | `BTC_Ransom.csv`, `BTC_Mixers.csv` | none: 4,973-byte page has 0 licence/terms/copyright tokens; the files also embed walletexplorer.com / blockchain.info data | **UNCONFIRMED** |
| Ransomwhere | live export 2026-09-20 | CC BY 4.0 on the Zenodo deposit v1.1.0 only | **UNCONFIRMED** |
| WatchYourBack | `btc_resolv.csv` | GPL-3.0 for the repository (software); not shown to govern the data; the file's 309 rows cite 30 other publishers | **UNCONFIRMED** |

**Ransomwhere, measured.** The Zenodo v1.1.0 file (md5 matches the Zenodo record) was compared record by record with
the retained live export: the live export has **8 records the deposit lacks** (all Akira, created 2024-10-29) and
**2,229 shared records whose USD values differ** (after re-pricing); 11,178 addresses' observation fields (address,
family, date, transaction hash/time/amount) are identical, 8,949 records are byte-identical. The CC BY licence is
therefore established for the deposit, not for the artifact THEMIS used, and is not transferred. The site's text
(server-rendered, so an earlier note calling it client-rendered is wrong) has no licence statement, says the data
are "entirely publicly available", and cites the Zenodo DOI for citation. Live API: HTTP 502 today.

### 26.3 Git history (OBSERVED)

Public since 2026-09-16; 0 forks/stars/watchers; `main` only; `HEAD = origin/main = 30ffd0b` (all 92 commits are on
GitHub; the local tags `v1.0-paper*` are not). `demo_data/` is in all 92 commits from the first (`b47da84`) and was
changed in 6 (`b47da84`, `627fa53`, `95ff42f`, `5736bea`, `57e2cc5`, `6245e0c`): 10 blob versions, 6 of which carry
third-party records (`observations_sample` 1 blob in 92 commits; `verified_anchors` 1 in 92; `revenue` 2, in 60 and
32; `ground_truth` 2, in 39 and 53; `manifest.json` 4, aggregates only). `git rm` removes files from `HEAD` only; the
blobs stay reachable from every earlier commit. Removal from history needs `git filter-repo` (not installed) or BFG,
changes all 92 hashes, a force-push, and re-cut tags and release hashes; clones, forks and GitHub caches can retain
the data. **No rewrite was performed or prepared.**

### 26.4 Options and recommendation (author's choice, not made)

* **A, keep:** only TagPack (MIT notice), Schnöring (CC BY: credit, licence link, indicate changes) and OFAC; the files
  would first have to be rebuilt per source, and the six historical blobs are unaffected.
* **B, `git rm` at `HEAD`:** minimal and reversible; history (all 92 commits) still serves the blobs, so it does not
  by itself address distribution through history. Sufficiency is a risk judgment left to the author.
* **C, remove + rewrite history:** removes the blobs from `main`; all hashes change, force-push, stale tags/hashes,
  copies persist elsewhere. Cost is smallest now (one branch, one author, 0 forks).
* **Conservative release policy under uncertainty (not a legal conclusion):** do not include the third-party rows of
  Elliptic++, Rodwald, Ransomwhere (live export) or WatchYourBack until permission is confirmed. The release
  ZIP already excludes `demo_data/`. Recommended order: ask the four parties for written confirmation, then B at
  minimum; C if history must stop serving unconfirmed rows.
* **Reproducibility without rows:** yes for Elliptic++, Rodwald and WatchYourBack (fetch, recorded SHA-256, adapters, and
  aggregate `expected_output/`); only **partly** for Ransomwhere (the live export is a moving target and the
  licence-clean Zenodo copy differs in 8 records and 2,229 USD values, impact not measured); the
  WatchYourBack subset of `ground_truth.csv` and of the anchor set has no regenerating script.

### 26.5 Status

**CONDITIONALLY READY — EXTERNAL CONFIRMATION REQUIRED**, unchanged: permission is confirmed for 3 of the 8 tracked
sources (TagPack, Schnöring, OFAC) and not for the other 5 (Elliptic++, Rodwald ransomware, Rodwald mixers,
Ransomwhere live export, WatchYourBack). Author decisions pending: the `demo_data/` policy (A/B/C), the four permission
requests, the software licence, and the paper's "openly redistributable" wording.
