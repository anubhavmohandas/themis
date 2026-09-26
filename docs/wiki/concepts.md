# The ideas behind THEMIS

[← Wiki home](README.md) · [Project README](../../README.md)

**T**rust and **E**vidence-based **H**euristic **M**ethod for **I**nvestigative
**S**ource Assessment — provenance-aware auditing of public cryptocurrency
attribution labels (Bitcoin, and the EVM chains in `themis/config/chains.yml`; the paper's
seven-source study is Bitcoin), built alongside the paper *Provenance Before Precision: Auditing Public
Bitcoin Attribution Labels and Their Effect on Forensic Conclusions* (ICISHCT
2026, under review).

## What THEMIS is

A blockchain records transfers, not identities. Everything said about *who*
controlled an address is a claim layered on top, and those claims come from a
short list of public corpora reused without much scrutiny of where they came
from. THEMIS audits them: what corroborates what, which agreement is inherited
rather than independent, how much has no cross-source comparison at all, and
what the choice of trust rule does to a downstream forensic figure.

It is a measurement tool, not a labeling tool. It does not decide whether an
address is "really" a scam, a mixer or an exchange; it measures how well the
*public evidence for that decision* holds up — its provenance, independence,
currency, and sensitivity to what you are willing to trust.

The analysis engine (`themis/taxonomy.py`, `provenance.py`, `analysis.py`,
`trust/`) carries no dataset-specific logic. Every source's provenance rule,
category and trust policy lives in `themis/config/` (YAML). Reproducing the
paper is one configuration of that engine.

## Research question

> How reliable is publicly available cryptocurrency attribution data for
> forensic investigation and blockchain tracing?

- **RQ1** — can a public label be classified by reproducible evidence-quality
  rules rather than an unstated notion of "trustworthy"? (`themis taxonomy`, `explain`)
- **RQ2** — how much do the major open sources overlap, how often do they
  conflict, and how much of the agreement is independent? (`themis audit`)
- **RQ3** — how far does a forensic conclusion move under different trust
  rules, and at what coverage? (`themis drift`)

`themis bootstrap` and `themis anchors` quantify how much confidence either
answer can support.

## What THEMIS does not claim

- **Public ≠ reliable.** Being published says nothing about accuracy.
- **Supported ≠ true.** Passing a trust condition means the evidence meets that
  condition's bar, not that the label is correct.
- **Agreement ≠ independent corroboration**; **multiple datasets ≠ multiple
  independent sources**; **high overlap ≠ proof of copying.**
- **Unknown ≠ independent, unknown ≠ shared.** An unresolved provenance root is
  an unknown relationship, never counted as a distinct additional source and
  never as a shared one.
- **Unverifiable ≠ false; no date ≠ stale.** A claim with no revision date is
  `currency-unknown`.
- **Coverage ≠ accuracy.** `themis drift`'s strictest rule keeps 13.8% of
  addresses; that is a coverage trade-off, not a more accurate estimate of the rest.
- **Declared confidence ≠ verified ground truth.** A source calling its output
  "manually verified", or GraphSense tagging a claim `forensic`, is a statement
  about that source's process, not a check THEMIS has performed. Source-native
  confidence is preserved and never mapped onto a THEMIS tier.
- **A reference corpus ≠ ground truth.** `themis anchors` reports *agreement with
  a small open anchor set*, not source accuracy, and refuses to estimate a source
  that rests on fewer than two independent provenance roots.

A forensic result without its trust rule and coverage is incomplete; every
figure this tool prints carries both.

## Evidence taxonomy

- **Tiers** — `verified` (provenance ends in evidence a third party could
  re-check: seized data, a court record, a sanctions designation, an issuer's
  self-disclosure); `derived` (heuristic propagation or curated annotation);
  `unverified-report` (crowd report, forum post, automated extraction);
  `unknown` (an upload with no declared methodology — never silently `derived`).
  A source's own "manually verified" declaration does not by itself reach
  `verified`; a *record* whose root is re-checkable (an OFAC listing) does.
- **Flags** — `currency-unknown`, `stale`, `conflicting`, `circular`; orthogonal
  to the tier.
- **Conflict logic** — exact / hierarchical refinement / entity-type conflict /
  licit-illicit conflict / incomparable. *Incomparable* means fewer than two
  datasets contributed a category the taxonomy can interpret; one opinion is not
  agreement with itself.

## Provenance terminology

- **Claim** — one source asserting one category about one address; the unit of analysis.
- **Root** — where a claim's evidence originates, which is not the dataset that
  republished it. Assigned from a source's declared rule, **per record where
  records differ** (WatchYourBack cites an external URL on every row, so its
  Treasury-cited records are rooted at OFAC and only the rest at WatchYourBack).
- **Resolved / native / verified / unresolved** — a known origin; the source *is*
  that origin; the origin is re-checkable; an unknown relationship.
- **Circular / inherited** — apparently independent claims that share one resolved root.
- **Structured label** — a `type:entity` raw label (`onlinewallet:flexcoin`); its
  category-shaped prefix is canonicalized like any alias and the entity kept.

## Trust-rule interpretation

`themis drift` re-runs one task (ransomware revenue) under four rules: **A** naive
union, **B** address-level deduplication (the baseline), **C** inherited claims
collapsed to their root, **D** the addresses an anchor set names. D is *the
highest declared confidence present*, not verified ground truth: in the paper
corpus it is exactly the addresses TagPack tags `confidence: forensic` (plus
WatchYourBack's ransomware annotations), and almost all of it is one upstream
study. Read the ratio and the coverage together; neither means anything alone.
