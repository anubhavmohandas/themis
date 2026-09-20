"""Overview semantics browser QA (Playwright). Drives the built dashboard against a running API and
checks that every Overview figure names its population and that drill-downs keep it.

    python scripts/overview_browser_qa.py sample   # API started with no THEMIS_OBSERVATIONS
    python scripts/overview_browser_qa.py full     # API started with THEMIS_OBSERVATIONS=<observations.csv.gz> THEMIS_AS_OF=2026-09-15

Needs: `themis-web` on :5001, `npx vite preview --host 127.0.0.1 --port 4173` in frontend/ after
`npm run build`, and a Python with playwright + a Chromium. Screenshots go to results/overview_cleanup/
(git-ignored). The full-mode literals are the frozen paper corpus figures, not values the UI supplies."""
import json, pathlib, re, sys, time, urllib.request
from playwright.sync_api import sync_playwright

MODE = sys.argv[1]
OUT = pathlib.Path(__file__).resolve().parent.parent / "results" / "overview_cleanup" / f"shots_{MODE}"; OUT.mkdir(parents=True, exist_ok=True)
UI, API = "http://127.0.0.1:4173", "http://127.0.0.1:5001"
R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def call(path, method="GET"):
    req = urllib.request.Request(API + path, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def new_analysis():
    jid = call("/api/jobs/paper", "POST")["job_id"]
    for _ in range(120):
        j = call(f"/api/jobs/{jid}")
        if j["status"] in ("complete", "failed"):
            assert j["status"] == "complete", j.get("error")
            return j["analysis_id"]
        time.sleep(2)
    raise SystemExit("job timed out")


def has(body, *needles):
    return all(n.lower() in body.lower() for n in needles)


aid = new_analysis()
summary = call(f"/api/analysis/{aid}/summary")
ov = summary["result"]["overview"]
check("API overview scope matches mode", ov["scope"] == ("FULL_CORPUS" if MODE == "full" else "BUNDLED_SAMPLE"), ov["scope"])
check("API meta carries corpus_scope", summary["meta"]["corpus_scope"] == ov["scope"], str(summary["meta"].get("corpus_scope")))

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    errs, bad = [], []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
    pg.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)
    pg.goto(UI, wait_until="networkidle")
    pg.evaluate(f"localStorage.setItem('themis.active_analysis_id', '{aid}')")
    pg.goto(UI + "/overview", wait_until="networkidle"); pg.wait_for_timeout(1200)
    body = pg.inner_text("body")

    if MODE == "full":
        check("sidebar says paper reproduction + FULL CORPUS", has(body, "paper reproduction", "full corpus"))
        for needle in ("1,545,710", "1,497,106", "1,497,191", "15,413", "1.03%", "7,845", "7,112", "429", "853,583 / 1,497,106",
                       "499,327 / 1,545,710", "32.30%", "1,035,420 / 1,545,710", "66.99%", "n = 15,413", "LIVE FULL CORPUS · NORMALIZED ADDRESSES",
                       "LIVE FULL CORPUS · CLAIM BASED", "98.97%", "1,481,693 / 1,497,106", "10,515", "3,197"):
            check(f"shows {needle}", needle.lower() in body.lower())
        for stale in ("15,400", "7,832", "483,296 / 1,545,710", "268,891", "3,184", "86.41%", "bundled seven-source", "BUNDLED SAMPLE"):
            check(f"does not show {stale}", stale.lower() not in body.lower())
        check("intro states reconstructed corpus", "reconstructed seven-source research corpus" in body)
        check("normalized and raw are separate labelled cells", has(body, "normalized addresses", "raw address keys", "after source-specific normalization", "before cross-source normalization"))
    else:
        check("sidebar says paper reproduction + BUNDLED SAMPLE", has(body, "paper reproduction", "bundled sample"))
        for needle in ("1,545,710", "1,497,191", "15,400", "7,832", "not available", "SAMPLE CURRENCY DIAGNOSTICS", "268,891 claims",
                       "853,583 / 1,497,191", "86.41%", "sample-backed view", "n = 15,400 sample multi-dataset addresses", "3,184"):
            check(f"shows {needle}", needle.lower() in body.lower())
        for stale in ("15,413", "1,497,106", "reconstructed seven-source", "bundled seven-source", "98.97%"):
            check(f"does not show {stale}", stale.lower() not in body.lower())
        check("sample currency label precedes its numbers", body.lower().index("sample currency diagnostics") < body.index("86.41%"))
        check("no corpus-wide share for sample multi-dataset", not re.search(r"multi-dataset addresses[^\n]*\d\.\d\d%", body, re.I))

    check("no share anywhere is over a claims/addresses mix (tagpack)", "483,296 / 1,545,710" not in body)
    for w in (1280, 1440, 1920):
        pg.set_viewport_size({"width": w, "height": 1100}); pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / f"overview_{w}.png"), full_page=True)
        over = pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check(f"no horizontal overflow at {w}", not over)
    pg.set_viewport_size({"width": 1440, "height": 1000})

    # refresh keeps scope
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(1200)
    body2 = pg.inner_text("body")
    check("scope label survives refresh", has(body2, "full corpus" if MODE == "full" else "bundled sample"))
    check("numbers survive refresh", ("15,413" if MODE == "full" else "15,400") in body2)

    # ---- drill-downs
    pg.locator("a.metric", has_text="Multi-dataset addresses").click(); pg.wait_for_timeout(1500)
    url = pg.url; t = pg.inner_text("body")
    if MODE == "full":
        check("multi-dataset drill: population=normalized_full_corpus", "population=normalized_full_corpus" in url, url)
        check("multi-dataset drill lands on FULL CORPUS RECORDS", "full corpus records" in t.lower() and "bundled sample" not in t.lower())
        check("multi-dataset drill: 15,413 addresses", "15,413" in t)
    else:
        check("multi-dataset drill: population=bundled_sample", "population=bundled_sample" in url, url)
        check("multi-dataset drill lands on SAMPLE AGREEMENT RECORDS", "sample agreement records" in t.lower())
        check("multi-dataset drill: 15,400 addresses", "15,400" in t)
    pg.screenshot(path=str(OUT / "drill_multi.png"))

    pg.goto(UI + "/overview", wait_until="networkidle"); pg.wait_for_timeout(1000)
    pg.locator(".barrow", has_text="Exact agreement").click(); pg.wait_for_timeout(1500)
    url, t = pg.url, pg.inner_text("body")
    check("exact-agreement drill keeps its population", "outcome=exact" in url and f"population={'normalized_full_corpus' if MODE == 'full' else 'bundled_sample'}" in url, url)
    check("exact-agreement drill lands on the right records", ("full corpus records" if MODE == "full" else "sample agreement records") in t.lower())

    pg.goto(UI + "/overview", wait_until="networkidle"); pg.wait_for_timeout(1000)
    pg.locator(".barrow", has_text="Hierarchical refinement").click(); pg.wait_for_timeout(1500)
    url, t = pg.url, pg.inner_text("body")
    check("conflicts drill keeps its population", "/conflicts?kind=hierarchical" in url and "population=" in url, url)
    if MODE == "sample":
        check("conflicts drill labelled sample", "sample agreement records" in t.lower())

    # a full-corpus figure followed into the sample must say so (sample mode), a sample link into the full corpus too
    other = "normalized_full_corpus" if MODE == "sample" else "bundled_sample"
    pg.goto(f"{UI}/claims?comparable=yes&population={other}", wait_until="networkidle"); pg.wait_for_timeout(1500)
    t = pg.inner_text("body").lower()
    check("population mismatch is stated", ("you followed a full-corpus figure" in t) if MODE == "sample" else ("you followed a bundled-sample figure" in t))

    check("no console errors", not errs, "; ".join(errs[:3]))
    check("no HTTP errors", not bad, str(bad[:3]))
    b.close()

fails = [n for n, ok, _ in R if not ok]
print(f"\n{len(R) - len(fails)}/{len(R)} passed", "FAIL: " + ", ".join(fails) if fails else "")
json.dump([dict(check=n, ok=ok, detail=d) for n, ok, d in R], open(OUT / "qa.json", "w"), indent=1)
sys.exit(1 if fails else 0)
