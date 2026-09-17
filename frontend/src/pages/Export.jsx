import { api } from "../lib/api.js";

const FILES = [
  { name: "report.json", label: "Canonical report (JSON)", desc: "Dataset summary, agreement, independence, kappa, freshness, reliability profile and audit trail — the same object every page here renders." },
  { name: "sources.csv", label: "Source registry (CSV)", desc: "Every bundled dataset's id, chain, provenance mode and citation." },
  { name: "agreement.csv", label: "Agreement outcomes (CSV)", desc: "Exact / hierarchical refinement / entity-type conflict / licit-illicit conflict / incomparable, with counts and shares." },
];

export default function ExportPage() {
  return (
    <>
      <div className="pageintro">
        <div className="kicker">Research / Export</div>
        <h1>Export the canonical result</h1>
        <p className="lead">Every figure on every page comes from one result object; these are the same numbers, exported.</p>
      </div>

      <div className="section grid cols-3">
        {FILES.map((f) => (
          <div className="tile" key={f.name}>
            <div className="k">{f.label}</div>
            <p className="muted" style={{ fontSize: 12.5, minHeight: 54 }}>{f.desc}</p>
            <a className="btn secondary" href={api.exportUrl(f.name)} style={{ textDecoration: "none", display: "inline-block" }}>
              Download {f.name}
            </a>
          </div>
        ))}
      </div>

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
