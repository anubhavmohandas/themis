<a id="readme-top"></a>

<div align="center">

# THEMIS

### How much evidence really stands behind a public<br>"this crypto address belongs to X" label?

A measurement and audit tool for public blockchain attribution labels.<br>
It traces every label to its origin, checks whether agreement is real, and shows how much an answer moves when you trust different things.

<p>
  <img alt="Licence: MIT" src="https://img.shields.io/badge/licence-MIT-2ea44f">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="Release v1.0-paper" src="https://img.shields.io/badge/release-v1.0--paper-0969da">
  <img alt="Paper: ICISHCT 2026" src="https://img.shields.io/badge/paper-ICISHCT%202026-8250df">
</p>

<p>
  <a href="#quick-start"><b>Quick start</b></a> &nbsp;·&nbsp;
  <a href="#how-to-read-a-result"><b>Read a result</b></a> &nbsp;·&nbsp;
  <a href="#choose-your-path"><b>Choose your path</b></a> &nbsp;·&nbsp;
  <a href="#the-paper-and-its-data"><b>The paper</b></a> &nbsp;·&nbsp;
  <a href="#faq"><b>FAQ</b></a> &nbsp;·&nbsp;
  <a href="docs/wiki/README.md"><b>Wiki</b></a>
</p>

<img src="docs/images/how-it-works.svg" alt="How THEMIS works: trace each label to its origin, test different trust rules, get a plain-English assessment" width="820">

</div>

## The problem, in 30 seconds

- A blockchain shows **transfers**, not **people**. "This address is a scam" is always someone's *claim*.
- Those claims come from a handful of public datasets that copy from each other.
- Ten datasets saying the same thing can be **one** opinion repeated ten times.

THEMIS does not decide who owns an address. It measures **how strong the evidence behind a label really is**: where it came from, whether the agreement is independent, and how much a forensic conclusion changes under a different trust rule.

Built for the paper *Provenance Before Precision: Auditing Public Bitcoin Attribution Labels and Their Effect on Forensic Conclusions* (ICISHCT 2026).

> [!IMPORTANT]
> **What THEMIS does not say.**
> A public label is not automatically **true**. Passing a trust rule means the evidence meets that bar, not that the label is **correct**. Many datasets agreeing does not mean many **independent** sources. No outcome proves a label right: THEMIS judges the evidence, not a single address.

## Quick start

Needs Python 3.10+ (Node 18+ only for the dashboard).

```bash
git clone https://github.com/anubhavmohandas/themis && cd themis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

themis ingest examples/example_attribution.csv --source-id demo --no-reference
```

<details>
<summary><b>What you get back</b></summary>

<br>

```
According to the THEMIS report, the assessment of this dataset is EVIDENCE CONCERNS.
  because:
    x 1 of 11 addresses (9.1%) carry labels in this file that contradict each other.
    + All 12 rows carried a valid identifier.
    - No reference corpus was supplied, so the labels were not tested against any other public source.
```

Every analysis ends this way: an outcome, and the measured numbers behind it.

</details>

<details>
<summary><b>Want the web dashboard?</b></summary>

<br>

```bash
pip install -e ".[ui]"
python run.py            # needs Node 18+
```

The dashboard calls the same analysis functions as the command line; it adds no analysis of its own.

</details>

## How to read a result

Every audit ends in one of five outcomes. Open one to see what it means.

<details>
<summary>🟢 <b>EVIDENCE SUPPORTED</b></summary>

<br>The evidence is strong and independent, and no measured problem was found. It is still a statement about evidence, not a proof that any label is correct.

</details>

<details>
<summary>🟢 <b>SUPPORTED WITH CAVEATS</b></summary>

<br>Good evidence, but gaps remain, for example a share of stale labels or of agreement inherited from one origin. The result lists them.

</details>

<details>
<summary>🟡 <b>NOT ESTABLISHED</b></summary>

<br>Nothing is wrong, but there is too little independent evidence to say the labels are right. For example, no reference corpus was supplied.

</details>

<details>
<summary>🔴 <b>EVIDENCE CONCERNS</b></summary>

<br>A measured problem is large enough that the labels should not be relied on until it is resolved, for example many addresses whose own rows contradict each other.

</details>

<details>
<summary>⚪ <b>CANNOT ASSESS</b></summary>

<br>The file failed the pre-flight checks (for example no valid address column), so no assessment was made. That is not a verdict on the data.

</details>

## Choose your path

<details open>
<summary><b>🔎 I want to audit my own CSV of address labels</b></summary>

<br>

```bash
themis ingest path/to/your.csv --source-id my_dataset
```

Add `--reference build/observations.csv.gz` to compare against the paper's reference corpus. A dataset THEMIS has never seen is never assumed independent.
→ [Audit your own data](docs/wiki/your-own-data.md)

</details>

<details>
<summary><b>🧪 I want to re-check the paper's numbers</b></summary>

<br>

```bash
# 1. fetch the seven sources yourself (locations and hashes: THIRD_PARTY_DATA.md)
python scripts/build_corpus.py --out build/ ...      # full command: REPRODUCE.md section 3
# 2. reproduce and verify
themis --observations build/observations.csv.gz --data-dir build --as-of 2026-09-15 reproduce-paper
```

Without a corpus, `reproduce-paper` stops with `BLOCKED - INPUT CORPUS NOT AVAILABLE` and lists what to fetch. It never prints a false PASS.
→ [Reproduce the paper](docs/wiki/reproduce-the-paper.md) · [REPRODUCE.md](REPRODUCE.md)

</details>

<details>
<summary><b>📊 I want to see how much sources agree, and how the answer moves</b></summary>

<br>

| Run | Shows |
|---|---|
| `themis audit` | overlap, agreement, conflict and independence between sources |
| `themis drift` | the same question under four trust rules, each with its coverage |
| `themis explain <address>` | one address traced back to its provenance roots |
| `themis bootstrap --both` | root-cluster confidence intervals |

These four need the reference corpus. → [The ideas behind THEMIS](docs/wiki/concepts.md)

</details>

<details>
<summary><b>🛠 I want to work on the code</b></summary>

<br>

```bash
pip install -e ".[test,ui]"
python -m pytest                  # tests that need the paper corpus skip with a stated reason
cd frontend && npm ci && npm run build
```

→ [Install and use](docs/wiki/install-and-use.md) · [Project layout](docs/wiki/project-layout.md) · [Testing and known limits](docs/wiki/testing-and-limits.md)

</details>

## The paper and its data

| | |
|---|---|
| **Release** | tag `v1.0-paper`, the artifact of the final ICISHCT 2026 manuscript |
| **Manuscript** | not distributed; [`paper/paper_claims.yml`](paper/paper_claims.yml) pins its SHA-256 |
| **Third-party data** | **not shipped.** Redistribution terms of the underlying sources are not uniform, so `demo_data/` holds only a README |
| **Rebuild** | fetch the seven sources, run `scripts/build_corpus.py`; source locations, hashes and expected outputs are in [REPRODUCE.md](REPRODUCE.md) and [THIRD_PARTY_DATA.md](THIRD_PARTY_DATA.md) |
| **Ransomwhere** | the live service changes, so exact reproduction of its figures needs the author's retained, hashed 2026 export |

## FAQ

<details>
<summary><b>Why does it say "4 datasets agree" can mean only 2 sources?</b></summary>

<br>If three datasets copied the same original report, that is one piece of evidence, not three. THEMIS traces each claim to its provenance root and counts roots. Where the origin is unknown it says so and never counts the claim as independent.

</details>

<details>
<summary><b>Does high agreement mean the labels are right?</b></summary>

<br>No. Agreement can be inherited, and even independent sources can be wrong together. THEMIS reports agreement, independence and coverage side by side, and never a single reliability score.

</details>

<details>
<summary><b>Why is no dataset included in the repository?</b></summary>

<br>The sources have different, and for some unstated, redistribution terms. The paper's data statement is that the derived observation table is not redistributed. Details: [Data and licences](docs/wiki/data-and-licenses.md).

</details>

<details>
<summary><b>Does THEMIS support chains other than Bitcoin?</b></summary>

<br>The paper's findings cover Bitcoin only. The ingest path also recognises several EVM chains and was stress-tested on them; those tests check the implementation and do not validate the paper's seven-source findings. External validation on an unseen, provenance-documented dataset remains future work.

</details>

## Documentation

| | |
|---|---|
| [The ideas](docs/wiki/concepts.md) | evidence tiers, provenance, trust rules |
| [Install and use](docs/wiki/install-and-use.md) | setup, commands, dashboard, architecture |
| [Audit your own data](docs/wiki/your-own-data.md) | upload flow, pre-flight checks, limits, security |
| [Reproduce the paper](docs/wiki/reproduce-the-paper.md) | step by step, and how the paper is verified |
| [Data and licences](docs/wiki/data-and-licenses.md) | what is and is not shipped |
| [Testing and known limits](docs/wiki/testing-and-limits.md) | what is tested, what is not |
| [Project layout and citation](docs/wiki/project-layout.md) | where things live |

## Licence and citation

THEMIS's code is MIT ([LICENSE](LICENSE)). It grants no rights over third-party datasets; see [Data and licences](docs/wiki/data-and-licenses.md). Until the paper has a final reference, cite it by title:

> *Provenance Before Precision: Auditing Public Bitcoin Attribution Labels and Their Effect on Forensic Conclusions.* ICISHCT 2026.

<br>

<div align="center">

<a href="#readme-top">↑ Back to top</a>

<br><br>

### Made with ❤️ by Anubhav Mohandas

<sub>THEMIS · MIT licence · [Wiki](docs/wiki/README.md) · [Reproduce](REPRODUCE.md) · [Third-party data](THIRD_PARTY_DATA.md)</sub>

</div>
