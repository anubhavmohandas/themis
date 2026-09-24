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
| 2 | Schnöring et al. | figshare doi:10.6084/m9.figshare.26305093.v3 "BitcoinTemporalGraph", file `addresses.csv` (the address, category, source table). *Not* Zenodo 22239038, which an earlier version of this table cited: that record's labels are per-transaction entity names without category or source | [2] Schnoering & Vazirgiannis, Sci. Data 12, 404 (2025) | corpus: paper build / rebuilt and row-count-checked 2026-09-20 | **CC BY 4.0** | figshare API `license.name = CC BY 4.0` (2026-09-20) | No | Yes (103,812 claims over 101,387 addresses, complete) | **CONFIRMED** with attribution |
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

The development repository is already public and has contained
`observations_sample.csv.gz` since its first commit; nothing here rewrites that
history — that would be a separate decision.

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

## Redistribution matrix (re-checked 2026-09-24; conservative: `UNCONFIRMED` is not `PERMITTED`)

Every upstream location below was fetched again on 2026-09-24. "Located" means the license text
itself (or the platform's structured license field) was read, not inferred. Nothing here is a legal
conclusion, and nothing was removed from the repository on the strength of this table: the release
policy is the author's (see "What is decided and what is not").

| source | upstream URL | upstream license | license text located? | redistribution explicit? | derived redistribution explicit? | attribution | share-alike | research-only | commercial restriction | status | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GraphSense TagPack | github.com/graphsense/graphsense-tagpacks | MIT | yes: `LICENSE` in the repository root (HTTP 200, 2026-09-24; GitHub `spdx_id: MIT`) | yes (MIT) | yes (MIT permits modification and sublicensing) | keep the copyright and permission notice (© 2022 Iknaio Cryptoasset Analytics GmbH; © 2018-2022 AIT Austrian Institute of Technology) | no | no | no | **CONFIRMED REDISTRIBUTABLE** | repository license; the individual tag creators' own rights are not separately stated |
| Schnöring et al. | figshare doi:10.6084/m9.figshare.26305093 (v3, `addresses.csv`) | CC BY 4.0 | yes: figshare API `license` = CC BY 4.0 with its deed URL (2026-09-24) | yes | yes (CC BY permits adaptations) | yes: credit, link the license, indicate changes | no | no | no | **CONFIRMED REDISTRIBUTABLE** | figshare metadata for the exact version the corpus was built from (v3) |
| Ransomwhere | ransomwhe.re (live `api.ransomwhe.re/export`); Zenodo doi:10.5281/zenodo.13999026 | CC BY 4.0 for the Zenodo deposit (v1.1.0, published 2024-10-27) | for the Zenodo deposit only (Zenodo API `cc-by-4.0`, 2026-09-24). The live export the corpus was built from (retrieved 2026-09-20) is a different, later artifact; `ransomwhe.re` returned no readable page text (client-rendered), so no live terms were found | not for the live export | not for the live export | yes (for the Zenodo deposit) | no | no | no | **UNCONFIRMED** for the records actually in the corpus (the Zenodo v1.1.0 subset alone would be CONFIRMED) | earlier notes (2026-09-19) marked this CONFIRMED; that read the Zenodo record, not the live export the corpus uses |
| Elliptic++ | github.com/git-disl/EllipticPlusPlus (data on a Google Drive folder the README links) | none stated | no: GitHub `license: null`, no LICENSE file in the repository; the README asks for citation and states no terms | not stated | not stated | citation requested (KDD '23) | not stated | not stated | not stated | **UNCONFIRMED** | the base Elliptic dataset is reported (not re-read today) to carry CC BY-NC-ND 4.0; whether that extends to Elliptic++'s address data is unconfirmed |
| Rodwald - ransomware | sydeus.rodwald.pl/datasets/ (`BTC_Ransom.csv`) | none stated | no: the page (fetched 2026-09-24, 3,688 characters of text) contains no license, terms or copyright text | not stated | not stated | not stated | not stated | not stated | not stated | **UNCONFIRMED** | the DepCoS-RELCOMEX paper is paywalled |
| Rodwald - mixers | sydeus.rodwald.pl/datasets/ (`BTC_Mixers.csv`) | none stated | no (same page) | not stated | not stated | not stated | not stated | not stated | not stated | **UNCONFIRMED** | as above; the page says the article link is "soon" |
| WatchYourBack | github.com/cybersec-code/watchyourback (`data/tagging/btc_resolv.csv`) | GPL-3.0 for the repository | yes: `LICENCE` (GNU GPL v3 text) at the repository root; GitHub `spdx_id: GPL-3.0` | the license text permits conveying, but the repository does not say the tag data is a licensed "work" | not stated for the data | GPL notices | **yes if GPL applies to the data**: a redistributed derivative would have to be GPL-3.0 | no | no (GPL permits commercial use) | **UNCONFIRMED** | if GPL does apply, shipping these rows inside a repository under MIT or Apache-2.0 would conflict (see Decision 2). Upstream's README documents the tag-file format and says nothing about licensing the data |
| OFAC SDN list | treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml | none: a US government work | not applicable (17 U.S.C. § 105); not re-fetched | yes (no copyright in US government works) | yes | none required | no | no | no | **CONFIRMED REDISTRIBUTABLE** | recorded 2026-09-18; the statutory basis is general, not a per-file notice |

### Which tracked files carry which sources

| tracked file | records from | worst status | note |
|---|---|---|---|
| `demo_data/observations_sample.csv.gz` | all seven (Elliptic++ 20,083, Rodwald 108,139, Ransomwhere 11,186, WatchYourBack 309 among 268,891 rows) | UNCONFIRMED | record-level |
| `demo_data/revenue.csv.gz` | Rodwald ransomware + Ransomwhere | UNCONFIRMED | 61,508 address rows |
| `demo_data/verified_anchors.txt.gz` | TagPack `forensic` + WatchYourBack ransomware | UNCONFIRMED (the WatchYourBack half; GPL question) | 146,243 bare addresses |
| `demo_data/ground_truth.csv` | WatchYourBack + OFAC | UNCONFIRMED (the WatchYourBack half) | 289 addresses |
| `demo_data/manifest.json` | none: counts and root shares | not a record set | aggregates; safe to keep |
| `examples/*.csv` | none: synthetic (`example_feed`) | not applicable | |
| `tests/`, `REPRODUCE.md`, `expected_output/explain_14BW…txt` | a handful of individual addresses (one address, its labels) | incidental | judged by the author; not a dataset |

### What is decided and what is not

- **Not decided, by rule:** whether `demo_data/` stays tracked. Until the author chooses, nothing was removed. The conservative
  default already applied to a *release build* (`scripts/make_release.py`) ships none of the `demo_data/` files.
- **The repository is public** (github.com/anubhavmohandas/themis, created 2026-09-16; on 2026-09-24 it reported 0 forks, 0 stars,
  0 watchers and no releases; `main` only was pushed, the `v1.0-paper*` tags exist locally). `demo_data/` has been in it since
  the first commit (`b47da84`).
- **`git rm` is not enough.** The five files exist as 10 distinct blob versions across 6 of the 89 commits, from the first commit on. Removing them
  from the current tree leaves every one retrievable from history. Removing them from history means rewriting it with
  `git filter-repo --path demo_data --invert-paths` (not installed on this machine) or BFG, which changes **every** commit hash
  (the files exist from the first commit), needs a force-push to `main`, invalidates the local `v1.0-paper*` tags and the release
  ZIP hashes recorded in `REPRODUCE.md` and the report, and does not remove copies already cloned or cached by GitHub
  (cached views and unreachable objects can be purged only through GitHub Support). Because no fork exists today, the practical exposure
  is the public clone URL itself. **No history rewrite was performed or prepared.**
- **Options for the author** (each also needs the paper's "openly redistributable" wording in §8 changed if it stays as written,
  since it is not supported for Elliptic++ or Rodwald):
  1. *Confirm and keep*: ask the Elliptic++ and Rodwald authors (and ransomwhe.re) in writing; record each answer here.
  2. *Untrack going forward only* (`git rm --cached`, commit): stops new distribution; history still serves the old files.
  3. *Untrack and rewrite history* (filter-repo + force-push): removes them from the default branch history; consequences above.
  4. *Replace with a synthetic sample*: keeps demos and tests working without any third-party record; the corpus-dependent tests
     then skip exactly as they do in the release.

## Attribution

If the bundle is redistributed, keep with it: the MIT notice for GraphSense
TagPack (© Iknaio Cryptoasset Analytics GmbH; © AIT Austrian Institute of
Technology), the CC BY 4.0 attributions for Schnöring et al. and Ransomwhere,
and the citations in the table above.
