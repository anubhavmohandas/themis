# Install and use

[← Wiki home](README.md) · [Project README](../../README.md)

## Installation

```
git clone <repo> && cd themis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"          # add ,ui to run the web backend: pip install -e ".[test,ui]"
```

Python ≥ 3.10 (developed and tested on 3.14.6; the 3.10 floor is from inspection,
not a test run). One required dependency, PyYAML. NumPy is optional and never
changes a canonical result (see [Reproduce the paper](reproduce-the-paper.md#reproducibility)). Node ≥ 18 for the dashboard.

## Main modules

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

## Architecture

```
frontend/        React 18 + Vite dashboard; talks to the API over HTTP
themis/api.py    FastAPI JSON layer - request parsing and serialization only
themis/*.py      Python analysis core - the CLI and the API call the same functions
scripts/         build_corpus.py (from-source rebuild), result-set generators
```

The API and the frontend contain no analysis: every number comes from the same
`themis.report` / `analysis` / `graph` functions the CLI calls, so the dashboard
and `themis audit` cannot diverge. (The React pages only format backend values.)
