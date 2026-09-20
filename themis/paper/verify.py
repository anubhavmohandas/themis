"""Compare what THEMIS generated with what the manuscript declares.

Three layers, checked in this order and expected to agree:
  1. THEMIS-generated metrics (PaperMetrics)            - what the software measured
  2. paper/paper_claims.yml (the manuscript manifest)   - what the paper declares
  3. the final PDF's text                               - what the paper actually prints

Layer 2 is the canonical declaration; the PDF check only catches a manifest that
was updated after (or before) the PDF. The flow is one-way: analysis produces
values, the manifest declares expectations, this module compares. Nothing in the
analysis reads the manifest. A tolerance is never implicit: a comparison rule
either says how the paper rounds a number or it is an exact match.
"""
from __future__ import annotations
import decimal, hashlib, math, os, pathlib, re, shutil, subprocess
import yaml

PASS, FAIL, INFO, NMC, NOT_REPRODUCED = "PASS", "FAIL", "INFORMATIONAL", "NOT_MACHINE_CHECKABLE", "NOT_REPRODUCED"
BLOCKED = "BLOCKED"
COMPARISONS = ("exact_integer", "exact_string", "rounded_percent", "rounded_decimal", "range",
               "approximate_text")
CLASSES = ("HEADLINE_STABLE", "SUPPORTING_STABLE", "DIAGNOSTIC", "SENSITIVITY", "LIMITATION")
PKG = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = PKG / "paper" / "paper_claims.yml"
_D = decimal.Decimal


def load_manifest(path=None) -> dict:
    p = pathlib.Path(path or os.environ.get("THEMIS_PAPER_CLAIMS") or DEFAULT_MANIFEST)
    with open(p) as fh:
        m = yaml.safe_load(fh)
    m["_path"] = str(p)
    return m


def manifest_hash(m: dict) -> str:
    return hashlib.sha256(pathlib.Path(m["_path"]).read_bytes()).hexdigest()


# ------------------------------------------------------------------ comparison
def _dec(x) -> decimal.Decimal:
    return _D(str(x))


def _half_up(x: decimal.Decimal, decimals: int) -> decimal.Decimal:
    return x.quantize(_D(1).scaleb(-decimals), rounding=decimal.ROUND_HALF_UP)


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def compare(rule: str, generated, claim: dict) -> tuple[bool, str]:
    """(matches, detail). `claim` carries `expected` and the rule's parameters."""
    exp = claim.get("expected")
    if rule == "exact_string":
        return str(generated) == str(exp), ""
    if not _is_number(generated) or (isinstance(generated, float) and not math.isfinite(generated)):
        return False, f"generated value {generated!r} is not a finite number"
    g = _dec(generated)
    if rule == "exact_integer":
        # a USD sum carries cents; the paper prints whole dollars, half-up
        got = _half_up(g, 0)
        return got == _dec(exp), (f"generated {generated} rounds half-up to {got}"
                                  if g != g.to_integral_value() else "")
    if rule in ("rounded_percent", "rounded_decimal", "approximate_text"):
        d = int(claim.get("decimals", 0))
        scale = _dec(100) if rule == "rounded_percent" else _dec(claim.get("scale", 1))
        shown = _half_up(g * scale, d)
        want = _half_up(_dec(exp) * (_dec(100) if rule == "rounded_percent" else 1), d)
        return shown == want, f"generated rounds to {shown}"
    if rule == "range":
        lo, hi = claim.get("min"), claim.get("max")
        ok = (lo is None or g >= _dec(lo)) and (hi is None or g <= _dec(hi))
        return ok, f"generated {generated}, declared range [{lo}, {hi}]"
    raise ValueError(f"unknown comparison rule {rule!r} (known: {', '.join(COMPARISONS)})")


def paper_value(claim: dict):
    """The declared value as the paper states it, for display."""
    if "expected" in claim:
        return claim["expected"]
    if "min" in claim or "max" in claim:
        return f"[{claim.get('min')}, {claim.get('max')}]"
    return None


# -------------------------------------------------------------------- one claim
def verify_claim(cid: str, claim: dict, metrics, experiments: dict | None = None) -> dict:
    metric = claim.get("metric", cid)
    cls = claim.get("class", "SUPPORTING_STABLE")
    exp_meta = (experiments or {}).get(claim.get("experiment"), {})
    row = dict(id=cid, metric=metric, section=claim.get("section"), text=claim.get("text"),
               **{"class": cls}, comparison=claim.get("comparison"),
               paper_value=paper_value(claim), generated_value=None, basis=None, delta=None,
               decimals=claim.get("decimals"), scale=claim.get("scale"),
               experiment=claim.get("experiment"),
               function=claim.get("function") or exp_meta.get("function"),
               artifact=claim.get("artifact") or (exp_meta.get("artifacts") or [None])[0],
               status=None, detail="")
    if cls not in CLASSES:
        return dict(row, status=FAIL, detail=f"unknown class {cls!r}")
    if claim.get("machine_checkable") is False:
        return dict(row, status=NMC, detail=claim.get("reason", ""))
    if metric not in metrics.values:
        if cls in ("DIAGNOSTIC", "SENSITIVITY"):      # a diagnostic that this run did not ask for
            return dict(row, status=NOT_REPRODUCED, detail="not generated in this run")
        return dict(row, status=FAIL, detail=f"metric {metric!r} is not produced by THEMIS")
    val, basis = metrics.values[metric], metrics.basis[metric]
    row.update(generated_value=val, basis=basis)
    rule = claim.get("comparison")
    if "expected" not in claim and "min" not in claim and "max" not in claim:
        return dict(row, status=INFO, detail="regenerated; the paper declares no value for it")
    if rule not in COMPARISONS:
        return dict(row, status=FAIL, detail=f"unknown comparison rule {rule!r}")
    if basis == "UNAVAILABLE":
        return dict(row, status=NOT_REPRODUCED, detail="not obtainable from the loaded input")
    if isinstance(val, float) and math.isnan(val):
        return dict(row, status=FAIL, detail="generated value is NaN")
    try:
        ok, detail = compare(rule, val, claim)
    except (ValueError, decimal.InvalidOperation) as e:
        return dict(row, status=FAIL, detail=str(e))
    if _is_number(val) and _is_number(claim.get("expected")) and rule == "exact_integer":
        row["delta"] = float(_dec(val) - _dec(claim["expected"]))
    if basis == "LIVE":
        return dict(row, status=PASS if ok else FAIL, detail=detail)
    if not ok and basis == "FROZEN_MANIFEST":
        return dict(row, status=FAIL, detail="the frozen corpus figure disagrees with the paper. " + detail)
    why = {"FROZEN_MANIFEST": "only a figure frozen in the reference sample's manifest is available; "
                              "it " + ("agrees" if ok else "disagrees") + " with the paper but was not recomputed",
           "SAMPLE_OBSERVED": "the loaded input is a sample of the claims; its value is not the corpus's"}[basis]
    return dict(row, status=NOT_REPRODUCED, detail=why, frozen_agrees=ok if basis == "FROZEN_MANIFEST" else None)


# ------------------------------------------------------------------- PDF layer
def render_token(claim: dict, spec: dict) -> str:
    """The way the paper prints the manifest's expected value, for the PDF check."""
    if "token" in spec:
        return spec["token"]
    rule, exp, d = claim.get("comparison"), claim.get("expected"), int(claim.get("decimals", 0))
    if rule == "exact_integer":
        s = f"{int(exp):,}"
    elif rule == "rounded_percent":
        s = f"{_half_up(_dec(exp) * 100, d)}%"
    elif rule in ("rounded_decimal", "approximate_text"):
        s = f"{_half_up(_dec(exp), d)}"
    else:
        s = str(exp)
    return spec.get("prefix", "") + s + spec.get("suffix", "")


def _norm(t: str) -> str:
    t = (t.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("–", "-").replace("−", "-")
          .replace("‑", "-").replace(" ", " "))
    return re.sub(r"\s+", " ", t).strip()


def extract_pdf_pages(pdf) -> list[str] | None:
    """Layout-preserving text, one string per page; None if no extractor."""
    exe = shutil.which("pdftotext")
    if not exe or not pathlib.Path(pdf).is_file():
        return None
    out = subprocess.run([exe, "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return out.split("\f")[:-1] if out.endswith("\f") else out.split("\f")


def locate_pdf(manifest: dict, given=None) -> pathlib.Path | None:
    name = (manifest.get("paper") or {}).get("file")
    cands = [given, os.environ.get("THEMIS_PAPER_PDF")]
    if name:
        cands += [PKG / "paper" / name] + [PKG.parents[i] / name for i in range(0, 3) if len(PKG.parents) > i]
    for c in cands:
        if c and pathlib.Path(c).is_file():
            return pathlib.Path(c)
    return None


def check_pdf_claim(claim: dict, pages: list[str]) -> dict:
    spec = claim.get("pdf")
    if not spec:
        return dict(status="NOT_CHECKED", page=None, detail="no PDF locator declared")
    tok = render_token(claim, spec)
    if "row" in spec:                                   # a table row: find its line, take one cell
        for i, pg in enumerate(pages):
            lines = pg.splitlines()
            for j, line in enumerate(lines):
                cells = [x for x in re.split(r"\s{2,}", line.strip()) if x]
                col = spec["col"]
                if cells and cells[0] == spec["row"] and len(cells) == 1 and j + 1 < len(lines):
                    # a label that wraps onto two lines: the figures sit on the next line, without the label
                    cells, col = [x for x in re.split(r"\s{2,}", lines[j + 1].strip()) if x], col - 1
                elif not (cells and cells[0] == spec["row"]):
                    continue
                if len(cells) > col >= 0:
                    ok = _norm(cells[col]) == _norm(tok)
                    return dict(status=PASS if ok else FAIL, page=i + 1, token=tok,
                                detail=f"row {spec['row']!r} col {spec['col']} prints {cells[col]!r}")
        return dict(status=FAIL, page=None, token=tok, detail=f"row {spec['row']!r} not found in the PDF")
    if "{v}" not in spec["text"] and not spec.get("literal"):
        return dict(status=FAIL, page=None, token=tok, detail="locator has no {v}: it cannot tie the PDF to the manifest value")
    phrase = _norm(spec["text"].replace("{v}", tok))
    for i, pg in enumerate(pages):
        if phrase in _norm(pg):
            return dict(status=PASS, page=i + 1, token=tok, detail=f"found {phrase!r}")
    joined = _norm(" ".join(pages))
    return dict(status=FAIL, page=None, token=tok,
                detail=f"{phrase!r} not found" + (" (the pdf and the manifest disagree)" if phrase not in joined else ""))


def verify_pdf(manifest: dict, pdf=None) -> dict:
    if pdf and not pathlib.Path(pdf).is_file():      # never quietly check a different paper than the one asked for
        return dict(status="NOT_CHECKED", path=str(pdf), reason=f"the PDF given does not exist: {pdf}", results={})
    path = locate_pdf(manifest, pdf)
    if path is None:
        return dict(status="NOT_CHECKED", reason="no PDF found (pass --paper or set THEMIS_PAPER_PDF)", results={})
    pages = extract_pdf_pages(path)
    if pages is None:
        return dict(status="NOT_CHECKED", path=str(path), reason="pdftotext (poppler) is not installed", results={})
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    declared = (manifest.get("paper") or {}).get("sha256")
    res = {cid: check_pdf_claim(c, pages) for cid, c in manifest["claims"].items() if c.get("pdf")}
    bad = [k for k, v in res.items() if v["status"] == FAIL]
    return dict(status=FAIL if bad else PASS, path=str(path), sha256=sha, pages=len(pages),
                same_file_as_manifest=(declared == sha) if declared else None,
                n_checked=len(res), failed=bad, results=res)


# ------------------------------------------------------------------- whole run
def verify(metrics, manifest: dict, pdf=None, check_pdf: bool = True) -> dict:
    claims = manifest.get("claims", {})
    policy = manifest.get("policy", {})
    rows, warnings = [], []
    for cid, c in claims.items():
        rows.append(verify_claim(cid, c, metrics, manifest.get("experiments")))
    for cid in manifest.get("required", []):
        if cid not in claims:
            cls = "HEADLINE_STABLE"
            rows.append(dict(id=cid, metric=cid, section=None, text="declared as required but absent from the manifest",
                             comparison=None, paper_value=None, generated_value=None, basis=None, delta=None,
                             experiment=None, function=None, artifact=None, status=FAIL,
                             detail="a claim the manifest requires has no entry", **{"class": cls}))
    pdf_res = verify_pdf(manifest, pdf) if check_pdf else dict(status="NOT_CHECKED", reason="disabled", results={})
    for r in rows:
        r["pdf"] = pdf_res.get("results", {}).get(r["id"])
    if pdf_res.get("same_file_as_manifest") is False:
        warnings.append("the PDF is not the file the manifest was written against (sha256 differs)")
    uncovered = sorted(set(metrics.values) - {r["metric"] for r in rows})
    counts = {}
    for r in rows:
        counts.setdefault(r["class"], {}).setdefault(r["status"], 0)
        counts[r["class"]][r["status"]] += 1

    def effect(r, kind):     # what a status does to the overall verdict, per the manifest's class policy
        quiet = r["class"] in ("DIAGNOSTIC", "SENSITIVITY")
        return (policy.get(r["class"]) or {}).get(kind, "ignore" if quiet else {"on_fail": "fail", "on_not_reproduced": "block"}[kind])
    failing = [r["id"] for r in rows if r["status"] == FAIL and effect(r, "on_fail") == "fail"]
    pdf_bad = [k for k in pdf_res.get("failed", [])
               if effect(next(r for r in rows if r["id"] == k), "on_fail") == "fail"]
    blocked = [r["id"] for r in rows if r["status"] == NOT_REPRODUCED and effect(r, "on_not_reproduced") == "block"]
    status = FAIL if (failing or pdf_bad) else BLOCKED if blocked else PASS
    return dict(status=status, claims=rows, counts=counts, failing=failing + pdf_bad, blocked=blocked,
                pdf=dict((k, v) for k, v in pdf_res.items() if k != "results"),
                warnings=warnings, uncovered_metrics=len(uncovered),
                paper=manifest.get("paper"), manifest_sha256=manifest_hash(manifest) if "_path" in manifest else None)


# ------------------------------------------------------------------- rendering
def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:,.6g}" if abs(v) < 1e6 else f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def show(v, row: dict, declared: bool = False) -> str:
    """A value the way the paper prints it, from the rule the claim declares. A
    `declared` value is already in the paper's units; a generated one is scaled."""
    d, rule = row.get("decimals"), row.get("comparison")
    if _is_number(v) and d is not None and rule == "rounded_percent":
        return f"{_half_up(_dec(v) * 100, int(d))}%"
    if _is_number(v) and d is not None and rule in ("rounded_decimal", "approximate_text"):
        return f"{_half_up(_dec(v) * (1 if declared else _dec(row.get('scale') or 1)), int(d))}"
    return _fmt(v)


def format_console(res: dict, only_class=None, width: int = 78) -> str:
    out = ["THEMIS PAPER VERIFICATION", "-" * width]
    for r in res["claims"]:
        if only_class and r["class"] != only_class:
            continue
        if r["status"] in (INFO, NMC):
            continue
        tag = r["status"] if r["status"] != NOT_REPRODUCED else "NOT REPRODUCED"
        pdf = (r.get("pdf") or {}).get("status")
        out.append(f"{r['id']}  [{r['class']}]")
        out.append(f"  paper  {show(r['paper_value'], r, True):>22}    themis {show(r['generated_value'], r):>22}   {tag}"
                   + (f"   pdf {pdf}" if pdf and pdf != "NOT_CHECKED" else ""))
        if r["status"] in (FAIL, NOT_REPRODUCED) and r["detail"]:
            out.append(f"    {r['detail']}")
    out += ["-" * width]
    for cls, cnt in sorted(res["counts"].items()):
        n = sum(cnt.values())
        out.append(f"{cls:<20}{cnt.get(PASS, 0)}/{n} PASS   " +
                   "  ".join(f"{k} {v}" for k, v in cnt.items() if k != PASS))
    out.append(f"PDF layer: {res['pdf']['status']}" + (f" ({res['pdf'].get('reason')})" if res['pdf'].get('reason') else ""))
    for w in res["warnings"]:
        out.append(f"warning: {w}")
    out += ["", "FINAL STATUS", res["status"]]
    return "\n".join(out)


def claim_map_markdown(res: dict, metrics_meta: dict | None = None) -> str:
    """PAPER_CLAIM_MAP.md: every claim, its analysis function and artifact, both values, the rule."""
    L = ["# Paper claim map", "",
         f"Paper: {(res.get('paper') or {}).get('title', '')} ({(res.get('paper') or {}).get('file', '')})", "",
         "Generated by `themis verify-paper` / `themis reproduce-paper`; do not edit. Status `NOT_REPRODUCED` means the "
         "loaded input could not recompute the value (a frozen or sampled figure is not a reproduction).", "",
         "| section | page | claim | metric | analysis function | source artifact | generated | paper | rule | class | basis | status |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["claims"]:
        page = (r.get("pdf") or {}).get("page") or ""
        L.append("| {} | {} | {} | `{}` | `{}` | {} | {} | {} | {} | {} | {} | **{}** |".format(
            r.get("section") or "", page, (r.get("text") or "").replace("|", "/"), r["metric"],
            r.get("function") or "", r.get("artifact") or "", show(r["generated_value"], r), show(r["paper_value"], r, True),
            r.get("comparison") or "", r["class"], r.get("basis") or "", r["status"]))
    return "\n".join(L) + "\n"
