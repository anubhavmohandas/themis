import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useJob } from "../lib/useJob.js";
import { fmt, humanize, pct } from "../lib/format.js";
import { ErrorBox, Section, Tag } from "../components/ui.jsx";
import Pipeline from "../components/Pipeline.jsx";

// Everything on this page is rendered from the backend: the paper's declared
// values (paper/paper_claims.yml), what THEMIS generated, each claim's status,
// its evidence and its section. Nothing below types a paper value, and no PASS
// is ever derived here - a status is whatever the verifier returned.

const TONE = { PASS: "ok", FAIL: "hot", NOT_REPRODUCED: "flag", BLOCKED: "flag", NOT_RUN: "", NOT_MACHINE_CHECKABLE: "", INFORMATIONAL: "" };
const WORD = { NOT_REPRODUCED: "not reproduced", NOT_RUN: "not run", NOT_MACHINE_CHECKABLE: "not machine-checkable", INFORMATIONAL: "informational" };
const CLASS_WORD = { HEADLINE_STABLE: "headline", SUPPORTING_STABLE: "supporting", DIAGNOSTIC: "diagnostic · taxonomy-sensitive", SENSITIVITY: "sensitivity", LIMITATION: "limitation" };
const GROUP_LABEL = { RQ1: "RQ1", RQ2: "RQ2", RQ3: "RQ3", table1: "Table 1", figure1: "Figure 1", table2: "Table 2", figure2: "Figure 2" };

const StatusTag = ({ s }) => <Tag tone={TONE[s]}>{WORD[s] || s}</Tag>;
const Sec = ({ s }) => (s ? <span className="paper-ref" style={{ position: "static" }}>§{s}</span> : null);

// render a value the way the paper states it, from the rule the backend attached to the claim
function show(v, c, declared = false) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v !== "number") return String(v);
  if (c.comparison === "rounded_percent" && c.decimals !== undefined && c.decimals !== null) return pct(v, c.decimals);
  if ((c.comparison === "rounded_decimal" || c.comparison === "approximate_text") && c.decimals !== undefined && c.decimals !== null)
    return (v * (declared ? 1 : (c.scale ?? 1))).toFixed(c.decimals);
  return Number.isInteger(v) ? fmt(v) : v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export default function PaperProof() {
  const [status, setStatus] = useState(null);
  const [claims, setClaims] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(null);          // {claim?, exp}
  const [filter, setFilter] = useState("HEADLINE_STABLE");
  const job = useJob();

  const load = useCallback(() => Promise.all([api.paperStatus(), api.paperClaims()])
    .then(([s, c]) => { setStatus(s); setClaims(c); setErr(null); })
    .catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = () => job.run(() => api.startPaperReproduction(), () => load());
  const running = job.job?.status === "running";

  if (err) return <ErrorBox title="Could not load the paper reproduction status">{err}</ErrorBox>;
  if (!status || !claims) return <div className="loading">Loading…</div>;

  const { corpus, latest_run: run_, paper } = status;
  const rows = claims.claims.filter((c) => filter === "all" || c.class === filter);

  return (
    <div>
      <Section title="Paper reproduction" meta="executable manuscript"
        note="Reproduction means recomputing the paper's empirical measurements from declared inputs and comparing them with what the manuscript states. It does not establish that any attribution label is true.">
        <div className="panel pad">
          <div className="kv"><span>Paper</span><span>{paper?.title} <span className="fnt">({paper?.file}, {paper?.version})</span></span></div>
          <div className="kv"><span>Software</span><span>THEMIS {status.software_version}</span></div>
          <div className="kv"><span>Corpus</span><span>{corpus.available
            ? <>{corpus.scope === "FULL_CORPUS" ? "Full seven-source corpus" : "Bundled reference sample of the seven-source corpus"} · {fmt(corpus.n_claims_loaded)} claims loaded · analysis date {corpus.analysis_as_of_date}</>
            : "Not available"}</span></div>
          {corpus.note && <div className="kv"><span>Sample</span><span style={{ fontFamily: "inherit" }}>{corpus.note}</span></div>}
        </div>
      </Section>

      {!corpus.available && <DataRequired corpus={corpus} />}

      <Section title="Three things that are never blurred">
        <div className="metrics c3">
          {status.modes.map((m) => (
            <div key={m.id} className="metric"><div className="m-label">{m.label}</div><div className="m-sub" style={{ marginTop: 6 }}>{m.text}</div></div>))}
        </div>
      </Section>

      <Section title="Run">
        <div className="panel pad" style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 260, fontSize: 12.5, lineHeight: 1.6 }}>
            Runs every experiment in order, writes a self-contained result directory, and compares it with the manuscript.
            {run_ && <> Last run <span className="mono">{run_.run_id}</span>.</>}
          </div>
          <button type="button" className="btn" disabled={running || !corpus.available} onClick={run}>{running ? "Running…" : "Run full reproduction"}</button>
        </div>
        {job.error && <div style={{ marginTop: 12 }}><ErrorBox title="Could not start">{job.error}</ErrorBox></div>}
        {job.job && <div style={{ marginTop: 12 }}><Pipeline job={job.job} title="Reproduction pipeline" /></div>}
        {job.job?.status === "failed" && <div style={{ marginTop: 12 }}><ErrorBox title="Reproduction failed">{job.job.error}</ErrorBox></div>}
      </Section>

      {run_ && <Verdict run={run_} />}

      <Section title="Individual experiments" meta="select one to see how it was derived">
        <div className="panel"><div className="rowlist">
          {status.experiments.map((e) => (
            <div key={e.id}>
              <div><div className="rl-title">{e.title} <StatusTag s={e.status} /> <Sec s={e.section} /></div></div>
              <button type="button" className="btn small secondary" onClick={() => setSel({ exp: e.id })}>Evidence</button>
            </div>))}
        </div></div>
      </Section>

      <Section title="Paper claim matrix" meta={claims.run_id ? `run ${claims.run_id}` : "no run yet - paper values only"}>
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
          {["HEADLINE_STABLE", "SUPPORTING_STABLE", "DIAGNOSTIC", "LIMITATION", "all"].map((k) => (
            <button key={k} type="button" className={`btn small${filter === k ? "" : " secondary"}`} onClick={() => setFilter(k)}>{k === "all" ? "all" : CLASS_WORD[k]}</button>))}
        </div>
        <div className="tablewrap"><table>
          <thead><tr><th>Paper claim</th><th>§</th><th className="num">Paper</th><th className="num">THEMIS</th><th>Basis</th><th>Status</th></tr></thead>
          <tbody>{rows.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => setSel({ claim: c, exp: c.experiment })}
              style={sel?.claim?.id === c.id ? { background: "var(--sfa)" } : undefined}>
              <td>{c.text}<div className="fnt small">{CLASS_WORD[c.class]}</div></td>
              <td><Sec s={c.section} /></td>
              <td className="num">{show(c.paper_value, c, true)}</td>
              <td className="num">{show(c.generated_value, c)}</td>
              <td className="small">{c.basis ? humanize(c.basis).toLowerCase() : ""}</td>
              <td><StatusTag s={c.status} />{c.delta ? <div className="fnt small">Δ {c.delta}</div> : null}</td>
            </tr>))}</tbody>
        </table>
          <div className="tablefoot">{rows.length} of {claims.claims.length} claims. A status is what the verifier returned: PASS needs a live computation equal to the manuscript's declared value; a frozen or sampled figure is shown as not reproduced.</div></div>
      </Section>

      {sel && <Evidence sel={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

function DataRequired({ corpus }) {
  const req = corpus.required;
  return (
    <Section title="Paper reproduction data required">
      <div className="callout hot"><div className="co-head">Reproduction status · blocked — input corpus not available</div>
        <div className="co-body">
          <p style={{ marginTop: 0 }}>The research package does not redistribute the third-party-derived observation table, and none was found. Nothing here is a PASS.</p>
          <p className="fnt">{corpus.message}</p>
          <div className="form-label">Sources to fetch</div>
          <ul>{req.sources.map((s) => <li key={s.id}><b>{s.name}</b> — {s.citation}. <span className="fnt">Licence: {s.license}</span></li>)}</ul>
          <div className="form-label">Build</div>
          <p className="mono">{req.build_command}</p>
          <p>Also supply: {req.also_needed.join("; ")}. {req.data_dir}. See {req.docs.join(", ")}.</p>
        </div></div>
    </Section>
  );
}

function Verdict({ run }) {
  const heads = run.counts.HEADLINE_STABLE || {};
  return (
    <Section title="Verification result" meta={<>paper ↔ THEMIS</>}>
      <div className={`callout${run.status === "FAIL" ? " hot" : ""}`}>
        <div className="co-head">Paper ↔ THEMIS: {run.status}</div>
        <div className="co-body">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            {Object.entries(run.groups || {}).map(([k, s]) => <span key={k}>{GROUP_LABEL[k] || k} <StatusTag s={s} /></span>)}
          </div>
          Headline claims: {fmt(heads.PASS || 0)} pass · {fmt(heads.FAIL || 0)} fail · {fmt(heads.NOT_REPRODUCED || 0)} not reproduced.
          {run.failing.length > 0 && <> Failing: <span className="mono">{run.failing.join(", ")}</span>.</>}
          {run.status === "BLOCKED" && <> No mismatch was found, but required corpus-wide input was unavailable, so this is not a PASS.</>}
          <div className="fnt small" style={{ marginTop: 8 }}>Manuscript PDF check: {run.pdf.status}{run.pdf.reason ? ` (${run.pdf.reason})` : run.pdf.n_checked ? ` — ${run.pdf.n_checked} printed values located` : ""}</div>
          {run.warnings.map((w) => <div key={w} className="fnt small">{w}</div>)}
        </div>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------- evidence panel
function Evidence({ sel, onClose }) {
  const [exp, setExp] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { setExp(null); setErr(null); api.paperExperiment(sel.exp).then(setExp).catch((e) => setErr(e.message)); }, [sel.exp]);
  const c = sel.claim;
  return (
    <Section title={exp ? `Evidence · ${exp.title}` : "Evidence"} meta={<button type="button" className="btn small secondary" onClick={onClose}>Close</button>}>
      {err && <ErrorBox title="Could not load the experiment">{err}</ErrorBox>}
      {!exp && !err && <div className="loading">Loading…</div>}
      {exp && (
        <div className="panel pad">
          {c && <>
            <div className="kv"><span>Claim</span><span style={{ fontFamily: "inherit" }}>{c.text}</span></div>
            <div className="kv"><span>Paper / THEMIS</span><span>{show(c.paper_value, c, true)} / {show(c.generated_value, c)} <StatusTag s={c.status} /></span></div>
            <div className="kv"><span>Rule</span><span>{c.comparison || "—"} · metric {c.metric}</span></div>
            {c.detail && <div className="kv"><span>Detail</span><span style={{ fontFamily: "inherit" }}>{c.detail}</span></div>}
          </>}
          <div className="kv"><span>Experiment</span><span style={{ fontFamily: "inherit" }}>{exp.title} <StatusTag s={exp.status} /> <Sec s={exp.section} /></span></div>
          <div className="kv"><span>Analysis function</span><span>{exp.function}{exp.function_location?.file ? ` — ${exp.function_location.file}${exp.function_location.line ? `:${exp.function_location.line}` : ""}` : ""}</span></div>
          <div className="kv"><span>Artifacts</span><span>{exp.artifact_names.map((n) => <span key={n}><a href={api.paperArtifactUrl(exp.id, n)}>{n}</a>{" "}</span>)}</span></div>
          <div style={{ marginTop: 14 }}><Detail exp={exp} /></div>
          {exp.claims.length > 1 && <details className="more" style={{ marginTop: 12 }}><summary>All {exp.claims.length} claims this experiment supports</summary>
            <div className="tablewrap"><table><tbody>{exp.claims.map((x) => (
              <tr key={x.id}><td>{x.text}</td><td className="num">{show(x.paper_value, x, true)}</td><td className="num">{show(x.generated_value, x)}</td><td><StatusTag s={x.status} /></td></tr>))}</tbody></table></div></details>}
        </div>)}
    </Section>
  );
}

function Detail({ exp }) {
  const a = exp.artifacts || {};
  const rod = a["fig1a_data.json"];
  const mon = a["fig1b_data.json"];
  const t2 = a["table2.json"];
  const d = a["condition_d_trace.json"];
  if (rod) return <RodwaldTable rows={rod} />;
  if (mon) return <Simple head={["Source", "Addresses", "Share of seed"]} rows={mon.map((r) => [r.source, fmt(r.addresses), pct(r.share)])}
    foot={`${fmt(mon[0]?.seed_addresses)} seed addresses (provenance root ${mon[0]?.root}). Recurrence of one provenance root in datasets that could otherwise be read as independent.`} />;
  if (t2) return <Simple head={["Condition", "Observations", "Addresses", "Revenue (USD)", "vs B", "Coverage"]}
    rows={t2.rows.map((r) => [`${r.condition} · ${r.label}`, fmt(r.observations), fmt(r.addresses), fmt(r.revenue_usd), `${r.ratio_vs_B.toFixed(2)}×`, pct(r.coverage_vs_B, 1)])} foot={t2.note} />;
  if (d) return <TraceD d={d} />;
  const first = Object.values(a).find(Boolean);
  return first ? <details className="more"><summary>Generated result</summary><pre className="txt" style={{ maxHeight: 360, overflow: "auto", fontSize: 11 }}>{JSON.stringify(first, null, 1)}</pre></details> : null;
}

function Simple({ head, rows, foot }) {
  return (
    <div className="tablewrap"><table><thead><tr>{head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={j ? "num" : ""}>{v}</td>)}</tr>)}</tbody></table>
      {foot && <div className="tablefoot">{foot}</div>}</div>
  );
}

function RodwaldTable({ rows }) {
  return (
    <>
      <div className="form-label">Group containment · {rows[0]?.dataset}.{rows[0]?.field} against {rows[0]?.candidate}</div>
      <Simple head={["Group", "Size", "Inside", "Containment", "Verdict"]}
        rows={[...rows].sort((a, b) => b.size - a.size).map((r) => [r.code, fmt(r.size), fmt(r.overlap_with_candidate), pct(r.containment), r.well_formed ? r.verdict : `${r.verdict} (malformed)`])}
        foot={`The candidate is derived by containment, not named: a group is inherited when it lies wholly inside it, independent when it is disjoint, and a malformed value is reported rather than judged.`} />
    </>
  );
}

function TraceD({ d }) {
  return (
    <>
      <div className="form-label">Condition {d.condition} · {d.label}</div>
      <div className="kv"><span>Eligibility rule</span><span style={{ fontFamily: "inherit" }}>{d.eligibility_rule.map((r) => `${r.predicate}: ${r.description}`).join(" ")}</span></div>
      <div className="kv"><span>Retained</span><span>{fmt(d.retained_addresses)} addresses · coverage {pct(d.coverage_vs_B, 1)} of B · revenue ${fmt(Math.round(d.revenue_usd))}</span></div>
      <div className="kv"><span>Anchor set</span><span style={{ fontFamily: "inherit" }}>{d.anchor_set.origin}</span></div>
      <div className="kv"><span>Interpretation</span><span style={{ fontFamily: "inherit" }}>{d.interpretation}. Not: {d.not_interpreted_as}.</span></div>
      <div style={{ marginTop: 12 }}><Simple head={["Source-native criterion", "Addresses meeting it", "Share of retained"]}
        rows={d.declared_confidence_criteria.map((c) => [`${c.source}.${c.field} = ${c.equals}`, fmt(c.addresses_meeting), pct(c.share_of_retained, 1)])}
        foot={`${fmt(d.addresses_meeting_any_criterion)} retained addresses meet at least one criterion; ${fmt(d.addresses_meeting_no_criterion)} meet none in the loaded corpus.`} /></div>
      <div style={{ marginTop: 12 }}><Simple head={["Provenance concentration", "Addresses", "Share of retained"]}
        rows={d.provenance_concentration.map((c) => [c.label, fmt(c.addresses), pct(c.share_of_retained, 1)])} /></div>
    </>
  );
}
