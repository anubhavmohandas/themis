import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";

const FILES = [
  { name: "analysis_summary.json", label: "Analysis summary (JSON)", desc: "Meta, canonical result and audit trail for this analysis — the same object every page here renders." },
  { name: "normalized_claims.csv", label: "Normalized claims (CSV)", desc: "This analysis's own claims after schema mapping and normalization." },
  { name: "limitations.json", label: "Limitations (JSON)", desc: "The algorithmically-generated caveats for this analysis's result." },
];

export default function ExportPage() {
  const { analysisId, meta } = useAnalysis();

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Research / Export</div>
        <h1>Export the active analysis</h1>
        <p className="lead">Every figure on every page comes from one result object; these are the same numbers, exported.</p>
      </div>

      {!analysisId ? (
        <div className="section">
          <div className="callout muted">
            No active analysis. <Link to="/">Upload a dataset or reproduce the paper</Link> to begin.
          </div>
        </div>
      ) : (
        <>
          <div className="section">
            <span className={`badge ${meta?.mode === "PAPER_REPRODUCTION" ? "flag" : "ok"}`}>
              mode = {meta?.mode}
            </span>
          </div>
          <div className="section grid cols-3">
            {FILES.map((f) => (
              <div className="tile" key={f.name}>
                <div className="k">{f.label}</div>
                <p className="muted" style={{ fontSize: 12.5, minHeight: 54 }}>{f.desc}</p>
                <a className="btn secondary" href={api.exportUrl(analysisId, f.name)} style={{ textDecoration: "none", display: "inline-block" }}>
                  Download {f.name}
                </a>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="section">
        <div className="callout muted">
          For the CLI equivalents (including a full paper-reproduction bootstrap run), see{" "}
          <code>themis report --bootstrap --json out.json</code>,{" "}
          <code>themis drift --json out.json</code> and{" "}
          <code>themis explain &lt;address&gt; --json out.json</code>.
        </div>
      </div>
    </>
  );
}
