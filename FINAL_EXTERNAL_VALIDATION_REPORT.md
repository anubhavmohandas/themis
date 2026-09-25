# Final external validation report

Written for: the THEMIS author, ahead of the paper's final revision.

**Dataset:** Forta Foundation `labelled-datasets`, `labels/1/etherscan_malicious_labels.csv` (selection and rejection trail: `FINAL_DATASET_SELECTION_REPORT.md`).
**Question:** does THEMIS handle a real, previously unused attribution file without dataset-specific tuning, and what does it establish about it?

**Read this first.**

1. One genuine generic defect was found and fixed (section 21): the internal-consistency check silently skipped subjects whose labels the taxonomy cannot place, so a bare zero hid 13 subjects that carry two different labels. One wording line in the Address Inspector was also corrected.
2. Nothing dataset-specific was added to production code. No Forta string, column name or label appears in `themis/` or `frontend/src`.
3. The seven-source reference corpus is Bitcoin-only and this file is Ethereum, so the cross-source layer was **not exercised** (section 17). That limits what this validation shows.
4. 80.33% of the addresses also occur in MBAL, which THEMIS processed earlier (selection report, section 5). Whether that disqualifies "unseen" is the author's call.

Evidence lives outside the repository, beside it: `forta_evidence/` (raw API JSON, GUI text and screenshots, greps, timings) and `forta_testdata/` (the two driver scripts). The frozen input is `final_dataset_testdata/forta/`. No Forta row is committed.

## 1-3. Candidate search, rejections, selection
See `FINAL_DATASET_SELECTION_REPORT.md`. HackForums (arXiv:2608.13930) was the best fit but its repository holds only a README; no data exists to test.

## 4. Proof it was previously unused
0 hits for 15 identifying terms in the working tree, all 108 revisions (`git grep`, `git log -S/-G`), and every sibling evidence directory. `forta_evidence/unseen_proof*.txt`. Status: PREVIOUSLY UNUSED as a dataset; address-level overlap with MBAL noted.

## 5-7. References, licence, file identity
Repo `github.com/forta-network/labelled-datasets`, commit `40a9c2f2bd7e9ddfdd0f3540db589f0288e1e88a` (2023-01-26). No paper, no DOI. MIT, Copyright 2022 Forta Foundation. Public: yes. Research-usable: yes. Redistributable: **unresolved** (the Etherscan labels' own terms are not addressed). File 678,922 bytes, 7,780 rows, SHA-256 `9a787753c7caf64d506de755830ac85d05f21973939763251f54c38136505f42`. Used unmodified, no sampling (the file is under every limit).

## 8. Schema (upstream vs THEMIS)
| column | upstream documentation | THEMIS mapping | confidence |
|---|---|---|---|
| `banned_address` | none for this file | claim subject, address | 0.88 |
| `wallet_tag` | none | attribution label | 0.879 |
| `data_source` | none; README says the addresses carry Etherscan labels `exploit`, `heist`, `phish-hack` | declared source, with a warning that 3 values name a class, not a provenance | 0.88 |
| category, entity, actor, timestamp, chain | absent | unmapped | |

## 9. Raw inspection (independent of THEMIS)
UTF-8, no BOM, LF, 4 quote characters, 0 non-ASCII bytes. 7,780 rows, 0 malformed rows. Empty cells: `wallet_tag` 7, others 0. Every identifier is `0x` plus 40 hex; no zero address. 6,998 rows all-lowercase, 782 mixed-case, 0 all-uppercase. 7,259 distinct addresses when case-folded; 521 addresses occur twice and **in all 521 the two rows differ only in letter case** (0 byte-identical rows). No address occurs under more than one `data_source`. `data_source`: phish-hack 7,570, exploit 139, heist 71. `wallet_tag`: 7,126 distinct strings; 90.3% match `Fake_Phishing<number>`, i.e. a sequence label, not a category. No timestamp, entity, chain or category column. Ground-truth arithmetic: 7,780 − 7 (no label) − 2 (bad EIP-55 checksum) − 506 (repeats) = 7,265 claims; 7,259 − 7 = 7,252 addresses; 13 addresses carry two different tags.

## 10. Provenance methodology
The invariants were applied as written: a source-like string is not a provenance root; different source strings are not independent roots; a label prefix is not a source; licence is not provenance. `etherscan-*-list` names a list, not where each claim came from. Result: provenance **UNRESOLVED** for every claim.

## 11-12. Reference overlap and independence
Overlap with the bundled reference sample: 0 / 7,259, structurally (0 of 228,775 reference addresses are EVM-shaped). Independence from the reference corpus: **unresolved by measurement**, plausible on declared provenance. MBAL overlap 5,831 (80.33%): material, dependency suspected. dawsbot 10 (0.14%).

## 13. Preflight (backend and GUI compared)
Without a chain: `dataset_state supported_attribution_data`, `status blocked`, blocker `chain_required`: the identifiers validate on ethereum, bnb_smart_chain, polygon and avalanche_c and the file names no chain. This is correct behaviour, not a defect: validation is chain-specific and is not skipped. The chain is stated by the README's path `labels/1/` (Ethereum mainnet), so choosing `ethereum` is a documented external fact supplied by the user, not a wrong mapping. Both the API (`chain=ethereum`) and the GUI dropdown then gave `ready`, chain source `user`, confidence 1.0, identical mapping and identical warnings. No mapping was edited.

## 14. Identifier validity
7,778 of 7,780 identifiers pass (99.97%). EIP-55: 6,998 not encoded (lowercase), 780 valid, 2 invalid, and the 2 rejected are the two THEMIS names. I re-derived this with an independent pure-Python Keccak-256 (self-tested on the empty-string vector); it matched exactly. Syntax check only: a valid identifier is not a valid attribution.

## 15. Taxonomy
**0 of 7,265 claims interpretable**: every claim is `canon: unknown`, polarity unknown, evidence tier unknown. The bundled taxonomy has no phishing/exploit vocabulary and `Fake_Phishing<n>` is a sequence label. This is a measured limitation, not a defect: the taxonomy is config-driven and I did not extend it (that changes the paper's configuration hash and is a scientific decision). Consequently THEMIS says nothing about what these labels mean.

## 16. Internal consistency (separate from cross-source conflict)
After the fix, measured on 7,265 claims and confirmed against raw:

| bucket | n |
|---|---|
| repeated observation | 0 |
| repeated same label | 0 |
| compatible multi-label claim | 0 |
| internal contradiction | 0 |
| **uninterpretable multi-label** (new) | **13** |

The 13 subjects are exactly the 13 the raw file has (set equality checked). Chain-aware: subjects are `ethereum:<address>`, and the same address on two chains stays two subjects (unit test). The zeros are measured, not unexecuted: the check ran over 7,252 subjects; the four zeros are zeros over 0 interpretable multi-claim subjects. The 506 repeats do not appear under "repeated observation" because ingestion collapses them first; they are reported as `duplicate claim: 506` in rejected rows (all 506 are case variants of one address).

## 17. Reference comparison
`reference_match: computed, n_matched 0`. Agreement `not_applicable` ("no target address had a matching reference claim"). Conflicts `not_applicable` ("which is different from finding none"). Four of six trust rules `not_applicable`; the other two keep 0 / 7,265. Nothing about agreement, conflicts or shared provenance was measured here. The target-audit logic (`classify_target_address`) was not exercised for the same reason.

## 18. GUI ↔ backend
Same SHA-256, same input, separate analyses. Leaf-by-leaf: `summary` 755 values, 2 differences; `conflicts` 12 values, 1 difference (page size); `provenance` 287 values, 16 differences; `trust-coverage` 61 values, 0 differences. Every difference is the `source_id`: the GUI derives it from the file name, my API script used the default. No number differs. Checked on screen against the JSON: 7,265 claims; 7,252 targets; 515 rejected (506/7/2); declared sources 7,061 / 134 / 70; 780/6,998/2 checksum states; 0 / 7,252 reference match; 100% unresolved. Address Inspector for a two-label address shows both records "not merged". Console errors 0, page errors 0.
**Gap (not fixed):** the GUI does not display `internal_consistency` at all (no reference in `frontend/src`). The numbers exist in the API and the `analysis_summary.json` export, so nothing is GUI-only, but a person using only the GUI cannot see section 16. Whether to add a panel is a feature decision.

## 19. Scale
Within shipped limits; no product default was changed or raised. API: preflight 0.1 s, analysis job 2.1 s, 7,265 claims. GUI analysis 0.5 s. In-process ingest 0.31 s, 39 MB peak RSS (that Python process, no reference loaded). The API process stood at 448 MB after several analyses, mostly the bundled reference sample; not attributable to this file. Query latency: claims 3.7 ms, summary 2.3 ms, provenance 5.7 ms, conflicts 0.9 ms, trust 2.7 ms, address 1.4 ms. This file is 679 KB, so it says nothing about large-scale behaviour (MBAL and BitcoinHeist covered that).

## 20-21. Defects and fixes
**D1 (genuine, generic).** `taxonomy.internal_consistency` dropped any multi-claim subject whose claims were all `canon: unknown`, and counted `unknown + mapped` as "repeated same label". Its own docstring said every multi-claim subject lands in exactly one bucket. THEMIS's own convention elsewhere is to say `not_applicable` rather than show 0 for an empty denominator. Real trigger: 13 addresses, each with two different Etherscan tags.
Process followed: reduced to synthetic fixtures with generic labels (`code-A`, `code-B`, `exchange`); 4 tests written and confirmed failing; fixed generically in `themis/taxonomy.py` (a fifth outcome `uninterpretable multi-label`; identical unmapped claims count as a repeat; unmapped-plus-mapped is no longer "same label"); the same file was rerun.
**One existing test was changed, on purpose.** `test_unmapped_labels_contribute_no_interpretable_opinion` asserted all buckets sum to 0, which pinned the silent behaviour. It now asserts the four interpretable buckets are 0, and a new test asserts the fifth is 1. This reverses an earlier design decision for this one case; the author should confirm they agree.
**D2 (wording).** Address Inspector said "single-source: nothing to compare" beside an address holding two different records. Changed to "single-source: no cross-source comparison possible" (`frontend/src/pages/Address.jsx`).
Not defects: the chain-required block (correct), 0% taxonomy interpretation (limitation), 0 overlap (structural).

## 22. Tests
Baseline `700 passed, 7 skipped`. After: `704 passed, 7 skipped` (4 new, run twice, the second after the wording change). Frontend build succeeds. Browser E2E 18/18, run twice (after the taxonomy fix, and after the wording change). The E2E ran against my own API on port 5002 because port 5001 was held by an older THEMIS process I did not start, which I left alone.

## 23. Paper regression
`themis drift`, `anchors`, `explain 14BWrn1…`, `bootstrap --both`: byte-identical to `expected_output/` and to the previous session's runs. `themis audit`: differs from `expected_output/audit.txt` only in its first `note:` line, the stale wording that predates this work and is identical to the previous session's output. `themis reproduce-paper`: **BLOCKED**, 0 mismatches (20 PASS, 0 FAIL, 9 NOT REPRODUCED), because no full-corpus build exists on this machine. The frozen baseline (`impact-audit-e428b60`) was a FULL_CORPUS PASS 29/29, so it is not comparable. Like-for-like control: the same command on a pristine worktree of HEAD `d901c2e` (removed afterwards) also gave BLOCKED; 35 artifacts (all metrics, tables, anchors, bootstrap bounds, drift, RQ1) are byte-identical; the other 17 differ in run id, git-dirty flag, absolute paths, timestamps, timings and figure IDs (the six I opened confirm this; the figure PDF/SVGs I did not open). Result: no unexplained seven-source numeric change. The current commit is not `PASS` on the full corpus and cannot be re-shown here.

## 24. What THEMIS establishes
Chain-ambiguous EVM identifiers are stopped until the chain is stated. 7,780 rows reduce to 7,265 distinct claims over 7,252 addresses, and the arithmetic matches an independent count. Two identifiers fail EIP-55. Case-variant repeats are collapsed rather than double-counted. The declared source column is recognised as a class of evidence, not a provenance. No claim has a timestamp, so currency is not computed. 13 addresses carry two different labels. None of this needed dataset-specific logic.

## 25. What it cannot establish
Whether any address is phishing, an exploit or a heist. Who controls it. Whether Etherscan's tag was right. Independence from anything (provenance is unresolved). Anything about agreement or conflict with the reference corpus. Whether a label such as `Fake_Phishing3901` means anything to the bundled taxonomy (it does not). Redistribution rights.

## 26. Final interpretation
This is a list of Ethereum addresses that Etherscan tagged, relayed through Luabase and Forta, with no per-claim source, no date and no evidence attached. THEMIS handles it correctly, honestly reports that it can establish almost nothing about its reliability, and found one real gap in doing so. Overclaim audit of every screen and API string that contains reliable / trust / verified / accurate / ground truth / independent / confirmed / legitimate / forensic (30 distinct strings): all are negations, definitions or counters at 0 ("not independent", "never counted as independent", "not a verification", "Verified 0.00%"), except the one corrected in D2. Open wording risk, left unchanged as an author decision: the product titles "Dataset reliability profile", "Attribution reliability" and "Trust Analysis" sit above a page that here reports 0% resolved provenance.

**Stopping rule.** Its stated conditions hold: no unresolved generic defect, GUI and backend agree, the paper commands are byte-identical to the frozen baseline and the sample-only `reproduce-paper` is unchanged. Subject to the two caveats above (80.33% address overlap with MBAL; cross-source layer unexercised because the reference corpus is Bitcoin-only), **DATASET TESTING IS COMPLETE.** The next task is the research paper's final revision. I have not searched for another dataset and have not started a paper edit.

## Uncommitted
Working tree: `themis/taxonomy.py`, `tests/test_internal_consistency.py`, `frontend/src/pages/Address.jsx`, and these two reports. Nothing is committed.
