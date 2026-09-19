# Third-party data

THEMIS's own code license is a separate question (see `README.md` §11: no
`LICENSE` file has been chosen yet). This document covers only the public
datasets the bundled sample derives from, and the one government list the
anchor file draws on.

**What is bundled** (all under `demo_data/`, all *derived*, none a source's
original file):

| file | contents | derived from |
|---|---|---|
| `observations_sample.csv.gz` | 268,891 normalized claims: address, canonical category, raw label, provenance fields | all seven sources (Elliptic++ and TagPack sampled; the other five complete) |
| `verified_anchors.txt.gz` | 146,243 bare addresses — Condition D's anchor set | TagPack tags with `confidence: forensic` **∪** WatchYourBack's ransomware addresses (rebuilt and confirmed identical with `scripts/build_corpus.py`) |
| `revenue.csv.gz` | 61,508 rows: address, USD received, family | Rodwald ransomware + Ransomwhere |
| `ground_truth.csv` | the 289-address open anchor set | WatchYourBack manual annotations + OFAC SDN |
| `manifest.json` | full-corpus counts recorded when the corpus was built | — |

No transaction graph, no feature file, and no source's raw file is included.
All license findings below were re-checked on **2026-09-19** directly against
each source's own repository, Zenodo record or page — not assumed.

**No legal conclusion is drawn here.** Where redistribution terms are not
confirmed, that is stated as `UNCONFIRMED`; the decision is the author's.

## Per-source status

| # | Source | Official location | Cited in paper as | Retrieval date (corpus / license check) | License | License evidence | Raw bundled? | Derived bundled? | Redistribution |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GraphSense TagPack | github.com/graphsense/graphsense-tagpacks | [1] Haslhofer et al., arXiv:2102.13613 | corpus: paper build (Sep 2026) / check: 2026-09-19 | **MIT** | `LICENSE` in repo root, © Iknaio Cryptoasset Analytics GmbH and AIT (read 2026-09-19) | No | Yes (25,362 sampled claims + the `forensic` half of the anchor file) | **CONFIRMED** (MIT; keep the copyright + permission notice with the derived rows) |
| 2 | Schnöring et al. | Zenodo doi:10.5281/zenodo.22239038, "Bitcoin transaction graphs: training, labelled entities, and CoinJoins" | [2] Schnoering & Vazirgiannis, Sci. Data 12, 404 (2025) | corpus: paper build / check: 2026-09-19 | **CC BY 4.0** | Zenodo API `metadata.license.id = cc-by-4.0` (2026-09-19) | No | Yes (103,812 claims, complete) | **CONFIRMED** with attribution. Note the record is dated 2026-09-01: the author should confirm it is the version the corpus was built from |
| 3 | Ransomwhere | ransomwhe.re; Zenodo doi:10.5281/zenodo.13999026 | [17] export retrieved 15 Sep 2026 | corpus: 2026-09-15 live export / check: 2026-09-19 | **CC BY 4.0** (Zenodo dataset) | Zenodo API `cc-by-4.0` (2026-09-19). The live API returned HTTP 502 on 2026-09-19, so the live export's own terms were not re-read | No | Yes (11,186 claims, complete; revenue rows) | **CONFIRMED** for the Zenodo-published dataset; the live export the paper used is presumed the same dataset but was not separately checked |
| 4 | Elliptic++ | github.com/git-disl/EllipticPlusPlus | [14] Elmougy & Liu, KDD '23 | corpus: paper build / check: 2026-09-19 | **NONE STATED** | GitHub API `license: null`; the repository's README asks for citation and states no terms. The base Elliptic dataset it extends is separately CC BY-NC-ND 4.0 elsewhere; whether that covers Elliptic++'s own address data is unconfirmed | No | Yes (20,083 sampled claims; **53.24% of all corpus claims**) | **UNCONFIRMED** |
| 5 | Rodwald — ransomware | sydeus.rodwald.pl/datasets (`BTC_Ransom.csv`) | [15] Rodwald, DepCoS-RELCOMEX 2024 (Springer) | corpus: paper build / check: 2026-09-19 | **NONE STATED** | The dataset page (read 2026-09-19) carries no license or terms text and its legend documents feature columns only, not the `source` letter code; the paper is paywalled | No | Yes (50,322 claims, complete; revenue rows) | **UNCONFIRMED** |
| 6 | Rodwald — mixers | sydeus.rodwald.pl/datasets (`BTC_Mixers.csv`) | [16] Rodwald, DepCoS-RELCOMEX 2025 (Springer) | corpus: paper build / check: 2026-09-19 | **NONE STATED** | Same page, same finding | No | Yes (57,817 claims, complete) | **UNCONFIRMED** |
| 7 | WatchYourBack | github.com/cybersec-code/watchyourback | [6] Gomez, Moreno-Sanchez & Caballero, ACM CCS 2022 | corpus: paper build / check: 2026-09-19 (data file re-fetched, 309 rows identical to the bundle) | **GPL-3.0** for the repository | GitHub API `spdx_id: GPL-3.0` (2026-09-19). Whether it extends to `data/tagging/btc_resolv.csv` specifically is not stated | No | Yes (309 claims, complete; the ransomware half of the anchor file; 104 of the 289 ground-truth anchors) | **PARTIALLY CONFIRMED** — code license only; GPL-3.0 is copyleft |
| — | OFAC SDN list | treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml | — | fetched 2026-09-18 | US government work (public domain) | — | No | Yes (185 of the 289 ground-truth anchors; used to verify WatchYourBack's Treasury-cited records) | **CONFIRMED** |

## What this means for a release

- **Confirmed permissive** — TagPack, Schnöring, Ransomwhere, OFAC: 39.74% of
  corpus claims (32.30 + 6.72 + 0.72; OFAC adds none).
- **Unconfirmed** — Elliptic++ (53.24%) and both Rodwald releases (7.00%
  combined): **60.24% of corpus claims** are derived from sources with no
  stated redistribution terms.
- **Partially confirmed** — WatchYourBack (0.02%): code license only.

The repository is already public (github.com/anubhavmohandas/themis) and has
contained `observations_sample.csv.gz` since its first commit; nothing here
rewrites that history — that would be a separate decision.

### Conservative release options (the author's choice; the release below applies option 2 by default)

1. **Confirm** with the Elliptic++ and Rodwald authors and record the answer
   here; ship the bundle as is.
2. **Rebuild instead of ship.** Replace the unconfirmed sources' rows with
   download instructions plus checksums and let a reviewer run
   `scripts/build_corpus.py` on files they fetched themselves. This is now a
   real option: today's TagPack repository rebuilds to exactly the paper's
   499,327 claims / 483,296 addresses; WatchYourBack's 309 rows and Condition
   D's 146,243-address anchor set rebuild identically; only the sampling of
   Elliptic++ and TagPack in the bundled sample is not itself reproducible.
3. **Substitute** a small synthetic demo for those sources (the release includes `examples/` for the upload flow).

**What the release does (a conservative default, not a legal conclusion).**
The paper's Data availability statement says *the derived observation table is
not redistributed, because the redistribution terms of the constituent sources
differ.* The release therefore ships **none** of the files in the first table
above - no `observations_sample.csv.gz`, `verified_anchors.txt.gz`,
`revenue.csv.gz`, `ground_truth.csv` or `manifest.json`. It ships the code, the
tests (those that need the corpus skip with a stated reason), the rebuild script,
`expected_output/` (aggregate statistics only) and small synthetic examples. A
reviewer fetches the sources from their published locations and runs
`scripts/build_corpus.py`; `REPRODUCE.md` gives the commands. The
development repository still tracks `demo_data/` (already public since its first
commit); changing that is a separate decision.

Two things this leaves to the author: whether to confirm terms with the
Elliptic++ and Rodwald authors and then ship a sample after all, and how a
reviewer without the sources is served (the anchor set `ground_truth.csv` is
curated from WatchYourBack's file and the OFAC list and is not yet scripted).

## Attribution

If the bundle is redistributed, keep with it: the MIT notice for GraphSense
TagPack (© Iknaio Cryptoasset Analytics GmbH; © AIT Austrian Institute of
Technology), the CC BY 4.0 attributions for Schnöring et al. and Ransomwhere,
and the citations in the table above.
