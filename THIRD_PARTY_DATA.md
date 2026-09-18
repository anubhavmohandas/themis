# Third-party data

THEMIS's own code license is a separate question, tracked in `LICENSE` (not
yet added — see README §11). This document covers only the seven public
datasets `demo_data/` derives from.

**What's actually bundled**: `demo_data/observations_sample.csv.gz` and
`ground_truth.csv` contain *normalized, derived* rows (address, canonical
category, provenance fields) produced by THEMIS's own ingestion pipeline —
never the source's original file verbatim, and never anything beyond what
each source itself publishes as address/label pairs (no transaction graphs,
no raw text beyond the label field). All license findings below were
confirmed 2026-09-18 directly against each source's own repository, Zenodo
record, or publication — not assumed from a source's general reputation.

**No legal conclusion is drawn here.** Where a source's redistribution terms
are not directly confirmed, that is stated plainly as `UNCONFIRMED`, and the
conservative action (verify with the source's authors before further
redistribution) is the author's to take, not this document's to decide.

| Source | Citation | License | Retrieval date | Redistribution status | Raw data included? | Transformed data included? | Notes |
|---|---|---|---|---|---|---|---|
| GraphSense TagPack | GraphSense TagPack collection (github.com/graphsense/graphsense-tagpacks) | MIT (repo's own LICENSE file) | 2026-09-18 | **CONFIRMED** — MIT permits redistribution/derivatives | No | Yes | 32.30% of corpus claims. Per-tag GraphSense `confidence` id survives in `subcat` but isn't yet used to re-tier evidence (see README §13). |
| Schnöring et al. | Schnoering & Vazirgiannis, Bitcoin transaction-graph dataset with entity labels (Zenodo DOI 10.5281/zenodo.22239038) | CC BY 4.0 (Zenodo record) | 2026-09-18 | **CONFIRMED** — CC BY permits redistribution/derivatives with attribution | No | Yes | 6.72% of corpus claims. |
| Ransomwhere | Crowd-sourced ransomware tracker (ransomwhe.re; Zenodo DOI 10.5281/zenodo.6512122) | CC BY (Zenodo record) | 2026-09-18 | **CONFIRMED** — CC BY permits redistribution/derivatives with attribution | No | Yes | 0.72% of corpus claims. Manually reviewed submissions, but platform-level review, not independent re-verification — see `config/sources/ransomwhere.yml`. |
| Elliptic++ | Elmougy & Liu, "Elliptic++: A Graph Network of Bitcoin Blockchain Transactions and Wallet Addresses" (arXiv:2306.06108); github.com/git-disl/EllipticPlusPlus | **UNCONFIRMED** — the dataset's own repo states no explicit license, only a citation request; the base Elliptic dataset it extends is separately CC BY-NC-ND 4.0 elsewhere, not confirmed to also cover Elliptic++'s own address data | 2026-09-18 | **UNCONFIRMED** | No | Yes | **Largest single source: 53.24% of all corpus claims.** Verify directly with the dataset's authors before further redistribution. |
| Rodwald (ransomware corpus) | Rodwald, "Preparing a Dataset of Ransomware BTC Addresses for Machine Learning Purpose" (Springer, 978-3-031-61857-4_22) | **UNCONFIRMED** — paper is paywalled (Springer); no license text retrievable from the author's data-hosting site | 2026-09-18 | **UNCONFIRMED** | No | Yes | 3.26% of corpus claims. |
| Rodwald (mixer corpus) | Rodwald, "Preparing a Dataset of Mixers BTC Addresses for Machine Learning Purpose" (Springer, 978-3-031-92734-8_19) | **UNCONFIRMED** — same as above | 2026-09-18 | **UNCONFIRMED** | No | Yes | 3.74% of corpus claims. |
| WatchYourBack | "Watch Your Back: Identifying Cybercrime Financial Relationships in Bitcoin through Back-and-Forth Exploration" (CCS'22); github.com/cybersec-code/watchyourback | GPL-3.0 confirmed for the **analysis code**; not separately confirmed for the address/tag **data** specifically | 2026-09-18 | **PARTIALLY CONFIRMED** (code only) | No | Yes | Smallest source (0.02% of corpus claims, 309 addresses) — lowest individual risk by volume, but GPL-3.0 is copyleft. |

## Summary

- **Confirmed permissive**: TagPack, Schnöring, Ransomwhere — together 39.74%
  of the corpus's claims (32.30% + 6.72% + 0.72%).
- **Unconfirmed, largest exposure**: Elliptic++ (53.24% of claims) and both
  Rodwald corpora (7.00% combined). These should be verified directly with
  their authors before the bundled sample is redistributed further.
- **Partially confirmed, immaterial size**: WatchYourBack (0.02% of claims;
  code license confirmed, data license not separately confirmed).

## Recommended conservative release strategy

Until Elliptic++ and Rodwald's status is confirmed, a public release
artifact should either:

1. Obtain explicit confirmation from those authors and record it here, or
2. Replace those rows in the bundled sample with download/reconstruction
   instructions (source URL, retrieval steps, expected row counts) plus
   checksums, rather than shipping the derived rows directly, or
3. Ship a smaller synthetic/demo substitute for those two sources and keep
   the full sample available only to reviewers who've separately confirmed
   licensing for themselves.

This document does not choose between these — that is the author's decision
per the repository's actual release plan, not something to apply
unilaterally.
