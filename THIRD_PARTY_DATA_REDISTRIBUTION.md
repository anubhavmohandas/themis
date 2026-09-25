# Third-party data redistribution: investigation and decision record

Date of evidence: **2026-09-24**. Scope: the five files tracked under `demo_data/` in the public
repository `github.com/anubhavmohandas/themis`. Investigation only: nothing was removed, rewritten,
re-licensed or changed (no code, paper, taxonomy, corpus or history edits).

**This is not a legal conclusion.** `UNCONFIRMED` means "no redistribution permission for this exact
artifact was found in the places listed". The conservative release policy in §8 is a policy under
uncertainty, not a finding that anything is unlawful. The decision between Options A/B/C (§7) is the
author's and has not been made.

Supersedes, where they differ: the percentages in the first half of `THIRD_PARTY_DATA.md` (which
predate the Ransomwhere downgrade; corrected figure in §3) and the note there that ransomwhe.re is
client-rendered (it is server-rendered; its text was read, §2.4).

---

## 1. What is redistributed (Phase 1)

Tracked under `demo_data/` (all in `HEAD` = `30ffd0b` = `origin/main`):

| file | bytes | rows | source(s) | fields retained | classification |
|---|---|---|---|---|---|
| `observations_sample.csv.gz` | 6,738,666 | 268,891 | all seven corpus sources (Elliptic++ 20,083 and TagPack 25,362 are seeded samples; the other five are complete: Schnöring 103,812, Rodwald ransomware 50,322, Rodwald mixers 57,817, Ransomwhere 11,186, WatchYourBack 309) | `address`, `source`, `raw_label`, `canon`, `polarity`, `prov_family`, `lastmod`, `heuristic`, `subcat` | **NORMALIZED DATA** (record-level; a filtered sample for two sources) |
| `revenue.csv.gz` | 1,920,979 | 61,508 (Rodwald ransomware 50,322 + Ransomwhere 11,186) | Rodwald `BTC_Ransom.csv`, Ransomwhere export | `address`, `dataset`, `usd`, `family`, `src_letters` | **DERIVED DATA** (per-address USD totals, i.e. aggregated from the source's amount columns) |
| `verified_anchors.txt.gz` | 3,669,612 | 146,243 bare addresses (1,625 `0x…`, 144,618 other) | TagPack `confidence: forensic` ∪ WatchYourBack ransomware addresses | address only | **DERIVED DATA** (a selection; no labels, no attribution in the file) |
| `ground_truth.csv` | 24,657 | 289 (OFAC 185, WatchYourBack 104) | OFAC SDN list; WatchYourBack `btc_resolv.csv` | `address`, `ground_truth_label`, `ground_truth_source`, `ground_truth_evidence_type`, `ground_truth_date`, `ground_truth_independent`, `notes` | **DERIVED DATA** (curated selection, labels mapped to THEMIS categories) |
| `manifest.json` | 3,191 | n/a | none (counts and shares) | counts only | **AGGREGATED DATA**; contains no address or record |

None of the five is **VERBATIM DATA** (no source file is copied whole) and **none is SYNTHETIC**:
every row is a real upstream record, filtered or normalized. `examples/*.csv` are the only synthetic
files and are not under `demo_data/`.

Per-property answers for `observations_sample.csv.gz` (the only file with per-claim rows from all
sources):

| property | answer |
|---|---|
| records copied directly | yes for `address`, `raw_label` (the source's own label string, e.g. `HelixMixer`, `INDIVIDUAL`), and `lastmod` (TagPack, Ransomwhere: the source's own date) |
| records transformed | yes: one row per (address, label, source) claim; sources re-shaped into one schema; Elliptic++ class code 1/2/3 stored as a raw label; TagPack and Elliptic++ sampled |
| labels transformed | yes: `canon`, `polarity`, `subcat`, `heuristic` are THEMIS-assigned; `raw_label` is the untouched source label |
| addresses preserved | yes, verbatim (incl. 25,362 TagPack claims over 17,806 addresses) |
| source attribution preserved | partly: the `source` and `prov_family` columns name the dataset and its originating root (e.g. `rodwald:S`, `schnoering:BitcoinTalk`, `tagpack:Talos Cisco`); the file carries **no** licence text, citation, URL or copyright notice. Those live in `THIRD_PARTY_DATA.md`, which is not inside `demo_data/` |
| fields dropped | Elliptic++ and Rodwald feature columns, transaction graphs, TagPack URLs/confidence, WatchYourBack URL/ticker/subtype, Ransomwhere transaction lists |

Per source, rows in `observations_sample.csv.gz` (sum 268,891):

| source | rows | addresses | share of sample rows |
|---|---|---|---|
| Schnöring | 103,812 | 101,387 | 38.61% |
| TagPack (sampled) | 25,362 | 17,806 | 9.43% |
| Elliptic++ (sampled) | 20,083 | 20,083 | 7.47% |
| Rodwald mixers | 57,817 | 57,817 | 21.50% |
| Rodwald ransomware | 50,322 | 50,322 | 18.71% |
| Ransomwhere | 11,186 | 11,186 | 4.16% |
| WatchYourBack | 309 | 309 | 0.11% |

Rows from sources with no confirmed permission: **139,717 of 268,891 (51.96%)**.

Mixing: every file except `manifest.json` mixes confirmed and unconfirmed sources in one blob, so any
file-level action (keep, delete, rewrite) is all-or-nothing unless the files are first rebuilt per source.

Inventory of who is in what (checked by set arithmetic on the tracked files):
`ground_truth.csv` = 185 OFAC (0 of them appear among WatchYourBack claims) + 104 WatchYourBack
(103 of them present in the WatchYourBack claims; the 104th, `1E6qZkzb…`, label `sextortion`, is not among
the sample's WatchYourBack claims; why was not investigated). `verified_anchors.txt.gz` shares 44 addresses with the WatchYourBack claims; the rest of the
146,243 follows the TagPack `forensic` half.

---

## 2. Source-by-source evidence (Phase 2)

The corpus has **seven** sources (`demo_data/manifest.json` `per_source`): Elliptic++, Schnöring,
Rodwald ransomware, Rodwald mixers, Ransomwhere, GraphSense TagPack, WatchYourBack. The "seventh"
source not named in the task brief is **Schnöring et al.** OFAC is **not** a corpus source: it appears only in
`ground_truth.csv` (185 rows) and as the root of 71 re-rooted WatchYourBack records, so it is an eighth
row below. Rodwald is two artifacts, treated separately.

Evidence tier used: (1) licence file / structured licence field; (2) dataset README; (3) site terms;
(4) publisher metadata; (5) author statement. Software licences were **not** used as data licences.

### 2.1 GraphSense TagPack
* **Artifact used.** git clone of `github.com/graphsense/graphsense-tagpacks`, retrieved 2026-09-20,
  branch tip `7f9a5d1f93435379cfaed4675fb734fa42848ca5` (2026-09-11); THEMIS input hash (86 files)
  `33cc3d04…8ce2` in `expected_output/retained_table_build_manifest.json`.
* **Licence.** `LICENSE` in the repository root (re-fetched 2026-09-24,
  `https://raw.githubusercontent.com/graphsense/graphsense-tagpacks/master/LICENSE`): "MIT License /
  Copyright (c) 2022 Iknaio Cryptoasset Analytics GmbH / Copyright (c) 2018-2022 AIT Austrian Institute of
  Technology". GitHub API `license.spdx_id = MIT`.
* **Does it cover the data?** The repository *is* the tag data (`packs/`, `actors/`); the README describes
  it as "a curated collection of TagPacks … collected from public sources either by the GraphSense core team
  or by other contributors" and requires each tag to cite a public source and contain no PII. This is a
  data repository, so the MIT licence is on the data itself, not on separate software.
* **Residual.** No per-pack `license:` field exists in any pack (`grep` over `packs/`, `actors/`: none).
  Packs list third-party creators (`Talos Cisco`, `INTERPOL CNTL`, `Paquet-Clouston et al.`,
  `Beaunard Grobler`, `github user 3xp0rt`, `EtherScanDB Team`, `Matteo Romiti`, `CSH CryptoFinance
  Team`); the repository's licence is the only statement, and those creators' own rights are not
  separately stated.

### 2.2 Schnöring et al. (the seventh corpus source)
* **Artifact used.** `addresses.csv` (6,911,449 bytes, sha256 `a451de6d…a283`), figshare
  `10.6084/m9.figshare.26305093.v3` ("BitcoinTemporalGraph"), retrieved 2026-09-20. Columns:
  `address, entity, category, source`.
* **Licence.** figshare API `https://api.figshare.com/v2/articles/26305093/versions/3` (2026-09-24):
  `license = {name: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/"}`, version 3,
  published 2025-02-05, files `dataset.tar.gz` and `addresses.csv` (6,911,449 bytes: the same size as
  THEMIS's copy). The licence is a field of the exact record and version that hosts the exact file.
* **Residual.** The dataset compiles labels from BitcoinTalk, Montréal (Paquet-Clouston et al.), Padua
  (Conti et al.), Princeton (Huang et al.) and others; CC BY 4.0 is the compilers' grant. Whether each
  original source permitted that grant was not investigated here.

### 2.3 Elliptic++
* **Artifact used.** `wallets_classes.csv` (`address,class`; 30,421,134 bytes, sha256 `4e5132c9…02f9`) from
  the authors' Google Drive folder that the README links
  (`drive.google.com/drive/folders/1MRPXz79Lu_JGLlJ21MDfML44dKN9R08l`), retrieved 2026-09-20. THEMIS
  uses 822,937 addresses, 53.24% of all corpus claims.
* **Evidence searched, all negative for a licence:**
  * GitHub API `license: null`; repository contents are `.gitattributes`, `Actors Dataset/`,
    `Transactions Dataset/`, `README.md`, `images/`. **No LICENSE file** anywhere in the tree (including the two
    dataset sub-directories, which hold only READMEs, notebooks and edge-list stubs).
  * README (153 lines, searched for licence/terms/permission/cite/Drive): says only "If you use our dataset in
    your work, please cite our paper" and "If you … create something with this dataset, please let us
    know by email: yelmougy3@gatech.edu". Points to the Drive folder for the data.
  * Issue #4, "Questions about if this dataset is legal" (2024-05-07, closed): a user asked whether it is
    legal to use and cite. The reply, from account `ll72`: "Yes the paper is published in ACM sigkdd 2023.
    You can cite it." This concerns citation/use, not redistribution, and is a forum reply, not a licence.
  * Paper (arXiv 2306.06108, full text searched for licence/permission/terms/redistribut*/ethic*): "The Elliptic++ dataset and its tutorials
    are made publicly available at https://www.github.com/git-disl/EllipticPlusPlus". The only permission
    boilerplate is ACM's, about the *paper* ("Permission to make digital or hard copies … Publication rights
    licensed to ACM"). Crossref lists the ACM copyright-policy licence for the paper only.
  * Google Drive folder page (fetched 2026-09-24, title "Elliptic++ Dataset – Google Drive"): the listing is
    rendered by JavaScript, so **its file listing could not be enumerated**; whether a licence file sits in the
    folder is not established. Only the README and repository were checked.
* **Not substituted.** The base Elliptic dataset is reported, by a search-result summary of its Kaggle page
  (`kaggle.com/datasets/ellipticco/elliptic-data-set`; the page itself did not render for the fetcher), to be
  CC BY-NC-ND 4.0. Nothing found states that this applies to Elliptic++ and it is **not** used as
  Elliptic++'s licence. It is recorded because, if it did apply, "NC" and "ND" would restrict exactly what
  `observations_sample.csv.gz` does.

### 2.4 Ransomwhere
* **Artifact used.** The live export `https://api.ransomwhe.re/export`, retrieved 2026-09-20 (5,575,290
  bytes, sha256 `c249b94f…8959`; `ransomwhere.json`), 11,186 records over 11,186 addresses.
* **What carries a licence.** Zenodo `10.5281/zenodo.13999026`, "Ransomwhere: A Crowdsourced Ransomware
  Payment Dataset", v1.1.0 (2024-10-27), creator Cable, Jack; Zenodo API `metadata.license.id = cc-by-4.0`,
  `access_right: open`, one file `ransomwhere.json` (5,572,091 bytes, `md5:8a7bff74…d40f`). All three
  Zenodo versions (1.0.0 2022-05-02, 1.0.1 2022-09-18, 1.1.0 2024-10-27) carry `cc-by-4.0`; concept DOI
  `10.5281/zenodo.6512122`.
* **Is the licensed artifact the artifact THEMIS used? Measured, not assumed.** I downloaded the Zenodo
  file (md5 equals the Zenodo record's checksum) and compared it record by record with THEMIS's retained live
  export:

  | comparison | count |
  |---|---|
  | records in Zenodo v1.1.0 | 11,178 |
  | records in the live export THEMIS used | 11,186 |
  | in the live export, absent from Zenodo | **8** (all family `Akira`, created 2024-10-29, two days after the deposit) |
  | in Zenodo, absent from the live export | 0 |
  | shared addresses whose `address`, `family`, `updatedAt`, transaction hash/time/amount are identical | 11,178 of 11,178 |
  | shared addresses whose `transactions[].amountUSD` and `balanceUSD` differ (USD re-priced after 2024-10-27) | **2,229** (19.9%) |
  | shared records byte-identical in every field | 8,949 |

  So the live export is a **later and partly modified artifact**: a superset by 8 records, and with different
  USD values for 2,229 records. The observation rows (address, family, date) of 11,178 addresses are
  field-identical to the CC BY deposit; `revenue.csv.gz`'s USD values for those 2,229 addresses, and the 8 Akira
  rows, are **not** in the licensed artifact.
* **Site terms.** `https://ransomwhe.re` (HTTP 200, 15,141 bytes; server-rendered). Text read: contains no
  licence, copyright or terms text (checked for those words: none). It says "All Ransomwhere data is entirely
  publicly available", describes the API ("The most basic endpoint is https://api.ransomwhe.re/export"), and
  asks citers to use "Cable, Jack. (2024). Ransomwhere: A Crowdsourced Ransomware Payment Dataset (1.1.0) [Data
  set]. Zenodo. https://doi.org/10.5281/zenodo.6512122". That is the strongest pointer that the site's data and the
  Zenodo deposit are the same dataset. It is a citation instruction, not a licence statement for the live export,
  and "publicly available" is not a permission. It also states that unlabeled payments "are sourced from *Showing the
  Receipts: Understanding the Modern Ransomware Ecosystem*", i.e. part of the data is itself third-party-sourced.
* **Live API today.** `GET https://api.ransomwhe.re/export` returned HTTP 502 on 2026-09-24 (also 2026-09-19).
* **Software repository.** `github.com/cablej/ransomwhere` is MIT (site code: `backend/`, `docs/`); not a data licence
  and not used as one.

### 2.5 Rodwald (two artifacts)
* **Artifacts used.** `BTC_Ransom.csv` (10,634,799 bytes, sha256 `667b5ac6…a603`, server
  `last-modified: Mon, 26 Feb 2024`) and `BTC_Mixers.csv` (15,713,849 bytes, sha256 `f4baae03…e561`), both from
  `https://sydeus.rodwald.pl/datasets/`, retrieved 2026-09-20. THEMIS uses 50,322 and 57,817 rows (7.00% of
  corpus claims together) plus the 50,322 revenue rows.
* **Licence evidence.** The page is 4,973 bytes of HTML (fetched 2026-09-24). Searched for licen*/terms/copyright/CC/creative: **0 matches**.
  It lists author "Przemyslaw Rodwald", creation/update dates, download links and a column legend. The legend
  marks each feature by origin: `[W] walletexplorer.com, [B] blockchain.info, [C] calculated`, so the files
  themselves embed data from two further third parties (the `LAB_CLU_WAL`/`NAM_CLU_WAL` cluster labels come
  from walletexplorer.com). The mixers article is listed as "Springer link soon".
* **Paper.** DepCoS-RELCOMEX 2024 chapter `10.1007/978-3-031-61857-4_22`, "Preparing a Dataset of Ransomware BTC
  Addresses for Machine Learning Purpose" (Springer Nature). Crossref licence metadata is Springer's text-and-
  data-mining terms for the *chapter*; the chapter is paywalled and its page redirects to a login. The
  2025 (mixers) article has no link yet. Neither can be read as a data licence.

### 2.6 WatchYourBack
* **Artifact used.** `data/tagging/btc_resolv.csv` (46,236 bytes, sha256 `8c65f5d1…a9c3`), from
  `github.com/cybersec-code/watchyourback`, retrieved 2026-09-20 (309 lines). Re-fetched 2026-09-24:
  byte-identical (same sha256).
* **Licence found.** `LICENCE` at the root: "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007"; GitHub
  `spdx_id = GPL-3.0`. This is the licence of the repository, which is a *software* project.
* **Does it reach the data? Not established.** README (212 lines, searched for licence/terms/GPL/cite and
  its Tags section read) documents setup, tags format ("CSV file, no
  headers, no index, with six columns: address, ticker, category, tag, subtype, and url"), paths, oracles and the
  exchange classifier. It contains no statement about the data. What the file itself shows:
  * every row carries a source URL; the 309 rows cite **30 distinct hosts** (home.treasury.gov 82,
    bitcointalk.org 41, cryptoscamdb.org 28, research.checkpoint.com 24, ransomwhe.re 20, treasury.gov 20,
    assetforfeiturelaw.us 18, bleepingcomputer.com 17, walletexplorer.com 13, crystalblockchain.com 12, …);
  * `data/tagging/` also holds sub-directories of imported third-party tag sets
    (`graphsense-tagpacks/`, `tracking-ransomware-end-to-end/`, `bitcoinabuse/`, `blockchain_info/`, …).
  So the tags are a compilation of facts curated from other parties' publications. A repository-wide GPL notice
  does not say whether the compilers of `btc_resolv.csv` intended GPL to govern this file, nor can it license
  what other parties published.
* **Consequence recorded, not decided.** If GPL-3.0 were held to govern the data, redistribution would carry
  share-alike terms; that is a question about the author's future software licence too.

### 2.7 OFAC SDN list (eighth row: ground truth only)
* **Artifact used.** `https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml` (HTTP 200,
  fetched 2026-09-18; header re-read 2026-09-24), 185 addresses in `ground_truth.csv`.
* **Basis.** Statutory: 17 U.S.C. § 105(a): "Copyright protection under this title is not available for any
  work of the United States Government …" (fetched from law.cornell.edu 2026-09-24). No OFAC page states a data
  licence or terms of use (the Sanctions List Service page and FAQ topic 1501 were read: no terms text). The
  status below rests on the statute alone.
* **Residual.** The `ground_truth_label` categories ("darknet market", "mixer", "exchange") are THEMIS's
  mapping of SDN entries; the SDN facts are government works, THEMIS's mapping is the author's.

---

## 3. Redistribution matrix (Phase 3)

`Final status` uses only the three permitted values. Percentages are of the 1,545,710 corpus claims
(`demo_data/manifest.json`).

| Source | Exact upstream artifact used by THEMIS | Upstream URL | Licence found | Licence applies to exact artifact? | Raw redistribution allowed? | Derived redistribution allowed? | Modification allowed? | Attribution required? | Share-alike required? | Research-only? | Commercial restriction? | Evidence | Final status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GraphSense TagPack (32.30%) | git clone at `7f9a5d1` (2026-09-11), retrieved 2026-09-20 | github.com/graphsense/graphsense-tagpacks | MIT | Yes: the repository is the data | Yes (MIT) | Yes (MIT) | Yes (MIT) | Yes: keep © Iknaio Cryptoasset Analytics GmbH and © AIT notice | No | No | No | `LICENSE` root file; GitHub `spdx_id: MIT`; no per-pack licence override; creators' own rights not separately stated | **CONFIRMED REDISTRIBUTABLE** |
| Schnöring et al. (6.72%) | `addresses.csv`, figshare v3 (sha256 `a451de6d…`) | doi.org/10.6084/m9.figshare.26305093.v3 | CC BY 4.0 | Yes: figshare record + version + file | Yes | Yes (adaptations) | Yes, with indication of changes | Yes: credit, licence link, indicate changes | No | No | No | figshare API `license` field of v3 (2026-09-24); file size equals THEMIS's copy | **CONFIRMED REDISTRIBUTABLE** |
| Elliptic++ (53.24%) | `wallets_classes.csv` from authors' Google Drive folder (sha256 `4e5132c9…`) | github.com/git-disl/EllipticPlusPlus (data: Drive link in README) | None found | n/a (no licence) | Not stated | Not stated | Not stated | Citation requested, not a licence term | Not stated | Not stated | Not stated | GitHub `license: null`, no LICENSE file, README/paper/issue #4 searched, Drive listing not enumerable; base-Elliptic CC BY-NC-ND 4.0 reported but not shown to apply | **UNCONFIRMED** |
| Rodwald, ransomware (3.26%) | `BTC_Ransom.csv` (sha256 `667b5ac6…`) | sydeus.rodwald.pl/datasets/ | None found | n/a | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | 4,973-byte page, 0 licence/terms/copyright tokens; paper is Springer-paywalled (Crossref licence is the publisher's TDM terms for the chapter); file also embeds walletexplorer.com and blockchain.info data | **UNCONFIRMED** |
| Rodwald, mixers (3.74%) | `BTC_Mixers.csv` (sha256 `f4baae03…`) | sydeus.rodwald.pl/datasets/ | None found | n/a | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | same page; article "soon", no publication to read | **UNCONFIRMED** |
| Ransomwhere (0.72%) | live export `api.ransomwhe.re/export`, 2026-09-20 (sha256 `c249b94f…`) | ransomwhe.re; doi.org/10.5281/zenodo.13999026 | CC BY 4.0 on the Zenodo deposit v1.1.0 only | **No / not shown.** Live export differs from the deposit: +8 records, 2,229 records with different USD values; 11,178 addresses' observation fields are identical | For the Zenodo deposit: yes. For the live export: not stated | Same split | Zenodo: yes; live: not stated | Zenodo: yes (credit, licence link, changes) | No | No | No | Zenodo API `cc-by-4.0`; site has no licence text ("entirely publicly available" is not a licence); site cites the Zenodo concept DOI; live API HTTP 502 | **UNCONFIRMED** |
| WatchYourBack (0.02%) | `data/tagging/btc_resolv.csv` (sha256 `8c65f5d1…`) | github.com/cybersec-code/watchyourback | GPL-3.0 for the repository (software) | **Not shown** to apply to the data file | GPL text permits conveying; not shown to govern this data | Not shown | Not shown | GPL notices, if it applies | **Yes, if GPL applies to the data** | No | No (GPL permits commercial use) | `LICENCE` (GPL v3 text) at root; README silent on data; file is a compilation of 30 third-party URL hosts | **UNCONFIRMED** |
| OFAC SDN list (0%; ground truth only) | `sdn_advanced.xml`, fetched 2026-09-18 | treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml | None (US Government work; no data licence published) | Statutory, not a licence: 17 U.S.C. § 105(a) | Yes (no copyright subsists) | Yes | Yes | No | No | No | No | statute text quoted; OFAC pages state no terms | **CONFIRMED REDISTRIBUTABLE** (statutory basis only) |

Shares: confirmed sources (TagPack 32.30 + Schnöring 6.72) = **39.02%** of corpus claims; unconfirmed sources
(Elliptic++ 53.24 + Rodwald 7.00 + Ransomwhere 0.72 + WatchYourBack 0.02) = **60.98%**. The older `THIRD_PARTY_DATA.md`
figures (39.74% / 60.24%) counted Ransomwhere as confirmed and are superseded. In the *bundled sample* the split is 48.04% /
51.96% of 268,891 rows (§1).

---

## 4. The four named blockers (Phase 4)

1. **Elliptic++: `UNCONFIRMED`.** No licence exists for the exact Elliptic++ artifact in the repository, README,
   paper, or issue tracker. Paper-access terms (ACM), code licence (none) and the base Elliptic licence were
   **not** substituted. One open item could change this: the Drive folder's own contents were not listable.
2. **Rodwald: `UNCONFIRMED`.** Exact artifacts identified (`BTC_Ransom.csv` last modified 2024-02-26;
   `BTC_Mixers.csv`, created 2025-01-22 / updated 2025-01-31, both on the author's site). The paper is
   downloadable only behind Springer access, the dataset page carries no terms.
3. **Ransomwhere: `UNCONFIRMED`.** The CC BY 4.0 licence explicitly covers the Zenodo deposit v1.1.0. The
   live export THEMIS used is a different artifact: it has 8 extra records and USD values that differ in 2,229
   records, and the site states no licence. The Zenodo licence is **not** transferred. The measured relationship
   (11,178 addresses' observation fields identical) is recorded as a fact, and is the basis of the narrower
   option in §8, not of a status change.
4. **WatchYourBack: `UNCONFIRMED`.** Software licence (GPL-3.0, repository) and data licence (none stated for
   `btc_resolv.csv`) are kept apart; the file's rows point to 30 other publishers.

---

## 5. Can public THEMIS stay reproducible without the rows? (Phase 5)

Tooling that exists today and does not carry rows: `scripts/build_corpus.py` (downloads nothing; adapters for
all seven sources; every source optional), `REPRODUCE.md` (commands and per-source rebuild results),
`expected_output/retained_table_build_manifest.json` (SHA-256 and byte size of each exact input file, adapter
versions, per-source counts), `demo_data/manifest.json` (aggregates), `expected_output/*` (aggregate results),
synthetic `examples/*.csv`, and the release ZIP builder, which already excludes `demo_data/`. Without the rows,
`themis reproduce-paper` reports `BLOCKED` (20 PASS / 0 FAIL / 9 NOT_REPRODUCED) and 135 tests skip with a
stated reason; with a reviewer-rebuilt corpus the retained-table regression is `PASS` (29/29).

| Source | Fetch route | Checksum on file | Build/normalise code | Can be reproduced without redistributing rows? | What is lost / risk |
|---|---|---|---|---|---|
| Elliptic++ | README's Google Drive link | yes: sha256 `4e5132c9…`, 30,421,134 bytes | yes (`build_corpus.py`, 822,942 → 822,937 claims, 5 dropped rows counted) | **Yes** | Google Drive is not an archival host. The bundled 20,083-row sample is a seeded sample and only exists if the file is fetched; a clean checkout has no demo rows for 53.24% of claims |
| Rodwald ransomware / mixers | direct `https://sydeus.rodwald.pl/datasets/BTC_*.csv` (HTTP 200 today) | yes: two sha256 | yes (50,322 / 57,817 rows and the 50,322 revenue rows rebuild byte-identical) | **Yes** | single personal-site host; the files have no versioned URL |
| Ransomwhere | `https://api.ransomwhe.re/export` (HTTP 502 today and on 2026-09-19) | yes: sha256 `c249b94f…` | yes | **Partly.** A reviewer can fetch a live export, but it is a moving target: by the measurement above the export changed after 2024-10-27 in 2,229 records' USD values and gained rows, so a later fetch need not hash to the recorded file. The only stable, licence-clean copy is Zenodo v1.1.0, which lacks 8 records and has different USD values, so revenue-based results (drift Tables) would differ. **Not measured here** | Reproducing the paper's revenue figures needs the specific 2026-09-20 file, which cannot be shipped without confirmation |
| WatchYourBack | `raw.githubusercontent.com/cybersec-code/watchyourback/main/data/tagging/btc_resolv.csv` | yes: sha256 `8c65f5d1…` | yes (309 rows identical) | **Yes** for the corpus rows. The 104 WatchYourBack rows of `ground_truth.csv` and the ≤44 WatchYourBack addresses in the anchor set have **no script** that regenerates them; `ground_truth.csv` is not produced by any script in the repository | needs a small generator for the WatchYourBack ground-truth subset (not written; out of scope) |
| Rodwald + Ransomwhere revenue | as above | as above | yes | same answers as their sources | `revenue.csv.gz` would have to be rebuilt by the reviewer |

Aggregate statistics, expected-output hashes and synthetic fixtures are already tracked and remain safe to keep
because they contain counts and derived numbers, not third-party rows (one exception judged incidental:
`expected_output/explain_14BW….txt`, one address and its labels).

---

## 6. Git history impact (Phase 6)

State: repository public since 2026-09-16T23:11:05Z; on 2026-09-24 GitHub reported `private:false`, 0 forks, 0
stars, 0 watchers; branches: `main` only; `HEAD = origin/main = 30ffd0b` (all 92 commits are on GitHub; an older
note that HEAD was unpushed is out of date). Tags `v1.0-paper`, `v1.0-paper-rc1`, `v1.0-paper-rc2` exist **locally
only** (`git ls-remote --tags origin` is empty).

`demo_data/` was added in the first commit `b47da84` (2026-09-17) and is present in **all 92 commits**. It was
modified in 6 commits: `b47da84`, `627fa53`, `95ff42f`, `5736bea`, `57e2cc5`, `6245e0c`.

| file | blob versions | blob (first 12) | commits containing it | first → last commit |
|---|---|---|---|---|
| `observations_sample.csv.gz` | 1 | `dc0788a44980` | 92 | `b47da84` → `30ffd0b` |
| `verified_anchors.txt.gz` | 1 | `316774267fd8` | 92 | `b47da84` → `30ffd0b` |
| `revenue.csv.gz` | 2 | `ebc5577d9962` (rounded USD) | 60 | `b47da84` → `0eeeb25` |
| | | `25d2547a78b9` (full precision) | 32 | `6245e0c` → `30ffd0b` |
| `ground_truth.csv` | 2 | `4e9c078feade` | 39 | `b47da84` → `4aca414` |
| | | `045d6ca277bf` | 53 | `95ff42f` → `30ffd0b` |
| `manifest.json` (aggregates only) | 4 | `fa7dcf67b8f7` / `a3982bc89d24` / `52770cab8f24` / `6fac8b8f0363` | 37 / 3 / 4 / 48 | `b47da84` → `30ffd0b` |

Total **10 blob versions**, of which **6 carry third-party records** (the 4 `manifest.json` versions are counts).
Method: for each commit in `git rev-list HEAD`, `git rev-parse <commit>:<path>` gives the blob present in that commit;
grouping by blob id gives the commit counts above.

**Does deletion alone remove public accessibility? No.** Git is a content-addressed object store; a commit points
to a tree, the tree to blobs. `git rm` + commit creates a *new* commit whose tree lacks the path; every earlier
commit still points to the old blob, and GitHub serves any commit reachable from a ref: `git clone` fetches all of
history, and `git show b47da84:demo_data/observations_sample.csv.gz` (or the web URL for that SHA) works after the
deletion. Only the working tree at `HEAD` changes.

**What actual historical removal requires** (not run, not prepared; `git-filter-repo` and `bfg` are not installed on this machine):
1. Rewrite every commit that contains the path: `git filter-repo --path demo_data --invert-paths` (or a
   file-level equivalent such as `--path` of the specific files, or BFG). Because the files exist from the first
   commit, **all 92 commit hashes change**; the tags `v1.0-paper*` and the release-ZIP hashes recorded in
   `REPRODUCE.md` and the report then refer to commits that no longer exist and must be re-cut.
2. Force-push the rewritten `main` (`git push --force`); a pushed-history rewrite is destructive to anyone who
   has cloned.
3. Coordinate: the repository has one author and no forks/stars/watchers as of 2026-09-24, so coordination is
   currently trivial but not knowable for clones made since 2026-09-16.
4. Old objects survive elsewhere: existing clones, any forks made before the rewrite, and GitHub's cached
   objects (commit URLs by SHA can continue to resolve until GitHub garbage-collects; GitHub documents that
   purging cached views/unreferenced objects requires GitHub Support). Rewriting cannot recall data already
   copied.
5. Repair references: README/REPRODUCE/report hashes, the tags, and the commit ids quoted in the reports.

---

## 7. Three release options (Phase 7)

**Option A. Keep the data.** Valid only for sources with confirmed permission, i.e. TagPack, Schnöring, OFAC.
Obligations if kept:
* TagPack (MIT): keep "Copyright (c) 2022 Iknaio Cryptoasset Analytics GmbH / Copyright (c) 2018-2022 AIT Austrian
  Institute of Technology" and the MIT permission notice with the rows; no share-alike.
* Schnöring (CC BY 4.0): credit the authors, link the licence, indicate changes (normalization, category mapping,
  sampling; the CSV's `source` column names the origin but there is no notice in `demo_data/`); no additional restrictions.
* OFAC: no obligation.
* If Ransomwhere were confirmed as CC BY 4.0 for the live export: attribution to Cable, Jack, a licence link, an
  indication of changes. If WatchYourBack's data were confirmed GPL-3.0: share-alike would attach to redistribution
  (the interaction with the still-undecided software licence is the author's question, not this document's).
* **A only fits the current files if they are first rebuilt per source**: today each file mixes confirmed and
  unconfirmed rows, so "keep the confirmed part" means replacing the files with TagPack + Schnöring + OFAC-only
  subsets (new blobs). A does **not** affect the six historical blobs that already contain unconfirmed rows.

**Option B. Remove from the current tree only** (`git rm` and commit).
* New clones' working tree at `HEAD` no longer has the files; the release ZIP (which already excludes them)
  matches.
* Every old commit (all 92) still contains them; the repository history still redistributes those 6 blobs to
  anyone who clones or opens an old SHA. Public-visibility timeline is unchanged: they have been public since
  2026-09-16.
* **Sufficiency per licensing situation** (not decided here):
  * Sources with confirmed permission: no removal was ever needed.
  * Sources UNCONFIRMED: B stops new advertising at `HEAD` but does not stop distribution through history. If
    the concern is that any public copy is a redistribution, B is not sufficient. If the author accepts
    continued historical availability while permission is sought (and would restore the files if granted), B
    is the minimal, reversible step. Which of these applies is a judgment about risk that the evidence does not settle.
  * Copyleft (WatchYourBack, if GPL applies): B does not undo any past conveyance.

**Option C. Remove and rewrite history** (filter-repo/BFG + force-push). Not executed.
* Affected files disappear from all 92 commits; every commit hash changes (the files date from the first
  commit), so the tags, the `v1.0-paper` release hashes and any quoted commit ids must be redone.
* Force-push is required and is destructive; existing clones and any cache keep the old data; GitHub Support
  is the route for cached views.
* Documentation to repair: `REPRODUCE.md`, `THEMIS_RELEASE_READINESS_REPORT.md`, `THIRD_PARTY_DATA.md`, `README.md`
  references to commits/hashes.
* Irreversible for readers who already fetched. Advantage: the public repository stops serving the blobs
  from `main`; cost is small now because `main` is the only branch and there are 0 forks.

---

## 8. Final recommendation matrix (Phase 8)

Conservative release policy under uncertainty (not a legal conclusion): **for every `UNCONFIRMED` source, do
not include the third-party rows in the release until permission is confirmed.**

| Source | Redistribution status | Can remain in public `demo_data/`? | Required obligations | Recommended repository action | Confidence |
|---|---|---|---|---|---|
| GraphSense TagPack | CONFIRMED REDISTRIBUTABLE | Yes | Keep MIT notice (© Iknaio Cryptoasset Analytics GmbH; © AIT) | Keep; add the notice next to the rows | High for the repository licence; medium that no individual pack creator claims different terms |
| Schnöring et al. | CONFIRMED REDISTRIBUTABLE | Yes | CC BY 4.0: credit, licence link, indicate changes | Keep; add the attribution next to the rows | High |
| OFAC SDN | CONFIRMED REDISTRIBUTABLE (statute only) | Yes (185 ground-truth rows) | None | Keep | High that OFAC data are US Government works; the label mapping is THEMIS's own |
| Elliptic++ | UNCONFIRMED | **No: do not include until permission is confirmed** | none until permission; then whatever the authors state | Remove 20,083 sample rows from the tracked bundle (A-rebuild) and decide history (B vs C). Ask the authors (contact in README: yelmougy3@gatech.edu); check the Drive folder for a licence file | High that no public licence exists in the places checked; the Drive folder listing was not readable |
| Rodwald ransomware | UNCONFIRMED | **No: do not include until permission is confirmed** | same | Remove 50,322 observation rows and the 50,322 revenue rows; ask the author (P. Rodwald via the site) | High |
| Rodwald mixers | UNCONFIRMED | **No: do not include until permission is confirmed** | same | Remove 57,817 rows; ask the author | High |
| Ransomwhere | UNCONFIRMED (live export); the Zenodo v1.1.0 subset is CC BY 4.0 | **No for the live-export rows.** Author-only alternative: rebuild the Ransomwhere part from Zenodo v1.1.0 (11,178 addresses, CC BY, attribution to Cable, Jack), which changes the corpus (−8 records, different USD for 2,229) | if confirmed: CC BY 4.0 attribution | Ask the maintainer (Zenodo creator "Cable, Jack") whether the live export is under the same licence; do not change the corpus without an explicit decision | High that the artifacts differ (measured); low on the maintainer's intent |
| WatchYourBack | UNCONFIRMED | **No: do not include until permission is confirmed** (309 observation rows, 104 ground-truth rows, ≤44 anchor addresses) | if GPL governs: share-alike | Remove or regenerate the WatchYourBack parts; ask the repository owners/paper authors (Gómez, Moreno-Sánchez, Caballero) | High that no data licence is stated; medium on how a court/maintainer would read the repo-wide GPL |

**Evidence-based recommendation.** (1) First obtain written answers from the four parties above: a confirmation
makes the removal question moot for that source. (2) Until then the release artifacts already comply with the
conservative policy (the ZIP excludes `demo_data/`). (3) For the public repository, Option B is the minimum that
follows the evidence; if the concern is that history keeps serving unconfirmed rows, only Option C addresses it, and
the exposure is now small (0 forks/stars/watchers, one branch, one author, tags unpushed). The window narrows over time.
(4) If any files are kept, rebuild them per confirmed source (TagPack, Schnöring, OFAC) so the confirmed part can
carry its notices. This is a recommendation to the author, who has not chosen.

---

## 9. Not done, deliberately

No file removed or edited under `demo_data/`; no `git rm`, `filter-repo`, force-push or tag change; no
LICENSE added; no code, paper, taxonomy, provenance-logic or corpus change; WalletClassification not reopened;
the software-licence decision is not started. Retrieval of the Elliptic++ Google Drive listing, the live
Ransomwhere endpoint (HTTP 502) and the Springer chapter (paywall) failed and are recorded as such above.
