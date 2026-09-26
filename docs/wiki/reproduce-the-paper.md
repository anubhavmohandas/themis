# Reproduce the paper

[← Wiki home](README.md) · [Project README](../../README.md)

## Paper reproduction

The reference corpus is **not shipped with a release** (the paper's data
statement: the derived observation table is not redistributed; see [Data and licences](data-and-licenses.md)). Build
it from the sources, then point THEMIS at it:

```
python scripts/build_corpus.py --out build/ --tagpack ... --schnoering ... (see [REPRODUCE.md](../../REPRODUCE.md))
themis --observations build/observations.csv.gz --data-dir build/ --as-of 2026-09-15 audit
themis --observations build/observations.csv.gz --data-dir build/ --as-of 2026-09-15 drift
themis --observations build/observations.csv.gz --as-of 2026-09-15 bootstrap --both
```

A development checkout also carries a 268,891-claim sample in `demo_data/`, so
plain `themis audit | drift | bootstrap --both | anchors | explain <address>` work
there and match `expected_output/` byte for byte. [REPRODUCE.md](../../REPRODUCE.md) has exact
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

### The executable paper: `reproduce-paper` and `verify-paper`

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

## Reproducibility

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
- `expected_output/` holds the frozen CLI output; [REPRODUCE.md](../../REPRODUCE.md) has the commands.
