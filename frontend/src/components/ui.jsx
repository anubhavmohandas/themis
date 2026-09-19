import { Link, useNavigate } from "react-router-dom";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { PAPER_SECTIONS } from "../lib/vocab.js";

// --------------------------------------------------------------------- headings
export function PageHead({ kicker, title, lead, mono, children }) {
  return (
    <header className="pagehead">
      {kicker && <div className="kicker">{kicker}</div>}
      {mono ? <div className="head-row"><h1 className="mono">{title}</h1>{children}</div> : <h1>{title}</h1>}
      {lead && <p className="lead">{lead}</p>}
    </header>
  );
}

// Paper section badge: paper-reproduction mode only; hover/focus shows the
// section title. Never carries a number.
export function PaperRef({ sec }) {
  const { isPaper } = useAnalysis();
  if (!isPaper || !PAPER_SECTIONS[sec]) return null;
  return (
    <button type="button" className="paper-ref" aria-label={`Paper section ${sec}: ${PAPER_SECTIONS[sec]}`}>
      §{sec}
      <span className="pop" role="tooltip">Paper: Section {sec} — {PAPER_SECTIONS[sec]}</span>
    </button>
  );
}

export function Section({ title, sec, meta, note, children, id }) {
  return (
    <section className="section" id={id}>
      <div className="section-head">
        <h2>{title}</h2>
        {(meta || sec) && <span className="section-meta">{meta}{sec && <PaperRef sec={sec} />}</span>}
      </div>
      {note && <p className="section-note">{note}</p>}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------- metrics
// items: {label, value, sub, to, tone, top, text}. Clickable when `to` is set.
export function MetricStrip({ items, cols }) {
  const n = cols || items.length;
  return (
    <div className={`metrics${n === 3 ? " c3" : ""}`}>
      {items.map((m) => {
        const inner = (
          <>
            <div className="m-label">{m.label}</div>
            <div className={`m-val${m.text ? " text" : ""} ${m.tone || ""}`}>{m.value}</div>
            {m.sub && <div className="m-sub">{m.sub}</div>}
          </>
        );
        const cls = `metric${m.top ? " topline" : ""}${m.top === "hot" ? " hot" : ""}`;
        return m.to
          ? <Link key={m.label} to={m.to} className={cls} title={m.hint}>{inner}</Link>
          : <div key={m.label} className={cls}>{inner}</div>;
      })}
    </div>
  );
}

// ------------------------------------------------------------------- bar rows
// rows: {label, share (0..1), fill, hatch, pct, n, to, labelMono}
// Every row shows a percentage AND its count; `den` on the caller supplies the
// denominator text so no percentage stands alone.
export function BarRows({ rows, cols = "190px 1fr 74px 96px" }) {
  const nav = useNavigate();
  return (
    <div className="barrows" style={{ gridTemplateColumns: cols }}>
      {rows.map((r) => (
        <div key={r.key || r.label} className={`barrow${r.to ? " link" : ""}`}
          onClick={r.to ? () => nav(r.to) : undefined} title={r.title}>
          <span className="bar-label" style={{ color: r.labelColor, fontFamily: r.labelMono ? "var(--mn)" : undefined }}>
            {r.to ? <Link to={r.to} onClick={(e) => e.stopPropagation()} style={{ color: "inherit" }}>{r.label}</Link> : r.label}
          </span>
          <div className="bar-track">
            <i className={r.hatch ? "hatch" : ""} style={{ width: `${Math.max(0, Math.min(1, r.share || 0)) * 100}%`, background: r.hatch ? undefined : r.fill }} />
          </div>
          <span className="bar-pct">{r.pct}</span>
          <span className="bar-n">{r.n}</span>
        </div>
      ))}
    </div>
  );
}

export const Legend = ({ items }) => (
  <div className="legend">
    {items.map((i) => (
      <span key={i.label}>
        <span className={`sw${i.hatch ? " hatch" : ""}`} style={{ background: i.hatch ? undefined : i.fill }} />{i.label}
      </span>
    ))}
  </div>
);

// ------------------------------------------------------------------ status text
// Status is always a word, never colour alone.
export const Status = ({ tone = "mut", children }) => <span className={`st ${tone}`}>{children}</span>;
export const Tag = ({ tone, children, title }) => <span className={`tag ${tone || ""}`} title={title}>{children}</span>;

// ----------------------------------------------------------------------- states
export function Loading({ children = "Loading…" }) { return <div className="loading">{children}</div>; }

export function ErrorBox({ title = "Request failed", children }) {
  return (
    <div className="errbox" role="alert">
      <div className="eb-head">{title}</div>
      <div className="eb-body">{children}</div>
    </div>
  );
}

export function Empty({ eyebrow = "No active analysis", children, action }) {
  return (
    <div className="empty">
      <div className="eyebrow">{eyebrow}</div>
      <p>{children}</p>
      {action}
    </div>
  );
}

// Every analysis page starts here: no analysis / loading / error / stopped, else children.
export function Gate({ children, needSummary = true }) {
  const { analysisId, ready, summary, summaryError, stopped } = useAnalysis();
  if (!ready) return <Loading />;
  if (!analysisId) {
    return (
      <Empty action={<Link className="btn" to="/">New analysis</Link>}>
        Upload a dataset or reproduce the paper to begin. Every figure in THEMIS belongs to one analysis.
      </Empty>
    );
  }
  if (summaryError) return <ErrorBox title="Could not load this analysis">{summaryError}{"\n"}It may have been cleared when the server restarted. Start a new analysis from the workspace menu.</ErrorBox>;
  if (needSummary && !summary) return <Loading>Loading analysis…</Loading>;
  if (needSummary && stopped) {
    return (
      <Empty eyebrow="Analysis stopped at pre-flight" action={<Link className="btn" to="/">New analysis</Link>}>
        This dataset did not pass pre-flight, so no audit was produced for it.
      </Empty>
    );
  }
  return children;
}

// ---------------------------------------------------------------------- drawer
export function Drawer({ title, onClose, children, foot }) {
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={title}>
        <div className="drawer-head">
          <span className="eyebrow">{title}</span>
          <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="drawer-body">{children}</div>
        {foot && <div className="drawer-foot">{foot}</div>}
      </aside>
    </>
  );
}

// ----------------------------------------------------------------------- forms
export function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className={`field${value ? " active" : ""}`}>
      {label}:
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

export function SearchBox({ value, onChange, placeholder, onSubmit }) {
  return (
    <form className="field grow" onSubmit={(e) => { e.preventDefault(); onSubmit?.(); }}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <circle cx="5" cy="5" r="3.7" stroke="currentColor" /><path d="M7.8 7.8 11 11" stroke="currentColor" />
      </svg>
      <input type="text" value={value} placeholder={placeholder} spellCheck={false}
        onChange={(e) => onChange(e.target.value)} aria-label={placeholder} />
    </form>
  );
}

export function Pager({ offset, limit, total, onChange }) {
  return (
    <div className="pager">
      <button type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <button type="button" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

export function RadioRow({ name, value, onChange, options, counts }) {
  return (
    <div className="radiorow" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <label key={o.key} className={value === o.key ? "on" : ""}>
          <input type="radio" name={name} checked={value === o.key} onChange={() => onChange(o.key)} />
          {o.label}
          {counts && counts[o.key] !== undefined && <span className="cnt">{counts[o.key].toLocaleString("en-US")}</span>}
        </label>
      ))}
    </div>
  );
}

export function Warn() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true">
      <path d="M6.5 1.2 12.3 11.5H.7z" fill="none" stroke="currentColor" strokeWidth="1" />
      <rect x="6" y="4.8" width="1" height="3.4" fill="currentColor" /><rect x="6" y="9" width="1" height="1" fill="currentColor" />
    </svg>
  );
}

// Callout listing evidential limitations - text comes from the backend.
export function Limitations({ items, title = "Evidential limitations" }) {
  if (!items?.length) return null;
  return (
    <div className="callout">
      <div className="co-head"><Warn /><span>{title}</span></div>
      <ul>{items.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </div>
  );
}

export const Mono = ({ children }) => <span className="mono">{children}</span>;
