import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { useJob } from "../lib/useJob.js";
import { bytes, fmt, pct } from "../lib/format.js";
import { ErrorBox, PageHead, Section } from "../components/ui.jsx";
import Pipeline from "../components/Pipeline.jsx";

const ROLES = [
  { key: "address", label: "Address", required: true },
  { key: "label", label: "Label" },
  { key: "category", label: "Category" },
  { key: "actor", label: "Actor" },
  { key: "source", label: "Declared source / URL" },
  { key: "timestamp", label: "Revision date" },
  { key: "confidence", label: "Confidence" },
];

async function sha256(file) {
  if (!window.crypto?.subtle) return null;
  const digest = await window.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Live checks derived from the pre-flight response and the current mapping
// (so editing a select updates them). Detection figures are the backend's.
function checksFor(pf, mapping) {
  const d = pf.detection;
  const out = [];
  const detected = d.confidence && d.confidence !== "NONE" && d.blockchain;
  out.push({
    ok: detected ? "ok" : "fail",
    text: detected
      ? `Cryptocurrency addresses detected: ${d.blockchain}, confidence ${d.confidence}`
      : "No cryptocurrency addresses detected in any column",
    sub: detected ? `${pct(d.sample_hit_rate, 1)} of ${fmt(d.sampled)} sampled rows in “${d.address_field}” are valid ${d.blockchain} addresses (${fmt(d.total_rows)} rows in file)` : null,
  });
  const structured = mapping.address && (mapping.label || mapping.category);
  out.push({
    ok: structured ? "ok" : "fail",
    text: structured ? "Attribution structure found: an address column and a label or category column" : "Attribution structure missing: map an address column and a label or category column",
  });
  if (d.unsupported_chain_field) out.push({ ok: "warn", text: `Column “${d.unsupported_chain_field}” looks like an unsupported chain and will not be analysed` });
  out.push(mapping.timestamp
    ? { ok: "ok", text: `Revision date mapped to “${mapping.timestamp}”: currency can be assessed` }
    : { ok: "warn", text: "No revision-date column mapped: every label will be reported as currency-unknown" });
  out.push(mapping.source
    ? { ok: "ok", text: `Declared source mapped to “${mapping.source}”` }
    : { ok: "warn", text: "No declared-source column mapped" });
  return out;
}
const MK = { ok: "✓", warn: "!", fail: "✕" };
const TONE = { ok: "ok", warn: "flag", fail: "hot" };

export default function HomePage() {
  const nav = useNavigate();
  const { activate } = useAnalysis();
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [hash, setHash] = useState(undefined);        // undefined: computing, null: unavailable
  const [pf, setPf] = useState(null);
  const [pfBusy, setPfBusy] = useState(false);
  const [mapping, setMapping] = useState({});
  const [sourceId, setSourceId] = useState("uploaded_dataset");
  const [useReference, setUseReference] = useState(true);
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);
  const upload = useJob();
  const paper = useJob();
  const pipeRef = useRef(null);
  const started = !!upload.job;
  useEffect(() => { if (started) pipeRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [started]);

  // choose a file -> client-side hash + live pre-flight, immediately
  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setHash(undefined); setPf(null); setError(null); upload.reset();
    sha256(file).then((h) => { if (!cancelled) setHash(h); }).catch(() => { if (!cancelled) setHash(null); });
    setPfBusy(true);
    api.preflight(file)
      .then((r) => { if (!cancelled) { setPf(r); setMapping(r.mapping); } })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setPfBusy(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  const pick = (f) => { if (f) { setFile(f); setSourceId((f.name || "uploaded_dataset").replace(/\.(csv|gz)+$/i, "") || "uploaded_dataset"); } };

  const finish = (j) => {
    if (j.status === "complete") { activate(j.analysis_id, j.meta); nav("/overview"); }
  };
  const runAnalysis = () => upload.run(() => api.startAnalysisJob({ file, sourceId, useReference, mapping }), finish);
  const runPaper = () => paper.run(() => api.startPaperJob(), finish);

  const uploading = upload.job?.status === "running";
  const checks = pf ? checksFor(pf, mapping) : [];
  const blocked = !pf || !mapping.address || uploading;

  return (
    <div>
      <PageHead kicker="New analysis" title="Audit a public attribution dataset"
        lead="Load a CSV of cryptocurrency attribution claims. THEMIS inspects it, lets you confirm how its columns map onto claims, then measures provenance, cross-source agreement, independence and currency against the bundled reference corpus. It reports evidence, not verdicts." />

      <div className="two-col">
        <div>
          <Section title="1 · Dataset">
            <div className={`dropzone${over ? " over" : ""}`} role="button" tabIndex={0}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.current?.click(); } }}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]); }}>
              <div className="dz-title">Drop a CSV here, or <span style={{ color: "var(--ac)" }}>choose a file</span></div>
              <div className="fnt" style={{ fontSize: 11.5 }}>.csv or .csv.gz · processed by the THEMIS API, never sent elsewhere</div>
              <input ref={fileInput} type="file" accept=".csv,.gz" hidden onChange={(e) => pick(e.target.files?.[0])} />
            </div>

            {file && (
              <div className="filecard" style={{ marginTop: 12 }}>
                <div><span className="mut">file </span>{file.name}</div>
                <div><span className="mut">size </span>{bytes(file.size)}{pf ? ` · ${fmt(pf.n_rows)} rows · ${pf.fieldnames.length} columns` : ""}</div>
                <div style={{ wordBreak: "break-all" }}><span className="mut">sha-256 </span>
                  {hash === undefined ? "computing…" : hash === null ? "unavailable in this browser context" : hash}</div>
              </div>
            )}

            {file && (
              <div className="controls" style={{ marginTop: 12, marginBottom: 0 }}>
                <label className="field">Source id:
                  <input type="text" value={sourceId} onChange={(e) => setSourceId(e.target.value)} style={{ width: 170 }} />
                </label>
                <label className="field" title="Compare against the bundled seven-dataset reference corpus. Without it only internal checks (address validity, currency) are possible.">
                  <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
                  compare against reference corpus
                </label>
              </div>
            )}
          </Section>

          {error && <ErrorBox title="Pre-flight failed">{error}</ErrorBox>}
          {pfBusy && <div className="loading">Inspecting file…</div>}

          {pf && (
            <>
              <Section title="2 · Pre-flight" meta={`${fmt(pf.n_rows)} rows`}>
                <div className="panel pad">
                  {checks.map((c, i) => (
                    <div key={i} className="checkline">
                      <span className={`mk ${TONE[c.ok]}`}>{MK[c.ok]}</span>
                      <div><div>{c.text}</div>{c.sub && <div className="mut" style={{ fontSize: 11.5 }}>{c.sub}</div>}</div>
                    </div>
                  ))}
                </div>
              </Section>

              <Section title="3 · Schema mapping" note="THEMIS’s best guess at which column plays which role. Correct anything before running: nothing is analysed until you confirm.">
                <div className="tablewrap">
                  <table>
                    <thead><tr><th>Role</th><th>Column</th><th>First row</th></tr></thead>
                    <tbody>
                      {ROLES.map((r) => (
                        <tr key={r.key}>
                          <td>{r.label}{r.required && <span className="hot"> *</span>}</td>
                          <td>
                            <select className="plain" value={mapping[r.key] || ""} aria-label={`${r.label} column`}
                              onChange={(e) => setMapping({ ...mapping, [r.key]: e.target.value || null })}>
                              <option value="">— not present —</option>
                              {pf.fieldnames.map((f) => <option key={f} value={f}>{f}</option>)}
                            </select>
                          </td>
                          <td className="mono small mut">{mapping[r.key] && pf.sample_rows[0] ? String(pf.sample_rows[0][mapping[r.key]] ?? "").slice(0, 48) : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details className="more">
                  <summary>Show {pf.sample_rows.length} sample rows</summary>
                  <div className="tablewrap"><table>
                    <thead><tr>{pf.fieldnames.map((f) => <th key={f}>{f}</th>)}</tr></thead>
                    <tbody>{pf.sample_rows.map((row, i) => <tr key={i}>{pf.fieldnames.map((f) => <td key={f} className="mono small">{row[f]}</td>)}</tr>)}</tbody>
                  </table></div>
                </details>
                <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center" }}>
                  <button type="button" className="btn" disabled={blocked} aria-disabled={blocked} onClick={runAnalysis}>
                    {uploading ? "Running…" : "Run analysis"}
                  </button>
                  {!mapping.address && <span className="hot" style={{ fontSize: 12 }}>Map an address column to continue.</span>}
                </div>
                {mapping.address && !(pf.detection.confidence && pf.detection.confidence !== "NONE" && pf.detection.blockchain) && (
                  <div className="inline-note" role="alert">
                    Pre-flight found no cryptocurrency addresses in this file. If you run anyway, THEMIS cannot validate the values in “{mapping.address}” as addresses of any chain, and the results will not be meaningful.
                  </div>
                )}
              </Section>
            </>
          )}

          {upload.error && <ErrorBox title="Could not start the analysis">{upload.error}</ErrorBox>}
          {upload.job && (
            <div ref={pipeRef}><Section title="Pipeline">
              <Pipeline job={upload.job} title="Analysis pipeline" />
              {upload.job.status === "stopped" && (
                <div className="inline-note" role="alert" style={{ whiteSpace: "pre-line" }}>
                  <strong>Stopped at pre-flight.</strong>{"\n"}{upload.job.preflight?.message || "This dataset did not pass pre-flight, so no audit was produced."}
                </div>
              )}
              {upload.job.status === "failed" && (
                <ErrorBox title="Analysis failed">{upload.job.error}</ErrorBox>
              )}
            </Section></div>
          )}
        </div>

        <aside style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="panel pad">
            <div className="form-label">Reproduce the paper</div>
            <p className="mut" style={{ fontSize: 12.5, lineHeight: 1.6, margin: "0 0 12px" }}>
              Run the published method on the bundled seven-source research corpus: provenance, agreement, independence, chance-corrected agreement and currency. Drift, the bootstrap and anchor validation run on demand from <Link to="/paper">Reproduce Paper</Link>.
            </p>
            <button type="button" className="btn secondary" onClick={runPaper} disabled={paper.job?.status === "running"}>
              {paper.job?.status === "running" ? "Running…" : "Reproduce paper"}
            </button>
          </div>
          {paper.error && <ErrorBox title="Could not start">{paper.error}</ErrorBox>}
          {paper.job && <Pipeline job={paper.job} title="Reproduction pipeline" />}
          {paper.job?.status === "failed" && <ErrorBox title="Reproduction failed">{paper.job.error}</ErrorBox>}
        </aside>
      </div>
    </div>
  );
}
