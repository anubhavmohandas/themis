"""The paper's figures, drawn from generated data rows and nothing else.

`*_rows` turn an experiment result into the rows written to fig*_data.csv/json;
`render_*` draw a figure from those rows alone, so a figure can be regenerated
from the artifact on disk and can never carry a value that is not in it. Every
figure gets a sidecar `<figure>.metadata.json` naming the computation behind it.

Palette: Okabe-Ito (colour-vision-deficiency safe), with a hatch as a second
encoding so the figures survive greyscale printing. Each panel has one axis.
matplotlib is an optional dependency (`pip install "themis[figures]"`); without
it the data files are still written and the figures are reported as not rendered.
"""
from __future__ import annotations
import csv, datetime, json, pathlib, textwrap

from . import experiments as ex

INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
BLUE, VERMILION, GREEN, GREY = "#0072B2", "#D55E00", "#009E73", "#8c959f"
FORMATS = ("png", "pdf", "svg")

try:                                     # optional; the data files never need it
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except ImportError:                      # pragma: no cover - exercised only without matplotlib
    HAVE_MPL = False


# --------------------------------------------------------------- data rows
def fig1a_rows(b: ex.AnalysisBundle) -> list[dict]:
    rows = []
    for d in ex.rodwald_containment(b)["decodes"]:
        for g in d["groups"]:
            rows.append(dict(dataset=d["dataset"], field=d["field"], candidate=d["candidate"], code=g["code"],
                             size=g["size"], overlap_with_candidate=g["overlap_with_candidate"],
                             containment=g["containment"], verdict=g["verdict"], well_formed=g["well_formed"]))
    return rows


def fig1b_rows(b: ex.AnalysisBundle) -> list[dict]:
    rows = []
    for rt in ex.montreal_recurrence(b)["roots"]:
        for r in rt["recurrence"]:
            rows.append(dict(root=rt["root"], seed_addresses=rt["seed_addresses"], source=r["source"],
                             addresses=r["addresses"], share=r["share"]))
    return rows


def fig2_rows(b: ex.AnalysisBundle) -> list[dict]:
    """The same rows as Table 2: one object, two presentations."""
    return [dict(condition=r["condition"], label=r["label"], claim_observations=r["observations"],
                 unique_addresses=r["addresses"], revenue_usd=r["revenue_usd"],
                 ratio_vs_B=r["ratio_vs_B"], coverage_vs_B=r["coverage_vs_B"])
            for r in ex.table2(b)["rows"]]


def write_rows(rows: list[dict], stem: pathlib.Path) -> None:
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        w.writeheader()
        w.writerows(rows)
    with open(f"{stem}.json", "w") as f:
        json.dump(rows, f, indent=1)


# ------------------------------------------------------------------ drawing
def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _save(fig, out: pathlib.Path, name: str, meta: dict) -> list[str]:
    written = []
    for fmt in FORMATS:
        p = out / f"{name}.{fmt}"
        fig.savefig(p, dpi=300, bbox_inches="tight", metadata={"Software": "THEMIS"} if fmt == "png" else None)
        written.append(p.name)
    plt.close(fig)
    (out / f"{name}.metadata.json").write_text(json.dumps(
        dict(meta, figure=name, formats=written,
             generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat()), indent=1))
    return written


def _bars(ax, labels, values, colors, hatches, fmt, xmax):
    ys = list(range(len(labels)))[::-1]
    for y, v, c, h in zip(ys, values, colors, hatches):
        ax.barh(y, v, height=0.62, color=c, edgecolor="white", hatch=h, linewidth=0)
        ax.text(v + xmax * 0.015, y, fmt(v), va="center", fontsize=8, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=8.5, color=INK)
    ax.set_xlim(0, xmax * 1.16)


def render_fig1a(rows: list[dict], out: pathlib.Path, meta: dict) -> list[str]:
    if not HAVE_MPL:
        return []
    rows = sorted(rows, key=lambda r: -r["size"])
    fig, ax = plt.subplots(figsize=(6.4, 0.34 * len(rows) + 1.3))
    labels = [f"{r['code']}  (n = {r['size']:,}{'' if r['well_formed'] else ', malformed'})" for r in rows]
    vals = [100 * r["containment"] for r in rows]
    # a malformed code is never counted as decoded, whatever its overlap
    color = [GREY if not r["well_formed"] else BLUE if r["containment"] > 0.999 else VERMILION for r in rows]
    hatch = ["" if c == BLUE else "//" for c in color]
    _bars(ax, labels, vals, color, hatch, lambda v: f"{v:.1f}%", 100)
    ax.set_xlabel(f"share of the group also present in {rows[0]['candidate']} (%)", fontsize=8.5, color=MUTED)
    ax.set_title(f"{rows[0]['dataset']}: undocumented '{rows[0]['field']}' field, decoded by containment",
                 fontsize=9.5, color=INK, loc="left")
    _style(ax)
    return _save(fig, out, "fig1a_rodwald_containment", meta)


def render_fig1b(rows: list[dict], out: pathlib.Path, meta: dict) -> list[str]:
    if not HAVE_MPL:
        return []
    rows = sorted(rows, key=lambda r: -r["share"])
    fig, ax = plt.subplots(figsize=(6.4, 0.34 * len(rows) + 1.3))
    _bars(ax, [f"{r['source']}  ({r['addresses']:,})" for r in rows], [100 * r["share"] for r in rows],
          [BLUE if r["share"] > 0.5 else GREY for r in rows], ["" if r["share"] > 0.5 else "//" for r in rows],
          lambda v: f"{v:.2f}%", 100)
    ax.set_xlabel(f"share of the {rows[0]['seed_addresses']:,} seed addresses that reappear (%)", fontsize=8.5, color=MUTED)
    ax.set_title(f"Recurrence of provenance root {rows[0]['root']}", fontsize=9.5, color=INK, loc="left")
    _style(ax)
    return _save(fig, out, "fig1b_montreal_recurrence", meta)


def render_fig2(rows: list[dict], out: pathlib.Path, meta: dict) -> list[str]:
    if not HAVE_MPL:
        return []
    fig, (a, b_) = plt.subplots(1, 2, figsize=(9.6, 3.9), gridspec_kw=dict(wspace=0.12))
    labels = [f"{r['condition']}  " + textwrap.fill(r["label"].split(",")[0], 24).replace("\n", "\n   ") for r in rows]
    hatch = ["", "", "//", "xx"][:len(rows)] + [""] * max(0, len(rows) - 4)
    cols = [GREY, BLUE, GREEN, VERMILION] + [GREY] * max(0, len(rows) - 4)
    top = max(r["revenue_usd"] for r in rows) / 1e9
    _bars(a, labels, [r["revenue_usd"] / 1e9 for r in rows], cols, hatch, lambda v: f"${v:,.3f}B", top)
    a.set_xlabel("ransomware revenue (USD billion)", fontsize=8.5, color=MUTED)
    a.set_title("(a) Revenue", fontsize=9.5, color=INK, loc="left")
    _style(a)
    top = max(r["coverage_vs_B"] for r in rows) * 100
    _bars(b_, labels, [100 * r["coverage_vs_B"] for r in rows], cols, hatch, lambda v: f"{v:.1f}%", top)
    b_.set_yticklabels([])
    b_.set_xlabel("addresses retained, % of condition B", fontsize=8.5, color=MUTED)
    b_.set_title("(b) Coverage behind it", fontsize=9.5, color=INK, loc="left")
    _style(b_)
    return _save(fig, out, "fig2", meta)
