import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Tooltip from "../components/Tooltip.jsx";

const ROLES = [
  { key: "address", label: "Address field", required: true },
  { key: "label", label: "Label field" },
  { key: "category", label: "Category field" },
  { key: "actor", label: "Actor field" },
  { key: "source", label: "Declared source / URL field" },
  { key: "timestamp", label: "Timestamp field" },
  { key: "confidence", label: "Confidence field" },
];

// Loop 2 STEP 2/10: upload -> pre-flight -> schema mapping confirmation ->
// run audit. Nothing is analyzed as cryptocurrency attribution data until
// the user confirms the mapping.
export default function LandingPage() {
  const navigate = useNavigate();
  const { activate } = useAnalysis();

  const [file, setFile] = useState(null);
  const [stage, setStage] = useState("idle");        // idle -> preflighted -> running
  const [preflight, setPreflight] = useState(null);
  const [mapping, setMapping] = useState({});
  const [sourceId, setSourceId] = useState("uploaded_dataset");
  const [useReference, setUseReference] = useState(true);
  const [error, setError] = useState(null);
  const [paperBusy, setPaperBusy] = useState(false);

  async function runPreflight(e) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    try {
      const r = await api.preflight(file);
      setPreflight(r);
      setMapping(r.mapping);
      setStage("preflighted");
    } catch (err) {
      setError(err.message);
    }
  }

  async function confirmAndRun() {
    setStage("running");
    setError(null);
    try {
      const r = await api.createAnalysis({ file, sourceId, useReference, mapping });
      if (r.preflight?.stopped) {
        setError(null);
        setPreflight({ ...preflight, stopped: true, message: r.preflight.message });
        setStage("preflighted");
        return;
      }
      activate(r.analysis_id, r.meta);
      navigate("/overview");
    } catch (err) {
      setError(err.message);
      setStage("preflighted");
    }
  }

  async function reproducePaper() {
    setPaperBusy(true);
    setError(null);
    try {
      const r = await api.reproducePaper();
      activate(r.analysis_id, r.meta);
      navigate("/overview");
    } catch (err) {
      setError(err.message);
    } finally {
      setPaperBusy(false);
    }
  }

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Cryptocurrency Attribution Reliability Auditor</div>
        <h1>THEMIS</h1>
        <p className="lead">
          THEMIS evaluates the evidential reliability of public cryptocurrency attribution
          labels by analysing provenance, cross-source agreement, independence, conflicts,
          freshness and forensic conclusion sensitivity. It does not decide truth — it measures
          the strength, independence, traceability and limitations of the evidence used to
          claim it.
        </p>
      </div>

      <div className="section grid cols-2">
        <div className="tile">
          <div className="k">Audit your own dataset</div>
          <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
            Upload a CSV of cryptocurrency attribution claims. THEMIS inspects it, lets you
            confirm the column mapping, then runs a target-specific reliability audit against
            the bundled reference corpus.
          </p>
        </div>
        <div className="tile">
          <div className="k">Reproduce the paper</div>
          <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
            Run the full published methodology against the bundled seven-source research
            corpus — provenance, agreement, independence, drift and the cluster bootstrap.
          </p>
          <button type="button" onClick={reproducePaper} disabled={paperBusy}>
            {paperBusy ? "Loading…" : "Reproduce paper"}
          </button>
        </div>
      </div>

      <div className="section">
        <h2>Upload a dataset</h2>
        <div className="card">
          <form onSubmit={runPreflight}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <div className="k mono" style={{ fontSize: 11, marginBottom: 6, color: "var(--muted)" }}>CSV FILE</div>
                <input type="file" accept=".csv,.gz" onChange={(e) => {
                  setFile(e.target.files?.[0] || null); setStage("idle"); setPreflight(null);
                }} />
              </div>
              <div>
                <div className="k mono" style={{ fontSize: 11, marginBottom: 6, color: "var(--muted)" }}>SOURCE ID</div>
                <input type="text" value={sourceId} onChange={(e) => setSourceId(e.target.value)} />
              </div>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13.5 }}>
                <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
                <Tooltip text="Compare against the bundled seven-dataset reference corpus for reference comparability, agreement and independence. Without it, only internal checks (address validation, freshness) are possible.">
                  compare against reference corpus
                </Tooltip>
              </label>
              <button type="submit" disabled={!file}>Inspect file</button>
            </div>
          </form>
        </div>
      </div>

      {error && <div className="callout warn">{error}</div>}

      {preflight && stage === "preflighted" && !preflight.stopped && (
        <PreflightAndMapping preflight={preflight} mapping={mapping} setMapping={setMapping}
          onConfirm={confirmAndRun} busy={stage === "running"} />
      )}

      {preflight && preflight.stopped && (
        <div className="section">
          <h2>Dataset pre-flight</h2>
          <div className="callout warn" style={{ whiteSpace: "pre-line" }}>{preflight.message}</div>
        </div>
      )}
    </>
  );
}

function PreflightAndMapping({ preflight, mapping, setMapping, onConfirm, busy }) {
  const d = preflight.detection;
  return (
    <>
      <div className="section">
        <h2>Dataset pre-flight</h2>
        <div className="grid cols-3">
          <div className="tile">
            <div className="k">Detection confidence</div>
            <div className="v"><StatusBadge label={d.confidence} kind={d.confidence === "HIGH" ? "ok" : d.confidence === "NONE" ? "warn" : "flag"} /></div>
          </div>
          <div className="tile"><div className="k">Blockchain</div><div className="v">{d.blockchain || "—"}</div></div>
          <div className="tile"><div className="k">Rows</div><div className="v" style={{ fontSize: 16 }}>{preflight.n_rows.toLocaleString()}</div></div>
        </div>
      </div>

      <div className="section">
        <h2>Confirm schema mapping</h2>
        <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
          THEMIS's best guess at which column plays which role. Correct anything before running
          the audit — nothing is analyzed until you confirm.
        </p>
        <div className="card">
          <table>
            <thead><tr><th>Role</th><th>Column</th></tr></thead>
            <tbody>
              {ROLES.map((role) => (
                <tr key={role.key}>
                  <td>{role.label}{role.required && " *"}</td>
                  <td>
                    <select value={mapping[role.key] || ""}
                      onChange={(e) => setMapping({ ...mapping, [role.key]: e.target.value || null })}>
                      <option value="">— not present —</option>
                      {preflight.fieldnames.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section">
        <h2>Sample rows</h2>
        <div className="card" style={{ overflowX: "auto" }}>
          <table>
            <thead><tr>{preflight.fieldnames.map((f) => <th key={f}>{f}</th>)}</tr></thead>
            <tbody>
              {preflight.sample_rows.map((row, i) => (
                <tr key={i}>{preflight.fieldnames.map((f) => <td key={f}>{row[f]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section">
        <button type="button" onClick={onConfirm} disabled={busy || !mapping.address}>
          {busy ? "Running audit…" : "Confirm & run audit"}
        </button>
      </div>
    </>
  );
}
