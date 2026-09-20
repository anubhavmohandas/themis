# THEMIS

**T**rust and **E**vidence-based **H**euristic **M**ethod for **I**nvestigative
**S**ource Assessment — provenance-aware auditing of public Bitcoin attribution
labels, built alongside the paper *Provenance Before Precision: Auditing Public
Bitcoin Attribution Labels and Their Effect on Forensic Conclusions* (ICISHCT
2026, under review).

## 1. What THEMIS is

A blockchain records transfers, not identities. Everything said about *who*
controlled an address is a claim layered on top, and those claims come from a
short list of public corpora reused without much scrutiny of where they came
from. THEMIS audits them: what corroborates what, which agreement is inherited
rather than independent, how much has no cross-source comparison at all, and
what the choice of trust rule does to a downstream forensic figure.

It is a measurement tool, not a labeling tool. It does not decide whether an
address is "really" a scam, a mixer or an exchange; it measures how well the
*public evidence for that decision* holds up — its provenance, independence,
currency, and sensitivity to what you are willing to trust.

The analysis engine (`themis/taxonomy.py`, `provenance.py`, `analysis.py`,
`trust/`) carries no dataset-specific logic. Every source's provenance rule,
category and trust policy lives in `themis/config/` (YAML). Reproducing the
paper is one configuration of that engine.

## 2. Research question

> How reliable is publicly available cryptocurrency attribution data for
> forensic investigation and blockchain tracing?

- **RQ1** — can a public label be classified by reproducible evidence-quality
  rules rather than an unstated notion of "trustworthy"? (`themis taxonomy`, `explain`)
- **RQ2** — how much do the major open sources overlap, how often do they
  conflict, and how much of the agreement is independent? (`themis audit`)
- **RQ3** — how far does a forensic conclusion move under different trust
  rules, and at what coverage? (`themis drift`)

`themis bootstrap` and `themis anchors` quantify how much confidence either
answer can support.

## 3. What THEMIS does not claim

- **Public ≠ reliable.** Being published says nothing about accuracy.
- **Supported ≠ true.** Passing a trust condition means the evidence meets that
  condition's bar, not that the label is correct.
- **Agreement ≠ independent corroboration**; **multiple datasets ≠ multiple
  independent sources**; **high overlap ≠ proof of copying.**
- **Unknown ≠ independent, unknown ≠ shared.** An unresolved provenance root is
  an unknown relationship, never counted as a distinct additional source and
  never as a shared one.
- **Unverifiable ≠ false; no date ≠ stale.** A claim with no revision date is
  `currency-unknown`.
- **Coverage ≠ accuracy.** `themis drift`'s strictest rule keeps 13.8% of
  addresses; that is a coverage trade-off, not a more accurate estimate of the rest.
- **Declared confidence ≠ verified ground truth.** A source calling its output
  "manually verified", or GraphSense tagging a claim `forensic`, is a statement
  about that source's process, not a check THEMIS has performed. Source-native
  confidence is preserved and never mapped onto a THEMIS tier.
- **A reference corpus ≠ ground truth.** `themis anchors` reports *agreement with
  a small open anchor set*, not source accuracy, and refuses to estimate a source
  that rests on fewer than two independent provenance roots.

A forensic result without its trust rule and coverage is incomplete; every
figure this tool prints carries both.

## 4. Architecture

```
frontend/        React 18 + Vite dashboard; talks to the API over HTTP
themis/api.py    FastAPI JSON layer - request parsing and serialization only
themis/*.py      Python analysis core - the CLI and the API call the same functions
scripts/         build_corpus.py (from-source rebuild), result-set generators
```

The API and the frontend contain no analysis: every number comes from the same
`themis.report` / `analysis` / `graph` functions the CLI calls, so the dashboard
and `themis audit` cannot diverge. (The React pages only format backend values.)

## 5. Installation

```
git clone <repo> && cd themis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"          # add ,ui to run the web backend: pip install -e ".[test,ui]"
```

Python ≥ 3.10 (developed and tested on 3.14.6; the 3.10 floor is from inspection,
not a test run). One required dependency, PyYAML. NumPy is optional and never
changes a canonical result (see §16). Node ≥ 18 for the dashboard.

## 6. Paper reproduction

The reference corpus is **not shipped with a release** (the paper's data
statement: the derived observation table is not redistributed; see §13). Build
it from the sources, then point THEMIS at it:

```
python scripts/build_corpus.py --out build/ --tagpack ... --schnoering ... (see REPRODUCE.md)
themis --observations build/observations.csv.gz --data-dir build/ --as-of 2026-09-15 audit
themis --observations build/observations.csv.gz --data-dir build/ --as-of 2026-09-15 drift
themis --observations build/observations.csv.gz --as-of 2026-09-15 bootstrap --both
```

A development checkout also carries a 268,891-claim sample in `demo_data/`, so
plain `themis audit | drift | bootstrap --both | anchors | explain <address>` work
there and match `expected_output/` byte for byte. `REPRODUCE.md` has exact
commands, expected output, and which of the paper's numbers differ from THEMIS's
and why (`--taxonomy-fill` builds the "fresh normalization" variant; the default
is the paper snapshot's own behaviour — the two are never mixed silently).

| command | paper § | what it shows |
|---|---|---|
| `audit` | 5.1–5.2 | composition, corroboration depth, agreement outcomes, kappa, containment, decoding, circularity |
| `drift` | 5.3 | the same corpus and procedure under four trust rules, each with its coverage |
| `bootstrap [--both]` | 5.4 | root-cluster bootstrap intervals; prints resamples, seed, confidence, engine |
| `anchors` | 4.2 | agreement with the open anchor set per source, with independent-root support |
| `explain <address>` | 3 | one address traced to its provenance roots, apparent vs actual corroboration |
| `taxonomy`, `sources` | 3 | the rules and the source registry, printed from config |
| `report [--bootstrap] [--anchors]` | — | the canonical result object as one JSON document with its audit trail |
| `ingest <file>` | — | audit a dataset THEMIS has not seen |

Global options: `--json FILE`, `--observations FILE`, `--data-dir DIR`, `--as-of DATE`.

### 6.1 The executable paper: `reproduce-paper` and `verify-paper`

**"Verify the paper" means:** recompute the paper's empirical measurements from
declared inputs and compare them with what the manuscript states. It does **not**
mean proving an attribution label true. THEMIS reproduces measurements; the
labels stay claims.

| command | what it does |
|---|---|
| `themis reproduce-paper` | runs every experiment in a fixed order (corpus audit, RQ1 tests, source depth, overlap, Rodwald decode, Montréal recurrence, currency, unresolved provenance, anchors, drift, bootstrap, Tables 1-2, Figures 1-2), writes `results/reproduction/<run_id>/` and compares the outcome with the manuscript |
| `themis verify-paper [--paper FILE.pdf] [--metrics paper_metrics.json]` | compares generated metrics with `paper/paper_claims.yml` and with the text of the final PDF; exit 0 PASS, 1 FAIL, 3 BLOCKED |
| `themis figures [--from-data DIR]` | Figures 1a/1b/2 as PNG, PDF, SVG plus their data and a `*.metadata.json` sidecar; `--from-data` redraws from `fig*_data.json` and needs no corpus |
| `themis reproduce <experiment>` | one experiment alone (`rodwald-containment`, `montreal-recurrence`, `source-depth`, `overlap`, `currency`, `unresolved-provenance`, `anchors`, `table1`, `table2`, `condition-d`) |
| `themis audit`, `drift`, `anchors` | the underlying analyses, unchanged |

Three things are never blurred: **live computation** (the corpus is loaded and
THEMIS recomputes the value), a **frozen expected artifact** (a figure shipped
with the sample; not a reproduction) and a **manuscript declaration**
(`paper/paper_claims.yml`). A PASS needs live computation equal to the
declaration. Every claim is `PASS`, `FAIL`, `NOT_REPRODUCED` (the loaded input
cannot recompute it), `INFORMATIONAL` or `NOT_MACHINE_CHECKABLE`, and the run is
`PASS`, `FAIL` or `BLOCKED` - never `PASS` when required input was unavailable.
The bundled sample recomputes cross-dataset results exactly but carries
corpus-wide totals only as manifest figures, so on it those are `NOT_REPRODUCED`.
With no corpus at all the result is `BLOCKED - INPUT CORPUS NOT AVAILABLE`, with
the list of sources and the build command.

Comparison rules are declared per claim, with no implicit tolerance:
`exact_integer`, `exact_string`, `rounded_percent`, `rounded_decimal`, `range`,
`approximate_text`. The verification hierarchy is THEMIS-generated metrics →
`paper/paper_claims.yml` → the final PDF; all three must agree. The manifest is
read only by the verifier, never by an analysis function. The Paper Reproduction
page of the dashboard shows the same verification matrix, fetched from the API.
Figures need `pip install -e ".[figures]"` (matplotlib); without it their data
files are still written.

## 7. Uploading a new Bitcoin attribution CSV

Dashboard: Upload → pre-flight → confirm schema → run. CLI: `themis ingest FILE
--source-id NAME [--map role=column ...] [--reference OBS | --no-reference]`.
Schema roles (address, label, category, source, timestamp, confidence) are
inferred from column names and sampled values and can be overridden. Try it with
the synthetic files in `examples/`.

An unrecognized `--source-id` has no provenance rule in `config/sources/`, so
every claim resolves **UNRESOLVED** by construction — a new dataset is never
assumed independent. Cross-source comparison needs a reference corpus (§6);
without one the audit says so and continues.

## 8. Pre-flight behavior

Before any workspace exists THEMIS never assumes an upload is cryptocurrency
data, and distinguishes four cases instead of one generic rejection:

| input | result |
|---|---|
| **Supported-chain attribution data** (Bitcoin: base58check, bech32/bech32m) | runs the full pipeline |
| **Crypto, not attribution** (e.g. a price series with a `symbol` column naming BTC) | stops: recognised as cryptocurrency-related but not attribution data — via an opt-in `symbol_aliases` content signal on the chain adapter, never from a filename |
| **Unsupported-chain attribution** (e.g. Ethereum) | stops: identified as crypto attribution data on a chain THEMIS does not support, via a chain-agnostic token-shape fallback |
| **Non-crypto** | stops: no address-shaped column and no asset-identity signal, with an explanation of what was looked for |
| **Malformed** (empty, binary, non-UTF-8, header only) | fails gracefully with a specific message, not a stack trace |

Invalid addresses (wrong checksum, wrong network, non-Bitcoin) and duplicate rows
are rejected with the row number and reason, never analysed.

## 9. Main modules

| module | CLI | dashboard |
|---|---|---|
| Upload / pre-flight | `ingest` | Upload |
| Audit (agreement, independence, kappa) | `audit` | Audit |
| Claims (bounded, filterable) | API `GET /api/analysis/{id}/claims` | Claims |
| Address Inspector | `explain` | Address |
| Provenance | `sources` | Provenance (lineage graph) |
| Trust-rule sensitivity | `drift` | Drift (paper mode only) |
| Anchor validation | `anchors` | JSON via `report --anchors` |
| Export | global `--json`; API `GET /api/analysis/{id}/export/{name}` | Export |

## 10. Evidence taxonomy

- **Tiers** — `verified` (provenance ends in evidence a third party could
  re-check: seized data, a court record, a sanctions designation, an issuer's
  self-disclosure); `derived` (heuristic propagation or curated annotation);
  `unverified-report` (crowd report, forum post, automated extraction);
  `unknown` (an upload with no declared methodology — never silently `derived`).
  A source's own "manually verified" declaration does not by itself reach
  `verified`; a *record* whose root is re-checkable (an OFAC listing) does.
- **Flags** — `currency-unknown`, `stale`, `conflicting`, `circular`; orthogonal
  to the tier.
- **Conflict logic** — exact / hierarchical refinement / entity-type conflict /
  licit-illicit conflict / incomparable. *Incomparable* means fewer than two
  datasets contributed a category the taxonomy can interpret; one opinion is not
  agreement with itself.

## 11. Provenance terminology

- **Claim** — one source asserting one category about one address; the unit of analysis.
- **Root** — where a claim's evidence originates, which is not the dataset that
  republished it. Assigned from a source's declared rule, **per record where
  records differ** (WatchYourBack cites an external URL on every row, so its
  Treasury-cited records are rooted at OFAC and only the rest at WatchYourBack).
- **Resolved / native / verified / unresolved** — a known origin; the source *is*
  that origin; the origin is re-checkable; an unknown relationship.
- **Circular / inherited** — apparently independent claims that share one resolved root.
- **Structured label** — a `type:entity` raw label (`onlinewallet:flexcoin`); its
  category-shaped prefix is canonicalized like any alias and the entity kept.

## 12. Trust-rule interpretation

`themis drift` re-runs one task (ransomware revenue) under four rules: **A** naive
union, **B** address-level deduplication (the baseline), **C** inherited claims
collapsed to their root, **D** the addresses an anchor set names. D is *the
highest declared confidence present*, not verified ground truth: in the bundled
corpus it is exactly the addresses TagPack tags `confidence: forensic` (plus
WatchYourBack's ransomware annotations), and almost all of it is one upstream
study. Read the ratio and the coverage together; neither means anything alone.

## 13. Dataset and license notice

Seven public datasets feed the paper corpus. Redistribution status differs and is
**not uniformly confirmed** — `THIRD_PARTY_DATA.md` has the per-source table
(license, evidence, retrieval date, status). TagPack (MIT), Schnöring and
Ransomwhere (CC BY 4.0) are confirmed; Elliptic++ (53% of claims) and both
Rodwald releases state no terms; WatchYourBack's GPL-3.0 covers its code.
**This release ships no third-party data and no observation table.** THEMIS's
own code has **no LICENSE file yet** — an author decision, separate from the
dataset terms.

## 14. Testing

```
python -m pytest
```

With the reference corpus present every test runs. Without it (the release),
tests that assert a number printed in the paper, or that drive the
paper-reproduction endpoints, **skip with a stated reason** rather than fail;
everything else — the adapters, address validation, the taxonomy, provenance
independence (every case A–G across CLI/API/flags/trust predicates), the trust
engine, ingest detection, export safety, the rebuild script — runs on synthetic
data. Tests have caught real defects, not just regressions: `classify_address`
counting one source's opinion as agreement (moved the §5.1 breakdown from 13,673
to 10,515 exact), a stray upstream `#` silently breaking joins, a bootstrap that
depended on whether numpy was installed, and a staleness date that made the
paper's own "99.9% over three years old" irreproducible.

## 15. Limitations

- **The paper and THEMIS disagree on 32 numbers**, chiefly §5.1's agreement
  breakdown (the paper pipeline counts one interpretable label as agreement),
  WatchYourBack-dependent overlaps and kappa values, and §5.4's exact-rate
  interval. `REPRODUCE.md` lists them.
- Several paper figures need the **full corpus**, not the sample: the
  multi-dataset-rate interval, 853,604 upper-bound clusters, corpus-wide
  freshness. The bundled sample keeps every multi-dataset address, so agreement,
  conflict and circularity figures are exact; corpus-wide totals come from a manifest.
- **The bundled sample's multi-dataset total is pre-`#`-fix (15,400).** It was computed
  when WatchYourBack's 87 `#`-prefixed addresses were still unjoined; the full
  corpus, with them joined, has 15,413 multi-dataset addresses (7,845 / 429 / 7,112 / 27).
  The manuscript states the full-corpus value.
- The anchor set (`ground_truth.csv`, 289 addresses) is curated from
  WatchYourBack and the OFAC list and is not yet scripted. It is small,
  concentrated in few roots, and yields an estimable figure for only two sources.
- WatchYourBack is resolved per record only for its 71 Treasury-cited `#`
  records. 16 other `#` records, 31 more Treasury-cited and 171 externally-cited
  records still resolve to its own root: the observation schema carries no
  per-record reference URL.
- Kappa keeps `unknown` as a class in its headline (an interpretable-only
  companion is printed beside it).
- TagPack's proper-noun entity labels ("Antpool") are not mapped to categories.
- `demo_data/revenue.csv.gz` keeps full float precision (an earlier cent-rounded
  copy biased Table 2 low by $2.55-$3.16; see REPRODUCE.md section 8).
- The dashboard was browser-tested against the Vite dev server with a real
  Chromium (2026-09-20): paper reproduction, evidence drill-down, upload,
  pre-flight, analysis pages, exports and workspace switching. Not tested: Safari,
  Firefox, mobile widths, a production `vite preview` session.
- Tested on Python 3.14 and Node 26 only.

## 16. Reproducibility

- Every `report` carries an audit trail: software version, timestamp, input file
  hash, and a hash of `taxonomy.yml` / `thresholds.yml` / `trust_rules.yml` /
  `sources/*.yml` / `notable_roots.yml` — equal hashes mean equal scientific rules.
- Staleness is judged at a **declared analysis date** (the bundled corpus
  declares 2026-09-15; `--as-of` overrides), never the wall clock.
- The canonical bootstrap is stdlib `random.Random(seed)` regardless of numpy;
  seed 42 / 2,000 resamples / 95% are read from `config/thresholds.yml`.
  `--fast` (numpy) is marked non-canonical.
- `scripts/build_corpus.py` records input hashes, adapter and normalization
  versions, retrieval dates and dropped rows, and is byte-deterministic. Checked
  against real data: today's GraphSense TagPack rebuilds to the paper's exact
  499,327 claims / 483,296 addresses.
- `expected_output/` holds the frozen CLI output; `REPRODUCE.md` has the commands.

## 17. Citation

The paper is under review at ICISHCT 2026. Until the reference is final, cite by
title: *"Provenance Before Precision: Auditing Public Bitcoin Attribution Labels
and Their Effect on Forensic Conclusions."*

## Appendix: layout

```
themis/            taxonomy, provenance, corpus, analysis, reliability, report, graph,
                   target_audit, workspace, api, cli, chains/, ingest/, trust/, tasks/, config/
themis/paper/      experiments, metrics (PaperMetrics), verify, figures, reproduce
paper/             paper_claims.yml - the manuscript's declared values (verifier input only).
                   The manuscript itself is not part of the repository (see REPRODUCE.md §8)
scripts/           build_corpus.py, generate_result_sets.py, independent_agreement_check.py
tests/             unit and paper-regression tests (paper tests skip without the corpus)
examples/          synthetic CSVs for the upload flow
expected_output/   frozen CLI output and metrics for comparison
frontend/          React + Vite dashboard
demo_data/         (development checkout only) bundled sample - not part of a release
```

**Config, not code, is dataset-specific.** Nothing under `themis/*.py` names a
source, category or trust condition by string literal; `provenance.resolve()`
reads a generic rule shape (`fixed_root` / `field_map` / `contains_rules` /
`substring_map`) from `config/sources/<id>.yml`. **One policy engine, any task:**
`themis/trust/` scores claims against composable predicates named in
`config/trust_rules.yml`; `tasks/ransomware_revenue.py` is the one module that
knows the task is a USD sum. **The decode may be inconclusive:** `decode_field`
returns `insufficient` or `malformed` rather than forcing a verdict.
