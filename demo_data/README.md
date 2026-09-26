# demo_data

This directory holds no data in a release or in the public repository.

**Why.** The paper's data statement is that the derived observation table is not
redistributed. The constituent sources are third-party datasets whose redistribution
terms are not uniform (some are permissive, some state no terms at all), so no real
record from them is shipped. Details and per-source status: [../THIRD_PARTY_DATA.md](../THIRD_PARTY_DATA.md).

**What is on the author's machine.** The author keeps the exact research artifacts
(the retained observation table, revenue file, anchor and ground-truth files, and the
raw source files with their hashes) privately, for reproducibility. Files placed here
are ignored by Git (`.gitignore`), so they cannot be added by accident. They are **not**
the authoritative source of the paper's claims.

**Where the paper's results come from.** From the declared seven-source rebuild and
reproduction pipeline, not from any file in this directory:

1. Fetch the seven sources yourself. Locations, versions/commits and licence notes:
   [../THIRD_PARTY_DATA.md](../THIRD_PARTY_DATA.md).
2. Rebuild the corpus: `python scripts/build_corpus.py --out build/ ...`
   ([../REPRODUCE.md](../REPRODUCE.md) section 3). It hashes every input and writes
   `build_manifest.json`; compare it with
   [../expected_output/retained_table_build_manifest.json](../expected_output/retained_table_build_manifest.json).
3. Point THEMIS at the build with `--data-dir build` (or `THEMIS_DATA_DIR=build`) and run
   `themis reproduce-paper`; expected aggregate outputs are in
   [../expected_output/](../expected_output/).

Exact reproduction of the Ransomwhere source needs the author's retained, hashed
2026-09-20 export: the live service changes.

To audit your own data instead, no corpus is needed: `themis ingest examples/example_attribution.csv --no-reference`.
