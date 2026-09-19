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

- **release / no reference corpus:** `173 passed, 92 skipped` — the 92 skipped
  are the tests that assert a number printed in the paper or drive paper mode;
  each says `reference corpus not present (not redistributed - see
  THIRD_PARTY_DATA.md; set THEMIS_DATA_DIR)`.
- **a corpus present** (development checkout, or `THEMIS_DATA_DIR` pointing at a
  matching one): `264 passed, 1 skipped` in a clean environment - the skip is the
  numpy cross-check of the exploratory `--fast` bootstrap path (numpy is optional);
  with numpy installed, `265 passed`.

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
DRIFT       A 61,508 obs / 54,000 addr / $1,367,997,317   B 54,000 / 54,000 / $1,101,304,942
            C 42,237 / 42,237 / $1,045,637,066            D 7,457 / 7,457 / $112,426,899   (B/D 9.8x, D covers 13.8%)
BOOTSTRAP   2,000 resamples, seed 42, 95% - exact 68.279% [6.012, 97.808] lower / [7.182, 85.130] upper
ANCHORS     289 anchors -> 268 usable; 361 claims excluded as same-root
            schnoering 94.1% (3 roots) [71.4, 100.0]   tagpack 43.6% (5 roots) [7.0, 97.2]   the other five: not estimable
```

(`drift` USD totals are $1–3 below the paper's: the bundle stores each row to
the cent; the paper sums unrounded upstream values.)

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

**What has been checked against real files (2026-09-19):**

| source | result |
|---|---|
| GraphSense TagPack (git clone of the MIT repo) | 499,327 claims over 483,296 addresses — exactly the paper's Table 1; all 25,362 frozen sample rows reproduced identically |
| WatchYourBack (upstream `btc_resolv.csv`) | 309 rows, identical to the bundle as a multiset |
| Condition D's anchor set (WatchYourBack ransomware ∪ TagPack `confidence: forensic`) | 146,243 addresses, identical to `verified_anchors.txt.gz` |
| Rodwald ransomware / mixers (author's site) | 50,322 / 57,817 rows and the 50,322 revenue rows, identical to the bundle |
| Ransomwhere (Zenodo snapshot, 2024-10-27) | 11,178 addresses, a strict subset of the paper's 11,186; the live API returned HTTP 502 that day |
| **Elliptic++, Schnöring** | **not re-fetched**: those adapters are checked only against synthetic files in the documented layout. Schnöring's `schnoering_addresses.csv` (address, category, source) was extracted by the authors from the Zenodo labelled-entity data and that extraction is not scripted |

Two caveats a full rebuild will show. (1) The bundled sample is not the corpus:
the multi-dataset-rate interval, the 853,604-cluster upper bound and corpus-wide
freshness need the full build. (2) The manifest's totals (1,497,191 addresses,
15,400 multi-dataset) predate joining WatchYourBack's 87 `#`-prefixed addresses;
joined, a full build gives roughly 85 fewer addresses and at least 15,413
multi-dataset ones (13 more TagPack–WatchYourBack addresses were found by the
TagPack rebuild alone).

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
   upstream) are joined, which changes the 2- and 3-dataset buckets (7,832 /
   429, not 7,904 / 357), the WatchYourBack overlaps and the kappa values (n 117
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

## 7. Auditing your own dataset

```
themis ingest examples/example_attribution.csv --no-reference
themis ingest path/to/your.csv --source-id my_dataset [--reference build/observations.csv.gz]
```

A CSV with no address-shaped column is stopped with an explanation; an
unsupported chain, a crypto-but-not-attribution file and a malformed file each
get their own message (`README.md` §8). A source id the registry does not know
resolves UNRESOLVED, never independent.
