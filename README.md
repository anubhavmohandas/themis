# THEMIS

**T**rust and **E**vidence-based **H**euristic **M**ethod for **I**nvestigative
**S**ource Assessment — provenance-aware auditing of public Bitcoin attribution
labels, and the runnable counterpart to *Provenance Before Precision: Auditing
Public Bitcoin Attribution Labels and Their Effect on Forensic Conclusions*
(submitted, ICISHCT 2026).

## 1. What THEMIS is

A blockchain records transfers, not identities. Everything an investigator says
about *who* controlled an address is a claim layered on top, and in practice
those claims come from a short list of public corpora that get reused across
research and forensic workflows without much scrutiny of where they actually
came from. THEMIS audits them: what corroborates what, which agreement is
inherited rather than independent, how much of the corpus has no public
cross-source comparison at all, and what the choice of trust rule does to a
downstream forensic figure.

It is a measurement tool, not a labeling tool. It does not decide whether any
address is "really" a scam, a mixer, or an exchange — it measures how well the
*public evidence for that decision* holds up: its provenance, its
independence, its currency, and its sensitivity to what you're willing to
trust.

THEMIS generalizes beyond the one paper it was built to reproduce: the
analysis engine (`themis/taxonomy.py`, `provenance.py`, `analysis.py`,
`trust/`) carries no dataset-specific logic at all. Every source's provenance
rule, every category, every trust-rule policy lives in `themis/config/`
(YAML). Reproducing the paper's exact figures is one configuration of that
engine, not a special case of it.

## 2. Research question

The paper (and this tool) is organized around three questions:

- **RQ1** — Can public attribution claims be classified using reproducible,
  evidence-quality rules rather than an unstated notion of "trustworthy"?
- **RQ2** — How much do major open sources actually overlap, how often do
  their labels conflict, and how much of that overlap is genuinely
  independent rather than one source restating another's finding?
- **RQ3** — How much does a downstream forensic conclusion (this paper uses a
  ransomware revenue estimate) change depending on which label-trust rule is
  applied to the same corpus?

`themis audit` answers RQ1/RQ2. `themis drift` answers RQ3. `themis
bootstrap`/`themis anchors` quantify how much confidence either answer can
actually support.

## 3. What THEMIS does not claim

- **Public ≠ reliable.** A label being published somewhere says nothing about
  its accuracy.
- **Supported ≠ true.** An address passing a trust condition means the
  evidence for it meets that condition's bar, not that the label is correct.
- **Agreement ≠ independent corroboration.** Two datasets naming the same
  category can both be restating one upstream source (paper §5.2; see §10
  below — "circular" is a real, measured flag, not an edge case).
- **Multiple datasets ≠ multiple independent sources**, and **unknown
  provenance ≠ independent** — an unresolved root is a genuinely unknown
  relationship, never scored as if it were a distinct, additional source.
- **Unverifiable ≠ false**, and **no date ≠ stale** — a claim with no revision
  field is `currency-unknown`, never silently treated as either current or
  outdated.
- **High overlap ≠ proof of copying**, and **a reference corpus (the open
  anchor set `themis anchors` checks against) ≠ ground truth** for the corpus
  as a whole.
- **Coverage ≠ accuracy.** Condition D in `themis drift` retains only 13.8% of
  addresses at its strictest trust rule; that is a coverage trade-off, not a
  more accurate estimate of the other 86.2%.
- **Declared confidence ≠ verified ground truth.** A source calling its own
  output "manually verified" is a claim about that source's process, not an
  independent check THEMIS has performed.
- THEMIS does not estimate absolute source-level accuracy against
  ground truth from the bundled open anchor set — `themis anchors` measures
  and reports exactly why that estimate isn't currently defensible (small,
  non-random reference set; most of it isn't independent of the sources
  being checked) rather than publishing one anyway.

A forensic result without its trust rule and coverage stated alongside it is
an incomplete result — every number this tool prints is reported with both.

## 4. Architecture

```
frontend/   React + Vite dashboard, talks to the API over HTTP
themis/api.py   thin FastAPI JSON layer (the `ui` extra) - no analysis logic
                of its own, a pass-through to themis.report/analysis/graph
themis/*.py     the Python analysis core - CLI and API both call the same
                functions, so they can never disagree
```

The API contains no analysis logic: every number it returns comes from the
same `themis.report`/`analysis`/`graph` functions the CLI calls directly, so
`themis audit` and the web dashboard cannot silently diverge.

## 5. Installation

```
git clone <repo>
cd themis
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test,ui]"
```

One required dependency: PyYAML, for the config files under `themis/config/`.
`fastapi`/`uvicorn`/`python-multipart` (the `ui` extra) are only needed to run
the web dashboard's backend; `pytest`/`httpx` (the `test` extra) only to run
the test suite. NumPy is never required: the cluster bootstrap's canonical,
reproducible path is pure-Python `random.Random` regardless of whether numpy
is installed (see §15) — numpy is only used if you explicitly opt into
`bootstrap(fast=True)` / `themis bootstrap --fast` for a much larger corpus
build, and that path is marked non-canonical in its own output.

## 6. Paper reproduction

```
themis audit                                            # RQ1/RQ2 - §5.1-5.2
themis drift                                             # RQ3 - §5.3
themis bootstrap --both                                  # §5.4
themis anchors                                           # §4.3/§4.7
themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7
themis taxonomy
themis sources
themis --json report.json report --bootstrap --anchors
```

Every command takes a global `--json FILE` (before the subcommand) to write
its result, and a global `--observations FILE` to run against a full local
build instead of the bundled sample; `report` additionally accepts its own
`--out FILE` after the subcommand, equivalent to the global `--json`. See
`REPRODUCE.md` for exact commands and expected headline output.

| command | paper section | what it demonstrates |
|---|---|---|
| `audit` | 5.1–5.2 | corpus composition, corroboration depth, agreement outcomes, and the three independence tests |
| `drift` | 5.3 | the same corpus and procedure under four label-trust rules |
| `bootstrap [--both]` | 5.4 | cluster-bootstrap intervals, resampling provenance roots rather than rows |
| `anchors` | 4.3/4.7 | provenance-aware validation against the bundled open anchor set, and why a source-level accuracy table isn't published |
| `explain <address>` | 3.2 | one address traced to its provenance roots, with apparent vs actual corroboration |
| `taxonomy` | 3.2 | the classification rules, printed so they can be checked |
| `sources` | — | the source registry: every bundled dataset's declared provenance rule and any address-normalization rule, read straight from config |
| `report` | — | the canonical result object (dataset summary, every analysis, the reliability profile, an audit trail) as one JSON document |
| `ingest <file>` | — | audit a dataset THEMIS has never seen - crypto detection, schema mapping, address validation, and (if a reference corpus is available) cross-source comparison |

## 7. Web dashboard

```
pip install -e ".[ui]"
python -m themis.api          # backend on http://127.0.0.1:5001

cd frontend
npm ci
npm run dev                   # frontend on http://127.0.0.1:5173
```

Both need to be running together. `frontend/src/lib/api.js` points at
`http://127.0.0.1:5001` by default; override with `VITE_API_URL` if you run
the API on a different port. `npm run build && npm run preview` serves the
production build.

## 8. Auditing a new dataset

`themis ingest` (CLI) / Upload (dashboard) runs the full pre-flight-through-
reliability-profile pipeline on any CSV. Schema roles (address/label/
category/source/timestamp/confidence) are inferred from column names and
sampled values and can be overridden with `--map role=column`. An
unrecognized `--source-id` gets no provenance rule from `config/sources/`, so
every claim it produces resolves `UNRESOLVED` by construction — a new dataset
is never silently assumed independent. Compare it against the bundled sample
with `--reference FILE` (a full observations build) or skip comparison with
`--no-reference`.

### Supported input

THEMIS never assumes an uploaded file is cryptocurrency-related, and
distinguishes four cases rather than collapsing them into one generic
rejection:

- **A supported-chain attribution CSV (Bitcoin today)** is detected via the
  registered blockchain adapters (`themis/chains/bitcoin.py`: base58check and
  bech32/bech32m) sampling every column for address-shaped values, and runs
  the full pipeline above.
- **An unsupported-chain attribution CSV** (e.g. Ethereum) is distinguished
  from non-crypto data via a chain-agnostic opaque-token-shape fallback and
  reported as "unsupported chain," not misreported as "not crypto."
- **Crypto data that isn't attribution data** (e.g. a Bitcoin OHLC/price
  series) is distinguished from genuinely non-crypto data (no address-shaped
  column and no asset-identity signal) via an opt-in `symbol_aliases` content
  signal on the adapter — never from the filename.
- **Non-crypto data** (no address-shaped column, no asset-identity signal)
  stops early with an explanation of what THEMIS looked for and didn't find.
- **Malformed CSV** input (encoding errors, missing columns) fails gracefully
  with a specific error, not a stack trace.

## 9. Main tool modules

| module | CLI | dashboard page |
|---|---|---|
| Upload / preflight | `themis ingest` | Upload |
| Audit (agreement, independence, kappa) | `themis audit` | Audit |
| Claims (bounded, filterable claim listing) | API only: `GET /api/analysis/{id}/claims` (a full unbounded CSV is `GET /api/analysis/{id}/export/{name}`) | Claims |
| Address Inspector | `themis explain <addr>` | Address |
| Provenance | `themis sources` | Provenance (lineage graph is dashboard/API-only via `graph.lineage_graph()`, not a CLI command) |
| Conflicts | surfaced within Audit's outcome breakdown and Claims' evidence-tier filter — not a separate page | — |
| Trust-rule sensitivity / drift | `themis drift` | Drift |
| Anchor validation | `themis anchors` | (JSON via `report --anchors`; not yet a dedicated page) |
| Export | CLI: global `--json FILE` before any command. Dashboard: `GET /api/analysis/{id}/export/{name}` (CSV) | Export |
| Paper reproduction | `themis report --bootstrap --anchors` | — |

## 10. Scientific terminology

- **Claim, not label.** The unit of analysis is one source asserting one
  category about one address. Keeping claims separate (rather than
  collapsing to "the corpus says X") is what makes disagreement visible.
- **Provenance root.** Where a claim's evidence actually originates, as
  opposed to which dataset republished it. Assigned from a source's own
  declared rule (`config/sources/<id>.yml`); never guessed from a dataset
  name. A root is *resolved* when it's a known evidential origin, *verified*
  when it terminates in independently re-checkable evidence, and *native*
  when the source **is** that origin rather than re-describing another
  source's finding.
- **Unresolved.** Deliberately distinct from "shares a root with everything
  else unresolved" — an unresolved root is an unknown relationship, not an
  asserted one.
- **Circular / inherited.** Two or more apparently-independent claims that
  trace to the same provenance root. Raw agreement counts these as
  corroboration; THEMIS reports both the raw count and the corrected one.
- **Evidence tier.** `verified` / `derived` / `unverified-report` / `unknown`
  — how a claim's methodology was declared, not how confident it sounds.
- **Currency-unknown vs. stale.** A claim with no revision date is
  `currency-unknown`. `stale` requires an actual date older than the
  configured threshold. Conflating the two would overclaim — most of this
  corpus has no date at all.
- **Structured label.** A `type:entity`-shaped raw label (e.g.
  `onlinewallet:flexcoin`); its category-shaped prefix is canonicalized like
  any other alias, and the entity half is preserved, not discarded.

## 11. Dataset / license notice

The bundled sample (`demo_data/`) contains normalized, derived rows from
seven public sources. **Redistribution status varies by source and is not
uniformly confirmed** — see `THIRD_PARTY_DATA.md` for the full per-source
breakdown (license, citation, retrieval date, redistribution status). In
short: TagPack (MIT), Schnöring (CC BY 4.0) and Ransomwhere (CC BY) are
confirmed permissive (~39% of the corpus). Elliptic++ (~53% of the corpus)
and Rodwald have **unconfirmed** redistribution status and should be verified
directly with their authors before further redistribution. WatchYourBack's
code repository is GPL-3.0; whether that extends to its address/tag data is
not separately confirmed.

**THEMIS's own code currently has no LICENSE file** — a repository-level
decision left to the author, tracked separately from the dataset licenses
above.

## 12. Testing

```
python -m pytest
```

191 tests. A large share assert a number printed in the paper — if the
implementation drifts from what was published, they fail. Several caught
genuine bugs during hardening, not just regressions: a circularity flag that
only fired when *every* dataset shared one root; `classify_address` counting
one source's opinion as two sources agreeing whenever every other matched
label failed to canonicalize (moved the §5.1 agreement breakdown from
13,673/88.79% exact to 10,515/68.28%); a stray upstream "#" character
silently breaking cross-source address matching for a subset of one source's
claims; and the cluster bootstrap producing different confidence-interval
endpoints depending on whether numpy happened to be installed. The rest cover
the generic engine directly: Bitcoin address validation against real mainnet
vectors, the new-dataset pipeline (crypto/non-crypto/unsupported-chain
detection, schema inference, rejection reporting), the trust-policy engine
against a synthetic non-Bitcoin task, provenance-independence edge cases, and
that an unconfigured source really does resolve UNRESOLVED rather than being
assumed independent.

## 13. Limitations

- The bundled sample's corpus-wide totals (e.g. 1,497,191 addresses) come
  from a manifest recorded when the full corpus was originally built, not
  live-recomputed on every run; a full local rebuild uses `--observations`
  against your own build. There is currently no bundled, from-source rebuild
  script — see `REPRODUCE.md`.
- The bundled revenue file stores USD rounded to cents, so `drift` totals can
  differ from the paper by a few dollars out of a billion.
- Bootstrap intervals over a small number of provenance-root clusters carry
  visible Monte Carlo noise; they are quoted at a fixed seed and 2,000
  resamples (see §15 for why the interval is now environment-independent).
- `themis anchors`' per-source accuracy figures describe agreement with a
  small (289-address), source-concentrated open reference set, not verified
  accuracy against ground truth for the corpus as a whole — see §3.
- The verified tier is *declared*, not independently confirmed — Condition D
  in `themis drift` uses each source's highest declared confidence.
- GraphSense TagPack's real per-tag confidence vocabulary (`forensic`,
  `forensic_investigation`, `service_data`, ...) survives per-claim in the
  bundled corpus but is not currently used to re-tier evidence — every
  TagPack claim gets one flat evidence tier regardless of it.
- WatchYourBack's own upstream data marks 87 of 309 claims with a leading
  "#"; THEMIS now normalizes the address for cross-source matching, but the
  correct provenance root for those 87 (many cite OFAC/other external
  sources rather than WatchYourBack's own methodology) is not yet
  reassigned — they still resolve to WatchYourBack's own root pending an
  author decision.
- TagPack's proper-noun entity names (e.g. "Antpool", "Lazarus group") are
  not mapped to taxonomy categories; that would require an external entity
  dictionary, a different feature from a category-synonym alias table.

## 14. Citation

The paper this tool reproduces is under submission (ICISHCT 2026) with a
blinded author field; a formal citation (authors, venue, year, pages) will be
added here once the submission is no longer under review. In the meantime,
cite by title: *"Provenance Before Precision: Auditing Public Bitcoin
Attribution Labels and Their Effect on Forensic Conclusions."*

## 15. Reproducibility

- Every `themis report` output includes an audit trail: software version,
  analysis timestamp, input file hash, and a config hash covering
  `taxonomy.yml`/`thresholds.yml`/`trust_rules.yml`/`sources/*.yml`/
  `notable_roots.yml` — two runs with the same config hash used the same
  scientific rules, regardless of when they ran.
- `themis explain`/`report`'s freshness figures default to the corpus's own
  `snapshot_date` (the latest revision date actually present in its claims),
  not the wall clock, so a paper-reproduction run doesn't drift "staler"
  every year it's re-run.
- The cluster bootstrap's canonical path (`fast=False`, the CLI default) is
  always `random.Random`, regardless of whether numpy is installed — the two
  RNGs are different algorithms and produced different CI endpoints (not
  point estimates) for the same seed before this was fixed. `--fast` opts
  into a numpy-accelerated path for a much larger corpus build; its output is
  marked `engine: "numpy_fast_exploratory"` and is not the canonical/paper
  path.
- See `REPRODUCE.md` for the exact end-to-end commands a reviewer would run
  in a clean environment.

## Appendix: layout

```
themis/
  taxonomy.py     tiers, flags, categories, conflict logic - all config-driven
  provenance.py   root resolution, address normalization, independence tests
  corpus.py       loading, sample-vs-full accounting
  analysis.py     agreement, independence, drift, freshness, bootstrap, anchors
  reliability.py  multidimensional reliability profile
  report.py       canonical result object, JSON export, audit trail
  graph.py        provenance lineage graph (config -> nodes/edges)
  api.py          thin FastAPI JSON API for the web dashboard (ui extra)
  cli.py          command line
  chains/         blockchain adapters (Bitcoin: base58check + bech32/bech32m)
  ingest/         new-dataset pipeline: detect, schema, validate, claims
  trust/          composable trust-rule policy engine
  tasks/          task-specific aggregation (ransomware revenue is the one bundled)
  config/         taxonomy.yml, trust_rules.yml, thresholds.yml, sources/*.yml
demo_data/        bundled corpus sample + manifest
tests/            paper regression + generic-engine tests
frontend/         React + Vite dashboard (talks to themis/api.py)
provenance_register.html   interactive register (same data, self-contained)
```

## Appendix: design notes

**Config, not code, is dataset-specific.** Nothing under `themis/*.py` names a
source, a category, or a trust condition by string literal. `provenance.py`'s
`resolve()` reads a generic rule shape (`fixed_root` / `field_map` /
`contains_rules` / `substring_map`) out of `config/sources/<id>.yml`; even
`is_unresolved(root)` derives its answer by walking that same config, not
from a hardcoded prefix tuple. Adding an eighth source, an eleventh category,
or a fifth trust condition is a config change.

**One policy engine, any task.** `themis/trust/` scores claims against
composable predicates (`root_independent_or_native`, `anchor_membership`,
...) named in `config/trust_rules.yml`; `themis/tasks/ransomware_revenue.py`
is the one module that knows the paper's task is a USD sum per address. A
different forensic task (sanctions exposure, entity counts) is a new module
in that shape, reusing the same policies, not a new branch in the engine.

**The decode is allowed to be inconclusive.** `decode_field` returns
`insufficient` for groups too small to establish containment and `malformed`
for values a source ships broken, instead of forcing every group to a
verdict.
