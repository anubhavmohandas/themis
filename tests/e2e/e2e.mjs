// Real-browser workflows against the built frontend (vite preview :4173) and the API (:5001). See README.md.
import { chromium } from "playwright-core";
import fs from "node:fs";

const SP = process.env.SP;
const BASE = "http://127.0.0.1:4173";
const API = "http://127.0.0.1:5001";
const exe = process.env.CHROMIUM_PATH || process.env.HOME + "/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell";

const results = [];
const browser = await chromium.launch({ executablePath: exe });
const ctx = await browser.newContext({ acceptDownloads: true });
const page = await ctx.newPage();
page.setDefaultTimeout(90000);
const dialogs = [], pageErrors = [], consoleErrors = [];
page.on("dialog", async (d) => { dialogs.push(d.message()); await d.dismiss(); });
page.on("pageerror", (e) => pageErrors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });

async function step(name, fn) {
  const t0 = Date.now();
  try { const note = await fn(); results.push({ name, status: "PASS", note: note || "", ms: Date.now() - t0 }); console.log("PASS", name, note || ""); }
  catch (e) {
    results.push({ name, status: "FAIL", note: String(e).split("\n")[0], ms: Date.now() - t0 }); console.log("FAIL", name, String(e).split("\n")[0]);
    try { await page.screenshot({ path: `${SP}/fail-${results.length}.png`, fullPage: true }); } catch {}
  }
}
const body = () => page.locator("body").innerText();
const expectText = async (re) => { const t = await body(); if (!re.test(t)) throw new Error(`page text does not match ${re}`); return t; };
const expectNoText = async (re) => { const t = await body(); if (re.test(t)) throw new Error(`page text unexpectedly matches ${re}`); return t; };
const xss = () => page.evaluate(() => window.__xss);

async function confirmIfAsked() {
  const cb = page.getByLabel(/I have reviewed the low-confidence mappings/);
  if (await cb.count()) { await cb.check(); await page.waitForTimeout(700); }
}
async function enabled(btn) {
  await page.waitForFunction((el) => el && !el.disabled, await btn.elementHandle(), { timeout: 60000 });
}
async function analyseCsv(file) {
  await page.goto(BASE + "/");
  await page.setInputFiles("input[type=file]", `${SP}/csv/${file}`);
  await page.getByText("2 · Pre-flight").waitFor();
  await confirmIfAsked();
  const run = page.getByRole("button", { name: /Run analysis/ });
  await enabled(run);
  await run.click();
  await page.waitForURL(/\/overview/);
  await page.getByText("Dataset reliability profile").waitFor();
}
async function extractDb(dbName, { driving = "wallets", joins = 0, meta = null } = {}) {
  await page.goto(BASE + "/database");
  await page.getByPlaceholder("dataset.sqlite").fill(dbName);
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await page.getByText("2 · Database inspection").waitFor();
  await page.getByText("3 · Table selection").waitFor();
  await page.getByLabel(/Driving \(claim-subject\) table/).selectOption(driving);
  for (let i = 0; i < joins; i++) await page.getByRole("button", { name: /\+ Join a table/ }).click();
  await page.getByRole("button", { name: /Preflight this join/ }).click();
  await page.getByText("4 · Pre-flight").waitFor();
  await confirmIfAsked();
  if (meta) {
    await page.getByText("Case-study metadata (optional)").click();
    for (const [label, value] of Object.entries(meta)) await page.getByLabel(new RegExp("^" + label)).fill(value);
  }
  const go = page.getByRole("button", { name: /Extract & analyse/ });
  await enabled(go);
  await go.click();
  await page.waitForURL(/\/overview/);
  await page.getByText("Dataset reliability profile").waitFor();
}

// ---------------------------------------------------------------- A: normal CSV
await step("A1 upload -> preflight -> analysis -> overview", async () => {
  await analyseCsv("normal.csv");
  await expectText(/Target claims/i);
  await expectText(/Unresolved provenance/i);
  await expectText(/the assessment of this dataset is/i);      // the closing summary, worded from config/assessment.yml
});
await step("A2 claims table pages server-side", async () => {
  await page.getByRole("link", { name: "Claims", exact: true }).first().click();
  await page.getByText(/matching claims/).waitFor();
  const n = await page.locator("tbody tr").count();
  if (n < 1) throw new Error("no claim rows");
  await expectText(/Showing 1–\d+ of 40 matching claims/);
  return `${n} rows shown of 40`;
});
await step("A3 address inspector", async () => {
  await page.locator("tbody tr td a").first().click();
  await page.waitForURL(/\/address/);
  await page.getByText("Confirmed independent roots").first().waitFor();
  await expectText(/Apparent datasets/i);
});
await step("A4 provenance explorer: declared sources are not roots", async () => {
  await page.getByRole("link", { name: "Provenance", exact: true }).first().click();
  await page.getByText(/Provenance of this file/).waitFor();
  const t = await body();
  if (/2 independent (roots|sources)/i.test(t)) throw new Error("implied two independent roots");
});
await step("A5 export downloads a CSV with neutralised cells", async () => {
  await page.getByRole("link", { name: "Exports", exact: true }).first().click();
  await page.getByText("normalized_claims.csv").first().waitFor();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.locator('a[href*="normalized_claims.csv"]').first().click()]);
  const text = fs.readFileSync(await dl.path(), "utf8");
  if (!text.startsWith("claim_id,address,source,raw_label")) throw new Error("unexpected header: " + text.slice(0, 60));
  return `${dl.suggestedFilename()} ${text.split("\n").length - 1} lines`;
});

// ---------------------------------------------------------------- B: healthy SQLite
await step("B healthy SQLite: inspect -> select -> preflight -> extract -> overview", async () => {
  await extractDb("healthy.db", { joins: 2 });
  await expectText(/Evidence profile: what this extraction does and does not establish/i);
  await expectNoText(/RECOVERED DATASET SUBSET/i);
  await expectNoText(/DATABASE INTEGRITY CHECK FAILED/);
});

// ---------------------------------------------------------------- C: corrupt SQLite
await step("C1 corrupt SQLite shows integrity failure and no table selection", async () => {
  await page.goto(BASE + "/database");
  await page.getByPlaceholder("dataset.sqlite").fill("corrupt.db");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await page.getByText("DATABASE INTEGRITY CHECK FAILED").waitFor();
  await expectText(/Analysis has not started\./);
  await expectNoText(/3 · Table selection/);
  await expectNoText(/Extract & analyse/);
});
await step("C2 server refuses extraction of the corrupt file", async () => {
  const spec = JSON.stringify({ driving_table: "wallets", joins: [] });
  const r = await page.request.post(API + "/api/sqlite/extract", { form: { db: "corrupt.db", spec, use_reference: "false", confirmed: "true" } });
  const j = await r.json();
  if (r.status() !== 200 || j.preflight.stopped !== true) throw new Error(`status ${r.status()} stopped=${j.preflight?.stopped}`);
  if (!/DATABASE INTEGRITY CHECK FAILED/.test(j.preflight.message)) throw new Error("wrong message");
  if (j.meta.n_claims !== 0) throw new Error("claims were created");
  const c = await page.request.get(`${API}/api/analysis/${j.analysis_id}/claims`);
  if (c.status() !== 409) throw new Error(`claims endpoint answered ${c.status()} for a stopped analysis`);
  return "stopped=true, 0 claims, /claims -> 409";
});

// ---------------------------------------------------------------- D: recovered subset
await step("D recovered subset: banner is prominent when declared", async () => {
  await extractDb("recovered.db", { joins: 2, meta: { "Analysis origin": "recovered_sqlite_subset", "Integrity status": "source_file_truncated",
    "Recovery status": "recovered_subset", "Source identity status": "partially_attributed", "Provenance resolution status": "unresolved",
    "Limitations": "partial recovery only\nprovenance resolution status: resolved" } });
  await expectText(/RECOVERED DATASET SUBSET/i);
  await expectText(/This analysis does not represent the complete original database\./i);
  await expectText(/did not verify it/);
  const alertText = await page.locator('[role="alert"]').first().innerText();
  if (!/RECOVERED DATASET SUBSET/i.test(alertText)) throw new Error("banner is not the alert region");
  // a newline in a value must not pose as another field row
  const rows = await page.locator('[role="alert"] strong').allInnerTexts();
  const forged = rows.filter((t) => /provenance resolution status/i.test(t)).length;
  if (forged !== 1) throw new Error(`expected exactly one 'provenance resolution status' label, found ${forged}`);
});
await step("D2 an original-database declaration does not raise the recovered banner", async () => {
  await extractDb("healthy.db", { joins: 2, meta: { "Analysis origin": "original_full_database", "Integrity status": "verified_by_analyst" } });
  await expectNoText(/RECOVERED DATASET SUBSET/i);
  await expectText(/Declared by the analyst/);
});

// ---------------------------------------------------------------- E: synthetic dependent-source demo
await step("E dependent-source demo: descriptors and dependency, never independent roots", async () => {
  await extractDb("dependent.sqlite", { joins: 0 });
  const t = await expectText(/DECLARED SOURCE DESCRIPTOR/i);
  if (!/POTENTIAL \/ DOCUMENTED DEPENDENCY/i.test(t)) throw new Error("dependency label missing");
  if (!/Confirmed independent roots\s*\n?\s*(not established|0)\b/i.test(t)) throw new Error("confirmed independent roots is not 'not established'");
  if (!/Independent corroboration\s*\n?\s*not established/i.test(t)) throw new Error("independent corroboration is not 'not established'");
  if (/[2-9]\d* independent (roots|sources)/i.test(t)) throw new Error("implies multiple independent roots");
  const sect = t.slice(t.search(/Evidence profile/i), t.search(/Evidence profile/i) + 1800).replace(/\n+/g, " | ");
  fs.writeFileSync(`${SP}/e2e-E-evidence-profile.txt`, sect);
  if (!/dependency_candidate|claim\(s\) carry a declared source/.test(t) && !/claim\(s\) carry/.test(t)) throw new Error("candidate-claims line missing");
  await expectText(/The dataset contains usable attribution records, but the evidence needed to treat its source descriptors as independent forensic corroboration is not established\./);
});

// ---------------------------------------------------------------- H: multi-chain, per-row chain
await step("H1 multi-chain file: chain per row, invalid identifiers rejected and shown, nothing crashes", async () => {
  await page.goto(BASE + "/");
  await page.setInputFiles("input[type=file]", `${SP}/csv/multichain.csv`);
  await page.getByText("2 · Pre-flight").waitFor();
  await expectText(/Blockchain: stated per row by 'chain'/);
  await expectText(/Declared source: 'source' \(a class of evidence, not a per-claim source\)/);
  await confirmIfAsked();
  const run = page.getByRole("button", { name: /Run analysis/ });
  await enabled(run);
  await run.click();
  await page.waitForURL(/\/overview/);
  await page.getByText("Dataset reliability profile").waitFor();          // a page that used to go blank when rows were rejected
  await expectText(/Identifier validity by chain/);
  await expectText(/Rejected rows/);
  await expectText(/bitcoin\s+50\s+\d+/);
  await expectNoText(/verified attribution|ground truth confirmed/i);
});
await step("H2 a mapping that does not fit the values is refused, and is not a verdict on the file", async () => {
  await page.goto(BASE + "/");
  await page.setInputFiles("input[type=file]", `${SP}/csv/multichain.csv`);
  await page.getByText("2 · Pre-flight").waitFor();
  await page.getByLabel("Meaning of address").selectOption({ label: "Market timestamp" });
  await page.getByText(/this column cannot date a claim/).first().waitFor();
  await expectText(/set by you/);
  await expectNoText(/does not appear to contain cryptocurrency attribution data/);
  await page.getByRole("button", { name: /Reset to THEMIS/ }).click();
  await page.getByText(/Blockchain: stated per row/).waitFor();
  await expectNoText(/set by you/);
});

// ---------------------------------------------------------------- F: XSS
await step("F1 hostile CSV renders as text, nothing executes", async () => {
  await analyseCsv("xss.csv");
  await page.getByRole("link", { name: "Claims", exact: true }).first().click();
  await page.getByText(/matching claims/).waitFor();
  await expectText(/<script>window\.__xss=1<\/script>/);
  if (await xss()) throw new Error("window.__xss was set");
  if (await page.locator("tbody img, tbody script").count()) throw new Error("hostile markup became DOM");
  await page.locator("tbody tr td a").first().click();
  await page.waitForURL(/\/address/);
  await page.getByText("Confirmed independent roots").first().waitFor();
  await page.getByRole("link", { name: "Provenance", exact: true }).first().click();
  await page.getByText(/Provenance of this file/).waitFor();
  await page.getByRole("link", { name: "Exports", exact: true }).first().click();
  await page.getByText("normalized_claims.csv").first().waitFor();
  if (await xss()) throw new Error("window.__xss was set on a later page");
});
await step("F2 hostile SQLite names render as text, nothing executes", async () => {
  await page.goto(BASE + "/database");
  await page.getByPlaceholder("dataset.sqlite").fill("xss.db");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await page.getByText("2 · Database inspection").waitFor();
  await expectText(/<img src=x onerror=window\.__xss=1>/);
  if (await xss()) throw new Error("window.__xss was set");
  if (await page.locator("main img, table img, table script").count()) throw new Error("hostile markup became DOM");
});
await step("F3 an error message echoing hostile input renders as text", async () => {
  await page.goto(BASE + "/database");
  await page.getByPlaceholder("dataset.sqlite").fill("<img src=x onerror=window.__xss=1>.db");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await page.getByText("Request failed").waitFor();
  await expectText(/<img src=x onerror=window\.__xss=1>/);
  if (await xss()) throw new Error("window.__xss was set");
});
await step("F4 no dialog, page error or unexpected console error across the whole run", async () => {
  if (dialogs.length) throw new Error("dialogs: " + dialogs.join(" | "));
  if (pageErrors.length) throw new Error("page errors: " + pageErrors.join(" | "));
  const real = consoleErrors.filter((m) => !/Failed to load resource/.test(m));
  if (real.length) throw new Error("console errors: " + real.join(" | "));
  return `${consoleErrors.length} failed-resource logs (expected 4xx on refusal paths)`;
});

// ---------------------------------------------------------------- G: a foreign origin in a real browser
await step("G a page on a foreign origin cannot read or write the API", async () => {
  const foreign = await browser.newPage();
  await foreign.goto("http://127.0.0.1:4999/");            // static page served from another port
  const out = await foreign.evaluate(async (api) => {
    const r = {};
    try { await fetch(api + "/api/health"); r.read = "readable"; } catch (e) { r.read = "blocked"; }
    try {
      const fd = new FormData(); fd.append("file", new Blob(["address,label\n"]), "x.csv"); fd.append("use_reference", "false");
      const resp = await fetch(api + "/api/analysis", { method: "POST", body: fd, mode: "no-cors" });
      r.write = "sent (opaque)";
    } catch (e) { r.write = "blocked"; }
    return r;
  }, API);
  await foreign.close();
  if (out.read !== "blocked") throw new Error("foreign origin could read a response: " + JSON.stringify(out));
  const list = await (await page.request.get(API + "/api/analysis")).json();
  if (list.some((a) => a.dataset_name === "x.csv")) throw new Error("the blind cross-origin upload created an analysis");
  return JSON.stringify(out);
});

await browser.close();
fs.writeFileSync(`${SP}/e2e-results.json`, JSON.stringify(results, null, 1));
const failed = results.filter((r) => r.status !== "PASS");
console.log(`\n${results.length - failed.length}/${results.length} steps passed`);
process.exit(failed.length ? 1 : 0);
