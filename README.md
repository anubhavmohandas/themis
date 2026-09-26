# THEMIS

**Can you trust a public "this crypto address belongs to X" label? THEMIS measures it.**

<sub>Made with ❤️ by Anubhav Mohandas · MIT licence</sub>

![How THEMIS works: collect, trace, compare, stress-test, report](docs/images/how-it-works.svg)

## The problem, in 30 seconds

- A blockchain shows **transfers**, not **people**. "This address is a scam" is always someone's *claim*.
- Those claims come from a handful of public datasets that copy from each other.
- Ten datasets saying the same thing can be **one** opinion repeated ten times.

THEMIS does not decide who owns an address. It checks **how strong the evidence behind a label really is**: where it came from, whether the agreement is real, and how much a forensic answer changes when you trust different things.

Built for the paper *Provenance Before Precision: Auditing Public Bitcoin Attribution Labels and Their Effect on Forensic Conclusions* (ICISHCT 2026, under review).

## Try it in 2 minutes

Needs Python 3.10+.

```
git clone <repo> && cd themis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

themis ingest examples/example_attribution.csv --source-id demo --no-reference
```

You get a plain-English verdict, for example: *"the assessment of this dataset is EVIDENCE CONCERNS, because 1 of 11 addresses carry labels that contradict each other."*

Want the web dashboard? Run `python run.py` (needs Node 18+).

## What can I do with it?

| I want to… | Run | Wiki |
|---|---|---|
| Audit my own CSV of address labels | `themis ingest FILE --source-id NAME` | [Audit your own data](docs/wiki/your-own-data.md) |
| See how much sources really agree | `themis audit` | [Reproduce the paper](docs/wiki/reproduce-the-paper.md) |
| See how the answer moves with the trust rule | `themis drift` | [The ideas](docs/wiki/concepts.md) |
| Trace one address back to its origin | `themis explain <address>` | [Install and use](docs/wiki/install-and-use.md) |
| Re-check the paper's numbers | `themis reproduce-paper`, `themis verify-paper` | [Reproduce the paper](docs/wiki/reproduce-the-paper.md) |

## What THEMIS does **not** say

- A label being public does not make it **true**.
- "Passes a trust rule" means the evidence meets that bar, not that the label is **correct**.
- Many datasets agreeing does not mean many **independent** sources.
- No verdict here means a label is proven right. It judges the evidence, not a single address.

## Read more (the wiki)

Everything detailed lives in [docs/wiki/](docs/wiki/README.md):

- [The ideas behind THEMIS](docs/wiki/concepts.md): research questions, evidence tiers, provenance, trust rules
- [Install and use](docs/wiki/install-and-use.md): setup, commands, dashboard, architecture
- [Audit your own data](docs/wiki/your-own-data.md): upload flow, pre-flight checks, size limits, security
- [Reproduce the paper](docs/wiki/reproduce-the-paper.md): step by step, plus how the paper is verified
- [Data and licences](docs/wiki/data-and-licenses.md): what data is (and is not) shipped
- [Testing and known limits](docs/wiki/testing-and-limits.md): what is tested, what is not
- [Project layout and citation](docs/wiki/project-layout.md)

## Licence and citation

THEMIS's code is MIT ([LICENSE](LICENSE)). It grants no rights over third-party datasets; see [Data and licences](docs/wiki/data-and-licenses.md). Until the paper has a final reference, cite it by title.
