# THEMIS

**T**rust and **E**vidence-based **H**euristic **M**ethod for **I**nvestigative
**S**ource Assessment — provenance-aware auditing of public Bitcoin attribution
labels, and the runnable counterpart to *Provenance Before Precision*.

A blockchain records transfers, not identities. Everything an investigator says
about *who* controlled an address is a claim layered on top, and in practice
those claims come from a short list of public corpora. This tool audits them:
what corroborates what, which agreement is inherited rather than independent,
and what the choice of trust rule does to a forensic figure.

## Install and run

No dependencies beyond the standard library. NumPy is used if present, only to
speed up the bootstrap.

```
pip install -e .
themis audit
themis drift
themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7
themis bootstrap --both
themis taxonomy
```

Every command takes `--json FILE` to write its result, and `--observations FILE`
to run against a full local build instead of the bundled sample.

## What each command shows

| command | paper section | what it demonstrates |
|---|---|---|
| `audit` | 5.1–5.2 | corpus composition, corroboration depth, agreement outcomes, and the three independence tests |
| `drift` | 5.3 | the same corpus and procedure under four label-trust rules |
| `explain <address>` | 3.2 | one address traced to its provenance roots, with apparent vs actual corroboration |
| `bootstrap [--both]` | 5.4 | cluster-bootstrap intervals, resampling provenance roots rather than rows |
| `taxonomy` | 3.2 | the classification rules, printed so they can be checked |

`audit` also computes Cohen's kappa for every overlapping dataset pair, so the
chance-corrected figures in §5.1 come from released code rather than an external
script. Pairs whose shared region is single-class are named as undefined instead
of being dropped.

`explain` is the shortest route to the argument. Try these three:

```
themis explain 14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7   # 4 datasets, 3 roots - circular
themis explain 34kWCKF2wCbe6uinit2uL4ND6d8yxsuxKM   # exchange vs sanctioned
themis explain 1LLEoSTzRmSL3xC5AWhsn9QjpGFh4Wx72N   # genuine corroboration
```

## The bundled corpus

`demo_data/` holds every claim from every source **except** Elliptic++ and
GraphSense TagPack, which are sampled, plus all 15,400 multi-dataset addresses
and the full revenue inputs. Agreement, conflict, independence and drift results
are therefore **exact**; corpus-wide totals come from `manifest.json`, which
records the true counts.

Two consequences are enforced in code rather than left to the reader:

* `bootstrap` withholds any rate whose denominator is the whole corpus when run
  on the sample, because the sample is not the corpus. Rates conditional on
  being multi-dataset are unaffected and are reported.
* `corpus_roots()` reads corpus-wide provenance figures from the manifest on the
  sample and computes them directly on a full build.

To rebuild the full corpus from source, use the ingest pipeline in the paper's
reproducibility bundle, then pass `--observations`. A full run takes about 13
seconds for `audit`.

## Design notes

**Claims, not labels.** The unit of analysis is a claim: one source asserting one
category about one address. Keeping claims separate is what makes disagreement
visible at all.

**Roots, not datasets.** A *provenance root* is where a claim's evidence actually
originates. `provenance.root_of` assigns it from a field the publisher declares,
or from the containment decode. Where lineage cannot be established the root is
marked *unresolved* — deliberately distinct from "shares a root with everything
else unresolved", which would assert a dependency nobody has shown.

**Absence of a date is not staleness.** A claim with no revision field is
`currency-unknown`. `stale` requires a date that is actually old. Conflating the
two would overclaim, and two thirds of this corpus has no date at all.

**The decode is allowed to be inconclusive.** `decode_field` returns
`insufficient` for groups too small to establish containment and `malformed` for
values the dataset ships broken, instead of forcing every group to a verdict.
One group in the real data is each.

## Tests

```
python -m unittest discover -s tests -v
```

39 tests, each asserting a number printed in the paper. If the implementation
drifts from what was published, they fail. Four of them caught genuine bugs: a circularity flag that only fired when
*every* dataset shared one root; a malformed provenance value silently judged as
inherited; the 1-dataset bucket of the corroboration histogram reporting the
sample count rather than the corpus count; and a first cut of the kappa stage
that excluded `unknown` labels, which quietly changed the comparable set and
moved the headline kappa from 0.655 to 0.684.

## Layout

```
themis/
  taxonomy.py     tiers, flags, categories, conflict logic
  provenance.py   root assignment and the three independence tests
  corpus.py       loading, sample-vs-full accounting
  analysis.py     agreement, independence, drift, cluster bootstrap
  cli.py          command line
demo_data/        bundled corpus sample + manifest
tests/            assertions against every published figure
provenance_register.html   interactive register (same data, self-contained)
```

## Limits worth knowing

The bundled revenue file stores USD rounded to cents, so drift totals can differ
from the paper by a few dollars out of a billion. Bootstrap intervals over 25
clusters carry visible Monte Carlo noise; they are quoted at a fixed seed and
2,000 resamples. And the verified tier is *declared*, not confirmed — condition
D uses each source's highest declared confidence, which is not the same as
independently re-verified ground truth.
