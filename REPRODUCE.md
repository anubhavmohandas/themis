# Reproducing THEMIS

This is the minimal path from a clean checkout to every number this README
and the paper cite. All commands below were run against the bundled sample
(`demo_data/`) on the commit this file ships with; expected output is quoted
verbatim from that run, not predicted.

Environment used to verify: Python 3.14.6, Node v26.8.2. `pyproject.toml`
declares `requires-python = ">=3.9"`; any supported version should reproduce
identical figures — nothing here depends on a Python-version-specific
numeric quirk.

## 1. Install

```
git clone <repo-url> themis
cd themis
python -m venv .venv
source .venv/bin/activate          # .venv\Scripts\activate on Windows
pip install -e ".[test,ui]"
```

No other setup is required: PyYAML is the only mandatory dependency, and the
bundled sample corpus ships in the repo (`demo_data/`) — there is no external
download step for paper reproduction.

## 2. Backend tests

```
python -m pytest
```

Expected: `191 passed`. If any test fails, stop here — the commands below
assume a clean test run.

## 3. Paper reproduction (CLI)

```
themis audit
```

Expected (abridged; run without a pipe to see the full output, including
Cohen's kappa and the independence/circularity section):

```
CORPUS
  1,545,710 claims over 1,497,191 addresses, 25 distinct provenance roots (21 identified, 4 unresolved)

CORROBORATION  (RQ2)
  single-dataset        1,481,791   98.97%
  two or more              15,400    1.03%

AGREEMENT  (among multi-dataset addresses)
  exact                       10,515   68.28%
  hierarchical refinement      1,253    8.14%
  entity-type conflict           340    2.21%
  licit/illicit conflict         108    0.70%
  incomparable                 3,184   20.68%
```

**Note on the "exact"/"incomparable" figures**: these are the current,
regression-tested, code-verified values. The paper draft as currently
published cites 13,673/88.79% exact and 23/0.15% incomparable — a real bug
(`classify_address` counting one source's opinion as two sources agreeing
whenever every other matched label failed to canonicalize) was found and
fixed after that draft was written; see `RECONCILIATION_REPORT.md` (local,
gitignored working log) for the full before/after and the required paper
edit. The 15,400/1.03% multi-dataset figure and the corpus totals above are
unaffected and match the published draft exactly.

```
themis drift
```

Expected:

```
  condition                                           obs  addresses     revenue USD   vs B
A naive union, sources summed as independent     61,508     54,000   1,367,997,317   1.24
B address-level deduplication                    54,000     54,000   1,101,304,942   1.00
C circular inheritance collapsed to its root     42,237     42,237   1,045,637,066   0.95
D highest-declared-confidence tier only           7,457      7,457     112,426,899   0.10
```

(USD totals can differ from the paper by a few dollars out of a billion — the
bundled revenue file stores cents; see README §13.)

```
themis bootstrap --both
themis anchors
themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7
```

`bootstrap`'s confidence intervals are deterministic at the default seed
(42) regardless of whether numpy is installed in your environment — see
README §15. `anchors` reports provenance-aware validation against the
bundled 289-address open reference set; it explicitly states which sources'
accuracy isn't estimable rather than omitting them silently.

## 4. Frontend build

```
cd frontend
npm ci
npm run build
```

Expected: a clean build with no errors, producing `frontend/dist/`. `npm run
preview` serves it locally for a manual check.

## 5. Running the dashboard end to end

```
# terminal 1
python -m themis.api

# terminal 2
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. "Reproduce Paper" loads the bundled sample
through the same `audit`/`drift`/`report` functions the CLI calls — the
dashboard and `themis audit` cannot diverge (README §4).

## 6. Auditing your own dataset

```
themis ingest path/to/your.csv --source-id my_dataset
```

or via the dashboard's Upload page. A CSV with no recognizable
address-shaped column is rejected with an explanation (README §8's four
supported-input cases); a recognized Bitcoin attribution CSV runs the full
pipeline and, if `demo_data/` is used as the reference corpus, reports
cross-source comparability against the bundled sample.

## 7. Full local corpus build (optional)

The bundled sample already contains every multi-dataset address and the full
revenue inputs, so `themis audit`/`drift`/`bootstrap` reproduce every figure
above without this step. There is currently no bundled from-source rebuild
script (see README §13) — a full local build (`--observations FILE`) would
need normalized claims assembled from each source's own raw data per
`THIRD_PARTY_DATA.md`'s licensing notes, in the CSV shape `corpus.py`'s
`FIELDS` documents.
