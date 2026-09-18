import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const PAGE_SIZE = 50;

export default function ClaimsPage() {
  const { analysisId } = useAnalysis();
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState({ source: "", canon: "", evidence_tier: "", currency: "" });

  const { data, error, loading } = useApiData(
    () => api.claims(analysisId, { ...filters, offset, limit: PAGE_SIZE }),
    [analysisId, offset, filters.source, filters.canon, filters.evidence_tier, filters.currency],
  );

  if (!analysisId) {
    return (
      <div className="section">
        <div className="callout muted">
          No active analysis. <Link to="/">Upload a dataset or reproduce the paper</Link> to begin.
        </div>
      </div>
    );
  }

  function setFilter(key, value) {
    setOffset(0);
    setFilters((f) => ({ ...f, [key]: value }));
  }

  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Claims</div>
        <h1>Browse individual claims</h1>
        <p className="lead">
          A bounded, filtered page at a time — never the whole corpus at once. Use{" "}
          <Link to="/export">Export</Link> for the full normalized claim set.
        </p>
      </div>

      <div className="section">
        <div className="card" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input placeholder="source" value={filters.source}
            onChange={(e) => setFilter("source", e.target.value)} style={{ width: 160 }} />
          <input placeholder="canon (category)" value={filters.canon}
            onChange={(e) => setFilter("canon", e.target.value)} style={{ width: 160 }} />
          <select value={filters.evidence_tier} onChange={(e) => setFilter("evidence_tier", e.target.value)}>
            <option value="">evidence tier: any</option>
            <option value="verified">verified</option>
            <option value="derived">derived</option>
            <option value="unverified-report">unverified-report</option>
            <option value="unknown">unknown</option>
          </select>
          <select value={filters.currency} onChange={(e) => setFilter("currency", e.target.value)}>
            <option value="">currency: any</option>
            <option value="current">current</option>
            <option value="stale">stale</option>
            <option value="currency-unknown">currency-unknown</option>
          </select>
        </div>
      </div>

      {error && <div className="callout warn">{error}</div>}
      {loading && <p className="muted">Loading claims…</p>}

      {data && (
        <div className="section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
            <span className="muted">{total.toLocaleString()} matching claims — page {page} of {pages}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </button>
              <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next
              </button>
            </div>
          </div>

          {data.claims.length === 0 ? (
            <p className="muted">No claims match these filters.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Address</th><th>Source</th><th>Raw label</th><th>Canon</th><th>Polarity</th><th>Evidence tier</th><th>Last revised</th></tr>
              </thead>
              <tbody>
                {data.claims.map((c, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 12.5 }}>
                      <Link to={`/address?q=${encodeURIComponent(c.address)}`}>{c.address}</Link>
                    </td>
                    <td>{c.source}</td>
                    <td className="muted">{c.raw_label}</td>
                    <td>{c.canon}</td>
                    <td>{c.polarity}</td>
                    <td><StatusBadge label={c.evidence_tier} /></td>
                    <td>{c.lastmod || <span className="muted">unknown</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
