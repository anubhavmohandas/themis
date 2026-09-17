import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import StatusBadge from "../components/StatusBadge.jsx";

export default function SourcesPage() {
  const { data, error, loading } = useApiData(() => api.sources(), []);
  if (loading) return <p className="muted">Loading source registry…</p>;
  if (error) return <div className="callout warn">{error}</div>;
  if (!data) return null;

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Source Registry</div>
        <h1>Every bundled dataset's declared provenance rule</h1>
        <p className="lead">Read straight from config/sources/ — adding a source is a config change, never an edit to the analysis engine.</p>
      </div>

      <div className="section">
        {Object.entries(data).sort().map(([sid, cfg]) => (
          <div className="card" key={sid} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <div>
                <span className="mono" style={{ fontWeight: 600 }}>{sid}</span>
                <span className="muted" style={{ marginLeft: 8 }}>{cfg.display_name}</span>
              </div>
              <StatusBadge label={(cfg.provenance || {}).mode || "no rule — UNKNOWN"}
                kind={cfg.provenance ? "ok" : "warn"} />
            </div>
            <table>
              <tbody>
                <tr><td style={{ border: "none", color: "var(--muted)", width: 140 }}>chain</td><td style={{ border: "none" }}>{cfg.chain}</td></tr>
                <tr><td style={{ border: "none", color: "var(--muted)" }}>citation</td><td style={{ border: "none" }}>{cfg.citation || "—"}</td></tr>
                <tr><td style={{ border: "none", color: "var(--muted)" }}>confidence semantics</td><td style={{ border: "none" }}>{cfg.confidence_semantics || "—"}</td></tr>
                {cfg.known_dependencies?.length > 0 && (
                  <tr><td style={{ border: "none", color: "var(--muted)" }}>known dependencies</td><td style={{ border: "none" }}>{cfg.known_dependencies.join(", ")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </>
  );
}
