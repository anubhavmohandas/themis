import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import MetricTile from "../components/MetricTile.jsx";
import Tooltip from "../components/Tooltip.jsx";

export default function AddressInspectorPage() {
  const { analysisId, meta } = useAnalysis();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function run(addr) {
    const a = (addr ?? query).trim();
    if (!a || !analysisId) return;
    setQuery(a);
    setLoading(true); setError(null); setResult(null);
    try {
      setResult(await api.address(analysisId, a));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (!analysisId) {
    return (
      <div className="section">
        <div className="callout muted">
          No active analysis. <Link to="/">Upload a dataset or reproduce the paper</Link> to begin.
        </div>
      </div>
    );
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
        </div>
      </div>

      {error && <div className="callout warn">{error}</div>}

      {result && !result.found && (
        <div className="callout muted">
          Address not present in this analysis.
        </div>
      )}

      {result && result.found && (
        meta?.mode === "PAPER_REPRODUCTION"
          ? <PaperAddressResult r={result} />
          : <TargetAddressResult r={result} />
      )}
    </>
  );
}

function IndependenceBlock({ indep }) {
  return (
    <div className="grid cols-3" style={{ marginTop: 14 }}>
      <MetricTile label="apparent corroboration" value={indep.apparent_dataset_count}
        help="Number of distinct datasets asserting a claim about this address." />
      <div className="tile">
        <div className="k">
          <Tooltip text="Distinct RESOLVED provenance roots only. An unresolved relationship between two sources is never counted as a confirmed independent one.">
            confirmed independent roots
          </Tooltip>
        </div>
        <div className="v" style={{ color: indep.circular ? "var(--warn)" : "var(--ok)" }}>{indep.confirmed_independent_root_count}</div>
      </div>
      <div className="tile">
        <div className="k">independence range</div>
        <div className="v" style={{ fontSize: 18 }}>{indep.independence_min} – {indep.independence_max}</div>
        <div className="d">unresolved sources: {indep.unresolved_source_count}</div>
      </div>
    </div>
  );
}

function PaperAddressResult({ r }) {
  return (
    <>
      <div className="section">
        <h2 className="mono" style={{ fontSize: 15, wordBreak: "break-all" }}>{r.address}</h2>
        <div className="tile" style={{ marginTop: 14, maxWidth: 260 }}>
          <div className="k">outcome</div>
          <div className="v" style={{ fontSize: 18 }}><StatusBadge label={r.outcome} /></div>
        </div>
        <IndependenceBlock indep={r.independence} />
        {r.circular && (
          <div className="callout warn" style={{ marginTop: 14 }}>
            Circularity detected — the apparent number of confirming datasets exceeds the number of
            confirmed independent provenance roots. Agreement here is inherited from a shared ancestor,
            not independently corroborated.
          </div>
        )}
        {r.flags?.length > 0 && (
          <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
            {r.flags.map((f) => <StatusBadge key={f} label={f} />)}
          </div>
        )}
      </div>

      <ClaimsTable title="Attribution claims" claims={r.claims} />
    </>
  );
}

function TargetAddressResult({ r }) {
  return (
    <>
      <div className="section">
        <h2 className="mono" style={{ fontSize: 15, wordBreak: "break-all" }}>{r.address}</h2>
        <div className="grid cols-2" style={{ marginTop: 14, maxWidth: 520 }}>
          <div className="tile">
            <div className="k">outcome</div>
            <div className="v" style={{ fontSize: 18 }}><StatusBadge label={r.outcome} /></div>
          </div>
          <div className="tile">
            <div className="k">reference comparability</div>
            <div className="v" style={{ fontSize: 15 }}>{r.comparability || "NO_REFERENCE_MATCH"}</div>
          </div>
        </div>
        <IndependenceBlock indep={r.independence} />
        {r.circular && (
          <div className="callout warn" style={{ marginTop: 14 }}>
            Circularity detected — some of the apparent confirming datasets share one resolved
            provenance root.
          </div>
        )}
      </div>

      <ClaimsTable title="Target claim(s)" claims={r.target_claims} empty="This analysis's dataset has no claim on this address." />
      <ClaimsTable title="Reference claims" claims={r.reference_claims} empty="No reference corpus claim was found for this address." />
    </>
  );
}

function ClaimsTable({ title, claims, empty }) {
  return (
    <div className="section">
      <h2>{title}</h2>
      {(!claims || claims.length === 0) ? (
        <p className="muted">{empty || "None."}</p>
      ) : (
        <table>
          <thead>
            <tr><th>Dataset</th><th>Label</th><th>Raw label</th><th>Provenance root</th><th>Root kind</th><th>Tier</th><th>Last revised</th><th>Flags</th></tr>
          </thead>
          <tbody>
            {claims.map((c, i) => (
              <tr key={i}>
                <td>{c.source}</td>
                <td>{c.label}</td>
                <td className="muted">{c.raw}</td>
                <td className="mono" style={{ fontSize: 12.5 }}>{c.root}</td>
                <td><StatusBadge label={c.root_kind} /></td>
                <td><StatusBadge label={c.tier} /></td>
                <td>{c.lastmod || <span className="muted">unknown</span>}</td>
                <td>{c.flags?.length ? c.flags.map((f) => <StatusBadge key={f} label={f} />) : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
