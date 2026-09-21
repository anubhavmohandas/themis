import { Status } from "./ui.jsx";
import { pct } from "../lib/format.js";

// Renders the backend's pre-flight (ingest/preflight.py) as the analyst reviews it
// before anything runs. Every check, confidence, status and blocker shown here is
// computed server-side; nothing is derived in the browser.
const MK = { ok: "✓", warn: "!", fail: "✕" };
const TONE = { ok: "ok", warn: "flag", fail: "hot" };
const STATUS_TONE = { ok: "ok", review: "flag", invalid: "hot", unused: "mut" };
const STATUS_TEXT = { ok: "valid", review: "needs review", invalid: "invalid", unused: "not used" };

export function PreflightChecks({ p }) {
  return (
    <div className="panel pad">
      {p.checks.map((c, i) => (
        <div key={i} className="checkline">
          <span className={`mk ${TONE[c.level]}`}>{MK[c.level]}</span>
          <div><div>{c.text}</div>{c.detail && <div className="mut" style={{ fontSize: 11.5 }}>{c.detail}</div>}</div>
        </div>
      ))}
    </div>
  );
}

// Why analysis cannot start. An unsupported dataset gets the headline and the
// fields it lacks; a merely blocked one lists what to fix.
export function PreflightVerdict({ p }) {
  if (p.can_analyze) return null;
  const unsupported = p.status === "unsupported";
  const [headline, ...rest] = (p.message || "").split("\n");
  return (
    <div className="inline-note" role="alert" style={{ whiteSpace: "pre-line" }}>
      <strong>{unsupported ? headline.replace(/\.$/, "") : "Analysis blocked at pre-flight"}</strong>
      {unsupported
        ? <>{"\n"}{rest.join("\n").trim()}</>
        : <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{p.blockers.map((b) => <li key={b.code}>{b.message}</li>)}</ul>}
      {unsupported && p.required.some((r) => !r.satisfied) && (
        <div style={{ marginTop: 8 }}>
          <strong>Required for attribution analysis, and absent:</strong>{" "}
          {p.required.filter((r) => !r.satisfied).map((r) => r.accepts.join(" / ")).join("; ")}
        </div>
      )}
    </div>
  );
}

// original column -> inferred THEMIS field -> confidence -> sample values -> validation status.
// The select is the user's correction; changing it re-runs the pre-flight on the server.
export function MappingTable({ p, fields, onChange }) {
  return (
    <div className="tablewrap">
      <table>
        <thead><tr><th>Original column</th><th>THEMIS semantic field</th><th className="num">Confidence</th><th>Sample values</th><th>Validation</th></tr></thead>
        <tbody>
          {p.columns.map((c) => (
            <tr key={c.column}>
              <td className="mono">{c.column}</td>
              <td>
                <select className="plain" value={c.semantic_type} aria-label={`Meaning of ${c.column}`}
                  onChange={(e) => onChange(c.column, e.target.value)}>
                  {fields.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
                </select>
              </td>
              <td className="num">{c.confidence == null ? "—" : pct(c.confidence)}{c.origin === "user" && <span className="mut"> · set by you</span>}</td>
              <td className="mono small mut" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={c.sample_values.join(" · ")}>{c.sample_values.join(" · ")}</td>
              <td>
                <Status tone={STATUS_TONE[c.status]}>{STATUS_TEXT[c.status]}</Status>
                {c.notes.map((n, i) => <div key={i} className="mut" style={{ fontSize: 11, marginTop: 3, maxWidth: 320 }}>{n}</div>)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Chain-dependent validation needs a chain. When it cannot be determined the user must choose;
// when it was detected the user can still override it.
export function ChainPicker({ p, chains, value, onChange }) {
  const ch = p.chain;
  if (ch.status === "not_required") return null;
  const need = ch.status === "undetermined" || ch.status === "ambiguous";
  return (
    <label className="field" style={{ marginTop: 12 }}>
      Blockchain{need ? " (required)" : ""}:
      <select className="plain" value={value || ""} aria-label="Blockchain" onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{ch.value && !value ? `${ch.value} (${ch.source === "detected" ? "detected" : ch.source})` : "— choose —"}</option>
        {chains.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </label>
  );
}

export function ConfirmMapping({ p, confirmed, onChange }) {
  if (p.status !== "needs_confirmation" && !(confirmed && p.can_analyze && p.user_confirmed)) return null;
  return (
    <label className="field" style={{ marginTop: 12, alignItems: "flex-start" }}>
      <input type="checkbox" checked={confirmed} onChange={(e) => onChange(e.target.checked)} />
      <span>I have reviewed the low-confidence mappings above and confirm them. THEMIS records this confirmation with the analysis.</span>
    </label>
  );
}
