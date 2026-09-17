import { useState } from "react";
import { api } from "../lib/api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import MetricTile from "../components/MetricTile.jsx";
import Tooltip from "../components/Tooltip.jsx";

const EXAMPLES = [
  { addr: "14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7", note: "4 datasets, 3 roots — circular" },
  { addr: "34kWCKF2wCbe6uinit2uL4ND6d8yxsuxKM", note: "exchange vs sanctioned — conflict" },
  { addr: "1LLEoSTzRmSL3xC5AWhsn9QjpGFh4Wx72N", note: "genuine independent corroboration" },
];

export default function AddressInspectorPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function run(addr) {
    const a = (addr ?? query).trim();
    if (!a) return;
    setQuery(a);
    setLoading(true); setError(null); setResult(null);
    try {
      setResult(await api.address(a));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Address Inspector</div>
        <h1>Trace one address</h1>
        <p className="lead">Every attribution claim against this address, where each one's evidence actually originates, and whether apparent multi-dataset agreement survives an independence check.</p>
      </div>

      <div className="section">
        <div className="card">
          <form onSubmit={(e) => { e.preventDefault(); run(); }} style={{ display: "flex", gap: 10 }}>
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="bc1... or 1... address" style={{ flex: 1 }} />
            <button type="submit" disabled={loading}>{loading ? "Searching…" : "Inspect"}</button>
          </form>
          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 12.5 }}>try:</span>
            {EXAMPLES.map((e) => (
              <button key={e.addr} type="button" className="secondary" style={{ fontSize: 11.5, padding: "4px 8px" }}
                onClick={() => run(e.addr)} title={e.note}>
                {e.addr.slice(0, 10)}… — {e.note}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="callout warn">{error}</div>}

      {result && !result.found && (
        <div className="callout muted">
          Address not present in this corpus. The bundled sample holds every multi-dataset address
          plus a random sample of single-dataset ones.
        </div>
      )}

      {result && result.found && <AddressResult r={result} />}
    </>
  );
}

function AddressResult({ r }) {
  return (
    <>
      <div className="section">
        <h2 className="mono" style={{ fontSize: 15, wordBreak: "break-all" }}>{r.address}</h2>
        <div className="grid cols-3" style={{ marginTop: 14 }}>
          <div className="tile">
            <div className="k">outcome</div>
            <div className="v" style={{ fontSize: 18 }}><StatusBadge label={r.outcome} /></div>
          </div>
          <MetricTile label="apparent corroboration" value={r.apparent_corroboration}
            help="Number of distinct datasets asserting a claim about this address." />
          <div className="tile">
            <div className="k">
              <Tooltip text="Number of distinct provenance roots behind those datasets' claims. If this is lower than apparent corroboration, some of the agreement is inherited from a shared ancestor, not independent.">
                independent corroboration
              </Tooltip>
            </div>
            <div className="v" style={{ color: r.circular ? "var(--warn)" : "var(--ok)" }}>{r.actual_corroboration}</div>
          </div>
        </div>
        {r.circular && (
          <div className="callout warn" style={{ marginTop: 14 }}>
            Circularity detected — the apparent number of confirming datasets exceeds the number of
            independent provenance roots. Agreement here is inherited from a shared ancestor, not
            independently corroborated.
          </div>
        )}
        {r.flags.length > 0 && (
          <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
            {r.flags.map((f) => <StatusBadge key={f} label={f} />)}
          </div>
        )}
      </div>

      <div className="section">
        <h2>Attribution claims</h2>
        <table>
          <thead>
            <tr><th>Dataset</th><th>Label</th><th>Raw label</th><th>Provenance root</th><th>Root kind</th><th>Tier</th><th>Last revised</th><th>Flags</th></tr>
          </thead>
          <tbody>
            {r.claims.map((c, i) => (
              <tr key={i}>
                <td>{c.source}</td>
                <td>{c.label}</td>
                <td className="muted">{c.raw}</td>
                <td className="mono" style={{ fontSize: 12.5 }}>{c.root}</td>
                <td><StatusBadge label={c.root_kind} /></td>
                <td><StatusBadge label={c.tier} /></td>
                <td>{c.lastmod || <span className="muted">unknown</span>}</td>
                <td>{c.flags.length ? c.flags.map((f) => <StatusBadge key={f} label={f} />) : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>
          Root kind: <StatusBadge label="DECLARED" /> the source config states this root outright ·{" "}
          <StatusBadge label="INFERRED" /> decoded from an undocumented code or a residue/fallback guess ·{" "}
          <StatusBadge label="UNKNOWN" /> no provenance rule configured for this source.
        </p>
      </div>
    </>
  );
}
