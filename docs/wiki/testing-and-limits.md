# Testing and known limits

[← Wiki home](README.md) · [Project README](../../README.md)

## Testing

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

## Limitations

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
