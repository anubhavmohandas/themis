# Project layout and citation

[← Wiki home](README.md) · [Project README](../../README.md)

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
demo_data/         (only README.md is tracked; the real sample stays on the author's machine, git-ignored)
```

**Config, not code, is dataset-specific.** Nothing under `themis/*.py` names a
source, category or trust condition by string literal; `provenance.resolve()`
reads a generic rule shape (`fixed_root` / `field_map` / `contains_rules` /
`substring_map`) from `config/sources/<id>.yml`. **One policy engine, any task:**
`themis/trust/` scores claims against composable predicates named in
`config/trust_rules.yml`; `tasks/ransomware_revenue.py` is the one module that
knows the task is a USD sum. **The decode may be inconclusive:** `decode_field`
returns `insufficient` or `malformed` rather than forcing a verdict.

## Citation

The paper is under review at ICISHCT 2026. Until the reference is final, cite by
title: *"Provenance Before Precision: Auditing Public Bitcoin Attribution Labels
and Their Effect on Forensic Conclusions."*
