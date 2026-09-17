import { useState } from "react";
import { api } from "../lib/api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Tooltip from "../components/Tooltip.jsx";
import ReliabilityProfile from "../components/ReliabilityProfile.jsx";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [sourceId, setSourceId] = useState("uploaded_dataset");
  const [useReference, setUseReference] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.ingest({ file, sourceId, useReference });
      setResult(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
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

      <div className="section">
        <h2>Upload a dataset</h2>
        <div className="card">
          <form onSubmit={onSubmit}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <div className="k mono" style={{ fontSize: 11, marginBottom: 6, color: "var(--muted)" }}>CSV FILE</div>
                <input type="file" accept=".csv,.gz" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </div>
              <div>
                <div className="k mono" style={{ fontSize: 11, marginBottom: 6, color: "var(--muted)" }}>SOURCE ID</div>
                <input type="text" value={sourceId} onChange={(e) => setSourceId(e.target.value)} />
              </div>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13.5 }}>
                <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
                <Tooltip text="Compare against the bundled seven-dataset reference corpus for cross-source agreement, independence and provenance. Without it, only internal checks (address validation, freshness) are possible.">
                  compare against reference corpus
                </Tooltip>
              </label>
              <button type="submit" disabled={!file || busy}>{busy ? "Auditing…" : "Run pre-flight audit"}</button>
            </div>
          </form>
        </div>
      </div>

      {error && <div className="callout warn">{error}</div>}

      {result && result.stopped && (
        <div className="section">
          <h2>Dataset pre-flight</h2>
          <div className="callout warn" style={{ whiteSpace: "pre-line" }}>{result.message}</div>
          <p className="muted">
            {result.basic_quality.rows.toLocaleString()} rows, columns: {result.basic_quality.columns.join(", ")}
          </p>
        </div>
      )}

      {result && !result.stopped && <IngestReport result={result} />}
    </>
  );
}

function IngestReport({ result }) {
  const d = result.detection, v = result.validation;
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
          <div className="tile"><div className="k">Address field</div><div className="v" style={{ fontSize: 16 }}>{d.address_field || "—"}</div></div>
        </div>
      </div>

      <div className="section">
        <h2>Schema interpretation</h2>
        <table>
          <thead><tr><th>Role</th><th>Column</th></tr></thead>
          <tbody>
            {Object.entries(result.schema_mapping).map(([role, col]) => (
              <tr key={role}><td style={{ textTransform: "capitalize" }}>{role}</td><td>{col || <span className="muted">not found</span>}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section">
        <h2>Input validation</h2>
        <div className="grid cols-3">
          <MiniTile label="input rows" value={v.n_input} />
          <MiniTile label="valid claims" value={v.n_valid} />
          <MiniTile label="rejected" value={v.n_rejected} />
        </div>
        {Object.keys(v.rejected_by_reason).length > 0 && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>Rejection reason</th><th className="num">Count</th></tr></thead>
            <tbody>
              {Object.entries(v.rejected_by_reason).map(([reason, n]) => (
                <tr key={reason}><td>{reason}</td><td className="num">{n.toLocaleString()}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h2>What THEMIS could and could not check</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
          {Object.entries(result.capabilities).map(([cap, ok]) => (
            <span key={cap} className={`badge ${ok ? "ok" : "muted"}`}>{ok ? "✓" : "–"} {cap.replaceAll("_", " ")}</span>
          ))}
        </div>
        {result.limitations.map((lim, i) => <div className="callout muted" key={i}>{lim}</div>)}
      </div>

      <div className="section">
        <h2>Reliability profile</h2>
        <ReliabilityProfile profile={result.reliability_profile} />
      </div>
    </>
  );
}

function MiniTile({ label, value }) {
  return <div className="tile"><div className="k">{label}</div><div className="v">{value.toLocaleString()}</div></div>;
}
