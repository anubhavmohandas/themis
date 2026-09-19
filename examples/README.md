# Examples

Tiny synthetic files for trying the upload flow without any third-party data.
Nothing here comes from a real dataset: the Bitcoin addresses are derived from
`sha256("themis-example-N")` (they correspond to no known key) and the labels
are made up.

| file | what THEMIS should do |
|---|---|
| `example_attribution.csv` | accept as Bitcoin attribution data; one address (`themis-example-7`) carries two labels that disagree; the provenance of the feed is UNRESOLVED (unknown source) so nothing is counted as independent corroboration |
| `example_non_crypto.csv` | stop at pre-flight: no cryptocurrency-shaped column |
| `example_unsupported_chain.csv` | stop at pre-flight: address-shaped values on a chain THEMIS does not support (Ethereum), reported as *unsupported chain*, not "not crypto" |
| `example_crypto_non_attribution.csv` | stop at pre-flight: recognised as cryptocurrency-related (a `symbol` column naming BTC) but not attribution data |

```
themis ingest examples/example_attribution.csv --no-reference
```
(or upload the file on the dashboard's Upload page). Comparison against a
reference corpus needs the corpus built with `scripts/build_corpus.py`.
