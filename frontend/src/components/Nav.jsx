import { Link, useLocation } from "react-router-dom";
import { useAnalysis } from "../lib/AnalysisContext.jsx";

const LINKS = [
  { href: "/", label: "Start" },
  { href: "/overview", label: "Overview", needsAnalysis: true },
  { href: "/address", label: "Address Inspector", needsAnalysis: true },
  { href: "/claims", label: "Claims", needsAnalysis: true },
  { href: "/provenance", label: "Provenance Explorer", needsAnalysis: true },
  { href: "/drift", label: "Trust-Rule Sensitivity", needsAnalysis: true, paperOnly: true },
  { href: "/sources", label: "Sources" },
  { href: "/export", label: "Export", needsAnalysis: true },
];

export default function Nav() {
  const { pathname } = useLocation();
  const { analysisId, meta } = useAnalysis();

  return (
    <div className="topnav">
      <div className="shell">
        <div className="brand">
          THEMIS
          <small>Attribution Reliability Auditor</small>
        </div>
        <nav className="navlinks">
          {LINKS.map((l) => {
            const disabled = l.needsAnalysis && !analysisId;
            const hidden = l.paperOnly && meta && meta.mode !== "PAPER_REPRODUCTION";
            if (hidden) return null;
            return disabled ? (
              <span key={l.href} className="mono" style={{ fontSize: 12.5, textTransform: "uppercase",
                letterSpacing: ".04em", padding: "8px 10px", color: "var(--rule)", cursor: "not-allowed" }}
                title="Start or upload an analysis first">
                {l.label}
              </span>
            ) : (
              <Link key={l.href} to={l.href} className={pathname === l.href ? "active" : ""}>
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {meta && (
        <div className="shell" style={{ paddingBottom: 12, paddingTop: 0, display: "flex", gap: 10,
          alignItems: "baseline", fontSize: 12.5 }}>
          <span className={`badge ${meta.mode === "PAPER_REPRODUCTION" ? "flag" : "ok"}`}>
            {meta.mode === "PAPER_REPRODUCTION" ? "Paper Reproduction" : "Uploaded Dataset"}
          </span>
          <strong>{meta.dataset_name}</strong>
          <span className="muted">{meta.blockchain || "—"}</span>
          <span className="muted">{meta.n_claims.toLocaleString()} claims</span>
          <span className="muted mono">as of {meta.analysis_as_of_date}</span>
        </div>
      )}
    </div>
  );
}
