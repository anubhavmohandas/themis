# Audit your own data

[← Wiki home](README.md) · [Project README](../../README.md)

## Uploading a new cryptocurrency attribution CSV

Dashboard: Upload → pre-flight → confirm schema → run. CLI: `themis ingest FILE
--source-id NAME [--map role=column ...] [--reference OBS | --no-reference]`.
Schema roles (address, label, category, source, timestamp, confidence) are
inferred from column names and sampled values and can be overridden. Try it with
the synthetic files in `examples/`.

**The closing assessment.** Every analysis ends with an executive summary: *"According to the
THEMIS report, the assessment of this dataset is X, because …"*, where X is `EVIDENCE SUPPORTED`,
`SUPPORTED WITH CAVEATS`, `NOT ESTABLISHED` (nothing wrong, but too little independent
evidence to say it is right), `EVIDENCE CONCERNS` (a measured problem rules the labels out) or
`CANNOT ASSESS` (failed pre-flight). It reads only figures the pipeline already measured and
the cut-offs in `themis/config/assessment.yml` (which also holds the wording of each outcome),
and lists the numbers behind it. It summarises the evidence for the labels, not any single
label: coverage is not accuracy, and no outcome means the labels are proven correct.

An unrecognized `--source-id` has no provenance rule in `config/sources/`, so
every claim resolves **UNRESOLVED** by construction — a new dataset is never
assumed independent. Cross-source comparison needs a reference corpus ([Reproduce the paper](reproduce-the-paper.md));
without one the audit says so and continues.

**Local use only.** The API binds `127.0.0.1` and has no authentication: it is a
single-user tool. What it does enforce, from `themis/config/api.yml` (whose header
states the threat model): CORS names the frontend's own origins, never `*`, and a
state-changing request from any other browser origin is refused; an upload is
capped in bytes *while it is read* (and a `.gz` also in decompressed size) and
in logical rows (see [Scale and limits](your-own-data.md#scale-and-limits)); a
client sees a generic message for any internal failure while the server log keeps
the detail; an SQLite database is opened only by a name inside `THEMIS_DB_DIR`,
read-only; a request whose `Host` header is not a local hostname (`hosts.allowed`,
port ignored) is refused, which closes DNS rebinding. Not covered: other local
processes.

### Scale and limits

THEMIS's architecture is **in-memory**: an uploaded dataset, its claims and every derived
table are held in RAM for the life of the analysis. Disk-backed storage is **not
implemented**, and THEMIS does not support arbitrary multi-gigabyte datasets.

- Measured on the 10,000,000-row / 850 MB unseen-dataset run ([MBAL_VALIDATION_REPORT.md](../../MBAL_VALIDATION_REPORT.md)):
  about **2.5 KB of RAM per row**, a peak near **24.7 GB**.
- The upload limit stays **256 MiB** (`upload.max_bytes`), and a **`upload.max_rows`** guard
  (default 1,000,000 logical CSV rows, about 2.5 GB) refuses a larger file before any
  analysis: HTTP 413, no partial result, service unaffected. Rows are CSV records, so a
  quoted newline is one row. Both live in `themis/config/api.yml`.
- The 10M-row analysis is a **documented scale test**, run under an explicit local config
  (`THEMIS_CONFIG_DIR` with raised limits) on a machine sized for it. It is not the
  public or browser path.
- The first Claims or Trust query on a very large analysis can be slow (the claims are
  sorted, and the trust rules evaluated, once per workspace and then cached).
- `analysis_summary.json` contains every claim and stays intentionally large; it is
  streamed rather than built in memory, but it is still as large as the analysis.

## Pre-flight behavior

Before any workspace exists THEMIS never assumes an upload is cryptocurrency
data, and distinguishes four cases instead of one generic rejection:

| input | result |
|---|---|
| **Supported-chain attribution data** (Bitcoin: base58check, bech32/bech32m; Ethereum, BNB Smart Chain, Polygon, Avalanche C-Chain: `0x` + 40 hex, EIP-55 reported separately from validity) | runs the full pipeline; the chain is stated per row, per file, or chosen by you (an EVM address is valid on every EVM chain, so it is never guessed) |
| **Attribution-like, schema unresolved** (identifier column that fails validation next to attribution labels) | stops, and says what was established (labels, the chain the file states) and why nothing ran; it is not called "not attribution data" |
| **Crypto, not attribution** (e.g. a price series with a `symbol` column naming BTC) | stops: recognised as cryptocurrency-related but not attribution data — via an opt-in `symbol_aliases` content signal on the chain adapter, never from a filename |
| **Unsupported-chain attribution** (e.g. Tron) | stops: identified as crypto attribution data on a chain THEMIS does not support, via a chain-agnostic token-shape fallback |
| **Non-crypto** | stops: no address-shaped column and no asset-identity signal, with an explanation of what was looked for |
| **Malformed** (empty, binary, non-UTF-8, header only) | fails gracefully with a specific message, not a stack trace |

Invalid addresses (wrong checksum, wrong network, non-Bitcoin) and duplicate rows
are rejected with the row number and reason, never analysed.
