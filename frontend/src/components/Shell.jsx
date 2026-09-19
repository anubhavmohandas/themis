import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { dateTime, fmt, shortId } from "../lib/format.js";

const GROUPS = [
  { title: "Analysis", needsAnalysis: true, items: [
    ["/overview", "Overview"], ["/claims", "Claims"], ["/address", "Address Inspector"],
    ["/provenance", "Provenance"], ["/conflicts", "Conflicts"], ["/trust", "Trust Analysis"], ["/export", "Exports"],
  ] },
  { title: "Research", items: [
    ["/paper", "Reproduce Paper"], ["/methodology", "Methodology"], ["/sources", "Sources"],
  ] },
  { title: "Workspace", items: [["/", "New Analysis"], ["/analyses", "Recent Analyses"]] },
];

export const PAGE_TITLES = {
  "/": "New Analysis", "/overview": "Overview", "/claims": "Claims", "/address": "Address Inspector",
  "/provenance": "Provenance", "/conflicts": "Conflicts", "/trust": "Trust Analysis", "/export": "Exports",
  "/paper": "Reproduce Paper", "/methodology": "Methodology", "/sources": "Sources", "/analyses": "Recent Analyses",
};

function modeLabel(mode) { return mode === "PAPER_REPRODUCTION" ? "Paper reproduction" : "Uploaded dataset"; }

function ActiveAnalysis() {
  const { analysisId, meta, summary, summaryError, stopped, chain, nClaims, nAddresses, analyses, activate, isPaper } = useAnalysis();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const nav = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const pick = (a) => { setOpen(false); activate(a.analysis_id, a); nav("/overview"); };

  return (
    <div className="active-analysis" ref={ref}>
      <div className="eyebrow">
        Active analysis
        <button type="button" className="aa-switch" onClick={() => setOpen((o) => !o)} aria-expanded={open}>Switch</button>
      </div>
      {meta ? (
        <div role="button" tabIndex={0} style={{ cursor: "pointer" }} onClick={() => setOpen((o) => !o)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((o) => !o); } }}>
          <div className="aa-mode"><span className="dot" />{modeLabel(meta.mode)}</div>
          <div className="aa-name">{meta.dataset_name}</div>
          <div className="aa-facts">
            <span>chain</span><b>{chain || "—"}</b>
            <span>claims</span><b>{summary ? fmt(nClaims) : "…"}</b>
            <span>{isPaper ? "addrs" : "targets"}</span><b>{summary ? fmt(nAddresses) : "…"}</b>
          </div>
          <div className="aa-status" style={{ color: summaryError || stopped ? "var(--ac)" : summary ? "var(--tl)" : "var(--mut)" }}>
            <span className="dot" />
            {summaryError ? "Unavailable" : stopped ? "Stopped at pre-flight" : summary ? "Analysis complete" : "Loading…"}
          </div>
          <div className="aa-facts" style={{ marginTop: 4 }}><span>run</span><b>{dateTime(meta.created_at)}</b></div>
        </div>
      ) : (
        <div style={{ marginTop: 9 }}>
          <div className="aa-name" style={{ color: "var(--mut)" }}>None. Start a new analysis or reproduce the paper.</div>
        </div>
      )}
      {open && (
        <div className="switcher" role="listbox" aria-label="Recent analyses">
          {analyses.length === 0 && <div className="sw-sub" style={{ padding: "10px 12px" }}>No analyses in this session.</div>}
          {analyses.map((a) => (
            <button key={a.analysis_id} type="button" role="option" aria-selected={a.analysis_id === analysisId}
              className={a.analysis_id === analysisId ? "cur" : ""} onClick={() => pick(a)}>
              <div className="sw-name">{a.dataset_name}</div>
              <div className="sw-sub">{modeLabel(a.mode)} · {shortId(a.analysis_id)} · {fmt(a.n_claims)} claims</div>
            </button>
          ))}
          <button type="button" onClick={() => { setOpen(false); nav("/"); }}><div className="sw-name">+ New analysis</div></button>
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const { analysisId } = useAnalysis();
  const [version, setVersion] = useState(null);
  useEffect(() => { api.health().then((h) => setVersion(h.version)).catch(() => setVersion(null)); }, []);
  return (
    <nav className="sidebar" aria-label="THEMIS">
      <div className="brand">
        <div className="brand-row"><Link to="/" className="brand-name">THEMIS</Link></div>
        <div className="brand-rule" />
        <div className="eyebrow">Attribution reliability<br />auditor</div>
      </div>
      <ActiveAnalysis />
      <div className="nav">
        {GROUPS.map((g) => (
          <div key={g.title} style={{ display: "contents" }}>
            <div className="nav-group">{g.title}</div>
            {g.items.map(([to, label]) => (g.needsAnalysis && !analysisId
              ? <span key={to} className="nav-item disabled" aria-disabled="true" title="Start or select an analysis first">{label}</span>
              : <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>{label}</NavLink>))}
          </div>
        ))}
      </div>
      <div className="side-foot">{version ? `engine v${version}` : "engine offline"}<br />evidence, not verdicts</div>
    </nav>
  );
}

export function Topbar() {
  const { pathname } = useLocation();
  const { analysisId, meta, theme, toggleTheme } = useAnalysis();
  return (
    <header className="topbar">
      <div className="tb-title">
        <strong>{PAGE_TITLES[pathname] || "THEMIS"}</strong>
        {meta && <span className="tb-crumb">{meta.dataset_name}</span>}
      </div>
      <div className="tb-right">
        {meta && <span className="tb-meta">as of {meta.analysis_as_of_date || "—"} · analysis {shortId(analysisId)}</span>}
        <button type="button" className="chip-btn" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        {analysisId && <Link to="/export" className="chip-btn plain">Export</Link>}
      </div>
    </header>
  );
}
