# MBAL pre-flight defect report

> **Historical record.** Commit hashes, test counts, file states and open decisions below describe the repository when this report was written (for example: `HEAD` `30ffd0b`, no `LICENSE`, `demo_data/` tracked, the earlier paper pin). They were resolved afterwards. The final state is the `v1.0-paper` tag, described by `README.md`, `REPRODUCE.md` and `THIRD_PARTY_DATA.md`.

Scope: what an unseen multi-chain attribution file (MBAL, 10,000,000 rows) exposed in THEMIS's
pre-flight, and how each defect was fixed **generically**. Nothing here says MBAL is reliable.
"Pre-flight now passes" means only: THEMIS understands enough of the schema to analyse the file
defensibly. Evidence files (screenshots, raw JSON) are kept outside the repository, in
`mbal_evidence/`, because they contain MBAL rows.

Baseline: HEAD `30ffd0b`, Python 3.14.6, Node v26.8.2, npm 11.19.1; 618 tests passed, 6 skipped.

## 1. The original GUI failure

Reproduced against the pre-change code (`git archive HEAD`) with the real browser:

| screen | what THEMIS said |
|---|---|
| Dataset type | "Not cryptocurrency attribution data" |
| Claim subject | "none found" |
| Verdict | "This dataset does not appear to contain cryptocurrency attribution data." |
| `address` column | "invalid: the values do not fit (1%)" |
| Chains offered | `["bitcoin"]` only |

The "wrong mappings" seen in the GUI (`chain → Declared confidence`, `address → Market timestamp`,
`categories → Timestamp: dataset creation`, `entity → Actor`) were **not produced by inference**.
On a fresh load none of them appears and nothing says "set by you". Replaying those five dropdown
selections in the old GUI reproduces the reported screen exactly, including
`address → Market timestamp: valid · set by you` and `chain → Declared confidence: valid`
(`baseline-old-stratified-edited-*`). So they were user selections, and the defect is that the old
pre-flight **accepted** them.

## 2. Root causes (all generic)

| # | defect | class | where |
|---|---|---|---|
| D1 | No EVM adapter. Ethereum/BNB/Polygon/Avalanche identifiers could not be validated, so 82% of the file was "not an address" | THEMIS | `chains/` |
| D2 | A chain name such as `bitcoin_mainnet` never resolved to a chain; a per-row chain column was only understood when it held one value | THEMIS | `chains/base.py`, `preflight._resolve_chain` |
| D3 | Profiling used the first 500 non-empty values of each column: what a column "is" depended on how the file was sorted | THEMIS | `detect.sample_values` |
| D4 | A user's mapping skipped value validation for shape-only semantics (`ts_market_candle` is in `_SHAPE_ONLY`) and for any free-form role: a value fit below the review threshold was only a note, status stayed "valid" | THEMIS | `preflight._column_record` |
| D5 | "Confidence" accepted any column with ≤10 distinct values, so a chain-name column (5 values) or a source-class column (3 values) qualified | THEMIS | `preflight._value_score` |
| D6 | Timestamp checks listed *invalid* user-mapped columns as "date columns present" | THEMIS | `preflight._checks` |
| D7 | Dataset state had two outcomes: supported or "does not appear to contain cryptocurrency attribution data" | THEMIS | `preflight._dataset_type` |
| D8 | A user's broken mapping made THEMIS say the *file* was not attribution data | THEMIS | same |
| D9 | Claim identity was the bare address; the audit, views, trust predicates and address inspector grouped by address string only, and the reference corpus was matched by string regardless of chain | THEMIS | `validate`, `target_audit`, `views`, `api`, `trust/` |
| D10 | A required label was `label or category`: a blank *entity* rejected rows that had a category; `entity` could become the claimed label | THEMIS | `validate`, `preflight` |
| D11 | A 3-value evidence-class column was reported as "N of N claims name a declared source: computed" | THEMIS | `ingest/gating.py` |
| D12 | The regex `$` accepts a trailing `\n` (found while writing the EVM adapter): `0x…\n` would have validated | THEMIS (caught before release) | `chains/evm.py` |
| D13 | Target audit: two distinct roots that both belong to *reference* sources made an address count as "distinct provenance" for a target whose own root was unresolved, and the profile counted it as "confirmed independent multi-root" | THEMIS | `target_audit._address_status`, profile counters |
| D14 | Overview crashed (blank page) whenever an upload had rejected rows: it read `validation.rejected`, the backend sends `rejected_examples` | THEMIS (UI/backend mismatch) | `Overview.jsx` |
| D15 | The claim's own category text (`subcat`) was not shown anywhere; only the taxonomy-mapped category ("unknown") appeared | THEMIS (UI/backend mismatch) | `api.py`, `Claims.jsx` |
| D16 | The mapping screen could not be reset, and re-choosing the same file did not fire `change`, so earlier edits silently persisted | THEMIS (UI) | `Home.jsx` |
| D17 | The validation summary carried per-row lists (`valid_chains`, `valid_labels`); introduced by this work, caught by the 10M-row test (307 MB `/summary`), guarded by a test that fails when the leak is restored | THEMIS | `ingest/pipeline.py` |
| D18 | The analysis summary and the job-status response carried a per-address map that no screen reads (1.5 GB at 10M rows); the browser tab crashed | THEMIS | `api.py` |
| D19 | The browser hashed the whole file in memory before upload (Web Crypto has no streaming digest); crashed the tab on an 850 MB file. The limit is now `api.yml: upload.browser_hash_max_bytes` and the server's hash is shown for larger files | THEMIS (UI) | `Home.jsx`, `api.py` |
| D20 | The address inspector's `chain` parameter was silently dropped (a `replace()` of mine that matched nothing): `?chain=polygon` returned the Ethereum claims. Caught at scale, guarded by four tests, one shown to fail without the fix | THEMIS (introduced and fixed within this work) | `api.py` |

Dataset problems are **not** in this table (see §6).

## 3. Row-order findings (Phase 5)

The same pre-flight logic against differently ordered or selected inputs. "Old" = HEAD, "new" = now.

| input | old classification | new classification | new chain | new identifier validity |
|---|---|---|---|---|
| original order, first 1,000 | non_crypto | attribution_like_unresolved (blocked) | — | 0.4% |
| original order, first 10,000 | non_crypto | attribution_like_unresolved (blocked) | — | 0.0% |
| original order, first 100,000 | non_crypto | attribution_claims (needs confirmation) | per row | 48.6% |
| 100k random (seed 42) | non_crypto | attribution_claims (ready) | per row | 83.4% |
| 100k stratified | non_crypto | attribution_claims (ready) | per row | 81.6% |
| 100k random, sorted by chain | non_crypto | attribution_claims (ready) | per row | 80.0% |
| Ethereum-only | non_crypto | attribution_claims (ready) | ethereum | 100% |
| BNB-only | unsupported_chain | attribution_claims (ready) | bnb_smart_chain | 100% |
| Polygon-only | unsupported_chain | attribution_claims (ready) | polygon | 100% |
| Avalanche-only | non_crypto | attribution_claims (ready) | avalanche_c | 99.8% |
| Bitcoin-only | non_crypto | attribution_like_unresolved (blocked) | — | 3.8% |
| balanced five-chain | non_crypto | attribution_claims (ready) | per row | 82.8% |

The old code said `non_crypto` for every input, so its failure was dominated by D1 (no EVM adapter) and
the Bitcoin lowercasing, not by ordering alone. To isolate ordering, the *new* code was also run with
the old "first rows" sampling (see the validation report §11): the result then depends on the prefix.
That is `ROW-ORDER-BIASED SCHEMA DETECTION` (measured: the same rows in reversed order made first-rows sampling conclude a single chain with 100% valid identifiers), fixed by D3 (seeded uniform draw over the whole input,
`profile_rows: 20000`, `sample_seed: 0`, both in `config/preflight.yml`).

Files whose first rows are unrepresentative are still judged by what they contain: the first 1,000 rows
(one chain, lowercased Bitcoin) are **correctly** reported as attribution-like with an unresolved
schema, not as non-attribution data.

## 4. Address-validation findings (Phase 11)

Full-file streaming counts, THEMIS's own Base58Check / Bech32 / EVM rules, nothing repaired:

| chain | rows | valid | invalid | notes |
|---|---:|---:|---:|---|
| bitcoin | 1,808,605 | 49,298 | 1,759,307 | Base58Check valid 1; Bech32 valid 49,297 |
| ethereum | 6,346,154 | 6,345,317 | 837 | all valid ones lowercase |
| bnb_chain | 1,605,827 | 1,605,794 | 33 | |
| polygon | 194,825 | 194,783 | 42 | |
| avalanche_c | 44,589 | 44,550 | 39 | |

Bitcoin, in detail: 1,758,356 Base58 addresses (start `1`/`3`): **100% are all-lowercase**; 788,260 use a
character outside the Base58 alphabet (788,231 of them the letter `l`, which real Base58 never contains);
970,090 fail the checksum; 5 have a bad length; 1 is valid. Bech32/Bech32m: 49,297 valid, 425 invalid.
527 are neither. Case-folding is *proved* for the 788,260 alphabet failures (a genuine address cannot
contain `l`) and overwhelmingly likely for all others (a genuine Base58 address is entirely lowercase
with probability about 2e-8). It cannot be proved per row without the originals and **no repair was
attempted**. Classified as `DATASET IDENTIFIER-INTEGRITY LIMITATION`, not a THEMIS defect.

EVM: syntax = `0x` + exactly 40 hex characters, nothing else; EIP-55 is reported separately.
No EVM identifier in the file is mixed-case, so **none encodes a checksum**: valid, `checksum not
encoded`, not "checksum failed". The 951 EVM failures include zero-width-space padding, mojibake of it,
appended SQL fragments, bare numbers and `protocol:name` strings. 117 addresses carry outer whitespace
(21 are valid Ethereum addresses with a trailing newline); THEMIS trims outer whitespace, **counts** it
and reports it, and rejects anything else (a zero-width character is not whitespace).

## 5. Mapping, multi-chain, multi-label and source-semantics decisions

**Mapping validation (D4–D6).** A choice picks the column; it never waives what the column contains.
`ts_*` roles need ISO-date-shaped values (including `ts_market_candle` and `ts_unclassified`); `chain`
needs values that resolve to a supported chain; `attribution_confidence` needs numbers or grades from a
configured vocabulary (`confidence_grades`); an identifier-shaped column cannot be a label, category,
actor, evidence, source, confidence or chain. Configured in `config/preflight.yml`
(`strict_value_semantics`, `identifier_excluded_semantics`).

**First-class chain semantics (D2).** `chain` / `blockchain` / `network` is a semantic field. A chain
column that resolves to one chain fixes it; one that resolves to several makes the chain **per row**:
each identifier is validated under its own row's chain and reported per chain. An unrecognised chain
name rejects the row, it is never assigned. Chain names normalise generically (lowercase,
non-alphanumerics to `_`, a trailing `_mainnet` dropped); a testnet name never resolves. Aliases live in
`config/chains.yml`.

**Multi-chain identity (D9).** A subject is `(chain, address)`; a claim is
`(chain, address, label, declared source)`. The reference corpus is matched only through the chain its
source declares (`Corpus.for_subject`); a source that declares none is not filtered, so the bundled
Bitcoin corpus is unaffected. The same string on four chains gives four subjects and four claims
(regression tests).

**Multi-label (Phase 13).** The MBAL documentation states "an address may belong to multiple
categories". THEMIS never splits by default. A label/category column is treated as token lists only
when the *column itself* shows it: at least 90% of its multi-token cells are built entirely from tokens
that also occur on their own elsewhere in the column, with no whitespace in any token. Then each token
is one claim, the whole cell is kept on every claim (`label_cell`), the first token is never picked, and
no hierarchy is inferred. `Doe, John`, one-off combinations and `a/b` are not split. Rows, addresses and
claims are counted separately (100,000 rows → 82,420 valid rows → 88,528 claims on the random sample).

**Source semantics (D11).** Upstream defines `source` as the label-generation method
(`ground_truth` = official reports, `external` = public platforms with a manual check of 20%,
`heuristic` = Common Spending / Fund Gathering). It is treated as a declared string. A declared-source
column with at most 12 distinct values over many rows is a *class of evidence*: provenance is reported
"insufficient data", every claim's root stays UNRESOLVED, the string never raises the evidence tier, and
three values are never three independent sources. `entity` is metadata (`attribution_entity`): it never
influences truth, provenance, independence, confidence or identifier validity, and is not required.

## 6. What is a MBAL limitation, not a THEMIS defect

lowercased Bitcoin identifiers (checksums destroyed); no per-row provenance or timestamp; a
`source` field whose meaning is a method class; 951 malformed EVM identifiers and injected text;
no EIP-55 checksums; paper and file disagree on chains, categories, entities and source shares
(validation report §3). None was "fixed" by weakening validation.

## 7. Generic fixes and regression tests

New: `themis/chains/evm.py`, `themis/config/chains.yml`, `tests/test_multichain_generalization.py`
(52 tests, synthetic fixtures, no MBAL names). Changed: `chains/base.py`, `config_io.py`, `corpus.py`,
`ingest/{detect,preflight,validate,claims,pipeline,gating,relational}.py`, `target_audit.py`,
`views.py`, `trust/*`, `api.py`, `config/preflight.yml`, and the frontend
(`Preflight`, `Home`, `Overview`, `Claims`, `Conflicts`, `Address`).
Existing tests that used Ethereum as the "unsupported chain" example were moved to Tron (a chain THEMIS
still lacks), and the "clean head, bad tail" test now forces a head-only sample so it still exercises
the full-file backstop. One test asserting the old private alias helper was replaced by a resolver test.

## 8. Before / after and backend comparison

- Old backend raw response: `mbal_evidence/baseline_preflight_stratified_raw.json`
  (`dataset_type: non_crypto`, `chains: ["bitcoin"]`).
- Old GUI: `baseline-old-stratified-initial.png`, `baseline-old-stratified-edited-after-edits.png`.
- New GUI: `after-new-stratified-initial.png`, `new-random-*.png`; new raw JSON:
  `after-new-stratified-gui-raw-preflight.json`.
- The GUI renders the backend's `checks`, `columns`, `established` and `blockers` without deriving
  anything; the same five bad selections now read `invalid` with the reason, and are never a verdict on
  the file (`mapping_unresolved`).
- Responsibility for the original failure: **BACKEND** (D1–D8). The GUI defects are D14–D16.

Success here does not mean MBAL is reliable. See `MBAL_VALIDATION_REPORT.md` for what THEMIS can and
cannot establish about it.
