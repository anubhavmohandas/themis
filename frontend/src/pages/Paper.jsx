import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { useJob } from "../lib/useJob.js";
import { dateTime, fmt, humanize, pct, shortId, usd } from "../lib/format.js";
import { ErrorBox, PageHead, PaperRef, Section, Status, Tag } from "../components/ui.jsx";
import Pipeline from "../components/Pipeline.jsx";

const STATE = {
  not_run: { label: "Not run", tone: "" },
  running: { label: "Running", tone: "flag" },
  complete: { label: "Complete", tone: "ok" },
  failed: { label: "Failed", tone: "hot" },
};

export default function PaperPage() {
  const nav = useNavigate();
  const { analysisId, meta, isPaper, analyses, activate, ready } = useAnalysis();
  const full = useJob();
  const runFull = () => full.run(() => api.startPaperJob(), (j) => { if (j.status === "complete") activate(j.analysis_id, j.meta); });
  const existing = analyses.filter((a) => a.mode === "PAPER_REPRODUCTION");
  const running = full.job?.status === "running";

  return (
    <div>
      <PageHead kicker="Research artifact" title="Reproduce the paper"
        lead="Run the published method on the bundled seven-source corpus. The corpus audit runs when the reproduction is created; trust-rule sensitivity, the cluster bootstrap and anchor validation run on demand, one at a time, and each result appears here when it completes." />

      <Section title="Full reproduction">
        <div className="panel pad" style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 260, fontSize: 12.5, lineHeight: 1.6 }}>
            {isPaper
              ? <>Active reproduction <span className="mono">{shortId(analysisId)}</span>, run {dateTime(meta.created_at)}, as of {meta.analysis_as_of_date}.</>
              : <span className="mut">The active analysis is not a paper reproduction. Start one, or switch to an existing one from the workspace menu.</span>}
          </div>
          {!isPaper && existing.map((a) => (
            <button key={a.analysis_id} type="button" className="btn secondary" onClick={() => activate(a.analysis_id, a)}>Use {shortId(a.analysis_id)}</button>
          ))}
          <button type="button" className="btn" disabled={running} onClick={runFull}>{running ? "Running…" : isPaper ? "Re-run full reproduction" : "Run full reproduction"}</button>
        </div>
        {full.error && <ErrorBox title="Could not start">{full.error}</ErrorBox>}
        {full.job && <div style={{ marginTop: 12 }}><Pipeline job={full.job} title="Reproduction pipeline" /></div>}
        {full.job?.status === "failed" && <div style={{ marginTop: 12 }}><ErrorBox title="Reproduction failed">{full.job.error}</ErrorBox></div>}
      </Section>

      {ready && isPaper && <Tasks analysisId={analysisId} onOverview={() => nav("/overview")} />}
    </div>
  );
}

function Tasks({ analysisId, onOverview }) {
  const [tasks, setTasks] = useState(null);
  const [payload, setPayload] = useState({});
  const [busy, setBusy] = useState({});
  const [errors, setErrors] = useState({});
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(() => api.tasks(analysisId)
    .then((t) => { setTasks(t.tasks); setPayload(t); setLoadError(null); })
    .catch((e) => setLoadError(e.message)), [analysisId]);
  useEffect(() => { setTasks(null); load(); }, [load]);

  // if the server says something is running (e.g. after a page reload), keep polling
  const serverRunning = tasks && Object.values(tasks).some((t) => t.state === "running");
  useEffect(() => {
    if (!serverRunning) return undefined;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [serverRunning, load]);

  const run = async (task) => {
    setBusy((b) => ({ ...b, [task]: true }));
    setErrors((e) => ({ ...e, [task]: null }));
    try {
      const t = await api.runTask(analysisId, task);
      setTasks(t.tasks); setPayload(t);
    } catch (e) {
      setErrors((x) => ({ ...x, [task]: e.message }));
      load();
    } finally {
      setBusy((b) => ({ ...b, [task]: false }));
    }
  };

  if (loadError) return <ErrorBox title="Could not load reproduction tasks">{loadError}</ErrorBox>;
  if (!tasks) return <div className="loading">Loading tasks…</div>;

  const ROWS = [
    { id: "audit", title: "Corpus audit", desc: "Agreement outcomes, provenance independence, chance-corrected agreement and currency. Runs when the reproduction is created.", sec: "5.1" },
    { id: "drift", title: "Trust-rule sensitivity", desc: "The same ransomware-revenue arithmetic under four trust rules, with coverage alongside each figure.", sec: "5.3" },
    { id: "bootstrap", title: "Cluster bootstrap", desc: "Confidence intervals that resample provenance roots, not rows. Lower-bound clustering only.", sec: "5.4" },
    { id: "anchors", title: "Anchor validation", desc: "Per-source agreement with an open anchor set, reported only where enough independent roots exist to estimate it.", sec: "5.4" },
  ];

  return (
    <Section title="Reproductions" meta="one run at a time">
      <div className="panel">
        <div className="rowlist">
          {ROWS.map((r) => {
            const server = tasks[r.id]?.state || "not_run";
            const state = busy[r.id] ? "running" : server;
            const st = STATE[state] || STATE.not_run;
            const err = errors[r.id] || tasks[r.id]?.error;
            return (
              <div key={r.id}>
                <div>
                  <div className="rl-title">{r.title} <Tag tone={st.tone}>{st.label}</Tag> <PaperRef sec={r.sec} /></div>
                  <div className="rl-desc">{r.desc}</div>
                  {err && state === "failed" && <div className="hot" style={{ fontSize: 12, marginTop: 5 }}>{err}</div>}
                </div>
                <div style={{ flex: "none" }}>
                  {r.id === "audit"
                    ? <button type="button" className="btn small secondary" onClick={onOverview}>View overview</button>
                    : r.id === "drift" && state === "complete"
                      ? <Link className="btn small secondary" to="/trust">View</Link>
                      : <button type="button" className="btn small" disabled={state === "running"} onClick={() => run(r.id)}>
                        {state === "running" ? "Running…" : state === "complete" ? "Re-run" : state === "failed" ? "Retry" : "Run"}</button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {payload.drift && tasks.drift?.state === "complete" && <DriftResult d={payload.drift} />}
      {payload.uncertainty && <BootstrapResult u={payload.uncertainty} />}
      {payload.anchor_validation && <AnchorResult a={payload.anchor_validation} />}
    </Section>
  );
}

// --------------------------------------------------------------- results
function DriftResult({ d }) {
  return (
    <div style={{ marginTop: 22 }}>
      <div className="form-label">Trust-rule sensitivity · result</div>
      <div className="tablewrap"><table>
        <thead><tr><th>Condition</th><th className="num">Addresses</th><th className="num">Revenue</th><th className="num">vs. baseline B</th><th className="num">Coverage</th></tr></thead>
        <tbody>{Object.entries(d.conditions).map(([k, c]) => (
          <tr key={k}><td><span className="mono" style={{ fontWeight: 600 }}>{k}</span> · {c.label}</td><td className="num">{fmt(c.addresses)}</td>
            <td className="num">{usd(c.usd)}</td><td className="num">{c.ratio_vs_B.toFixed(2)}×</td><td className="num">{pct(c.coverage_vs_B, 1)}</td></tr>))}</tbody>
      </table>
        <div className="tablefoot">Spread B / D {d.spread_B_over_D.toFixed(1)}×, A / D {d.spread_A_over_D.toFixed(1)}×. <Link to="/trust">Open Trust Analysis →</Link></div></div>
    </div>
  );
}

function BootstrapResult({ u }) {
  return (
    <div style={{ marginTop: 22 }}>
      <div className="form-label">Cluster bootstrap · result</div>
      <div className="tablewrap"><table>
        <thead><tr><th>Rate (among multi-dataset addresses)</th><th className="num">Point estimate</th><th className="num">{pct(u.confidence_level, 0)} interval</th></tr></thead>
        <tbody>{Object.entries(u.stats).map(([k, s]) => (
          <tr key={k}><td>{humanize(k)}</td><td className="num">{pct(s.point)}</td><td className="num">[{pct(s.ci_low)}, {pct(s.ci_high)}]</td></tr>))}</tbody>
      </table>
        <div className="tablefoot">
          {fmt(u.n_clusters)} root clusters resampled, {fmt(u.n_boot)} draws, seed {u.seed}, {u.upper_bound ? "upper" : "lower"}-bound clustering. {u.note}
          {" "}The intervals are wide because there are few independent roots: read them as a limit on what this corpus can support, not as error bars.
        </div></div>
    </div>
  );
}

function AnchorResult({ a }) {
  return (
    <div style={{ marginTop: 22 }}>
      <div className="form-label">Anchor validation · result</div>
      <div className="metrics c3" style={{ marginBottom: 12 }}>
        <div className="metric"><div className="m-label">Usable anchors</div><div className="m-val">{fmt(a.usable_anchors)}</div><div className="m-sub">of {fmt(a.anchors_total)} anchors · coverage {pct(a.coverage)}</div></div>
        <div className="metric"><div className="m-label">Self-root claims excluded</div><div className="m-val">{fmt(a.excluded_self_root_claims)}</div><div className="m-sub">a source cannot validate itself</div></div>
        <div className="metric"><div className="m-label">Estimable overall</div><div className="m-val text">{a.estimable ? "Yes" : "No"}</div><div className="m-sub">needs ≥{a.min_independent_roots} independent roots per source</div></div>
      </div>
      <div className="tablewrap"><table>
        <thead><tr><th>Source</th><th className="num">Anchors (n)</th><th className="num">Agreement</th><th className="num">Independent roots</th><th>Interval / reason</th></tr></thead>
        <tbody>{Object.entries(a.per_source).map(([s, v]) => (
          <tr key={s}><td className="mono">{s}</td><td className="num">{fmt(v.n)}</td><td className="num">{pct(v.anchor_agreement)}</td><td className="num">{fmt(v.independent_roots)}</td>
            <td className="small">{v.estimable ? <>{pct(v.ci_low)}–{pct(v.ci_high)} (root-cluster bootstrap)</> : <Status tone="flag">not estimable: {v.not_estimable_reason}</Status>}
              {" "}<span className="fnt">Wilson {pct(v.wilson_low)}–{pct(v.wilson_high)}</span></td></tr>))}</tbody>
      </table></div>
      <details className="more"><summary>Limitations of this anchor set</summary><div className="txt">{a.limitations}</div></details>
    </div>
  );
}
