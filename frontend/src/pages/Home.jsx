import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { useJob } from "../lib/useJob.js";
import { bytes, fmt, pct } from "../lib/format.js";
import { ErrorBox, PageHead, Section } from "../components/ui.jsx";
import Pipeline from "../components/Pipeline.jsx";
import { ChainPicker, ConfirmMapping, MappingTable, PreflightChecks, PreflightVerdict } from "../components/Preflight.jsx";

async function sha256(file) {
  if (!window.crypto?.subtle) return null;
  const digest = await window.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function HomePage() {
  const nav = useNavigate();
  const { activate } = useAnalysis();
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [hash, setHash] = useState(undefined);        // undefined: computing, null: unavailable
  const [pf, setPf] = useState(null);
  const [pfBusy, setPfBusy] = useState(false);
  const [edits, setEdits] = useState({});            // the analyst's {column: semantic field} corrections
  const [chain, setChain] = useState(null);           // a chain the analyst chose
  const [confirmed, setConfirmed] = useState(false);
  const [sourceId, setSourceId] = useState("uploaded_dataset");
  const [useReference, setUseReference] = useState(true);
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);
  const upload = useJob();
  const paper = useJob();
  const pipeRef = useRef(null);
  const started = !!upload.job;
  useEffect(() => { if (started) pipeRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [started]);

  // choose a file -> client-side hash
  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setHash(undefined);
    // the limit comes from the server's config: the browser must read the whole file to hash it, which crashes the tab on a huge one
    api.health()
      .then((h) => (file.size <= h.browser_hash_max_bytes ? sha256(file) : null))
      .then((h) => { if (!cancelled) setHash(h); })
      .catch(() => { if (!cancelled) setHash(null); });
    return () => { cancelled = true; };
  }, [file]);

  // the file, or any correction to it -> the server re-runs the pre-flight; what it returns is what will be enforced
  const editKey = JSON.stringify(edits);
  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setError(null); upload.reset(); setPfBusy(true);
    const t = setTimeout(() => {
      api.preflight(file, { semantics: edits, chain, confirmed })
        .then((r) => { if (!cancelled) setPf(r); })
        .catch((e) => { if (!cancelled) { setPf(null); setError(e.message); } })
        .finally(() => { if (!cancelled) setPfBusy(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, editKey, chain, confirmed]);

  const resetMapping = () => { setEdits({}); setChain(null); setConfirmed(false); };
  const pick = (f) => { if (f) { setEdits({}); setChain(null); setConfirmed(false); setPf(null); setFile(f); setSourceId((f.name || "uploaded_dataset").replace(/\.(csv|gz)+$/i, "") || "uploaded_dataset"); } };

  const finish = (j) => {
    if (j.status === "complete") { activate(j.analysis_id, j.meta); nav("/overview"); }
  };
  const runAnalysis = () => upload.run(() => api.startAnalysisJob({ file, sourceId, useReference, semantics: edits, chain, confirmed }), finish);
  const runPaper = () => paper.run(() => api.startPaperJob(), finish);

  const uploading = upload.job?.status === "running";
  const p = pf?.preflight;
  const blocked = !p || !p.can_analyze || uploading || pfBusy;

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
            <p className="mut" style={{ fontSize: 12, marginTop: 8 }}>
              Auditing a multi-gigabyte SQLite database instead? <Link to="/database">Open a database</Link> - it is
              inspected and streamed in chunks, never loaded whole or converted to CSV.
            </p>

            {file && (
              <div className="filecard" style={{ marginTop: 12 }}>
                <div><span className="mut">file </span>{file.name}</div>
                <div><span className="mut">size </span>{bytes(file.size)}{pf ? ` · ${fmt(pf.n_rows)} rows · ${pf.fieldnames.length} columns` : ""}</div>
                <div style={{ wordBreak: "break-all" }}><span className="mut">sha-256 </span>
                  {hash === undefined ? "computing…" : hash === null
                    ? (p?.input?.sha256 ? `${p.input.sha256} (computed by the server: too large to hash in the browser)` : "computed by the server once the pre-flight returns")
                    : hash}</div>
              </div>
            )}

            {file && (
              <div className="controls" style={{ marginTop: 12, marginBottom: 0 }}>
                <label className="field">Source id:
                  <input type="text" value={sourceId} onChange={(e) => setSourceId(e.target.value)} style={{ width: 170 }} />
                </label>
                <label className="field" title="Compare against the reference corpus. Without it only internal checks (address validity, currency) are possible.">
                  <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
                  compare against reference corpus
                </label>
              </div>
            )}
          </Section>

          {error && <ErrorBox title="Pre-flight failed">{error}</ErrorBox>}
          {pfBusy && <div className="loading">Inspecting file…</div>}

          {p && (
            <>
              <Section title="2 · Pre-flight" meta={`${fmt(pf.n_rows)} rows`}
                note="Nothing is analysed until the file has a defensible attribution schema: a claim subject that validates on a known chain, and something claimed about it.">
                <PreflightChecks p={p} />
                <PreflightVerdict p={p} />
                <ChainPicker p={p} chains={pf.chains} value={chain} onChange={setChain} />
              </Section>

              <Section title="3 · Schema mapping" note="What THEMIS took each column to mean, from its name and its values. Correct anything: the server re-validates every choice, and a mapping can never waive validation.">
                {Object.keys(edits).length > 0 && (
                  <div className="inline-note" style={{ marginBottom: 8 }}>
                    {Object.keys(edits).length} mapping{Object.keys(edits).length === 1 ? "" : "s"} set by you: {Object.keys(edits).join(", ")}.{" "}
                    <button type="button" className="chip-btn plain" onClick={resetMapping}>Reset to THEMIS's inferred mapping</button>
                  </div>
                )}
                <MappingTable p={p} fields={pf.semantic_fields}
                  onChange={(col, sem) => setEdits({ ...edits, [col]: sem })} />
                <ConfirmMapping p={p} confirmed={confirmed} onChange={setConfirmed} />
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
                  {!p.can_analyze && <span className="hot" style={{ fontSize: 12 }}>Analysis is blocked until the items above are resolved.</span>}
                </div>
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
              Run the published method on the seven-source research corpus: provenance, agreement, independence, chance-corrected agreement and currency. Drift, the bootstrap and anchor validation run on demand from <Link to="/paper">Reproduce Paper</Link>.
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
