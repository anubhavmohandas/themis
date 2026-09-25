# Final dataset selection report

Written for: the THEMIS author, to decide whether the selection is defensible and to stop future sessions repeating this search.

**Selected: Forta Foundation `labelled-datasets`, file `labels/1/etherscan_malicious_labels.csv`** (Ethereum mainnet, 7,780 rows).

Two things to read before anything else:

1. **The seven-source reference corpus is Bitcoin-only; this dataset is Ethereum.** Reference overlap is therefore 0 of 7,259 addresses by construction. That is not evidence of independence, and it also means THEMIS's cross-source layer (agreement, conflicts, shared provenance) could not be exercised on this dataset. What it does exercise is ingestion, chain handling, identifier validity, taxonomy interpretation, provenance gating and internal consistency.
2. **80.33% of its addresses (5,831 / 7,259) also appear in MBAL**, a dataset THEMIS already processed on 2026-09-24. MBAL is not one of the seven reference sources, and Forta the dataset (name, file, URL, hash, schema, author) was never used. But this is address-level prior exposure, and MBAL's `external` labels probably inherit from Etherscan-derived lists (not confirmed). The author should decide whether that disqualifies it as "unseen".

## 1. Search

Nothing in the seven paper sources, MBAL or BitcoinHeist was eligible (hard exclusions 1-2). Candidates came from the prior session's trail (below), from a web search this session, and from papers already in `~/Downloads`.

## 2. Rejection trail (so it is not repeated)

| candidate | reason rejected |
|---|---|
| **HackForums illicit-address dataset** (Amadou, Legout, Fouad, Avrachenkov, Motii; arXiv:2608.13930, 14 Aug 2026; `github.com/osteoner/Hackforums-dataset`) | Best methodological fit (own extraction from CrimeBB, LLM screen plus expert verification, 2,438 addresses, 12 categories, temporal metadata). **But the repository contains only `README.md`.** Verified through the GitHub tree API: one branch, no tags, no releases, no forks, two commits (2026-07-31), README still says "TODO" for structure and licence. No data file exists to freeze. Worth re-checking if the authors publish it. |
| Schnoering, Zenodo 10.5281/zenodo.22239038 (CC BY 4.0, 1 Sep 2026) | Same author as a bundled reference source (`schnoering`); the page does not name its upstream label sources; the 2.5 GB payload is graph parquet, not an attribution table. Independence unresolved, schema unsuitable. |
| ImMike/crypto-wallet-address-labels (MIT) | An aggregator whose own README lists Elliptic (a reference source) and Forta as inputs. Derived. |
| dawsbot/eth-labels | Already processed by THEMIS on 2026-09-18 (`external_data/README.md`, `HARDENING_LOG.md`). Exclusion 3. |
| ScamSniffer scam-database (GPL-3.0) | One class only (phishing); live, refreshed daily with a 7-day delay, so it is a moving target with no version to pin; README documents no schema. Not downloaded. Ranked below Forta. |
| Cryptocurrency Exchange Scams dataset (`cryptoexchangescam.github.io`) | 182 addresses, no licence stated. Too small. |
| Giveaway scams (NDSS'23, `double-and-nothing.github.io`) | The site content returned nothing about files, fields or licence; no data file was verified. Not pursued. |
| Maru92/EntityAddressBitcoin | Repository holds only a README; the data is not in it. Not pursued. |
| Leng et al. 2026 (Blockchain: R&A, doi 10.1016/j.bcra.2026.100486) | Not examined for a released dataset (a method paper). Not pursued. |
| Prior session: Real-CATS, OFAC SDN, UK FCDO list, Kaggle vagifa / hamishhall, CryptoScamDB, IEEE DataPort BTC transactions, "Clean Up the Mess" | See `project_bitcoinheist_closure_and_final_dataset_search` memory; Real-CATS and OFAC derived from reference sources, FCDO has only 3 crypto addresses, the rest lack labels, licence or a download. |

"Not pursued" means not examined in depth, not proven unsuitable.

## 3. Proof it is unseen

Terms searched: `forta`, `labelled-datasets`, `luabase`, `banned_address`, `wallet_tag`, the three `data_source` strings, the file name, the commit prefix `40a9c2f2bd`, the file SHA-256, `Wakabayashi`, `Fake_Phishing`, `phish-hack`, `github.com/forta`. Methods: `git grep` on the working tree, `git grep` across all 108 revisions, `git log -S` and `-G`, and a grep of every sibling evidence and test-data directory outside the repository (md, txt, json, py, csv, log, mjs, yml, html).

Result: **0 hits everywhere** apart from this session's own artifacts. Raw output: `forta_evidence/unseen_proof.txt`, `forta_evidence/unseen_proof_outside_repo.txt`.

Status: **PREVIOUSLY UNUSED (as a dataset).** Caveat: address-level overlap with MBAL, section 5.

`etherscan` also appears in none of the seven source registries or any config file.

## 4. Identity

| item | value |
|---|---|
| authoritative page | https://github.com/forta-network/labelled-datasets |
| paper / DOI | none |
| pinned commit | `40a9c2f2bd7e9ddfdd0f3540db589f0288e1e88a`, the repository's HEAD and last commit (2023-01-26 23:42 UTC) |
| file | `labels/1/etherscan_malicious_labels.csv`, added in that one commit ("Add Ethereum Exploiter addresses") |
| size / rows | 678,922 bytes; 7,780 logical rows, 7,781 lines with header |
| SHA-256 | `9a787753c7caf64d506de755830ac85d05f21973939763251f54c38136505f42` |
| format | UTF-8, no BOM, LF, comma, 3 columns `banned_address, wallet_tag, data_source` |
| licence | MIT, "Copyright (c) 2022 Forta Foundation" (repo `LICENSE`, SHA-256 `c834dbf0…c6bb`) |
| stated upstream | README: Luabase `ethereum.tags` table, addresses carrying Etherscan labels `exploit`, `heist`, `phish-hack` |

**Publicly available:** yes. **Research-usable:** yes, under MIT. **Redistributable: unresolved.** MIT covers Forta's repository; the underlying Etherscan labels have their own terms that neither the repository nor its README addresses. The file was downloaded to `final_dataset_testdata/forta/` outside the repository and is not committed. The README documents this file only by a one-line description; it never names the three columns.

## 5. Independence screen

| measure | result |
|---|---|
| candidate addresses (case-folded) | 7,259 (7,780 rows) |
| overlap with the bundled reference sample (228,775 addresses) | **0 (0.00%)**; by source: schnoering 0, rodwald_mixers 0, rodwald_ransom 0, tagpack 0, ellipticpp 0, ransomwhere 0, watchyourback 0 |
| why | the reference sample holds 225,286 Base58, 3,478 bech32, 11 other, **0 EVM-shaped** addresses. The overlap cannot be non-zero |
| declared upstream vs the seven sources' declared dependencies | Luabase / Etherscan; none of the registries names either |
| supplementary, MBAL (not a reference source) | **5,831 / 7,259 = 80.33%**, all `ethereum_mainnet`; by MBAL source class 5,091 `external`, 737 `ground_truth`, 3 `heuristic`; MBAL categories `phishing` 4,674, `scam` 1,167 |
| supplementary, dawsbot eth-labels | 10 / 7,259 = 0.14% |

Verdicts:

- against the seven-source reference corpus: **UNRESOLVED by measurement** (zero overlap is structural); **plausibly independent on declared provenance** (no shared declared upstream);
- against MBAL: **MATERIAL OVERLAP, dependency suspected** (direction MBAL ← Etherscan-derived lists is plausible, not established);
- against dawsbot: low overlap.

## 6. Selection

Qualitative ranking of what was actually retrievable: HackForums would rank first but has no data. Of the retrievable candidates:

- **Forta etherscan_malicious_labels**: real, public, pinned to an immutable commit, MIT, an explicit `data_source` column, a real duplicate/case-variant structure, non-trivial size, documented upstream. Weaknesses: one platform's labels (Etherscan) as the single origin, three coarse classes, 0.14% to 80% overlap with previously processed data, and no schema documentation.
- ScamSniffer: one class, unpinned, no schema.
- The small sets (exchange scams, FCDO): too small to exercise anything.

Selected: **Forta `labels/1/etherscan_malicious_labels.csv`**. The other two Forta files (`phishing_scams.csv`, `malicious_smart_contracts.csv`) overlap it heavily (6,191 and 585 shared addresses) and were not used.
