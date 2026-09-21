# Examples

Tiny synthetic files for trying the upload flow without any third-party data.
Nothing here comes from a real dataset: the Bitcoin addresses are derived from
`sha256("themis-example-N")` (they correspond to no known key) and the labels
are made up.

| file | what THEMIS should do |
|---|---|
| `example_attribution.csv` | pass pre-flight as Bitcoin attribution data (chain detected from the addresses); one address (`themis-example-7`) carries two labels that disagree; the provenance of the feed is UNRESOLVED (unknown source) so nothing is counted as independent corroboration. Its bare `timestamp` column has no stated meaning, so THEMIS does not use it for staleness: map it yourself with `--map ts_attribution_last_updated=timestamp` (or the mapping screen) if it does date the labels |
| `example_non_crypto.csv` | stop at pre-flight: no cryptocurrency-shaped column |
| `example_unsupported_chain.csv` | stop at pre-flight: address-shaped values on a chain THEMIS does not support (Ethereum), reported as *unsupported chain*, not "not crypto" |
| `example_crypto_non_attribution.csv` | stop at pre-flight: an OHLC price series (a `symbol` column names BTC) - market data, not attribution claims: "Unsupported dataset for attribution analysis" |

```
themis ingest examples/example_attribution.csv --no-reference
```
(or upload the file on the dashboard's Upload page). Comparison against a
reference corpus needs the corpus built with `scripts/build_corpus.py`.

Every file is pre-flighted before anything runs: `themis preflight FILE` prints what each
column was taken to mean, the chain and how it was determined, and what blocks analysis;
`themis ingest` refuses to proceed when that fails, whatever `--map` says. A
`.db`/`.sqlite`/`.sqlite3` file can be inspected with `themis preflight FILE` (tables and row
counts) and `themis preflight FILE --table NAME` (pre-flight on a sample); analysis of a whole
SQLite table is not implemented yet.
