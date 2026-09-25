# BitcoinHeist validation report

**Question asked.** Does THEMIS understand a second external dataset without dataset-specific tuning, and what
can it establish about that dataset's labels? The dataset is UCI's *Bitcoin Heist Ransomware Address*.

**Read this first.**

1. **This was not an unseen dataset.** BitcoinHeist was already used on 2026-09-18 (a 51,413-row sample) and led
   directly to the `classify_address` fix (HARDENING_LOG bug #13). What is new here is the first pass over the
   whole file and the first provenance investigation.
2. **It is also not independent of THEMIS's reference corpus.** One of the seven bundled reference sources
   (`rodwald_ransom`) contains BitcoinHeist's ransomware addresses under BitcoinHeist's own label strings (§15).
   Overlap with the reference corpus therefore measures inheritance, not corroboration.
3. **Two genuine, generic THEMIS defects were found**, each reduced to a synthetic fixture, fixed and
   regression-tested: a target-audit over-credit (§18), which also invalidated the cross-corpus outcome counts
   in the earlier MBAL report (corrected, §19); and, while closing the within-dataset-contradiction scope gap
   the first defect's investigation exposed, a chain-blindness bug in an existing check on a different ingestion
   path (§24). The strict "no defect found" condition for closing dataset testing is therefore **not** met;
   §22 says where that leaves the decision.

The purpose was to find THEMIS defects and to fix only genuine, generic ones, not to make this dataset pass.
Nothing in production code names BitcoinHeist, its columns, its label strings, `white`, or the three study names.
No BitcoinHeist row is committed; test files, samples, screenshots and raw JSON are in `bitcoinheist_testdata/`
and `bitcoinheist_evidence/`, beside the repository.

---

## 1. Baseline

| item | value |
|---|---|
| HEAD | `e428b60` (`main`), working tree clean except an untracked `PAPER_MBAL_IMPACT_REPORT.md` that is not part of this work |
| Python / Node | 3.14.6 / v26.8.2 |
| tests before | 685 passed, 6 skipped (the 6 need a full corpus build) |
| tests after | **689 passed, 6 skipped** (4 new regression tests) |
| browser suite (`tests/e2e`) | 18/18 before and after |
| paper commands | `drift`, `anchors`, `bootstrap --both`, `explain 14BWrn1…` byte-identical to `expected_output/`; `audit` differs only in its first `note:` line, the same stale sample-note wording that predates this work |
| reference corpus used | the **bundled sample**, 268,891 claims / 228,775 addresses / 7 sources. No full local build exists on this machine, so overlap with "the corpus" is what the sample contains (§14) |

## 2. Authoritative identity

| item | value | source |
|---|---|---|
| dataset | Bitcoin Heist Ransomware Address, UCI Machine Learning Repository dataset 526 | <https://archive.ics.uci.edu/dataset/526/bitcoinheistransomwareaddressdataset> |
| file | `BitcoinHeistData.csv`, 235,882,597 bytes (UCI page: "225 MB") | UCI; measured |
| rows | **2,916,697** (UCI `num_instances`); measured 2,916,697 logical records in 2,916,698 physical lines (header + data, no embedded newlines) | UCI API; measured |
| SHA-256, CSV | `8ecc3744e444f35534a1bcabedc7a3b405fb5bbf41a752e51ee9a57987b8c438` | measured (identical to the archive member) |
| SHA-256, download | `bitcoinheistransomwareaddressdataset.zip` `cdf3bb34199367b08285cf7f9c1db06c4a262d353aa596055e97db77f4514e5b`, one member, the CSV above (member dated 2020-06-27) | measured |
| DOI | **10.24432/C5BG8V** | UCI page |
| licence | **CC BY 4.0** | UCI dataset page text ("licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license"). The JSON API omits the licence field; the page carries it |
| donated / updated | donated 2020-06-16; UCI record last updated 2024-04-16 | UCI |
| associated paper | Akcora, Li, Gel, Kantarcioglu, "BitcoinHeist: Topological Data Analysis for Ransomware Detection on the Bitcoin Blockchain", IJCAI 2020, arXiv:1906.07852 | arXiv; **not** cited by UCI: the record's `intro_paper` is empty and no creators are listed (the UCI page says "Please see the BitcoinHeist article for references" without naming it) |
| official hash | none published. Identity therefore rests on UCI's row count, the file's schema and the archive's internal date, not on a checksum | — |

The UCI record gives no creators and no introductory paper; linking the dataset to the IJCAI paper is by title
("BitcoinHeist"), the shared description text, and the paper's own statements, not by a UCI citation.

## 3. What every column means (upstream wording)

| column | upstream definition (UCI `variable_info`, paper §IV) | THEMIS |
|---|---|---|
| `address` | "String. Bitcoin address." | claim subject, 100% valid |
| `year` | "Integer. Year." | numeric, meaning unknown, unused |
| `day` | "Day of the year. 1 is the first day, 365 is the last day." | numeric, meaning unknown, unused |
| `length` | "Integer." Paper: designed to quantify mixing rounds, where transactions redistribute similar amounts in multiple rounds with newly created addresses to hide the coin origin | unused |
| `weight` | "Float." Weight quantifies merge behaviour (more input than output addresses) | unused |
| `count` | "Integer." Merging pattern, by number of transactions | unused |
| `looped` | "Integer." Counts transactions that split coins, move them by different paths and merge them in one address | unused |
| `neighbors` | UCI: "Integer." with **no definition**. Paper: the number of transactions that have the address as an output address | unused |
| `income` | "Integer. Satoshi amount (1 bitcoin = 100 million satoshis)." Paper: total coins output to the address | unused |
| `label` | "Category String. Name of the ransomware family (e.g., Cryptxxx, cryptolocker etc) or white (i.e., not known to be ransomware)." | attribution label |

All seven feature columns are per-address, per-24-hour-window graph features (Bitcoin graph 2009-01 to 2018-12,
edges under 0.3 BTC removed "since ransom amounts are rarely below this threshold"). The file is a machine-learning
feature table with one row per address-day, not a one-row-per-claim attribution file. Two documented facts were
checked against the data and hold: **white rows are capped at exactly 1,000 per day** (maximum measured 1,000;
no day exceeds it) and **no row has income below 0.3 BTC** (minimum 30,000,000 satoshi, both classes).

## 4. Where the labels come from, and what upstream says about `white`

UCI: "Ransomware addresses are taken from three widely adopted studies: Montreal, Princeton and Padua." The paper
(§V): "Our ransomware dataset is a union of datasets from three widely adopted studies: Montreal [30], Princeton
[17] and Padua [8]. The combined dataset contains 24,486 addresses from 27 ransomware families."

| study as the paper names it | reference in the paper's list | how that study collected addresses (read from the studies themselves) |
|---|---|---|
| Montreal | Paquet-Clouston, Haslhofer, Dupont, "Ransomware payments in the bitcoin ecosystem", arXiv:1804.04080 | 7,037 Locky addresses supplied by the APWG, 139 from a forum thread, 46 from web searches; then **expanded by the multiple-input clustering heuristic** and time-filtered |
| Padua | Conti, Gangwal, Ruj, "On the economic significance of ransomware campaigns", *Computers & Security* 2018, arXiv:1804.01341 | searches of vendor knowledge bases, removal guides, Reddit and image search; then **expanded by multi-input and shadow-address heuristics** |
| Princeton | Huang, McCoy et al., "Tracking Ransomware End-to-end", IEEE S&P 2018 (author affiliations: Princeton, NYU, UCSD, Google) | seed addresses scraped from public forum reports (e.g. Bleeping Computer), a proprietary ID-Ransomware list, and **synthetic victims** (ransomware executed in a sandbox); expanded by co-spending clustering |

Three consequences, all from the studies' own text: the ransomware labels are **not** all direct observations
(each study extended its seeds with a clustering heuristic); UCI's sentence "we are certain about ransomware labels"
is the dataset authors' assertion, and the upstream methods do not by themselves support that certainty for
every expanded address; and the label "Princeton" is the BitcoinHeist authors' name for the Huang et al. study
(its authors are not at one institution).

**`white`, verbatim from UCI:** "White Bitcoin addresses are capped at 1K per day (Bitcoin has 800K addresses
daily). Note that although we are certain about ransomware labels, we do not know if all white addresses are in
fact not related to ransomware." And: "white (i.e., not known to be ransomware)". THEMIS and this report use only
that reading: **`white` = not known to be ransomware**, never "legitimate" or "verified benign".

## 5. Independent profile of the full file

Stdlib-only, sharing no code with THEMIS (`profile_full.py`; own Base58Check and Bech32).

| measure | result |
|---|---|
| physical lines / logical rows | 2,916,698 / **2,916,697**; every record has exactly 10 fields |
| unique addresses | **2,631,095** |
| addresses seen once / on more than one day | 2,534,328 / **96,767** (382,369 rows; maximum 420 rows for one address) |
| rows in repeated addresses beyond the first | 285,602 |
| repeated **address + day** observations | **0** |
| duplicate rows (all ten fields) | **0** |
| missing values (empty, NA, nan, null, none) | **0** in every column |
| unparseable numbers | 0; scientific notation is used in `income` (717,156 rows) and `weight` (221,229 rows), e.g. `1e+08`; they parse, and the format is a representation of a number that is exact in this case |
| years | 2011–2018 (355,349 / 365,714 / 372,494 / 375,319 / 368,701 / 380,631 / 368,486 / 330,003); UCI and the paper say 2009–2018, and the file has no 2009 or 2010 rows |
| day | 1–365 |

| label counts | rows | unique addresses |
|---|---:|---:|
| `white` | 2,875,284 | 2,610,246 |
| ransomware (28 label strings, below) | 41,413 | **20,849** |
| **total** | 2,916,697 | 2,631,095 |

Ransomware label strings, rows / unique addresses: `paduaCryptoWall` 12,390 / 1,894; `montrealCryptoLocker`
9,315 / 1,509; `princetonCerber` 9,223 / 9,177; `princetonLocky` 6,625 / 6,584; `montrealCryptXXX` 2,419 / 1,354;
`montrealNoobCrypt` 483 / 28; `montrealDMALockerv3` 354 / 143; `montrealDMALocker` 251 / 21; `montrealSamSam` 62 / 44;
`montrealCryptoTorLocker2015` 55 / 32; `montrealGlobeImposter` 55 / 1; `montrealGlobev3` 34 / 5; `montrealGlobe` 32 / 7;
`montrealWannaCry` 28 / 5; `montrealRazy` 13 / 1; `montrealAPT` 11 / 2; `paduaKeRanger` 10 / 10; `montrealFlyper` 9 / 8;
`montrealXTPLocker` 8 / 3; `montrealVenusLocker` 7 / 1; `montrealXLockerv5.0` 7 / 3; `montrealCryptConsole` 7 / 5;
`montrealEDA2` 6 / 4; `montrealJigSaw` 4 / 3; `paduaJigsaw` 2 / 2; `montrealXLocker` 1 / 1; `montrealSam` 1 / 1;
`montrealComradeCircle` 1 / 1.

**Bitcoin identifier validity (Base58Check checksum verified, Bech32 tried).** 2,381,213 P2PKH and 249,881 P2SH
addresses pass. **One** value fails: the literal string `unknown` (4 rows, all `white`), a placeholder, not an
address. Two addresses contain no capital letters and still pass their checksum (33–34 characters, no `l`); they are
valid. There is no case-folding here, unlike MBAL. Ransomware addresses: 20,847 P2PKH and 2 P2SH (both
`montrealAPT`, consistent with the paper's "two multisig addresses" for APT).

**Label conflicts inside the file: none.** No address carries more than one label (0 addresses with two labels;
0 with both `white` and a ransomware label). Every repeated address repeats with the same label on different days.

**Paper ↔ file.** The paper reports 24,486 ransomware addresses from 27 families and "Four addresses have
conflicting ransomware labels between Montreal and Padua datasets". The file has **20,849** ransomware addresses,
28 label strings, and **no** conflicting address. Family spellings also differ within the file
(`montrealSam`/`montrealSamSam`, `montrealXLocker`/`montrealXLockerv5.0`, `montrealJigSaw`/`paduaJigsaw`,
`montrealGlobe`/`Globev3`/`GlobeImposter`). The released file is a different, smaller artifact than the paper's
combined set; the four conflicts are not in the file, and the file does not say how they were handled.

## 6. The deterministic sample (below the default row limit)

The default `upload.max_rows` is 1,000,000; the full file has 2,916,697, so a sample comes first.

**Rule** (`make_sample.py`): keep every row whose address satisfies
`int.from_bytes(sha256(b"bitcoinheist-sample-v1|" + address).digest()[:8], "big") < 2**64 // 6`. It is drawn by
address, so every row of a sampled address is kept; it does not depend on row order, Python version or platform; rows
are copied byte for byte in file order. The salt was fixed before looking at any result and not changed.

| | |
|---|---|
| file | `bitcoinheist_sample_1in6.csv`, 39,448,821 bytes |
| **SHA-256** | **`e0debb2e139121a36814db8100c3bb49d5d337cb310ab142ed45e376022382b0`** |
| rows / addresses | 487,799 / 439,455 |
| ransomware rows / addresses / label strings | 6,257 / 3,448 / 20 of 28 |
| contains `unknown` | no |

The draw is uniform over addresses, so prevalence estimated from it is unbiased (about one sixth of every
group), but rare families (one-row labels) are simply absent from it. Population figures below come from the
full pass, not from the sample.

The **same file** (verified by SHA-256: the GUI shows `e0debb2e…`, the API returns it in the pre-flight) went
through the backend and the GUI.

## 7. THEMIS on the sample: backend and GUI

| stage | result |
|---|---|
| pre-flight | dataset type **attribution claims**, state `supported_attribution_data`, status ready, blockers none; chain **bitcoin**, determined, 100% (Ethereum/BNB/Polygon/Avalanche 0%) |
| mapping (all inferred) | `address` → claim subject, 100%; `label` → attribution label, 100%; **the other seven columns "Numeric, meaning unknown", unused**; no `year`/`day` composition into a timestamp |
| warnings | "No attribution timestamp mapped: staleness will not be computed"; "No declared-source column mapped: provenance of these claims cannot be established" |
| rows → claims | 487,799 rows → **439,455 claims** over 439,455 subjects; 48,344 rows rejected as `duplicate claim` (same address, same label, same source, another day) = 487,799 − 439,455, matching the independent profile; **0** invalid identifiers |
| time | pre-flight 0.7 s; analysis 8.3 s (backend); GUI 6.7 s |

GUI vs backend: every figure on Overview (12 counts) appears on the page and equals the API value; the
`reliability_profile` the browser fetched equals the backend run field by field; no console or page error; every
page (Overview, Claims, Provenance, Conflicts, Trust, Exports, Address Inspector) rendered.

## 8. THEMIS on the full file (explicit local config)

The shipped `upload.max_rows` (1,000,000) is **unchanged**; `git diff themis/config` is empty. The run used a copy
of the config tree with `max_rows: 5000000` (`bitcoinheist_testdata/config_full/api.yml`), selected with
`THEMIS_CONFIG_DIR`. The 235,882,597-byte file is under the 256 MiB byte limit, so only the row limit had to move.

| measure | backend | GUI |
|---|---|---|
| pre-flight | ready, 2,916,697 rows, bitcoin determined, 4.2 s | ready, 6.8 s; SHA-256 shown as "computed by the server: too large to hash in the browser" |
| analysis | **40.5 s** (parse 3.9, validate 15.1, normalise 7.9, compare 12.3) | 41.1 s |
| rows → claims | 2,916,697 → **2,631,094** claims over 2,631,094 subjects | identical |
| rejected | 285,603 = 285,599 `duplicate claim` + **4 `invalid address`** | identical |
| identifiers checked / failed | 2,916,697 / 4; the chain table shows "100.00%" valid because 99.99986% rounds to it | identical |
| trust coverage (first query) | 17.2 s | rendered |
| peak memory | **8.08 GB** for one analysis (about 2.8 KB per row, in line with MBAL's 2.5 KB); two analyses held at once reached 14.2 GB | — |

Reconciliation with the independent profile (§5): 2,631,095 unique addresses = 2,631,094 valid claims + the one
placeholder address `unknown`; 2,916,697 − 2,631,095 = 285,602 repeats, of which 3 sit on the `unknown` rows,
so 285,599 duplicate claims + 4 invalid rows = 285,603 rejected. Every count agrees. The sample and the full run give
the same reference-overlap rate (0.99% and 0.9955%).

## 9. Duplicate observations and repeated addresses

THEMIS normalises one claim per (address, label, source). It therefore collapsed **285,599** repeated address-day
rows into the 2,631,094 claims and reported each as a rejected `duplicate claim` with its row number and the total.
It did not lose them silently and did not count them as separate claims. It does not carry the number of
repetitions per address or the days as evidence (they are not claim data), and it does not treat `year`/`day` as a
date. A 420-day address is one claim.

## 10. Label semantics: what THEMIS did with `white` and the family names

Every one of the 28 ransomware label strings and `white` maps to `canon: unknown`, `polarity: unknown`, evidence tier
`unknown`; the raw string is displayed unchanged. THEMIS's taxonomy has a generic `ransomware` category, but no rule
turns `princetonCerber` or `paduaCryptoWall` into it, and none was added (that would be BitcoinHeist-specific
vocabulary, and the "Princeton/Montreal/Padua" prefix is a study tag, not a category).

So THEMIS neither claimed that `white` is legitimate nor claimed that a family label is a ransomware verdict. It
also did not draw the distinction the upstream documentation draws (attribution to a family versus an admitted
uncertainty): it left both classes uninterpreted. `white` appears only as the file's own string. Section 16 shows
that treating `white` as "legitimate" would be wrong on the reference evidence, and THEMIS's refusal to interpret
it is why it did not make that error.

## 11. Bitcoin identifier validity

2,631,094 of 2,631,095 unique addresses are valid Bitcoin identifiers (Base58Check verified by THEMIS and,
independently, by `profile_full.py`; the two agree exactly, including the single failure `unknown`). "Valid" is
syntactic: THEMIS's own screen says so ("Valid means syntactically valid on that chain; it says nothing about
whether the label is true").

## 12. Repeated and conflicting labels: what was found and what THEMIS can see

| question | answer |
|---|---|
| addresses with multiple labels | **0** |
| addresses with `white` + a ransomware label | **0** |
| the four documented Montreal/Padua conflicts | **not present** in this file (each address has one label). They cannot be located, so THEMIS cannot have detected them |
| how the union was collapsed | not documented. §15 shows 9 addresses that an independent reference source places in **both** Montreal and Padua, each carrying one BitcoinHeist label (8 `montreal…`, 1 `padua…`): consistent with overlaps having been collapsed to one label by an undocumented precedence rule |
| would THEMIS detect a conflict if the file had kept it? | **Yes, as of the within-dataset check added 2026-09-25 (§24).** The same synthetic file (one address labelled `ransomware` and `exchange`, one labelled `montrealCryptoLocker` / `paduaCryptoWall`) now reports 1 `internal contradiction` (the `ransomware`/`exchange` address) and 0 in every other bucket; the two BitcoinHeist-vocabulary strings still map to `canon: unknown` and correctly contribute nothing. Before §24 this was **not detected within one file, by design**: THEMIS's only conflict notion was cross-**source** disagreement (paper §5.1), and a source contradicting itself was silently `incomparable`. That was a real scope gap, not a bug in the cross-source logic, and is now closed generically (not by reading BitcoinHeist's own label strings) |
| conflicts against the reference corpus | before the fix, 3 "conflicts" and 1,508 "exact agreements" were reported; all were reference-versus-reference (§18). After the fix: **0 exact, 0 conflicts, 26,193 incomparable** |

## 13. Provenance: what THEMIS established

`analysis_states.provenance`: "insufficient data: no declared-source field is mapped (or it is empty), so the
provenance of this dataset's claims cannot be established; every claim's root stays UNRESOLVED". Resolved 0,
partially resolved 0, **unresolved 2,631,094 / 2,631,094**. Evidence class: verified 0, derived 0, unverified
report 0, **unknown 2,631,094 / 2,631,094**. Staleness: not applicable (no attribution timestamp; the
`year`/`day` columns are observation dates of graph features, not attribution dates, and are never used as one).
This is correct: the file has no per-row source. THEMIS did **not** read `princeton`/`montreal`/`padua` off the
label and assign a root, and the address inspector shows the target claim's root as `bitcoinheist_…:unresolved`
next to a reference root `padua_conti_2018` (§14).

## 14. Reference-corpus overlap, as THEMIS reports it

| measure | full file | sample |
|---|---:|---:|
| target addresses also named by the reference corpus | **26,193** of 2,631,094 (0.9955%) | 4,340 of 439,455 (0.99%) |
| agreement outcomes | exact 0, hierarchical 0, entity-type 0, licit/illicit 0, **incomparable 26,193** | identical shape |
| independence | 26,193 apparent multi-source, **0 confirmed independent, 26,193 unresolved** | 4,340 / 0 / 4,340 |

"Incomparable" is the right outcome: THEMIS could not interpret a single BitcoinHeist label, so it compared none.
The overlap rate is low overall only because `white` (99.2% of the addresses) barely overlaps. **Split by class
(read directly from the reference corpus, not a THEMIS output):**

| BitcoinHeist class | addresses | named by the reference sample | share |
|---|---:|---:|---:|
| ransomware families | 20,849 | **20,846** | **99.99%** |
| `white` | 2,610,246 | 5,347 | 0.20% |

This is a sample of the reference corpus (268,891 of 1,545,710 claims), drawn to keep every multi-source address;
the true overlap of the complete corpus can only be larger.

## 15. Provenance and independence investigated properly (label family ≠ study ≠ root ≠ independent)

Four things that must not be conflated, and what the evidence supports for each:

| level | meaning | status here |
|---|---|---|
| **label family** | the string in the file (`princetonCerber`) | measured; 28 strings |
| **source study** | which published study contributed the address | **documented only in aggregate** ("a union of Montreal, Princeton, Padua"); the paper uses "family (study)" notation in a few places (APT (Montreal), Jigsaw (Padua), CryptoTorLocker2015 (Montreal/Padua)); no per-row source column and no rule that the prefix is the study |
| **confirmed provenance root** | an identified origin THEMIS can name | **none**: 0 of 2,631,094 |
| **independent provenance** | two claims with distinct confirmed roots | **not established; evidence of dependence** (below) |

Why the prefix cannot be trusted as the study, from an independent reference source (Schnoering records, per
address, which study named it; 9,248 BitcoinHeist ransomware addresses are in it):

| BitcoinHeist label prefix | studies Schnoering records for the same address | addresses |
|---|---|---:|
| `princeton…` | **Montréal only** | 6,544 |
| `padua…` | Padua | 1,905 |
| `montreal…` | **Padua only** | **731** |
| `montreal…` | Montréal | 56 |
| `montreal…` | Montréal and Padua | 7 |
| `montreal…` | Padua and BitcoinTalk / Montréal and BitcoinTalk / all three | 4 |
| `padua…` | Montréal and Padua | 1 |

All 6,544 `princetonLocky` addresses found there are recorded as Montréal addresses, which fits Montreal's
7,037 APWG Locky seeds, not Huang et al.'s 28 synthetic-victim Locky seeds. And 731 `montreal…` addresses are
recorded as Padua-only. Either Schnoering's tagging is coarse or BitcoinHeist's prefix is not the study of origin;
this report cannot say which, and the point stands: **the prefix does not establish the study**, still less a root.

Why the reference overlap is inheritance, not corroboration. `rodwald_ransom` (a reference source) records, per
address, an undocumented letter code. THEMIS's own generic containment test (`provenance.decode_field`, the tool
the paper used for the other letters) run with BitcoinHeist's ransomware addresses as the candidate upstream gives
a **clean split**:

| Rodwald letter group | addresses | inside BitcoinHeist | verdict |
|---|---:|---:|---|
| `H` | 11,738 | 11,737 (99.991%) | inherited |
| `RSH` | 6,546 | 6,546 | inherited |
| `SH` | 2,367 | 2,367 | inherited |
| `RH`, `HS`, `HRS`, `HR` | 33, 25, 23, 10 | all | inherited |
| `S` | 28,684 | 0 | independent |
| `RS` / `R` | 494 / 400 | 0 / 0 | independent |

Every group with an `H` is contained; every group without one has zero overlap: 20,742 Rodwald addresses. In
those addresses Rodwald's raw label is BitcoinHeist's exact string (`H`-only: 11,708 of 11,738; all of `HS`, `HRS`,
`HR`), for example `montrealWannaCry`, the BitcoinHeist authors' own naming. **Supported, not documented:** the
`H` input of Rodwald's ransomware set is BitcoinHeist (or the BitcoinHeist authors' compiled set), the letter
being undocumented and Rodwald's paper being paywalled. Direction is inferred from dates (BitcoinHeist 2020,
Rodwald 2024). Consequence: 99.5% of BitcoinHeist's ransomware addresses (20,741 of 20,849) are already inside a
reference source, so "overlap with the reference corpus" here is the same data seen twice.

Independence also fails on the upstream side. Montreal and Padua both seeded from public web reports and both
expanded with the multiple-input heuristic; Huang et al. also drew on public forum reports. Nothing in the
documentation shows the three seed sets to be disjoint, and Schnoering places 9 addresses in both Montreal and
Padua. No claim of independent provenance for BitcoinHeist's ransomware labels is supported.

Registry note (paper-relevant, not changed): `themis/config/sources/rodwald_ransom.yml` lists
`known_dependencies` as Ransomwhere, Princeton, Padua and Montreal, and leaves letters `S`/`H` undecoded
(`rodwald_own_SH`, unresolved). The test above supports adding BitcoinHeist as a dependency of the `H` input. That
is a change to the paper's provenance registry and to numbers the paper reports; it is the author's call and was
**not** made here.

## 16. What `white` is, on the reference evidence

5,347 BitcoinHeist `white` addresses are named by the reference sample (0.20% of `white`). By what the reference
sources call them (distinct addresses; one address can have several):

| reference says | addresses | mainly via |
|---|---:|---|
| individual | 3,258 | Schnoering |
| unknown | 799 | Elliptic++, TagPack |
| **mixer** | **587** | Rodwald mixers |
| licit (unspecified) | 367 | Elliptic++ |
| exchange | 329 | Schnoering, TagPack |
| mining | 219 | Schnoering |
| **ransomware** | **214** | Rodwald ransom 209, TagPack 4, Ransomwhere 4, Schnoering 1 |
| gambling | 153 | Schnoering |
| **darknet market** | **86** | Schnoering |
| ponzi | 42 | Schnoering, TagPack |
| sanctioned | 15 | TagPack |
| illicit (unspecified) / extremism / scam | 10 / 4 / 1 | Elliptic++, TagPack |

At least **214 `white` addresses are called ransomware** by a reference source, and 1,102 carry at least one
reference class among ransomware, mixer, gambling, darknet market, ponzi, sanctioned, illicit or scam. This is
disagreement between vocabularies and sources, not a ruling on which is right (Rodwald is itself a compiled,
partly unverifiable set, §15), but it is direct evidence that **`white` is not "legitimate"**, exactly as UCI's own
caveat says. THEMIS produced none of this: it reported `white` as uninterpreted and every matched address as
`incomparable`; these counts come from `white_vs_reference.py` reading the reference corpus.

## 17. Overclaim search

Searched every screen of the GUI runs (Pre-flight, Overview, Claims, Provenance, Conflicts, Trust, Exports,
Address Inspector) and the raw JSON for: reliable, verified, legitimate, ground truth, independent, confirmed,
trusted, accurate, forensic, validated, benign, "not ransomware", "known to be".

| word | lines matched (sample GUI run) | each one |
|---|---:|---|
| legitimate, ground truth, trusted, accurate, forensic, validated, benign, "known to be" | **0** | — |
| reliab* | 10 | the product name "Attribution reliability auditor" (8), "Dataset reliability profile", "Full reliability profile" |
| verified / verif* | 17 | field names and zeros: "attribution last independently verified" (a timestamp option, 10), "Verified 0 / 439,455", "Unverified report", "no attribution timestamp (last updated or last verified) is mapped" |
| independent* | 43 | negations and counts: "the agreement is not independent" (9), "independence cannot be confirmed" (16), "Unresolved is never counted as an independent source", "Confirmed independent multi-root 0 / 4,340" |
| confirmed | 43 | "N apparent · M confirmed · K unresolved" root counts on reference sources (the target's own root is unresolved in each), "independence cannot be confirmed", and a request parameter `confirmed:false` |

No sentence claims that a label is reliable, verified, ground truth, legitimate, independent or confirmed. One
cosmetic point: the chain table shows "100.00%" valid with 4 failed identifiers (the value is 99.99986%); the
count of failures is displayed next to it, and this was not changed. The words in **this report** are used the
same way: "confirmed", "independent" and "verified" appear only as measured quantities or negations, and the
`H` = BitcoinHeist statement is marked "supported, not documented".

## 18. The genuine defect: reference-versus-reference agreement reported as the target's own

**Symptom.** On the first sample run THEMIS reported, for the 4,340 reference-matched addresses, exact agreement
1,508, hierarchical refinement 40, entity-type conflict 1, licit/illicit conflict 2, incomparable 2,789. Yet every
BitcoinHeist label is `canon: unknown`, so the target had said nothing THEMIS could compare.

**Cause.** `taxonomy.classify_address` drops `unknown` claims before comparing (the bug-#13 rule), but a caller
that passed "target claims + reference claims" still counted two *reference* sources agreeing or disagreeing with
each other as the target's outcome. Concretely: address `114Tqaap…` (target label `paduaCryptoWall`, unmapped)
was "exact" because `schnoering` and `rodwald_ransom` agreed with each other, and both trace to the same root
(`padua_conti_2018`); address `1QHrs…` (target `white`) was a "licit/illicit conflict" between `ellipticpp`
and `tagpack`. The code's own comment states the opposite intent ("never the reference corpus's other, unrelated
internal agreement"). Callers: `target_audit.audit_target_against_reference`, `views.address_index` (claims and
conflicts pages, per-claim outcome) and the address inspector (`_explain_in_workspace`).

**Generic.** Any upload whose labels THEMIS cannot map triggers it; nothing about BitcoinHeist is required. The
earlier MBAL run showed the same defect for its 31 comparable subjects (§19).

**Fix** (one function, three call sites): `taxonomy.classify_target_address(target_claims, reference_claims)`
returns `incomparable` when the target has claims and none of them maps to a category; otherwise it is
`classify_address` on both sets, unchanged. In paper mode there is no target, and the function reduces to
`classify_address`. No constant, no source name, no dataset name.

**Test-first.** `tests/test_target_audit.py::TestUninterpretedTargetIsNotAgreement` (4 tests, synthetic
fixtures: two reference sources that agree, two that conflict, an unmapped target; audit, views and inspector;
plus a control in which a mapped target is still compared). Before the fix: 3 failed (`'exact' != 'incomparable'`,
`0 != 1`), the control passed. After: all pass.

**Regression.** Full suite 689 passed / 6 skipped; browser suite 18/18; `drift`, `anchors`, `bootstrap --both`,
`explain` byte-identical to `expected_output/`; `audit` differs only in the note line that already differed at HEAD.
**Rerun:** sample (439,455 claims) and full file (2,631,094): exact 0, conflicts 0, incomparable = matched;
independence unchanged (0 confirmed, all unresolved).

**Not changed, and why.** The Trust page's `exclude_conflicts` policies still read reference-internal conflict on
an address (`trust/predicates.py:_address_outcome`): that is a filter on an *address being contested*, not a target
agreement figure, and changing it is a policy decision.

## 19. Effect on the earlier MBAL report

`MBAL_VALIDATION_REPORT.md` §21 reported, for MBAL's 31 reference-matched subjects, exact 10 / entity-type 10 /
licit-illicit 9 / incomparable 2. The 31 rows were re-extracted from the raw file (exact string match against the
reference addresses; exactly 31) and re-run on the fixed code: **exact 2 / entity-type 9 / licit-illicit 7 /
incomparable 13**, independence unchanged (0 confirmed, 31 unresolved). "19 of 31 disagree" becomes 16 of 31 (16 of
the 18 that could be compared). The MBAL report is corrected in place with a dated note (§21, §20, §32); the old
percentages and interval are withdrawn. **`PAPER_MBAL_IMPACT_REPORT.md` (untracked, not mine) still quotes "19 of 31" and was
not edited.**

## 20. Answers

**A. Did THEMIS understand this second dataset without dataset-specific tuning?**
Structurally yes, semantically no. With no dataset-specific code it recognised an attribution file, Bitcoin at
100%, the subject and label columns, and left the seven graph-feature columns and the year/day alone; it read
2,916,697 rows correctly (0 shifted fields) and accounted for every row (2,631,094 claims + 285,599 repeats + 4
invalid). It did not understand what the labels mean (all 29 strings `unknown`, by design), and it does not
compose `year`+`day` into a date. Two caveats to "without tuning": the dataset had already shaped THEMIS once (bug
#13, 2026-09-18), so it is not a clean second test; and this run found and fixed one generic defect (§18).

**B. Did it distinguish documented ransomware attribution from uncertainty in `white`?**
It did not overclaim: `white` was never read as legitimate or verified, and no family string was read as a verdict.
It also did not represent the distinction: both classes stayed uninterpreted. The distinction is supported
externally: at least 214 `white` addresses are called ransomware, and 587 mixers, 86 darknet-market and 15
sanctioned addresses are among them (§16). That evidence came from reading the reference corpus, not from THEMIS.

**C. Did it detect repeated and conflicting address labels?**
Repeated: yes. 96,767 addresses recur (382,369 rows); repeated address-day and duplicate rows are 0; THEMIS
collapsed 285,599 repeats into single claims and reported each. Conflicting: the file contains **none**, and the
four documented Montreal/Padua conflicts are absent from it, so there was nothing to detect. Independently of this
file, THEMIS does not detect a label conflict *within* one source (§12). It initially mis-detected conflicts
*across* sources when labels were unmapped (§18); that is fixed.

**D. Could provenance and source independence actually be established?**
No. THEMIS: 0 resolved, 2,631,094 unresolved, 0 confirmed independent, 26,193 unresolved. The documentation
supports "a union of three studies" only in aggregate; the label prefix is not the study (6,544 `princeton…`
addresses are recorded as Montréal, 731 `montreal…` as Padua-only); the upstream studies share source types and
heuristics; and the reference sources' overlap is inheritance (Rodwald's `H` input is contained in BitcoinHeist,
20,742 addresses). What is established is negative: the provenance the file offers does not support independence.

**E. What forensic reliability conclusion, if any, is supported?**
**None as a reliability rate or a verdict.** Supported statements: the identifiers are syntactically valid Bitcoin
addresses (all but one placeholder); the ransomware labels come, by the dataset's own description, from three
published studies whose methods included heuristic clustering, with no per-address provenance in the file;
`white` means "not known to be ransomware" and is contradicted for at least 214 addresses by another source; the
reference agreement cannot corroborate the labels because the sources overlap by inheritance. That is
**INSUFFICIENT EVIDENCE FOR A FORENSIC RELIABILITY CONCLUSION**: a statement about what can be shown, not a
judgement that the labels are wrong.

## 21. Open findings for the author (not changed)

1. **Rodwald `H` = BitcoinHeist** (§15): treated as an **empirically supported dependency candidate**, not a
   confirmed one - no authoritative documentation currently establishes `H` = BitcoinHeist, only the clean
   containment split THEMIS's own decoder produces. A provenance-registry and paper change either way. Needs
   the author's decision and an impact run on the paper's numbers before any edit.
2. ~~No within-file contradiction detection~~ **Closed 2026-09-25** (§24): a generic, chain-aware
   `taxonomy.internal_consistency` now answers this for every dataset, cross-source conflict logic is
   unchanged, and BitcoinHeist itself reports zero (real absence, not an unmeasured gap).
3. ~~`capabilities.internal_consistency: true` set unconditionally with no check behind it~~ **Closed 2026-09-25**
   (§24): the CSV/API upload path now runs the same check the relational/SQLite path already had (which itself
   had a chain-blindness bug, also fixed). The GUI still does not surface either field; that remains open.
4. The chain table rounds 99.99986% to "100.00%" with 4 failures shown beside it (cosmetic).
5. ~~`PAPER_MBAL_IMPACT_REPORT.md` quotes the withdrawn MBAL figures~~ **Closed 2026-09-25**: corrected to the
   16-of-18 figures.
6. Everything in this report is now committed: `0ee2978` (the target-audit fix) and `395f527` (the
   internal-consistency generalization). `MBAL_VALIDATION_REPORT.md`'s correction and this report are docs-only
   and were committed alongside.

## 24. Generic addition: within-dataset label contradiction (2026-09-25)

Finding 2 above (§12) exposed a real scope gap, not specific to BitcoinHeist: THEMIS's only "do these labels
agree" logic (`taxonomy.classify_address`) requires >= 2 distinct **sources** by design, and a single source
contradicting itself about one subject silently fell through as `incomparable`, however loudly the file itself
disagreed with itself. Checking the codebase (not just this dataset) found the relational/SQLite ingestion path
already had a version of this (`ingest/relational.conflicts`, added for the earlier multi-table work) - but it
grouped by the bare address **string**, so the same address on two different chains could have been reported as
one subject contradicting itself, and the plain CSV/API upload path (what this report and MBAL's both used) had
no such check at all despite unconditionally declaring `capabilities.internal_consistency: true`.

**Fix, generic, both ingestion paths:** `taxonomy.internal_consistency(claims)`, grouped by
`provenance.subject_key` (chain-aware, so a repeated address string on two chains is two subjects, never one).
Every subject with more than one claim lands in exactly one of four buckets: `repeated observation` (byte-
identical claims), `repeated same label` (same category, not identical - e.g. a different raw spelling or
revision date), `compatible multi-label claim` (different categories that coexist, e.g. a generic placeholder
with a specific descendant), `internal contradiction` (categories that cannot both be true). The polarity/
hierarchy primitive itself (`label_relationship`) is shared with `classify_address`, not reimplemented a third
time. `ingest/relational.conflicts` now delegates to it and is chain-aware; `ingest/pipeline.ingest` (the CSV/API
path) now computes and returns it, backing the capability flag it already claimed.

**Regression-tested** (`tests/test_internal_consistency.py`, 12 tests): the five required synthetic scenarios -
same subject/same label, same subject/repeated time windows, compatible labels, incompatible labels, the same
address string on two different chains - plus single-observation, all-unknown-label, and three-way-compatible
edge cases; a direct test that `relational.conflicts` no longer conflates two chains; and two pipeline-level
tests through the real CSV ingestion path. Full suite: **700 passed, 7 skipped** (up from 688/6 at the previous
checkpoint, entirely the new tests plus one more full-corpus-build skip on this run); paper commands (`drift`,
`anchors`, `bootstrap --both`, `explain`) byte-identical to `expected_output/`; `audit` differs only in the
pre-existing stale note line (§1 baseline).

**Verified against BitcoinHeist itself**, both through the real pipeline (not the standalone `profile_full.py`):

| run | claims | repeated observation | repeated same label | compatible multi-label | internal contradiction |
|---|---:|---:|---:|---:|---:|
| sample (`bitcoinheist_sample_1in6.csv`) | 439,455 | 0 | 0 | 0 | 0 |
| full file (2,916,697 rows, `max_rows=3,500,000`) | 2,631,094 | 0 | 0 | 0 | 0 |

Consistent with §12: no BitcoinHeist address carries more than one label, so zero is a measured absence, not an
unmeasured gap - confirmed by running the same check against `bitcoinheist_testdata/synthetic_conflict.csv`
(§12's own fixture), which now reports exactly 1 `internal contradiction` (the `ransomware`/`exchange` address)
and 0 elsewhere; its `montrealCryptoLocker`/`paduaCryptoWall` address still contributes nothing, because both
strings remain `canon: unknown` in production (no BitcoinHeist vocabulary was added to close this).

**Not changed:** no paper number, no provenance registry entry, no dataset-specific string anywhere in
production code (`grep -rni "bitcoinheist\|montrealcrypto\|paduacrypto"` over `themis/`: no matches).

## 22. Verdict on closing dataset testing

The stated condition for closing was "no new generic scientific defect found". Two were found against
BitcoinHeist evidence: the target-audit over-credit (§18, from running the dataset) and, while closing the
scope gap it exposed (§12), a chain-blindness bug in the relational path's own within-dataset check (§24, found
by reading the existing code, not by a new dataset run). Both are fixed generically, test-first; the rerun on
the sample, the full file and the MBAL rows found no further generic defect; the paper outputs are byte-identical.
Strictly, the "no defect" sentence cannot be printed for this dataset; on the evidence I would close BitcoinHeist
-specific testing at this point, with the findings of §21 carried into the paper revision. Whether that satisfies
the *project's* overall closing condition depends on the still-unseen final dataset (§6 of the closure brief).

## 23. Reproduction

Everything is outside the repository except the fix and tests. `bitcoinheist_testdata/`: `profile_full.py`,
`make_sample.py`, `bitcoinheist_sample_1in6.csv`, `run_backend.py`, `gui_run.mjs`, `config_full/`,
`overlap_analysis.py`, `family_vs_reference.py`, `rodwald_vs_heist.py`, `decode_rodwald_H.py`,
`study_membership.py`, `white_vs_reference.py`, `mbal_recheck_extract.py`. Evidence: `bitcoinheist_evidence/`
(`backend_sample`, `backend_sample_BEFORE_FIX`, `backend_full`, `gui_sample`, `gui_full`, `mbal_recheck`,
`synthetic_conflict`, `paper_regression`, the analysis printouts, `pytest_after_fix.txt`). Sample:
`python make_sample.py BitcoinHeistData.csv out.csv`; API: `python -m themis.api` (full run:
`THEMIS_CONFIG_DIR=bitcoinheist_testdata/config_full`); backend: `python run_backend.py FILE OUTDIR`; GUI:
`vite preview --port 4173` then `node gui_run.mjs FILE OUTDIR 5001`. The GUI runs used headless Chromium against the
built frontend, on one machine; nothing here was run on the full reference corpus.
