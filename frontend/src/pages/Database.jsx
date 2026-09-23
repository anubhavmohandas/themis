import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { useJob } from "../lib/useJob.js";
import { bytes, fmt, pct } from "../lib/format.js";
import { ErrorBox, PageHead, Section, Status } from "../components/ui.jsx";
import Pipeline from "../components/Pipeline.jsx";
import { ChainPicker, ConfirmMapping, MappingTable, PreflightChecks, PreflightVerdict } from "../components/Preflight.jsx";

// Mirrors themis/ingest/relational.py:CASE_METADATA_FIELDS - generic, dataset-agnostic
// context an analyst may assert about an analysis's own evidential standing.
const CASE_METADATA_FIELDS = [
  { key: "analysis_origin", label: "Analysis origin", placeholder: "e.g. recovered_sqlite_subset" },
  { key: "integrity_status", label: "Integrity status", placeholder: "e.g. source_file_truncated" },
  { key: "recovery_status", label: "Recovery status", placeholder: "e.g. recovered_subset" },
  { key: "source_identity_status", label: "Source identity status", placeholder: "e.g. partially_attributed" },
  { key: "provenance_resolution_status", label: "Provenance resolution status", placeholder: "e.g. unresolved" },
  { key: "limitations", label: "Limitations", placeholder: "free text" },
];

// Upload/Open database -> Database Inspection -> Table Selection -> Schema
// Mapping -> Sample Preview -> Preflight -> (extraction produces the Dataset
// Profile / Provenance / Conflicts THEMIS then analyses like any other
// dataset). This page only covers the steps a CSV upload doesn't already
// have a screen for; Trust/Export etc. are the same pages every analysis uses.
export default function DatabasePage() {
  const nav = useNavigate();
  const { activate } = useAnalysis();
  const [db, setDb] = useState("");
  const [insp, setInsp] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [relationships, setRelationships] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [driving, setDriving] = useState(null);
  const [joins, setJoins] = useState([]);   // {table, local_table, local_key, foreign_key}

  const [pf, setPf] = useState(null);
  const [pfBusy, setPfBusy] = useState(false);
  const [edits, setEdits] = useState({});
  const [chain, setChain] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [sourceId, setSourceId] = useState("sqlite_dataset");
  const [useReference, setUseReference] = useState(true);
  const [caseMeta, setCaseMeta] = useState({});   // optional, generic analyst-asserted context (see CASE_METADATA_FIELDS)
  const extract = useJob();

  const integrityFailed = insp && insp.integrity.status !== "ok";

  const inspect = () => {
    if (!db.trim()) return;
    setBusy(true); setError(null); setInsp(null); setCandidates(null); setRelationships(null);
    setDriving(null); setJoins([]); setPf(null);
    api.sqliteInspect(db).then((i) => {
      setInsp(i);
      if (i.integrity.status !== "ok") return null;   // integrity check failed: do not offer table selection
      return Promise.all([api.sqliteCandidates(db), api.sqliteRelationships(db)])
        .then(([c, r]) => { setCandidates(c.candidates); setRelationships(r.relationships); });
    }).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };

  const addJoin = () => {
    const already = new Set([driving, ...joins.map((j) => j.table)]);
    const next = (insp?.tables || []).map((t) => t.table).find((t) => !already.has(t));
    if (!next) return;
    // pre-fill from a discovered relationship when one points at this table
    const rel = (relationships || []).find((r) => r.to_table === next && already.has(r.from_table));
    setJoins([...joins, {
      table: next, local_table: rel?.from_table || driving,
      local_key: rel?.from_column || "", foreign_key: rel?.to_column || "",
    }]);
  };

  const spec = driving ? { driving_table: driving, joins: joins.map((j) => ({
    table: j.table, local_table: j.local_table, local_key: j.local_key, foreign_key: j.foreign_key })) } : null;
  const specReady = !!driving && joins.every((j) => j.local_key && j.foreign_key);

  const runPreflight = () => {
    if (!specReady) return;
    setPfBusy(true); setError(null);
    api.sqliteRelationalPreflight({ db, spec, semantics: edits, chain, confirmed })
      .then(setPf)
      .catch((e) => { setPf(null); setError(e.message); })
      .finally(() => setPfBusy(false));
  };

  const p = pf?.preflight;
  const caseMetadata = Object.fromEntries(Object.entries(caseMeta).filter(([, v]) => v.trim()));
  const runExtraction = () => extract.run(
    () => api.startSqliteExtractJob({ db, spec, sourceId, useReference, semantics: edits, chain, confirmed,
      caseMetadata: Object.keys(caseMetadata).length ? caseMetadata : undefined }),
    (j) => { if (j.status === "complete") { activate(j.analysis_id, j.meta); nav("/overview"); } });

  return (
    <div>
      <PageHead kicker="New analysis · database" title="Open a SQLite attribution database"
        lead="Inspect a .db / .sqlite / .sqlite3 file, choose which table(s) hold the claims, join in a label or source table if the attribution isn't in one table, and confirm the mapping - all on bounded samples. Nothing is loaded whole; the driving table is streamed in chunks only once you extract." />

      <Section title="1 · Database" note="Opened by path relative to THEMIS_DB_DIR (set on the server) - the file itself is never uploaded.">
        <div className="controls">
          <label className="field grow">Path:
            <input type="text" value={db} onChange={(e) => setDb(e.target.value)} placeholder="dataset.sqlite" style={{ minWidth: 280 }} />
          </label>
          <button type="button" className="btn" disabled={!db.trim() || busy} onClick={inspect}>{busy ? "Inspecting…" : "Inspect"}</button>
        </div>
      </Section>

      {error && <ErrorBox title="Request failed">{error}</ErrorBox>}

      {insp && (
        <Section title="2 · Database inspection" meta={`${bytes(insp.size_bytes)}${insp.sqlite_version ? ` · SQLite ${insp.sqlite_version}` : ""}`}>
          <div className="filecard">
            <div><span className="mut">file </span>{insp.filename}</div>
            <div><span className="mut">integrity </span>
              <Status tone={insp.integrity.status === "ok" ? "ok" : "hot"}>{insp.integrity.status}</Status>
              {insp.integrity.errors.length > 0 && <span className="mut"> · {insp.integrity.errors[0]}</span>}
            </div>
          </div>
          <div className="tablewrap" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>Table</th><th className="num">Rows</th><th>Columns</th><th>Primary key</th><th>Foreign keys</th></tr></thead>
              <tbody>
                {insp.tables.map((t) => (
                  <tr key={t.table}>
                    <td className="mono">{t.table}</td>
                    <td className="num">{t.n_rows == null ? "not counted" : fmt(t.n_rows)}</td>
                    <td className="mono small mut">{t.columns.map((c) => c.name).join(", ")}</td>
                    <td className="mono small">{t.columns.filter((c) => c.primary_key).map((c) => c.name).join(", ") || "—"}</td>
                    <td className="mono small">{t.foreign_keys.map((f) => `${f.from_column}→${f.table}.${f.to_column}`).join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {insp.views.length > 0 && <p className="mut" style={{ fontSize: 12 }}>{insp.views.length} view(s): {insp.views.map((v) => v.table).join(", ")}</p>}
        </Section>
      )}

      {integrityFailed && (
        <div className="inline-note" role="alert" style={{ whiteSpace: "pre-line" }}>
          <strong>DATABASE INTEGRITY CHECK FAILED</strong>
          {"\n"}Analysis has not started.
          {"\n\n"}The database appears truncated or damaged ({insp.integrity.status}
          {insp.integrity.errors[0] ? `: ${insp.integrity.errors[0]}` : ""}). Obtain a clean copy before treating
          the contents as a complete dataset. THEMIS does not attempt automatic recovery.
        </div>
      )}

      {candidates && (
        <Section title="3 · Table selection" note="What THEMIS thinks each table is for, and why. Pick the table that holds one row per claim subject, then join in a label/source table if the attribution lives elsewhere.">
          <div className="tablewrap">
            <table>
              <thead><tr><th>Table</th><th>Likely role</th><th className="num">Confidence</th><th>Why</th></tr></thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.table}>
                    <td className="mono">{c.table}</td>
                    <td>{c.role.replace(/_/g, " ")}</td>
                    <td className="num">{pct(c.confidence)}</td>
                    <td className="mut" style={{ fontSize: 12 }}>{c.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="controls" style={{ marginTop: 12 }}>
            <label className="field">Driving (claim-subject) table:
              <select className="plain" value={driving || ""} onChange={(e) => { setDriving(e.target.value || null); setJoins([]); setPf(null); }}>
                <option value="">— choose —</option>
                {insp.tables.map((t) => <option key={t.table} value={t.table}>{t.table}</option>)}
              </select>
            </label>
            {driving && <button type="button" className="btn secondary" onClick={addJoin}>+ Join a table</button>}
          </div>
          {joins.map((j, i) => (
            <div key={i} className="controls" style={{ marginTop: 8 }}>
              <span className="mono small">{j.table}</span>
              <label className="field">on:
                <select className="plain" value={j.local_table} onChange={(e) => { const n = [...joins]; n[i] = { ...j, local_table: e.target.value }; setJoins(n); }}>
                  {[driving, ...joins.slice(0, i).map((x) => x.table)].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="field">local key:
                <input className="mono small" value={j.local_key} onChange={(e) => { const n = [...joins]; n[i] = { ...j, local_key: e.target.value }; setJoins(n); }} style={{ width: 120 }} />
              </label>
              <label className="field">= {j.table}:
                <input className="mono small" value={j.foreign_key} onChange={(e) => { const n = [...joins]; n[i] = { ...j, foreign_key: e.target.value }; setJoins(n); }} style={{ width: 120 }} />
              </label>
              <button type="button" className="btn secondary" onClick={() => setJoins(joins.filter((_, x) => x !== i))}>Remove</button>
            </div>
          ))}
          {relationships?.length > 0 && (
            <p className="mut" style={{ fontSize: 11.5, marginTop: 8 }}>
              Discovered relationships: {relationships.map((r, i) => (
                <span key={i}>{i > 0 && "; "}{r.from_table}.{r.from_column} → {r.to_table}.{r.to_column} ({r.kind}, {pct(r.confidence)})</span>
              ))}
            </p>
          )}
          {driving && (
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn" disabled={!specReady || pfBusy} onClick={runPreflight}>
                {pfBusy ? "Running pre-flight…" : "Preflight this join"}
              </button>
            </div>
          )}
        </Section>
      )}

      {p && (
        <>
          {pf.join_warnings?.length > 0 && (
            <div className="inline-note" role="alert">
              {pf.join_warnings.map((w, i) => <div key={i}>{w}</div>)}
            </div>
          )}
          <Section title="4 · Pre-flight" meta={`sample of ${pf.sample_rows.length} joined rows`}
            note="Nothing is streamed until the joined sample has a defensible attribution schema.">
            <PreflightChecks p={p} />
            <PreflightVerdict p={p} />
            <ChainPicker p={p} chains={pf.chains} value={chain} onChange={setChain} />
          </Section>

          <Section title="5 · Schema mapping" note="Columns are shown as table__column since they may come from more than one joined table.">
            <MappingTable p={p} fields={pf.semantic_fields} onChange={(col, sem) => setEdits({ ...edits, [col]: sem })} />
            <ConfirmMapping p={p} confirmed={confirmed} onChange={setConfirmed} />
            <details className="more">
              <summary>Show {pf.sample_rows.length} sample rows</summary>
              <div className="tablewrap"><table>
                <thead><tr>{pf.fieldnames.map((f) => <th key={f}>{f}</th>)}</tr></thead>
                <tbody>{pf.sample_rows.map((row, i) => <tr key={i}>{pf.fieldnames.map((f) => <td key={f} className="mono small">{row[f]}</td>)}</tr>)}</tbody>
              </table></div>
            </details>
            <div className="controls" style={{ marginTop: 16 }}>
              <label className="field">Source id:
                <input type="text" value={sourceId} onChange={(e) => setSourceId(e.target.value)} style={{ width: 170 }} />
              </label>
              <label className="field" title="Compare against the reference corpus.">
                <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
                compare against reference corpus
              </label>
            </div>
            <details className="more" style={{ marginTop: 12 }}>
              <summary>Case-study metadata (optional)</summary>
              <p className="mut" style={{ fontSize: 12, maxWidth: 640 }}>
                Free-text context you assert about this analysis's own evidential standing - e.g. that this
                database is a recovered subset of a truncated original. THEMIS carries these values unchanged;
                it never infers or scores them.
              </p>
              {CASE_METADATA_FIELDS.map(({ key, label, placeholder }) => (
                <label key={key} className="field" style={{ marginTop: 6, alignItems: "flex-start" }}>
                  {label}:
                  <input type="text" value={caseMeta[key] || ""} placeholder={placeholder}
                    onChange={(e) => setCaseMeta({ ...caseMeta, [key]: e.target.value })} style={{ minWidth: 320 }} />
                </label>
              ))}
            </details>
            <div style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center" }}>
              <button type="button" className="btn" disabled={!p.can_analyze || extract.job?.status === "running"} onClick={runExtraction}>
                {extract.job?.status === "running" ? "Extracting…" : "Extract & analyse"}
              </button>
              {!p.can_analyze && <span className="hot" style={{ fontSize: 12 }}>Extraction is blocked until the items above are resolved.</span>}
            </div>
          </Section>
        </>
      )}

      {extract.error && <ErrorBox title="Could not start extraction">{extract.error}</ErrorBox>}
      {extract.job && (
        <Section title="Extraction pipeline">
          <Pipeline job={extract.job} title="Database extraction" />
          {extract.job.status === "stopped" && (
            <div className="inline-note" role="alert" style={{ whiteSpace: "pre-line" }}>
              <strong>Stopped at pre-flight.</strong>{"\n"}{extract.job.preflight?.message}
            </div>
          )}
          {extract.job.status === "failed" && <ErrorBox title="Extraction failed">{extract.job.error}</ErrorBox>}
        </Section>
      )}
    </div>
  );
}
