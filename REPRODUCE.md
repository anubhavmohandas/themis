# Reproducing THEMIS

Verified environment: Python 3.14.6, Node v26.8.2, npm 11.19.1, macOS 26.6.2
(arm64). Nothing here depends on a Python-version-specific numeric quirk, but
no other version has been run.

## 0. What can be reproduced from what

| you have | you can run | how |
|---|---|---|
| a **release** (no data) | the test suite; the upload flow on `examples/`; the frontend build | §1, §5, §6 |
| a release **plus the sources** you fetched | everything in the paper except the anchor validation | §3 |
| a **development checkout** (`demo_data/` sample present) | every command, byte-identical to `expected_output/` | §2 |

The paper's data statement is that the derived observation table is not
redistributed, so a release contains none of `demo_data/`. `THIRD_PARTY_DATA.md`
says why and lists where each source lives.

## 1. Install and test

```
git clone <repo-url> themis && cd themis
python -m venv .venv
source .venv/bin/activate            # .venv\Scripts\activate on Windows
pip install -e ".[test]"
python -m pytest
```

Only `pyproject.toml` supplies dependencies (PyYAML at runtime; pytest, httpx,
fastapi, python-multipart for the tests). Expected:

- **release / no reference corpus:** `556 passed, 135 skipped` - the 135 skipped
  are the tests that assert a number printed in the paper or drive paper mode;
  each says `reference corpus not present (not redistributed - see
  THIRD_PARTY_DATA.md; set THEMIS_DATA_DIR)`.
- **a corpus present** (development checkout, or `THEMIS_DATA_DIR` pointing at a
  matching one): `685 passed, 6 skipped` in a clean environment with `.[test,figures]`
  installed (numpy arrives with matplotlib). Without numpy the numpy cross-check
  of the exploratory `--fast` bootstrap path is skipped and the count is one lower.
  The 6 skipped assert the full-corpus Overview figures and need a full build:
  `THEMIS_OBSERVATIONS=build/observations.csv.gz THEMIS_AS_OF=2026-09-15 python -m pytest tests/test_overview.py`
  runs them (22 passed). Do not set `THEMIS_OBSERVATIONS` for the whole suite: the
  API tests would then load the full corpus, and they assert bundled-sample figures.

If a test fails, stop here; the rest assumes a clean run.

## 2. Paper commands on the bundled sample (development checkout)

```
themis audit
themis drift
themis bootstrap --both
themis anchors
themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7
```

`expected_output/` holds the exact output; the CLI prints no timestamps, so
`themis audit | diff - expected_output/audit.txt` is empty. Headline lines:

```
CORPUS      1,545,710 claims over 1,497,191 addresses, 25 distinct provenance roots (21 identified, 4 unresolved)
CORROBORATION   single-dataset 1,481,791 98.97%   two or more 15,400 1.03%
AGREEMENT   exact 10,515 68.28% | hierarchical refinement 1,253 8.14% | entity-type conflict 340 2.21%
            licit/illicit conflict 108 0.70% | incomparable 3,184 20.68%
            schnoering-tagpack  n= 8,139  raw 93.3%  kappa 0.655   (interpretable pairs only: n= 7,808  raw 97.3%  kappa 0.780)
DRIFT       A 61,508 obs / 54,000 addr / $1,367,997,318   B 54,000 / 54,000 / $1,101,304,945
            C 42,237 / 42,237 / $1,045,637,069            D 7,457 / 7,457 / $112,426,902   (B/D 9.8x, D covers 13.8%)
BOOTSTRAP   2,000 resamples, seed 42, 95% - exact 68.279% [6.012, 97.808] lower / [7.182, 85.130] upper
ANCHORS     289 anchors -> 268 usable; 361 claims excluded as same-root
            schnoering 94.1% (3 roots) [71.4, 100.0]   tagpack 43.6% (5 roots) [7.0, 97.2]   the other five: not estimable
```

(`drift` USD totals equal the paper's Table 2: the bundle keeps each row at full
precision, as the paper's own arithmetic does. An earlier cent-rounded bundle was $1–3 low; §8.)

**Two result sets, never mixed.** The default is the *paper snapshot*: labels
the paper-era adapters left `unknown` stay `unknown`. `expected_output/
metrics_final_corrected_candidate.json` is the same corpus with those labels
read by the structured-label parser (WatchYourBack's `type:entity` labels, 177
claims): agreement becomes 10,519 / 1,274 / 354 / 110 / 3,143. Regenerate either
with `python scripts/generate_result_sets.py --mode frozen|candidate --out DIR`;
`python scripts/independent_agreement_check.py` recomputes both breakdowns from
the raw table without importing `themis` and agrees with both.

## 3. Rebuilding the corpus from the sources

`scripts/build_corpus.py` downloads nothing. Fetch each source yourself (locations
and terms: `THIRD_PARTY_DATA.md`), then:

```
python scripts/build_corpus.py --out build/ \
  --tagpack          PATH/graphsense-tagpacks \
  --rodwald-ransom   PATH/BTC_Ransom.csv \
  --rodwald-mixers   PATH/BTC_Mixers.csv \
  --ransomwhere      PATH/ransomwhere.json \
  --watchyourback    PATH/watchyourback/data/tagging/btc_resolv.csv \
  --elliptic-classes PATH/wallets_classes.csv \
  --schnoering       PATH/schnoering_addresses.csv \
  --retrieved tagpack=YYYY-MM-DD --retrieved ransomwhere=YYYY-MM-DD ...
```

Every source is optional (a missing one is a warning). It writes
`observations.csv.gz`, `revenue.csv.gz`, `verified_anchors.txt.gz` and
`build_manifest.json` (input file hashes — names, never paths — adapter and
normalization versions, retrieval dates, dropped rows, warnings), byte-identical
for identical input. Add `--taxonomy-fill` for the corrected-candidate variant.

Then point THEMIS at it:

```
themis --observations build/observations.csv.gz --data-dir build --as-of 2026-09-15 audit
themis --observations build/observations.csv.gz --data-dir build --as-of 2026-09-15 drift
themis --observations build/observations.csv.gz --as-of 2026-09-15 bootstrap --both
```

`--as-of` is the date staleness is judged at; without it a full build uses the
newest revision date in its own claims, which is earlier than the retrieval date.

**What has been checked against real files (2026-09-19; the last two rows and the closing paragraph 2026-09-20):**

| source | result |
|---|---|
| GraphSense TagPack (git clone of the MIT repo) | 499,327 claims over 483,296 addresses — exactly the paper's Table 1; all 25,362 frozen sample rows reproduced identically |
| WatchYourBack (upstream `btc_resolv.csv`) | 309 rows, identical to the bundle as a multiset |
| Condition D's anchor set (WatchYourBack ransomware ∪ TagPack `confidence: forensic`) | 146,243 addresses, identical to `verified_anchors.txt.gz` |
| Rodwald ransomware / mixers (author's site) | 50,322 / 57,817 rows and the 50,322 revenue rows, identical to the bundle |
| Ransomwhere (Zenodo snapshot, 2024-10-27) | 11,178 addresses, a strict subset of the paper's 11,186; the live API returned HTTP 502 that day |
| Elliptic++ (`wallets_classes.csv`, authors' Google Drive) | 822,942 rows -> 822,937 claims (5 shorter than an address dropped and counted); classes 1/2/3 = 14,266 / 251,088 / 557,588 |
| Schnöring (`addresses.csv`, figshare 10.6084/m9.figshare.26305093.v3, CC BY 4.0, md5 verified) | 103,812 claims over 101,387 addresses, 7,222 Montréal - exactly Table 1. No extraction step: the paper's `schnoering_addresses.csv` is this published file. The earlier-cited Zenodo record 22239038 does not hold it |
| Ransomwhere (live export, 2026-09-20) | 11,186 addresses; reproduces `pipeline/out/e3.json` for conditions A and B to the last float digit |

All seven sources rebuilt together (`scripts/build_corpus.py`, 2026-09-20) give
**1,545,710 claims over 1,497,191 addresses**, every per-source count equal to the
manifest's, and all 268,891 frozen sample rows present verbatim. The public
sources had not moved since the paper's retrieval date.

Two caveats a full rebuild will show. (1) The bundled sample is not the corpus:
the multi-dataset-rate interval, the 853,604-cluster upper bound and corpus-wide
freshness need the full build. (2) The bundled sample's multi-dataset total (15,400)
predates joining WatchYourBack's 87 `#`-prefixed addresses; a full build has 15,413
multi-dataset addresses, which is the value the manuscript now states.

**Anchor validation** (`themis anchors`) needs `ground_truth.csv` in the data
directory (columns `address, ground_truth_label, ground_truth_source`, where the
last is a provenance *root*: `ofac_sdn` or `watchyourback_manual`). That file is
curated from WatchYourBack's annotations and OFAC's SDN list and is not
scripted, so it is the one paper command a release cannot reproduce.

## 4. Where THEMIS and the paper differ

THEMIS is stricter than the paper's pipeline in three places, and the differences
are what §5.1, §4.2 and §5.4 need updated:

1. **Agreement.** The pipeline counts an address `exact` when only one dataset
   contributed an interpretable category (13,673); THEMIS requires two (10,515)
   and reports the rest `incomparable` (3,184, not 23).
2. **WatchYourBack's `#` addresses** (87 of 309 rows carry a literal `#`
   upstream) are joined, which changes the 2- and 3-dataset buckets (7,845 /
   429 on the full corpus, not 7,904 / 357), the WatchYourBack overlaps and the kappa values (n 117
   and 210, not 46 and 138).
3. **Anchor validation** counts one decision per (source, address), leaves
   uninterpretable claims out of the denominator, resamples roots for the
   interval, and roots WatchYourBack's Treasury-cited records at OFAC.

Everything else in the paper that THEMIS computes reproduces.

## 5. Frontend

```
cd frontend
npm ci
npm run build
```

Expected: a clean Vite build (225 modules), producing `frontend/dist/`.
Only `package.json` and `package-lock.json` are used.

## 6. Running the dashboard

```
pip install -e ".[ui]"
python -m themis.api                 # backend on http://127.0.0.1:5001
cd frontend && npm run dev           # frontend on http://127.0.0.1:5173
```

"Reproduce paper" needs the reference corpus (`THEMIS_DATA_DIR` or a development
checkout); without it the page shows the instruction to build one. Uploading a
file works either way — without a corpus the audit runs without cross-source
comparison and says so. The dashboard has been driven through its API only:
**MANUAL BROWSER QA STILL REQUIRED.**

By default the API loads the bundled sample, and the Overview then says so: every figure is labelled
`BUNDLED SAMPLE`, `FULL-CORPUS MANIFEST` or `NOT AVAILABLE` (the sample cannot state the normalized
address count, the single-source share or the full-corpus multi-dataset count). To load a full build
instead, as the CLI's `--observations` / `--as-of` do:

```
THEMIS_OBSERVATIONS=build/observations.csv.gz THEMIS_AS_OF=2026-09-15 python -m themis.api
```

The Overview is then `FULL CORPUS`: 1,497,106 normalized addresses (1,497,191 raw address keys before
WatchYourBack's `#` marker is joined) and 15,413 multi-dataset addresses, all computed live.

## 7. Auditing your own dataset

```
themis ingest examples/example_attribution.csv --no-reference
themis ingest path/to/your.csv --source-id my_dataset [--reference build/observations.csv.gz]
```

A CSV with no address-shaped column is stopped with an explanation; an
unsupported chain, a crypto-but-not-attribution file and a malformed file each
get their own message ([docs/wiki/your-own-data.md](docs/wiki/your-own-data.md), "Pre-flight behavior"). A source id the registry does not know
resolves UNRESOLVED, never independent.

## 8. The executable paper (`reproduce-paper`)

```
themis reproduce-paper                 # writes results/reproduction/<run_id>/ and mirrors it to results/paper_proof/
themis verify-paper --paper /path/to/ICISHCT2026_THEMIS_Final_Verified.pdf
themis figures                          # or: themis figures --from-data results/paper_proof  (no corpus needed)
themis reproduce rodwald-containment
```

**What this proves and what it does not.** It recomputes the paper's empirical
measurements from the declared inputs and compares them with the manuscript
(`paper/paper_claims.yml`, and the printed values in the final PDF). It does not
prove that any attribution label is true.

**Inputs.** The paper's data statement is that the derived observation table is
not redistributed, so a release contains no corpus. Without one,
`themis reproduce-paper` prints `PAPER REPRODUCTION DATA REQUIRED` and
`BLOCKED - INPUT CORPUS NOT AVAILABLE` with the seven sources, their citations
and licence notes, and the build command; it exits 3 and writes no PASS. To
supply data: fetch the sources (§3), run `scripts/build_corpus.py`, then

```
themis --observations build/observations.csv.gz --data-dir build --as-of 2026-09-15 reproduce-paper
```

On the bundled sample (a development checkout) cross-dataset results (overlap,
Rodwald decode, Montréal recurrence, conclusion drift, anchors) are recomputed
live; corpus-wide totals (claims, addresses, roots, unresolved provenance, the
single-dataset share) are figures carried in `demo_data/manifest.json`, and
currency needs every claim. Those are reported `NOT_REPRODUCED`, so the run is
never `PASS` on the sample. A `PASS` needs a full build.

**Two reproduction statements, never merged.** They answer different questions and are reported separately.

1. **`PAPER ↔ THEMIS`, the shipped command.** `themis reproduce-paper` with no full corpus is
   `BLOCKED - INPUT CORPUS NOT AVAILABLE` (exit 3). The *authoritative* path is a **fresh raw-source
   rebuild**: fetch the seven sources (§3) → `scripts/build_corpus.py` (hashes every input) → the full
   observation table → `themis reproduce-paper`. Only that run's result is the reproduction of the paper.
2. **`REGRESSION VERIFICATION USING RETAINED FULL OBSERVATION TABLE: PASS`** (29 / 29 headline claims).
   This is compatibility evidence for the *current code* on a table kept from an earlier build, not a
   reproduction: a table that passes expected results proves compatibility, not provenance. Its record:

   | | |
   |---|---|
   | file | `observations.csv.gz`, kept locally (gitignored, not redistributed) |
   | SHA-256 | `e65bf05afdecea538e5fdcdbecffa8fcb0398f3cd7e2705bd47f8018d6029acd` |
   | rows / schema | 1,545,710 claims over 1,497,191 addresses; columns `address, source, raw_label, canon, polarity, prov_family, lastmod, heuristic, subcat` (`observations-v1`) |
   | source coverage | all seven: Elliptic++ 822,937 · TagPack 499,327 · Schnöring 103,812 · Rodwald ransomware 50,322 · Rodwald mixers 57,817 · Ransomwhere 11,186 · WatchYourBack 309 |
   | how it was made | `scripts/build_corpus.py` (SHA-256 `b3416342…091a85c5`, unchanged since commit `6245e0c`) from raw files retrieved **2026-09-20**; every input's SHA-256 (and TagPack's tree hash and commit `7f9a5d1`) is in `expected_output/retained_table_build_manifest.json` |
   | verified 2026-09-24 | the six retained raw files match those hashes, and rebuilding from them reproduces `observations.csv.gz`, `revenue.csv.gz`, `verified_anchors.txt.gz` and `build_manifest.json` **byte for byte** |
   | relationship to the paper's experiment | a **reconstruction**, not the original working file: it was built after the paper's data were collected, from a live Ransomwhere export and a moving TagPack branch, and it reproduces the paper's per-source counts and all 29 headline claims. It is not shown to be the identical table |

   So the retained table is a *certified retained reproduction artifact* (identity, hash, origin and
   inputs documented), and its PASS is reported only under the label above. A reviewer who rebuilds
   later may see different rows in the two moving sources (Ransomwhere's live export, TagPack); compare
   the raw-input hashes in their `build_manifest.json` with the retained one before comparing results.

**Output** (`results/reproduction/<run_id>/`): `metadata.json` (software version,
git commit, analysis date, corpus / taxonomy / source-registry / threshold hashes,
bootstrap seed and iterations, paper version), `source_manifest.json`,
`config_manifest.json`, `paper_metrics.json`, `verification.json`,
`PAPER_CLAIM_MAP.md`, `table1.*`, `table2.*`, `overlap_matrix.*`,
`source_depth.json`, `fig1a_data.*` / `fig1b_data.*` / `fig2_data.*` with the
figures and their `*.metadata.json` sidecars, `currency.json`,
`unresolved_provenance.json`, `anchors.json`, `condition_d_trace.json`,
`bootstrap_lower.json` / `bootstrap_upper.json`, `limitations.json` and a
generated `REPRODUCTION_REPORT.md`. Staleness is judged at the declared analysis
date, never the wall clock.

**Findings of the 2026-09-20 closure run** (details: `results/reproduction_closure/`, gitignored):

- *Table 2 revenue.* The four cells differed from the printed Table 2 by $1.32-$3.16
  on the old bundled `revenue.csv.gz`. Cause found: that file was written with
  `f"{usd:.2f}"`. Rodwald's values are exact cents but Ransomwhere's transaction sums are
  sub-cent, and the dedup `max` picks the unrounded Ransomwhere value only when it
  sits above Rodwald's, so the rounding errors are one-sided (8,244 rows differ, none by
  more than half a cent, all Ransomwhere). Run on the raw sources, the paper's own
  `pipeline/e3.py` logic reproduces `e3.json` for all four conditions and `themis.analysis.drift`
  on the old file reproduces the old figures exactly - both are faithful to their input.
  The artifact was the defect; `scripts/build_corpus.py` now writes `repr(float)` and the
  bundled file was replaced. No tolerance was added.
- *Full-corpus reproduction, paper `ICISHCT2026_THEMIS_Final_Verified.pdf`:* every
  machine-checkable claim is computed live. Its predecessor `..._Repaired_Final.pdf`
  (Table 2 identical) failed on three statements that were wrong in the paper, and only
  those were corrected: (a) "more than 99.5%" of Elliptic++ without a cross-source check
  became "about 99.5% of Elliptic++ addresses" (live 99.4803%); (b) "only 15,400 addresses
  appear in two or more datasets" became 15,413 and (c) "7,832 in two datasets" became 7,845
  (the old 15,400 / 7,832 were pre-normalisation; 7,845 + 429 + 7,112 + 27 = 15,413). The
  data statement also no longer calls the sources "openly redistributable" (no licence
  was found for Elliptic++ or Rodwald): they are "publicly accessible". The bundled sample
  cannot confirm (b)/(c) (it is 13 addresses short), so on the sample they are
  `SAMPLE_OBSERVED`, not PASS.
- *The manuscript is not distributed.* The repository and the release hold only the
  manifest, which names the PDF and pins its SHA-256. To run the PDF-layer check, give
  the PDF with `--paper FILE` or `THEMIS_PAPER_PDF`, or place it in `paper/` (git-ignored).
  Without the PDF the PDF layer is reported `NOT_CHECKED` in `verification.json`, and a PASS
  then covers the manifest against THEMIS only, not the printed text of the manuscript.
- *Definitions fixed in THEMIS, not the paper:* "33 provenance descriptors" counts
  distinct descriptor strings as `pipeline/analyse.py` does (`rodwald:S` is declared by
  both Rodwald datasets); `anchor_robust_max_ci_width` (a threshold of THEMIS's own
  choosing) no longer decides `source_accuracy_robustly_estimable` - the verdict is
  structural (five of seven sources have no usable interval), interval widths are reported
  descriptively.

The tests that back this: `tests/test_rq1_taxonomy.py` (the claim taxonomy as
rules, no corpus needed), `tests/test_source_to_artifact.py` (parsers, kept apart
from manuscript checks), `tests/test_paper_verifier.py` (the verifier itself can
fail), `tests/test_paper_reproduction.py` (mutation: change a metric, a source
row or a config rule and the verifier must FAIL; one drift object across Table 2,
Figure 2, CLI, API and PaperMetrics; independent oracles), `tests/test_api_paper.py`.
