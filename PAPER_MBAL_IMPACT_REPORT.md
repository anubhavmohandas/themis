# Paper impact report: what the MBAL experiment changes in the manuscript

> **Historical record.** Commit hashes, test counts, file states and open decisions below describe the repository when this report was written (for example: `HEAD` `30ffd0b`, no `LICENSE`, `demo_data/` tracked, the earlier paper pin). They were resolved afterwards. The final state is the `v1.0-paper` tag, described by `README.md`, `REPRODUCE.md` and `THIRD_PARTY_DATA.md`.

Date: 2026-09-25. Status: **impact analysis only. The manuscript, the PDF, `paper/paper_claims.yml` and the
code were not edited; nothing was committed.** Every recommendation below waits for author approval.

Written for: the author, deciding what to change in the paper.

## 0. What was examined

| item | identity |
|---|---|
| manuscript | `paper/manuscript/ICISHCT2026_THEMIS.md` (untracked local source). 154 of 154 prose sentences occur verbatim in the PDF of record, so source and PDF say the same thing |
| PDF of record | `ICISHCT2026_THEMIS_Final_Verified.pdf`, 6 pages, sha256 `11ad4bd19a76…bd8ea`, the file `paper_claims.yml` pins |
| implementation | git `e428b60` (`main`, clean tree), i.e. the MBAL work as re-split into 11 commits plus later commits |
| MBAL evidence | `MBAL_VALIDATION_REPORT.md`, `MBAL_PREFLIGHT_DEFECT_REPORT.md`, `MBAL_CHANGE_AUDIT.md` |
| paper outputs | `results/reproduction/final-verified-0d9cfe6` (pre-MBAL, full corpus, PASS) and the new run in §2 |

Structure note: the manuscript has no separate *Research Question*, *Contributions*, *Limitations* or
*Reliability method* sections. RQs and the contribution sentence sit in §1; the method is §3; limitations
are split between §4.3 and §5.4 ("Threats to validity"). The ledger in §4 uses the manuscript's own sections.
I recommend **not** adding new top-level sections.

Side effect of this audit: re-running `reproduce-paper` mirrors its output to `results/paper_proof/`, which
replaced the earlier sample-only mirror (`f586000`, BLOCKED). That mirror is backed up in the session
scratchpad; the new run is also kept as `results/reproduction/impact-audit-e428b60/`. Both are gitignored.

---

## 1. Answers in brief

1. **No existing seven-source numeric result changes.** Verified, not assumed (§2).
2. **The paper never claims "any dataset", automatic schema detection, multi-chain support or scale.** It is
   already Bitcoin-scoped and conservative. Two sentences over-reach relative to the evidence and are the
   only REQUIRED edits: the "the method itself only requires a label, a source and a date" sentence (§1) and
   the "adding another dataset requires an ingestion adapter … logic remains unchanged" sentence (§4.2).
3. **The paper does not imply "THEMIS tells whether a dataset is reliable."** It says the opposite (§4.2) and
   MBAL's outcome ("insufficient evidence for a forensic reliability conclusion") is the same thesis on a
   different dataset. A one-sentence positive framing would still help (§6).
4. **MBAL's role, decided scientifically: C, a case study, with D (stress-test/limits) content folded into
   Limitations. Not A, and not B** (§3).
5. **The paper separates three of the six evidential questions explicitly** (provenance, independence,
   corroboration) and coverage; technical validity and forensic defensibility are only implicit (§7).
6. **Do not quote the "31 comparable subjects" figure.** It was computed against the 268,891-claim bundled
   *sample*, not the 1,545,710-claim corpus the paper describes (§5, finding 9).
7. **Any MBAL number printed in the paper needs a reproducible script and manifest entries first.** MBAL
   numbers currently live in reports and in `mbal_evidence/` outside the repo, not in the paper harness (§8).

---

## 2. Do any seven-source numbers change?

**No existing seven-source numeric result changes.**

| check | result |
|---|---|
| Full-corpus `themis reproduce-paper` at HEAD `e428b60` (clean tree), retained observation table sha256 `e65bf05a…029acd` (same file as the pre-MBAL PASS), `--as-of 2026-09-15`, bootstrap both, PDF layer on | **`PAPER ↔ THEMIS: PASS`**, scope `FULL_CORPUS`. Headline 29/29, supporting 85/85, limitation 1/1, 0 FAIL, 0 NOT_REPRODUCED; RQ1, RQ2, RQ3, Table 1, Figure 1, Table 2, Figure 2 all PASS |
| Same run vs pre-MBAL run `0d9cfe6` | `paper_metrics.json`: **939 of 939 values identical, 0 differ.** corpus, taxonomy, source-registry, threshold, trust-rule and config hashes identical. `table1/2.csv`, `overlap_matrix.csv`, `rodwald_containment.csv`, `montreal_recurrence.csv`, `fig1a/1b/2_data.csv`, `anchors.json`, `bootstrap_lower/upper.json`, `currency.json`, `unresolved_provenance.json`, `source_depth.json`, `condition_d_trace.json`: byte-identical |
| Code path | Of the MBAL-era changes, only three lines of paper-path logic changed: `provenance.subject_key`, `trust/drift.group_by_address`, `trust/predicates._siblings`. Reference claims carry no `blockchain` key, so the key is the bare address as before. The adapter, validation, pre-flight and API changes are upload-only |
| MBAL report §28 | `themis drift`, `anchors`, `explain`, `bootstrap --both` byte-identical to `expected_output/` |

Caveats that stay attached (already in `REPRODUCE.md`, unchanged by this audit): the retained table is a
*reconstruction* built after the paper's data were collected, so this is regression evidence for the current
code, not a proof that it is the paper's original working file. The sample-only runs after MBAL are BLOCKED by
design (9 corpus-wide claims need the full table); they show 0 FAIL and an identical Table 2.

---

## 3. Where MBAL belongs

| option | verdict | scientific reasoning |
|---|---|---|
| **A. main experiment** | **No** | The paper's RQs are about *cross-source* overlap, circularity and drift. MBAL is one dataset with a three-value method field: it cannot answer RQ2 (nothing to overlap or test for inheritance) and cannot answer RQ3 (no downstream value to drift). Only RQ1-style classification applies |
| **B. external validation** | **No** | (i) THEMIS was changed *in response to* MBAL (D1–D20), so MBAL is not held out; it cannot validate the tool it shaped. (ii) The headline outcomes (provenance unresolved, zero independent corroboration) are near-tautological for a single dataset, so they do not discriminate a working independence test from a broken one. (iii) There is no ground-truth outcome to score against. Calling it "validation" would overstate it |
| **C. case study** | **Yes, primary role** | A real, unfamiliar, large multi-chain dataset run through the same evidence questions; what it shows is descriptive (identifier integrity, source-field semantics, what evidence exists) plus an honest account of the method failing first and being repaired generically without moving any paper number |
| **D. limitation / stress test** | **Yes, secondary** | The scale envelope, the fail-then-fix history and the taxonomy gap belong in Limitations, stated as bounds |

**Recommendation: C, with D folded into §5.4.** It mirrors the decision already taken for
WalletClassification (an unresolved-provenance case study). Use the words *case study* or *unseen-dataset
application*, never *validation* or *benchmark*. Whether it fits the page budget is a separate question (§15).

---

## 4. Section-by-section ledger

Classes: KEEP, REWORD, ADD EVIDENCE, NARROW CLAIM, REMOVE, ADD LIMITATION, ADD MBAL VALIDATION. As decided in
§3, the last class is used in this report to mean "add MBAL *case-study* content". No claim is classified
REMOVE. "Num." = does an existing seven-source number change (none does; "NEW" = a new number would be added).

### Abstract and title

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| A1 | Title: "Auditing Public **Bitcoin** Attribution Labels…" | The measured study is Bitcoin-only; MBAL is a case study, not the corpus | KEEP | Do not retitle; "Bitcoin" is accurate for what is measured | No | — |
| A2 | 1,545,710 claims, roughly 1.5M addresses, 98.97%, 0.49%, 7,508, 98.6–99.8%, USD 1.101 billion, USD 112.4 million, 13.8%, 9.8x | All reproduce, 939/939 identical | KEEP | None | No | — |
| A3 | THEMIS "exposes provenance, overlap, conflict, coverage and conclusion drift instead of reducing reliability to one score" | MBAL ends with no reliability percentage and an evidence profile | KEEP | None. This sentence is the paper's thesis and MBAL supports it | No | — |
| A4 | (absent) | MBAL is the only unseen-data evidence | ADD MBAL VALIDATION | One optional sentence, only if §5.5 is added: "Applied to an unseen 10-million-row multi-chain file, the same questions found unverifiable Bitcoin identifiers and unresolved provenance, and supported no reliability conclusion." Abstract is already dense | No | OPTIONAL |
| A5 | Keywords: "Bitcoin attribution" | Scope unchanged | KEEP | Do not add "multi-chain" | No | — |

### 1 Introduction (contains the RQs and the contribution)

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| I1 | "…whether they agree independently. If one dataset copied another…" | Consistent with MBAL: a method-class field is not an independent source | KEEP | None | No | — |
| I2 | RQ1–RQ3 | MBAL cannot answer RQ2/RQ3 (single source, no value field) | KEEP | Do not add an RQ4; a case study is not a hypothesis | No | — |
| I3 | "the method itself **only requires a label, a source and, where available, a date**" | MBAL: a `source` column existed and was still a 3-value *method class* (`ground_truth`/`external`/`heuristic`), so provenance stayed unresolved for every claim. Identifiers must also be valid *on a stated chain*: Bitcoin rows 2.73% valid, overall 82.4%, and an EVM string is valid on four chains, so the chain must be stated | **NARROW CLAIM / REWORD** | Replace with what the method actually needs: an identifier valid on a stated chain, a label, and a declared source that says where the claim came from (a source that only names a method class leaves provenance unresolved and independence untestable), plus a date where available | No | **REQUIRED** |
| I4 | "Bitcoin is used as the empirical case because it has the deepest supply of open address-level attribution data" | Still true | KEEP | Optional pointer: "Section 5.5 applies the same questions to one unseen multi-chain file" | No | OPTIONAL |

### 2 Related work

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| R1 | Prior work handles conflicts, cleaning or benchmarks but not source independence; "neither provides a general rule for judging an arbitrary public label" | The sentence is about prior work. MBAL's own authors measure label error (3.0% on 16,060 checked records) which answers a different question from evidentiary basis | KEEP | None | No | — |
| R2 | (absent) | If MBAL is used it must be cited | ADD EVIDENCE | Add the MBAL article (He et al., *Blockchain: Research and Applications*, doi 10.1016/j.bcra.2026.100555, pre-proof) and the Kaggle release (version, date, CC0). One clause noting that its 3.0% error rate answers "how many labels are wrong", while THEMIS asks "what supports the label" | No | RECOMMENDED if §5.5 is added |

### 3 Methodology

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| M1 | "The unit of analysis is one claim: one source assigning one category to one address." | Implementation: a subject is `(chain, address)`; a claim is `(chain, address, label, declared source)`; a multi-label cell becomes one claim per token (MBAL: 607,165 rows, 6.07%). Identical for a Bitcoin-only corpus | REWORD (minor) | "…one category to one address on one chain" | No | RECOMMENDED |
| M2 | Taxonomy tiers; "Manual annotation is not automatically verified" | MBAL's `ground_truth` ("deemed highly trustworthy, so no further validation was needed") was mapped to evidence tier UNKNOWN for all sampled claims, not VERIFIED. Second, independent instance of the paper's own rule | ADD MBAL VALIDATION | One sentence (in §4.3 or the case study): a source-native "ground truth" label is a declared method, not verified provenance | No | RECOMMENDED |
| M3 | Conflict logic; agreement is chance-corrected; root-level resampling | MBAL: no conflicts can arise inside the file; against the reference sample 16 of 18 comparable subjects disagree (9 entity-type, 7 licit/illicit; corrected 2026-09-25, see `MBAL_VALIDATION_REPORT.md` §21), but that slice is unrepresentative | KEEP | None. Do not quote the 31 (§5, finding 9) | No | — |
| M4 | Three independence tests (containment, decoding undocumented fields, naming residue) | All three need ≥2 sources with identifiable roots. MBAL supplies neither: independence is "unresolved" (0 confirmed, 31 unresolved), never "independent" | ADD LIMITATION | State that the tests presuppose several sources and that a single dataset yields *unresolved*, not *independent* | No | RECOMMENDED |
| M5 | (absent) six distinct questions | Paper explicitly separates provenance, independence, corroboration; technical validity and forensic defensibility are not named | ADD EVIDENCE | Short paragraph or compact table separating: technical validity, label availability, provenance, independence, corroboration, forensic defensibility (§7) | No | RECOMMENDED |

### 4 Practical implementation

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| C1 | Corpus, Table 1, 25 roots (21 identified, 4 unresolved), "33 descriptors" | Reproduced live; unchanged | KEEP | None | No | — |
| C2 | "Five malformed Elliptic++ entries were removed…" | Supplementary screen in this audit (§5, X1): with THEMIS's current Base58Check/Bech32 validator, 1,497,074 of 1,497,106 normalised addresses (99.998%) pass; 32 fail (TagPack 10, Schnoering 14, Rodwald 8; none Elliptic++, Ransomwhere, WatchYourBack). No population-level case folding | ADD EVIDENCE | Optional one sentence reporting the screen as an *observation*. **Do not filter these 32:** that would change the corpus and every count | NEW (additive) | OPTIONAL |
| C3 | "Address normalisation also removes non-address marker characters…"; §5.1: "a provenance audit cannot be stronger than its address normalisation" | MBAL is the extreme case: 1,758,356 Bitcoin identifiers case-folded and unverifiable; 117 identifiers padded with whitespace (THEMIS trims and counts them, rejects zero-width characters) | ADD MBAL VALIDATION | Cite MBAL as the strongest support for that sentence | No | RECOMMENDED |
| C4 | Retrieval dates retained "because public label sets change over time" | MBAL file (Feb 2024) does not reproduce its paper's tables: 5 chains vs 4, ground-truth share 62.4% vs 37.7%, 413 vs 932/933 entities; no official file hash exists | ADD EVIDENCE | One sentence: version drift between article and artifact; artifact identified by size and SHA-256, not by assumption | No | OPTIONAL |
| C5 | "THEMIS uses two checks rather than one: regression tests … and a manuscript harness…" | The harness did its job: generic changes for MBAL left 939/939 paper values identical | ADD EVIDENCE | Optional clause | No | OPTIONAL |
| **T1** | "THEMIS is not designed to return a single 'reliable / unreliable' score. It keeps the evidence visible." | MBAL's final line: insufficient evidence for a forensic reliability conclusion; no percentage offered | KEEP | None | No | — |
| **T2** | "In the present study, THEMIS contains source adapters for the seven corpora; **adding another dataset requires an ingestion adapter, while the provenance, containment, conflict and drift logic remains unchanged**." | (i) The software now has an upload path with pre-flight schema inference and user mappings the paper does not mention. (ii) MBAL needed far more than an adapter: 20 defects (D1–D20), including chain-aware claim identity (D9), source-class ≠ provenance (D11) and an over-credit in the independence audit (D13). The last is real: two reference roots were credited as independent corroboration to a target whose own provenance was unresolved. (iii) The seven-source path is unaffected (§2) | **REWORD / NARROW CLAIM** | Restrict the "unchanged" claim to the seven-source path, and say an unseen file goes through a pre-flight that infers and value-validates column meanings and refuses to analyse what it cannot interpret | No | **REQUIRED** |
| T3 | Released package contents; derived table not redistributed | Superset now true (adds API, GUI, multi-chain, pre-flight). The tag `v1.0-paper` predates the generic fixes | REWORD (conditional) | If the paper cites the released code, name a release that contains what the paper describes (§9) | No | RECOMMENDED |
| T4 | "retains only quantitative results that remained stable in the correction run" | Unchanged | KEEP | None | No | — |
| V1 | §4.3: condition D is "highest *declared* confidence tier rather than verified ground truth" | MBAL `ground_truth` is a second example of a declared tier (M2) | ADD MBAL VALIDATION | Optional cross-reference | No | OPTIONAL |
| V2 | Anchor validation: intervals too wide for "dataset X is Y percent accurate" | MBAL: agreement with a reference source is not truth; 31 comparable subjects in 8.2M cannot support any rate | KEEP | None | No | — |

### 5 Discussion and results

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| S1 | 98.97% single-dataset; 15,413 multi-source; 7,845 / 429 / 7,112 / 27 (sum 15,413); Elliptic++ 4,030 / 0.49% / 189 / 65 / 47 / 7 / 8; 67.12%, 66.66%, 64.50% | Reproduced | KEEP | None | No | — |
| S2 | Counts are "an upper bound on corroboration" | MBAL: 31 apparent multi-source subjects, 0 confirmed independent | ADD MBAL VALIDATION | Cite in the case study, not here | No | OPTIONAL |
| S3 | No aggregate agreement percentage as headline | MBAL likewise offers none | KEEP | None | No | — |
| S4 | 67.0% of claims have no revision field; 99.9% of dated TagPack claims older than 3 years | MBAL has no timestamp at all: staleness "not applicable", not "stale" | KEEP | Consistent with "missing date = currency unknown" | No | — |
| S5 | §5.2 Rodwald single-letter code decoded by containment; Montréal recurrence 98.62–99.81%; Elliptic++ block 53.2% of claims | Reproduced. MBAL adds a contrast: its `source` field cannot be decoded this way (no upstream corpus, and it names a method, not a party) | KEEP + ADD MBAL VALIDATION | Keep all numbers. In the case study: "source-like field ≠ provenance root" appears in both studies | No | RECOMMENDED |
| S6 | §5.3 Table 2, Fig. 2, 24.2%, 21.8%, 5.1%, 9.8x, "lower bound, not a corrected estimate" | Reproduced byte-identically | KEEP | **Untouched** (§12) | No | — |
| S7 | §5.3 assumes a downstream forensic procedure | MBAL has no value field, so RQ3/drift cannot run on it | ADD LIMITATION | State in the case study that drift was not exercised | No | RECOMMENDED |
| S8 | §5.4 "properties of this corpus and this declared trust protocol, not population estimates for all public Bitcoin labels" | MBAL is one dataset; it does not turn results into population estimates | KEEP | Untouched; optionally add "and MBAL, a single further dataset, does not change that" | No | — |
| S9 | §5.4 threats list (Condition D declared, revenue inherited, taxonomy judgement, containment direction, unknown provenance) | Missing: identifier validity is syntactic only; EVM checksum absent; in-memory scale envelope; MBAL shaped the tool so it is not held out; Bitcoin-only reference corpus makes EVM claims incomparable; taxonomy maps only 41.7% of MBAL label instances | ADD LIMITATION | Add a compact paragraph (text in §11, B) | No | REQUIRED if §5.5 is added, otherwise RECOMMENDED |

### 6 Conclusion, 7 Future work, references

| ID | Current claim | Evidence | Class → impact | Recommended change | Num. | Priority |
|---|---|---|---|---|---|---|
| Cn1 | All headline numbers; "Public Bitcoin labels are often used as if the label itself were evidence" | Unchanged, Bitcoin-scoped | KEEP | None | No | — |
| Cn2 | "a consistent artifact can still be consistently wrong" | MBAL is a real instance: a consistently case-folded identifier column | ADD EVIDENCE | Optional example | No | OPTIONAL |
| Cn3 | "a reproducible way to ask what a label is supported by, whether apparent corroboration is independent, and how much a conclusion changes" | This *is* the evidentiary-basis framing | KEEP | Optional: name the outcome "a forensic reliability conclusion" once (§6) | No | OPTIONAL |
| Cn4 | (absent) | MBAL's bottom line | ADD MBAL VALIDATION | Optional closing sentence, only with §5.5 | No | OPTIONAL |
| F1 | Verified open anchor set as the next step | Still the binding constraint | KEEP | None | No | — |
| F2 | "keep the taxonomy parser and address-normalisation tests as first-class parts of the release" | Done and extended (chain, identifier, multi-label tests) | REWORD | Optional: say what now exists | No | OPTIONAL |
| F3 | "tested on other forensic tasks, especially sanctions-exposure scoring"; intake-time provenance checks | The multi-chain identifier layer now exists, but no EVM reference corpus, no EIP-55 in MBAL, no Tron/Solana adapter, in-memory only | ADD LIMITATION (as future work) | Add: EVM reference corpora / verified anchors, EIP-55 handling, disk-backed storage | No | RECOMMENDED |
| B1 | Reference list, 20 items | MBAL, Kaggle release, optionally EIP-55 | ADD EVIDENCE | Add only what §5.5 uses | No | RECOMMENDED if §5.5 |

---

## 5. New MBAL findings, ranked by what they can honestly carry

| # | Finding | Value | Caveat that must travel with it |
|---|---|---|---|
| 4 | **Bitcoin identifier integrity.** All 1,758,356 Base58 addresses are lowercase (97.2% of 1,808,605 Bitcoin rows); 788,231 contain `l`, which Base58 lacks, so folding is *proved*; 970,090 further fail the checksum. Only Bech32 survives (49,297 valid). Nothing repaired; no case-insensitive matching | **HIGH** | A property of this file (Kaggle v1, 2024-02-08), not of the paper's version. 1,104 reference addresses reappear only case-insensitively (diagnostic; never counted) |
| 10 | **Final verdict: insufficient evidence for a forensic reliability conclusion**, no reliability percentage | **HIGH** | Explicitly "what can be shown, not a judgement that labels are wrong" |
| 6 | **Source-method class not mistaken for provenance**; every root UNRESOLVED; `ground_truth` never becomes VERIFIED | **HIGH** (conceptual) | The rule is a configured threshold (≤12 distinct values over many rows); failure mode is conservative (unresolved, not independent); exercised on one real dataset plus synthetic tests |
| 1 | **Unseen dataset exposed generalisation failures.** Old THEMIS classified every MBAL ordering as "not cryptocurrency attribution data"; D1–D20 | **HIGH** as an honesty result | Mostly engineering (no EVM adapter, D1) but with method-level defects (D9, D11, D13). Report as *development finding*, not validation |
| 2 | **Generic fixes preserved the paper**: 939/939 identical; byte-identical CLI outputs | **HIGH** (reproducibility) | Regression evidence on a reconstructed table (§2) |
| 11 | **Paper vs downloaded artifact mismatch** (chains, categories, entities, source shares) | **MEDIUM-HIGH** | Which version explains it is unresolved; the article is also internally inconsistent (933 vs 932 entities). State neutrally: "the file did not reproduce the article's tables, so label-quality statements were not transferred" |
| 3 | **10M-row multi-chain file analysed completely** (8,239,794 valid rows, 8,856,557 claims, nothing truncated) | **MEDIUM** | Needed a raised local config; ~24.7 GB peak RAM (~2.5 KB/row), one core, 142–147 s. **The shipped default refuses it** (256 MiB, 1,000,000 rows, HTTP 413). First Claims page 37 s, first Trust query 76 s. Not a scalability claim |
| 5 | **EVM checksum limitation**: all 8,190,444 valid EVM identifiers are single-case, none encodes EIP-55 | **MEDIUM** | Reported as "checksum not encoded", not "failed"; lowercase is not invalid. Consequence: a mistyped address cannot be detected |
| 7 | Provenance unresolved for every claim | MEDIUM | Trivial for a single dataset; present as consequence |
| 8 | Independent corroboration zero | LOW as a finding | By construction ("nothing to corroborate with"); do **not** present as an empirical discovery |
| 9 | Only 31 of 8,239,773 subjects comparable with reference data | LOW; **unsafe to quote** | Computed against the 268,891-claim bundled *sample* (all Bitcoin), not the 1,545,710-claim corpus; all 31 are native SegWit *because* case-folding destroyed the rest. To use it, rerun against the full retained table |

### Additional observation from this audit (X1, not in the MBAL reports)

Applying MBAL's identifier check to the seven-source corpus (retained table, THEMIS's current validator, the
paper's own address normalisation): **1,497,074 of 1,497,106 distinct addresses (99.998%) pass; 32 fail.**
By source: Elliptic++ 0/822,937, Ransomwhere 0/11,186, WatchYourBack 0/309 (all 309 valid after the marker
strip); Rodwald mixers 7, Rodwald ransomware 1, Schnoering 14, TagPack 10. Only 4 of 1,428,516 Base58-shaped
addresses are all-lowercase (2 valid, checksum-passing; 2 invalid), so nothing resembles MBAL's population
folding. This contrasts the two datasets on the same yardstick and is additive. It was run ad hoc, is **not**
in `paper_claims.yml`, and would need a harness claim before any number is printed. The 32 are left in the corpus
by design (§12).

---

## 6. Does the paper imply "THEMIS tells whether a dataset is reliable"?

**No.** Evidence: the abstract says "instead of reducing reliability to one score"; §4.2 says THEMIS "is not
designed to return a single 'reliable / unreliable' score"; the central question is "how much evidential weight
can those labels reasonably carry?"; §4.3 refuses "dataset X is Y percent accurate". The name still contains
"Trust". So no conceptual revision is *required*. A small *recommended* addition, in manuscript style, in §4.2
or the Conclusion: THEMIS reports the evidentiary basis for or against a forensic reliability conclusion, and
where that basis is thin it says so rather than producing a verdict. The MBAL outcome is the worked example.
The README's research-question wording ("How reliable is publicly available…") is broader than the paper's and
is a documentation matter, not a manuscript one.

## 7. The six distinctions

| question | in the paper today | in MBAL | note |
|---|---|---|---|
| technical validity | implicit (5 Elliptic++ strings removed; normalisation) | Bitcoin 2.73% valid, EVM ≥ 99.98%, overall 82.40% | seven-source: 99.998% (X1) |
| label availability | coverage and claims counts | every row has a category; taxonomy maps 41.7% of label instances; entity on 34.47% of rows | |
| provenance | explicit (25 roots) | none beyond a method class; all UNRESOLVED | |
| source independence | explicit (containment, decoding) | untestable | |
| corroboration | explicit (98.97% single-dataset) | 31 comparable (unsafe figure), 0 confirmed | |
| forensic defensibility | implicit ("evidential weight", drift) | INSUFFICIENT EVIDENCE for a reliability conclusion | |

MBAL is the cleanest demonstration that the first two do not imply the last four: 100% label coverage sits
beside 2.73% valid Bitcoin identifiers and zero resolved provenance. **Recommend adding this ladder** (M5),
either as a short paragraph or as the table in §14.

## 8. Scale, reproducibility and generalisability wording

**Scale.** The paper makes no scale claim; keep it that way. If MBAL is included, the only defensible
statement is a measured envelope: "default upload limit 256 MiB and 1,000,000 rows; a 10,000,000-row file was
analysed once under a raised local configuration, peaking near 24.7 GB of RAM (in-memory, single process, no
disk-backed storage)". **Forbidden wording:** "scales to", "large-scale support", "handles arbitrary size",
"efficient", "production-ready".

**Reproducibility.** The seven-source result is reproducible (PASS; retained table rebuilt byte-for-byte from
raw files). MBAL is *not yet* reproducible in the paper's sense: its numbers come from reports and evidence
outside the repo; the raw file has no official checksum (identity rests on modification date and a recorded
SHA-256 `0dc4c04a…2a57`); the run needs a raised config and ~25 GB RAM. Before any MBAL number enters the paper:
add a script (for example `themis reproduce mbal --file …`) and entries in `paper_claims.yml` with PDF
locators, so it obeys the same rule as every other number. Otherwise print only qualitative statements.

**Generalisability.** Claim generalisation of the *questions* (they transferred to a structurally different
dataset), never of the *results*. One extra dataset is n = 1.

---

## 9. Consequences for artifacts if the manuscript changes

- `paper_claims.yml` pins the PDF sha256 and every printed value has a PDF locator: any edit changes the hash and
  needs the manifest re-pinned and `verify-paper` rerun (107 locators today).
- The tag `v1.0-paper` and its ZIP predate the MBAL generic changes. A revised paper describing multi-chain or
  pre-flight behaviour needs a new tag and ZIP (paper is not shared, so no public inconsistency yet).
- `REPRODUCE.md` and README already state the 256 MiB / 1,000,000-row defaults and the 10M scale-test
  status; the paper must not say anything stronger.
- The paper PDF and manuscript source stay out of the repo and release (standing rule).

---

## 10. A. Mandatory paper changes

Only two, both wording, both narrowing an unsupported generality:

1. **I3** (§1): rewrite "the method itself only requires a label, a source and, where available, a date".
2. **T2** (§4.2): restrict "adding another dataset requires an ingestion adapter, while the … logic remains
   unchanged" to the seven-source path; mention the pre-flight for unseen files.

Conditional: **S9** (limitations paragraph) becomes REQUIRED if any MBAL content is added.

## 11. B. Optional strengthening changes

In rough order of value: M5 six-question ladder; M2/V1 `ground_truth` ≠ verified; C3 identifier-integrity
support for "no stronger than its normalisation"; S5 source-field ≠ provenance root; S7/M4 limits of the drift
and independence tests; C2 seven-source identifier screen (needs a harness claim); C4 version drift; A4/Cn4
abstract and conclusion sentences; F2/F3 future-work update; R2/B1 citations.

Candidate limitations text (S9), for approval:
"Identifier validity is checked syntactically only. In the unseen file, 97% of Bitcoin identifiers were
case-folded and unverifiable and no EVM identifier carried a checksum. Analysis is in-memory: a 10-million-row
file needed about 25 GB under a raised local configuration, and the default service refuses files above
1,000,000 rows. THEMIS was adjusted after exposure to this file, so it is a case study, not held-out
validation. The reference corpus is Bitcoin-only, so no EVM claim could be cross-checked."

## 12. C. Statements that should remain untouched

Every number in the abstract, Table 1, §5.1–§5.3, Table 2, Fig. 1 and Fig. 2, and the conclusion's figures. The
sentences: "THEMIS is not designed to return a single 'reliable / unreliable' score"; "This is a coverage
result, not a correctness result"; "The lower figure should not be read as a corrected ransomware-revenue
estimate"; "Condition D is based on declared confidence, not independently confirmed ground truth"; "Unknown
provenance is kept separate from shared provenance"; "properties of this corpus and this declared trust protocol,
not … population estimates for all public Bitcoin labels"; the title, keywords, RQ1–RQ3, the four trust
conditions and the data-availability statement. The 32 invalid identifiers (X1) are **not** removed.

## 13. D. Proposed new subsection outline (§5.5, case study; about 350–450 words)

**5.5 Case study: an unseen multi-chain dataset**
1. *Purpose and status.* One 10,000,000-row, five-chain file (MBAL, Kaggle v1, CC0), applied after the main
   study; not held out, because the tool was adjusted on it. It tests the questions, not the results.
2. *What was run.* The same evidence questions via the pre-flight and audit; identity by SHA-256; the article
   and the file did not agree, so article-level label-quality statements were not transferred.
3. *What THEMIS established.* Identifier validity by chain (Bitcoin 2.73%, EVM ≥ 99.98%); the Base58 case
   folding; no EVM checksum; source field is a method class, so provenance unresolved for every claim;
   independence untestable.
4. *What it did not establish.* Truth of any label; agreement with reference data (not estimable); drift (no
   value field).
5. *Outcome.* Insufficient evidence for a forensic reliability conclusion, "a statement about what can be
   shown, not a judgement that the labels are wrong".
6. *What it changed in the tool.* Generic repairs (EVM validation, chain-aware identity, order-robust
   profiling, value-checked mappings, an independence over-credit) with 939/939 paper values unchanged.
7. *Bounds.* Scale envelope in §8 wording; taxonomy gap; Bitcoin-only reference corpus.

## 14. E. Figures and tables

- **Recommended: one compact table** (Table 3), rows = the six questions, columns = seven-source study | MBAL
  (as in §7). Cells that still need harness backing: X1 (99.998%), and every MBAL figure. Drop the "31" cell.
- **Optional figure:** identifier validity by chain (Bitcoin 2.7% against 99.98%+ for four EVM chains), one bar
  chart; low cost, high clarity, but page-costly. Prefer the table.
- **No new revenue or drift figure.** MBAL has no value field.
- Existing Tables 1–2 and Figures 1–2: unchanged.

## 15. F. Expected page-count impact

Measured basis: 6 A4 pages at 10 pt; pages 1–3 carry ~900 words each; page 6 carries 431 words including the
reference list, so roughly **0.4–0.5 page (about 400 words) is free**. The venue's page limit is not recorded
anywhere in the repo, so **the author needs to state it**; earlier builds ran to 8 and 10 pages in the Springer
template.

| scope | added | result |
|---|---|---|
| mandatory only (I3, T2) | about 80–120 words | stays **6 pages** |
| mandatory + M5 + limitations paragraph + short §5.5 (about 250 words, no table) + 2 references | about 450 words | **6 pages, page 6 nearly full** |
| full §5.5 (about 450 words) + Table 3 + limitations + citations + abstract and conclusion sentences | about 800–900 word-equivalents | **7 pages** (about 6.5 filled) |

Rebuilds change the PDF hash (embedded date), so the manifest must be re-pinned after the final build.

---

## 16. Decisions for the author

1. Include MBAL at all, or limit the paper to the two mandatory rewordings? (Scientifically the two rewordings
   are needed either way.)
2. If included: is the venue limit 6 pages, more, or firm?
3. Approve role **C + D** and the wording "case study", not "validation"?
4. Approve adding a reproducible MBAL script and manifest entries before any MBAL number is printed?
5. Approve reporting the seven-source identifier screen (X1) as a new, additive claim?
6. A new release tag after any manuscript edit (T3, §9)?
7. Whether to notify the MBAL authors of the Bitcoin case-folding in the Kaggle file (courtesy; outside the paper).

**Stopped here. No manuscript edit, no commit.**
