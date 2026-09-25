# MBAL validation report

**Two questions, kept apart.**
**A.** Does THEMIS correctly understand and analyse an unfamiliar dataset?
**B.** What can THEMIS scientifically establish about MBAL itself?

The purpose was to find THEMIS defects and to fix only genuine ones, generically. It was not to make MBAL
pass. Nothing in production code names MBAL, its columns, its chain strings or its source strings; the paper
corpus, its numbers and its methodology were not touched. No MBAL row is committed: test files, screenshots
and raw JSON live in `mbal_testdata/` and `mbal_evidence/`, beside the repository, and this report quotes
counts, hashes and character classes only.

Companion: `MBAL_PREFLIGHT_DEFECT_REPORT.md` (the Phase 18 gate).

---

## BASELINE — BEFORE MBAL-DRIVEN FIXES

| item | value |
|---|---|
| HEAD | `30ffd0b88a586e3cfbf6a4ac0ecec449a32e3e9a` (branch `main`) |
| working tree at start | `M THEMIS_RELEASE_READINESS_REPORT.md`, `M themis/config/api.yml`, `?? THIRD_PARTY_DATA_REDISTRIBUTION.md` (pre-existing, not part of this work) |
| Python / Node / npm | 3.14.6 / v26.8.2 / 11.19.1 |
| tests | 618 passed, 6 skipped (the 6 need a full corpus build) |
| GUI on the stratified sample | Dataset type "Not cryptocurrency attribution data"; claim subject "none found"; attribution label `entity`; `address` "invalid (1%)"; only `bitcoin` offered as a chain |
| raw backend response | `dataset_type: non_crypto`, `status: unsupported` (`baseline_preflight_stratified_raw.json`) |
| automatic mappings | `chain` not used, `address` invalid, `categories` not used, `entity` label 88%, `source` declared source 100% |
| the "wrong" mappings | not automatic. Replaying five dropdown choices in the old GUI reproduces the reported screen exactly (`address → Market timestamp` "valid · set by you", `chain → Declared confidence` "valid"): the old pre-flight *accepted* them |

Evidence: `mbal_evidence/baseline-old-stratified-{initial,edited-after-edits}.png`, `…-gui.json`.

---

## 1. Exact file identity

| file | rows | bytes | SHA-256 |
|---|---:|---:|---|
| `dataset_10m_ads.csv` | 10,000,000 logical (10,000,023 physical lines) | 850,176,864 | `0dc4c04a2994af6aa9cc6f3216b252b5bfd315d3ea8042a05ffacdd070b52a57` (recomputed, matches) |
| `mbal_100k_stratified.csv` (was `mbal_100k_test.csv`) | 100,000 | 8,547,145 | `2aa065e89b6305d15baa6842694fc3bc118ee38d14b0fcca6984c55b5a2bd7dd` |
| `mbal_100k_random.csv` | 100,000 | 8,501,575 | `a433877698dc23952b8ffeca5b79715eda6d7b02f6494f29a3ac34347a71d2e4` |
| `mbal_edge_cases.csv` | 103 | — | `69514f44f8595e95dd4d26a70d97efcfae1acc5755d8514cca09fb6c8b4370c3` |

The file's modification time is 2024-02-08, the date of Kaggle version 1. No official hash for the artifact
is published, so identity to the Kaggle download rests on that date and the documented schema, not on a
checksum. Random sample: `random.Random(42).sample(range(10_000_000), 100_000)` under Python 3.14.6, taken
in file order from one streaming pass. The stratified file is used for coverage only (§18).

## 2. Authoritative references

| what | where |
|---|---|
| paper | He, Yang, Dong, Jiang, Pan, Chen, Song, Luo, Chen, Zhang, "MBAL: A 10-Million Annotated Crypto Address Dataset Across Leading Blockchains", *Blockchain: Research and Applications*, accepted 2026-07-30, journal pre-proof. DOI <https://doi.org/10.1016/j.bcra.2026.100555>; ScienceDirect PII S2096-7209(26)00116-8; local copy `1-s2.0-S2096720926001168-main.pdf` |
| dataset | Kaggle, <https://www.kaggle.com/datasets/yidongchaintoolai/mbal-10m-crypto-address-label-dataset>, (three of the authors, including the corresponding author, are affiliated with Codatta), version 1, modified 2024-02-08T15:05:42Z, download 993,552,997 bytes (zip of six files) |
| the Kaggle page's title for the article | "MBAL: A Dataset of 10 Million Annotated Crypto Addresses with Categories and Entities on Leading Blockchain Networks" (differs from the accepted title) |
| licence | **CC0 1.0** for the Kaggle dataset; the *article* is CC BY-NC-ND. The paper states no separate licence for the data |
| schema stated by Kaggle | `chain` (5 values incl. `avalanche_c_chain`), `address`, `categories` ("62 possible values. An address may belong to multiple categories"), `entity` ("may be unique or empty"), `source` ("three possible values: ground_truth, heuristic, external"). The page says "six columns" and lists five |
| label generation (paper §3.1) | ground truth = "official reports (e.g. OFAC sanctions list) and significant security incident records", "deemed highly trustworthy, so no further validation was needed"; external = Twitter, Discord, block explorers, "less reliable", 20% of labels per category manually checked by 10 students (Cohen's kappa 0.82); heuristic = Common Spending (multi-input) and Fund Gathering, "weak labels", never allowed to override validated ones |
| the paper's own error estimate | 16,060 manually checked records, 3.0% erroneous overall (ground truth 3.01%, external 2.98%, heuristic 3.00%), the same rate in every stratum |

Where the upstream text is silent, this report says so rather than inferring.

## 3. Paper ↔ file

| item | paper | downloaded file | classification |
|---|---|---|---|
| chains | 4: Bitcoin, Ethereum, BSC, Polygon | **5**: + Avalanche C-Chain (44,589 rows); the Kaggle page also lists 5 | PAPER / RELEASE MISMATCH |
| categories | 63 | 62 atomic (927 combinations) | DATASET VERSION EVOLUTION (which taxonomy version is unresolved) |
| entities | 933 (text) / 932 (Table 4), over 7,710,243 addresses | 413 distinct non-empty values over 3,446,839 rows | PAPER / RELEASE MISMATCH; the paper is also internally inconsistent (933 vs 932) |
| addresses | 10,000,000 | 10,000,000, all unique | agrees |
| ground truth | 3,767,030 (37.67%) | 6,238,900 (62.39%) | DATASET VERSION EVOLUTION |
| external | 939,832 (9.40%) | 1,780,144 (17.80%) | DATASET VERSION EVOLUTION |
| heuristic | 5,293,138 (52.93%) (abstract 5.3M, introduction 5.2M) | 1,980,956 (19.81%) | DATASET VERSION EVOLUTION |
| "validated" (GT + external) | 4,706,863 | 8,019,044 | derived from the two rows above |
| labels | 10,601,243 | 10,643,033 label instances | close, not equal |
| per chain (rows) | Bitcoin 4,595,936 / Ethereum 3,968,206 / BSC 1,376,518 / Polygon 59,340 | 1,808,605 / 6,346,154 / 1,605,827 / 194,825 | DATASET VERSION EVOLUTION |
| entities per chain | BSC 41, Polygon 105 | entity populated on 123 BSC rows and 15 Polygon rows | DATASET VERSION EVOLUTION |
| columns | not enumerated | five, the Kaggle page says "six" | DOCUMENTATION DIFFERENCE |
| paper's example addresses | one "Ethereum" example contains non-hex characters | — | DOCUMENTATION DIFFERENCE (illustrative text, not data) |
| parsing | — | 10,000,000 logical records in 10,000,023 physical lines | PARSING DIFFERENCE, accounted for (§10) |

The file (Feb 2024) predates the manuscript (accepted July 2026) by two and a half years and does not
reproduce its tables. **The paper and the file are not treated as the same artifact.** Anything the paper
says about label quality applies to the version it describes, not to this file.

## 4. Licence

CC0 1.0 (Kaggle). Nothing here redistributes MBAL rows; the derived test files are kept outside the
repository.

## 5. Schema

`chain, address, categories, entity, source`. THEMIS maps them (inferred, none set by a user):
`chain` → Blockchain (per row), `address` → Claim subject: address, `categories` → Attribution category,
`entity` → Entity (who), `source` → Declared source (flagged as a class of evidence).

## 6. Source-field semantics

Upstream defines `source` as how the label was made, not who made it. THEMIS therefore never reads
`ground_truth` as verified truth, `external` as confirmed provenance, or the three values as three sources.
Declared-source counts on the random sample: ground_truth 54,859, heuristic 21,455, external 12,214
claims; **provenance state: "insufficient data — a class or method of evidence, not where each claim came
from"**, every claim's root UNRESOLVED, evidence tier UNKNOWN for all 88,528 claims. `source` is also
confounded with chain: every BNB, Polygon and Avalanche row is `ground_truth`; `heuristic` appears only on
Bitcoin (142,378) and Ethereum (1,838,578).

## 7. Chain semantics

Five chain strings, each resolving to a registered chain (`ethereum`, `bitcoin`, `bnb_smart_chain`,
`polygon`, `avalanche_c`). The chain is stated **per row**, so each identifier is validated under its own
row's chain. An EVM address is syntactically identical on all four EVM chains, so the chain column is the
only thing that says which chain a subject is on. Without it THEMIS reports the chain as ambiguous and asks.
Full-file rows: Ethereum 6,346,154; Bitcoin 1,808,605; BNB 1,605,827; Polygon 194,825; Avalanche 44,589.

## 8. Category semantics

62 atomic categories, 927 distinct cells, 10,643,033 label instances. Confirmed multi-label
(documentation and data): 607,165 rows carry more than one label (the top combinations are
`cex,exchange` 295,564 and `nft,smart_contract` 151,331). THEMIS split them because the column itself
showed it is a token list (§16). **Taxonomy interpretability: THEMIS's taxonomy maps 12 of the 62 atomic
categories, covering 41.7% of label instances**; the rest (smart_contract, liquid_staking, wallet, nft,
honeypot, proxy, no_kyc, …) are not in THEMIS's taxonomy and are reported `unknown`, not guessed. That
measures the gap between two taxonomies; it is not a defect in either.

## 9. Entity semantics

3,446,839 of 10,000,000 rows (34.47%) carry an entity; 6,553,161 are blank. By chain: Ethereum 3,217,937
(50.7% of its rows), Bitcoin 228,536 (12.6%), Avalanche 228, BNB 123, Polygon 15. 413 distinct values; the
most frequent are `binance` (1,948,120), `metamask` (478,538), `coinbase` (165,779). THEMIS treats the
entity as metadata about the claim: it does not raise truth, provenance, independence, confidence or
identifier validity, is never required, and is never used as the claimed label when a category exists.
"An entity is named" is reported as coverage, not as ownership proven.

## 10. Parser findings

The logical-record count is **10,000,000** (streaming `csv`), against 10,000,023 physical lines: the header
plus 22 embedded line breaks inside 21 quoted address values. THEMIS's own parse stage reported
"10,000,000 rows · 5 columns". No row or column shift: every record has exactly five fields. Regression
test `TestLogicalCsvRecords` covers an embedded newline, a quoted comma, a quoted double quote, an empty
field, a 100,000-character field, Unicode and CRLF. All 21 embedded-newline values are a valid Ethereum
address followed by `\n`.

## 11. Row-order bias experiment

Old code: every ordering was classified `non_crypto`, dominated by the missing EVM adapter and the
lowercased Bitcoin. To isolate ordering, the *new* code was run with the *old* "first rows" sampling and
with uniform sampling on identical inputs:

| input | first-rows sampling | uniform sampling |
|---|---|---|
| original order, first 1,000 / 10,000 | attribution-like, schema unresolved (0.2% valid) | attribution-like, schema unresolved (0.4% / 0.0%) |
| original order, first 100,000 | **attribution-like, schema unresolved (0.2% valid)** | **supported, chain per row (48.6% valid)** |
| 100k random | supported, per row (61.4%) | supported, per row (83.4%) |
| 100k random sorted by chain | supported, per row (84.0%) | supported, per row (80.0%) |
| 100k random sorted by chain, reversed | **supported, ONE chain "determined", 100% valid** | supported, per row (82.8%) |

Identical rows in a different order made first-rows sampling conclude the file has a single chain and
100% valid identifiers. That is `ROW-ORDER-BIASED SCHEMA DETECTION`. Fixed generically: a seeded uniform
draw over the whole input (§ defect report D3). Small differences between uniform-sampling rows (0.80 vs
0.83) are ordinary sampling noise; the classification and chain state do not move.

## 12. Address validation by chain (full file)

| chain | rows | valid | invalid | Base58Check valid/invalid | Bech32 valid/invalid | other |
|---|---:|---:|---:|---|---|---:|
| bitcoin | 1,808,605 | 49,298 | 1,759,307 | 1 / 1,758,355 | 49,297 / 425 | 527 |
| ethereum | 6,346,154 | 6,345,317 | 837 | — | — | — |
| bnb_smart_chain | 1,605,827 | 1,605,794 | 33 | — | — | — |
| polygon | 194,825 | 194,783 | 42 | — | — | — |
| avalanche_c | 44,589 | 44,550 | 39 | — | — | — |

Within the 1,758,355 Base58 failures: 788,260 use a character outside the Base58 alphabet, 5 have the wrong
length, 970,090 fail the checksum. These are strict counts (no trimming). THEMIS's own full pipeline, which
also trims outer whitespace and counts it (82 identifiers), validates 8,239,804 of 10,000,000 identifiers
(82.40%): Ethereum 6,345,355, BNB 1,605,794, Polygon 194,783, Avalanche 44,550, Bitcoin 49,322. Ten of those
rows repeat a claim already made on an unpadded row (same chain, address, label and source) and are rejected
as duplicate claims, leaving **8,239,794 valid rows**; 21 subjects appear on two rows because a padded
identifier equals an unpadded one elsewhere in the file.

## 13. The Bitcoin lowercase finding — DATASET IDENTIFIER-INTEGRITY LIMITATION

All 1,758,356 Base58 addresses (starting `1` or `3`) are lowercase. 788,231 contain the letter `l`, which
does not exist in the Base58 alphabet, so those cannot be the original addresses. A genuine Base58 address
is entirely lowercase-or-digits with probability of about 2e-8, so all 1,758,356 having no capital letter
shows that **case-folding happened to the whole population**, and 970,090 further checksum failures are what
folding produces (any case change breaks a 32-bit checksum with probability 1 − 2⁻³²). Case-folding is
*proved* for the 788,260 alphabet failures and overwhelmingly likely for the rest; it cannot be shown per
row without the originals. **No repair was attempted, none is possible, and THEMIS does not match
identifiers case-insensitively.** Bech32 is lowercase by definition, so 49,297 native-SegWit addresses
remain valid. The paper's own printed Bitcoin example is lowercase as well. This is a dataset limitation,
not a THEMIS defect, and it was not "fixed" by weakening validation.

Independent confirmation, diagnostic only (never evidence, never an identity rule): the reference sample
holds 225,286 Base58 Bitcoin addresses, 225,284 of them with at least one capital letter. Of those, **1,104
reappear in the file only when case is ignored**, against 31 exact-string matches (native SegWit and
all-lowercase cases). The same real addresses are in the file, case-folded. THEMIS does not match
case-insensitively (a lowercase string is a different identifier), so none of the 1,104 counts as a
reference match; the number says that the folding is real and that a repaired copy of MBAL would overlap the
reference corpus far more than the file does.

## 14. EVM checksum interpretation

Validity is `0x` plus exactly 40 hex characters, nothing else. EIP-55 is reported separately. All
8,190,444 valid EVM identifiers are single-case (lowercase); **none encodes a checksum**. That is reported
as "checksum not encoded", not "checksum failed", and lowercase is not treated as invalid. What it costs:
a mistyped or altered address cannot be detected from them. The 951 EVM failures are zero-width-space
padding, mojibake of it, appended SQL fragments, bare numbers and `protocol:name` strings; one Ethereum row
holds a 126-character injected string. They are rejected with a reason and rendered as text.

## 15. Multi-chain identity

A subject is `(chain, address)`; a claim is `(chain, address, label, declared source)`. In this file all
10,000,000 address strings are unique, so no cross-chain collision occurs in the data; the rule is tested on
a synthetic fixture (the same string on Ethereum, Polygon, BNB and Avalanche gives four subjects, four
claims, no false duplicate). The reference corpus is matched only through the chain its source declares
(all seven bundled sources declare Bitcoin), so an EVM identifier can never match a reference claim by string.

## 16. Multi-label findings

Decision (documented upstream, re-derived from the data): the column holds token lists when at least 90% of
its multi-token cells are built only from tokens that also occur on their own. Then one claim per token,
the whole cell kept on every claim, no first-token selection, no inferred hierarchy. Measured on the full 10,000,000-cell column: 607,165 multi-token cells, 99.88% built entirely from established tokens, 57 established tokens (100k random sample: 99.5%, 32 tokens; stratified: 97.8%, 57). Rows, addresses and
claims are counted apart: **random sample 100,000 rows → 82,420 valid rows → 82,420 addresses → 88,528
claims**; full file 8,239,794 valid rows → 8,856,557 claims. Tested: one label, two, known plus unknown,
three, hierarchical-looking (`a/b`, `a:b`), a comma inside a literal (`Doe, John`), and unestablished
combinations (not split).

## 17. Random-sample analysis (population estimates)

`mbal_100k_random.csv`, THEMIS pipeline, no reference: 100,000 rows; 17,580 rejected (all "invalid
address": Bitcoin 17,570, Ethereum 7, BNB 2, Avalanche 1); 82,420 valid rows; 88,528 claims; 82,420
subjects; 26,832 claims (30.3%) with a category THEMIS's taxonomy maps; 36,041 claims carry an entity.
The sample's rejected share (17.58%) matches the full file's (17.60%), as it should.

## 18. Stratified-sample analysis (coverage only)

`mbal_100k_stratified.csv` reaches 55 distinct atomic tokens and the rare categories, which the random
sample misses (36 tokens). It was used for **coverage, rare conditions and schema behaviour only**: no
prevalence in this report comes from it. Its pipeline run: 82,707 valid rows, 94,239 claims.

## 19. Edge-case analysis

`mbal_edge_cases.csv` (103 rows: all five chains, all three source values, blank and populated entities,
single and multi-label cells, the nine rare categories, the three most common, shortest and longest
addresses per chain, valid and invalid Bitcoin and EVM examples, and embedded-newline records): 63 valid
rows, 40 rejected as invalid addresses, 3 identifiers trimmed (trailing newline) and accepted, 63 claims.

## 20. Intrinsic analysis (no reference corpus)

| property | finding (full file unless marked) |
|---|---|
| logical records / duplicates | 10,000,000; 0 duplicate addresses; duplicate claims none |
| identifier validity | 8,239,794 valid rows (82.4%); Bitcoin 2.7% valid, every EVM chain ≥ 99.98% |
| invalid classes | Bitcoin: alphabet 788,260, checksum 970,090, length 5, Bech32 425, other 527. EVM: 951 (padding, injected text, numbers, names) |
| label coverage | every row has a category (none blank) |
| taxonomy interpretability | 12/62 atomic categories = 41.7% of label instances mapped by THEMIS's taxonomy |
| multi-label structure | 607,165 rows (6.07%) carry ≥ 2 labels |
| entity coverage | 34.47% of rows; 50.7% Ethereum, 12.6% Bitcoin, ~0% BNB/Polygon/Avalanche |
| declared evidence method | ground_truth 62.4%, external 17.8%, heuristic 19.8%, confounded with chain (§6) |
| conflicts | within the file none can arise from unique addresses (a row's own labels are simultaneous, not competing); against the bundled reference sample 19 of 31 comparable subjects disagree (§21) |
| missing fields | entity blank on 65.5%; no timestamp, no per-row provenance URL, no confidence column |
| timestamps | none: staleness "not applicable", stated |
| provenance information present | none beyond the three-value method class; every root UNRESOLVED |

This is **not** cross-source corroboration.

## 21. Reference-corpus comparison

Run with the bundled reference sample (the full corpus is not redistributed; the sample holds 268,891
claims, all Bitcoin, from seven sources). **Random sample: 1 of 82,420 subjects (0.0012%) is also named by
the reference corpus** (a Bech32 address); the stratified sample also finds 1. Neither can say more. Every
EVM claim is incomparable by construction (no EVM reference source). For the one matched subject: label
agreement "exact"; MBAL's own root is UNRESOLVED, so **independence is "unresolved" (0 confirmed, 1
unresolved)**. Before this work THEMIS reported that address as one of two "confirmed independent roots":
the two roots belonged to reference sources, and it credited them to the target (defect D13). Agreement
with a reference source is not truth; one overlap is not corroboration.

**Full file (10,000,000 rows), same reference sample, through the real GUI/API:** 31 of 8,239,773 subjects
(0.0004%) are also named by the reference corpus; all 31 are native-SegWit addresses, the only Bitcoin
identifiers whose lowercase form survives folding. Outcomes over those 31: exact agreement 10 (32.3%),
entity-type conflict 10 (32.3%), licit/illicit conflict 9 (29.0%; Wilson 95% interval 16–47%), incomparable 2,
hierarchical refinement 0. Independence: 31 apparent multi-source subjects, **0 confirmed independent, 31
unresolved** (MBAL's own root is unresolved in every case). What that does and does not say: the reference
corpus here is a sample of Bitcoin sources under a different taxonomy; the 31 are an unrepresentative
slice; disagreement between two label vocabularies is not evidence about which is right; and agreement
with a reference source is not truth. No agreement rate is offered for MBAL as a whole because 31 subjects
in 8.2 million cannot support one. All 1,104 case-folded overlaps of §13 are excluded by design.

## 22. GUI ↔ backend consistency

Same input, same analysis (`mbal_100k_random.csv`, the 100k random file): every number on Overview, Claims,
Conflicts and Trust was traced to the backend JSON (`trace_numbers`): Overview 15/15, Claims 3/3,
Conflicts 1/1, Trust 3/3. The GUI derives nothing: the pre-flight `checks`, `established`, `blockers` and
per-chain validity are rendered as delivered. Two GUI/backend mismatches were found and fixed (defects
D14, D15).

## 23. Every THEMIS defect found

D1–D16 in the defect report, plus four found later: **D20** the address inspector silently ignored its `chain` argument (a mis-applied edit of mine, caught at scale, guarded by tests); **D17** the validation summary carried per-row lists
(`valid_chains`, `valid_labels`), which made `/summary` 307 MB at 10M rows (introduced by this work, caught
by the scale test, guarded by a test); **D18** the summary carried the per-address maps (1.5 GB at 10M rows,
unused by any screen); **D19** the browser hashed the whole file in memory before upload, which crashed the
tab on an 850 MB file. The job-status response also carried the per-address maps (D18 extended). Also: claims paging re-sorted all claims on every request (10–18 s at 8.8M claims)
and `analysis_summary.json` was built as one string.

## 24. Every MBAL limitation found

Lowercased Bitcoin identifiers (1,758,356, checksums unverifiable); no EIP-55 checksums; 951 malformed EVM
identifiers, 117 padded ones, injected text; no timestamp; no per-row provenance; a `source` field that is a
method class and is confounded with chain; entity nearly absent outside Ethereum/Bitcoin; a taxonomy mostly
outside THEMIS's; the paper and the file disagree on chains, categories, entities and source shares; the
paper's stated error rate (3.0%) is for a different version and applies to labels, not to identifier
integrity.

## 25. Generic fixes

See the defect report §7 and D1–D19. New `themis/chains/evm.py` and `themis/config/chains.yml`; sampling,
value validation, per-row chain, subject identity, category-first labels, entity metadata, multi-label,
source-class provenance, an honest dataset state, independence attribution in the audit, bounded payloads,
browser hash limit. Every constant sits in `config/preflight.yml`, `config/chains.yml` or `config/api.yml`.

## 26. Test results

Full Python suite, this work included: **671 passed, 6 skipped** (baseline 618 / 6; the 6 skips need a full
corpus build). Without a reference corpus (`THEMIS_DATA_DIR` empty): 542 passed, 135 skipped (documented 489
/ 135; `REPRODUCE.md` updated). New: `tests/test_multichain_generalization.py`, 52 tests over synthetic
fixtures, plus one regression in `tests/test_target_audit.py` (53 new tests in all; the count also includes the
existing tests I re-pointed). Two of the new guards were shown to fail when
the defect is restored (the per-row-list leak, the dropped `chain` argument of the address inspector).
Frontend build: `npm run build` clean.

## 27. Browser end-to-end

Real Chromium (headless shell) against `vite preview` and the API. On the 100k random file: upload →
pre-flight (ready in 1.1 s) → run (2.9 s) → Overview → Claims → Provenance → Conflicts → Trust → Exports →
Address Inspector, no console errors, the address link carries its chain. The five bad dropdown selections
replayed on the new stack: `chain → Declared confidence` and both timestamp mappings are `invalid` with the
reason; the file is reported as "schema unresolved: a mapping you set does not fit" rather than "not
attribution data". Existing repository browser suite (`tests/e2e`): **16/16 before my additions, 18/18 with two new synthetic multi-chain steps** (H1: per-row chain, rejected rows and per-chain validity render, no crash; H2: a mapping that does not fit is refused and is not a verdict on the file, and Reset restores the inferred mapping).

## 28. Paper regression

`themis drift`, `themis anchors`, `themis explain 14BWrn1…` are **byte-identical** to `expected_output/`.
`themis audit` differs in its first "note:" line only; the same difference is present with the pre-change
code (`git archive HEAD`), so it predates this work (`expected_output/audit.txt` carries an older wording of
the sample note) and was left alone. `themis bootstrap --both` is byte-identical too. No paper number, threshold, methodology or source was
changed; MBAL is not in the corpus.

## 29. Full 10M scale test

The real file (850,176,864 bytes, 10,000,000 logical records) is below the configured 1 GiB upload limit
(`config/api.yml`), so it is **accepted and analysed completely**: nothing is truncated or sampled.

> **Configuration note (added after the test).** This run used a local `upload.max_bytes` of 1 GiB, raised
> for the experiment. That value is **not** the shipped default: the author restored the limit to **256 MiB**
> because ~2.5 KB of RAM per row (below) makes a 1 GiB allowance inappropriate for the in-memory
> architecture, and added `upload.max_rows` (default 1,000,000 logical CSV rows), so the default service
> refuses this 10M-row file with HTTP 413. Repeating the 10M test needs an explicit local config
> (`THEMIS_CONFIG_DIR`) with both limits raised, on a machine with enough RAM. The measurements below
> are unchanged. Disk-backed storage is not implemented.

| measure | result |
|---|---|
| upload to the API (loopback) | 0.63 s |
| browser: file chosen → pre-flight ready | 14.2 s (the browser uploads 850 MB; the server parses all 10,000,000 rows and pre-flights); the browser did not hash the file (over the 128 MiB limit) and the server's SHA-256 is shown |
| analysis job | 142–147 s across runs: reference 0.7 s, parse 11.0 s, detect 1.4 s, validate 53.8 s, normalise 28.0 s, provenance/reference/independence/currency 46.6 s, assemble 0.2 s |
| throughput | about 70,000 rows/s end to end; validation about 185,000 rows/s |
| peak memory | the API process reached 24.7 GB resident, about 2.5 KB per input row (machine: 48 GB); one Python process |
| CPU | about 100% of one core throughout; nothing is parallel |
| temporary storage | one temporary copy of the upload (850 MB), removed when the job ends |
| completeness | 10,000,000 rows read, 10,000,000 identifiers checked, 8,239,794 valid rows + 1,760,206 rejected with a reason (1,760,196 invalid identifiers, 10 duplicate claims) = 10,000,000; 8,856,557 claims over 8,239,773 subjects; 0 truncated |
| browser | every page (Overview, Claims, Provenance, Conflicts, Trust, Exports) rendered, no console error |
| failure recovery | a 1.7 GB upload is refused with HTTP 413 in 5 ms, "The upload is larger than the 1,073,741,824-byte limit.", on both `/api/preflight` and `/api/jobs/analysis`; no crash, no partial verdict, the service stays healthy and the earlier analysis is intact |

API responsiveness on the finished 8.86M-claim analysis (warm unless stated):
summary 1.6 ms; claims page 1.8 ms, and the same page **37 s the first time** (a one-time sort of 8.86M claims
plus the distinct-subject count, cached per analysis); filtered claims queries 1.2–4.0 s; provenance 4.8 s;
Trust coverage **76 s the first time**, 3.2 s afterwards; address inspector 0.55 s; conflicts 1.2 ms.

**What the scale test broke, and what was fixed** (all generic, all now under test): the analysis summary was
**1.5 GB** (per-address maps no screen reads), then still 307 MB (per-row validation lists I had added), and
the job-status response carried the same maps; the browser tab crashed on each; it also crashed hashing the
file in memory. Each is fixed (summary now 32 KB; job status 295 KB, capped at 500 preview claims). Claims
paging re-sorted every request (19 s) and `analysis_summary.json` was built as one string; the sort is cached
and the export streams. **Remaining limits, stated, not fixed:** THEMIS analyses a CSV in memory, so 10M rows
need about 25 GB of RAM and a machine with less can fail; the 1 GiB limit bounds the file, not the memory; the
first Claims page and the first Trust query on a very large analysis are slow (37 s, 76 s); and the
`analysis_summary.json` export still contains every claim, so at this scale it is a multi-gigabyte download.
Population figures in this report come from this full pass and from the streaming counts, never from the
stratified sample.

## 30. What THEMIS can establish about MBAL

That the file has the shape of a multi-chain attribution dataset; that its identifiers are or are not
syntactically valid on the chain each row states (82.4% are, by chain as in §12); that 1,758,356 Bitcoin
identifiers are case-folded and cannot be validated; that no EVM identifier encodes a checksum; that rows,
addresses and claims number 10,000,000 / 8,239,794 / 8,856,557; that 6.07% of rows carry several labels;
what fraction of its labels THEMIS's taxonomy can interpret; that provenance is unresolved for every claim
and that its three source values are a method class; that 31 of 8.2 million subjects are comparable with the
bundled reference sample and that their independence is unresolved.

## 31. What THEMIS cannot establish

That any label is true; that `ground_truth` is verified; that `external` is confirmed; that an entity owns
its address; that the case-folded Bitcoin addresses are the addresses the labellers meant; that MBAL is
independent of, or agrees with, any reference source beyond one address; how MBAL compares with its paper
(the paper describes a different version).

## 32. Final forensic interpretation — evidence profile

| dimension | conclusion |
|---|---|
| DATA INTEGRITY | records parse cleanly (10,000,000 logical); 117 identifiers padded with whitespace, 951 malformed EVM, injected text |
| IDENTIFIER VALIDITY | EVM: 99.98%+ syntactically valid. Bitcoin: 2.7% — **IDENTIFIER-INTEGRITY LIMITATION** (case-folded) |
| CHAIN COMPATIBILITY | every row's chain string resolves; every EVM address is valid on the chain it states (and on the other three EVM chains, which is why the chain column is essential) |
| LABEL COVERAGE | complete (no blank category); multi-label on 6.07% of rows |
| TAXONOMY INTERPRETABILITY | partial: 41.7% of label instances map to THEMIS's taxonomy |
| ENTITY COVERAGE | partial: 34.5% of rows, concentrated on Ethereum and Bitcoin |
| DECLARED EVIDENCE METHOD | present as a 3-value class, confounded with chain; **not a provenance root** |
| PROVENANCE RESOLUTION | **PROVENANCE UNRESOLVED** for every claim |
| INDEPENDENT CORROBORATION | **INSUFFICIENT INDEPENDENT CORROBORATION**: nothing to corroborate with |
| CONFLICTS | none inside the file; against the reference sample 19 of 31 comparable subjects disagree (10 entity-type, 9 licit/illicit), a slice too small and too unrepresentative to generalise |
| REFERENCE-CORPUS AGREEMENT | not estimable for the dataset: 31 comparable subjects in 8,239,773 (exact 10, entity-type 10, licit/illicit 9, incomparable 2) |
| LIMITATIONS | see §24 |
| FORENSIC DEFENSIBILITY | **INSUFFICIENT EVIDENCE FOR A FORENSIC RELIABILITY CONCLUSION.** The evidence available is limited to identifier syntax, label structure and method class; no reliability percentage is offered because none is supported |

Overall: `PARTIAL EVIDENCE SUPPORT` for the EVM identifiers as syntactically well-formed, `IDENTIFIER-INTEGRITY
LIMITATION` for Bitcoin, `PROVENANCE UNRESOLVED` and `INSUFFICIENT INDEPENDENT CORROBORATION` throughout.
This is a statement about what can be shown, not a judgement that the labels are wrong.

## Overclaim audit (Phase 23)

Every screen of the MBAL analysis was searched for *reliable, trusted, verified, ground truth, accurate,
confirmed, independent, forensic, validated*. Each occurrence is a label of a measured quantity, a
negation, or the file's own value quoted as written: "reliability profile" (the product's page name; the
lead says "evidence, not verdicts"), "Verified 0.00% 0 / 88,528", "Confirmed independent multi-root 0 / 1",
"not a verification", "Valid means syntactically valid… it says nothing about whether the label is true",
"Unresolved is never counted as an independent source", `ground_truth` under "declared source (as written in
the file)". The safeguards hold: valid address ≠ verified attribution; `ground_truth` ≠ verified ground
truth; label exists ≠ label true; entity exists ≠ ownership proven; agreement ≠ truth; different source
values ≠ independent roots; technical usability ≠ forensic defensibility. The "accurate", "trusted" and
"forensic" hits are only the Trust page's title/preview and the nav.

## Production-code search (Phase 24)

`grep -rni "mbal\|dataset_10m_ads"` over `themis/`, `frontend/src/`, `scripts/`, `README.md`: no matches. The
literals `ethereum_mainnet`, `bitcoin_mainnet`, `bnb_chain_mainnet`, `polygon_mainnet`, `avalanche_c_chain`:
no matches. `ground_truth` appears only in pre-existing paper-anchor code. `categories` was added as a plural
of `category` in a generic hint list; chain aliases are public chain names in `config/chains.yml`, matched
after a generic `_mainnet` normalisation.
