import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import MetricTile from "../components/MetricTile.jsx";

const COLORS = { A: "#95a0af", B: "#1f4e79", C: "#2c6350", D: "#8a5e12" };
const usd = (n) => `$${Math.round(n).toLocaleString()}`;

export default function DriftPage() {
  const { analysisId, meta } = useAnalysis();
  const { data, error, loading } = useApiData(
    () => (analysisId ? api.drift(analysisId) : Promise.resolve(null)), [analysisId]);

  if (!analysisId) {
    return (
      <div className="section">
        <div className="callout muted">
          No active analysis. <Link to="/">Upload a dataset or reproduce the paper</Link> to begin.
        </div>
      </div>
    );
  }
  if (meta && meta.mode !== "PAPER_REPRODUCTION") {
    return (
      <div className="section">
        <div className="callout muted">
          Trust-rule sensitivity is reproduced against the bundled ransomware-revenue task and is
          only available for a Paper Reproduction analysis, not an uploaded dataset.
        </div>
      </div>
    );
  }
  if (loading) return <p className="muted">Loading trust-rule sensitivity…</p>;
  if (error) return <div className="callout warn">{error}</div>;
  if (!data) return null;

  const rows = Object.entries(data.conditions).map(([letter, c]) => ({ letter, ...c }));

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Trust-Rule Sensitivity</div>
        <h1>Same corpus, same procedure — different label-trust rule</h1>
        <p className="lead">
          The bundled forensic task is ransomware revenue estimation. Re-running it under four
          label-trust policies shows how much the conclusion depends on which claims are
          considered sufficiently trustworthy — coverage always travels with the figure.
        </p>
      </div>

      <div className="callout warn" style={{ fontSize: 13.5 }}>
        The interpretation is not "the lowest/highest-coverage condition is correct." It is: the
        forensic conclusion changes substantially depending on which labels are considered
        sufficiently trustworthy, and any number below must be read together with its coverage.
      </div>

      <div className="section">
        <div className="card" style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" />
              <XAxis dataKey="letter" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} tick={{ fontSize: 11 }} />
              <RTooltip formatter={(v) => usd(v)} labelFormatter={(l) => rows.find((r) => r.letter === l)?.label} />
              <Bar dataKey="usd" radius={[3, 3, 0, 0]}>
                {rows.map((r) => <Cell key={r.letter} fill={COLORS[r.letter]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="section">
        <table>
          <thead>
            <tr><th>Condition</th><th>Rule</th><th className="num">Observations</th><th className="num">Addresses</th><th className="num">Revenue (USD)</th><th className="num">vs baseline</th><th className="num">Coverage</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.letter}>
                <td><strong>{r.letter}</strong></td>
                <td>{r.label}</td>
                <td className="num">{r.observations.toLocaleString()}</td>
                <td className="num">{r.addresses.toLocaleString()}</td>
                <td className="num">{usd(r.usd)}</td>
                <td className="num">{r.ratio_vs_B != null ? `${r.ratio_vs_B.toFixed(2)}×` : "—"}</td>
                <td className="num">{r.coverage_vs_B != null ? `${(100 * r.coverage_vs_B).toFixed(1)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section">
        <div className="grid cols-3">
          <MetricTile label="shared addresses" value={data.shared_addresses}
            detail="counted twice under naive union (A)" />
          <MetricTile label="spread B / D" value={`${data.spread_B_over_D?.toFixed(1)}×`} />
          <MetricTile label="spread A / D" value={`${data.spread_A_over_D?.toFixed(1)}×`} />
        </div>
      </div>
    </>
  );
}
