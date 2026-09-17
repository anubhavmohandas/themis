import { BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import MetricTile from "../components/MetricTile.jsx";
import ReliabilityProfile from "../components/ReliabilityProfile.jsx";
import Tooltip from "../components/Tooltip.jsx";

const BAR = "#1f4e79";

export default function AuditPage() {
  const { data, error, loading } = useApiData(() => api.report(false), []);

  if (loading) return <p className="muted">Loading corpus audit…</p>;
  if (error) return <div className="callout warn">{error}</div>;
  if (!data) return null;

  const { dataset_summary: ds, agreement: a, independence: ind, kappa, freshness: f, limitations } = data;

  const sourceRows = Object.entries(ds.sources).map(([name, n]) => ({ name, n }));
  const outcomeRows = Object.entries(a.outcomes).map(([name, v]) => ({ name, n: v.n, share: v.share }));
  const rootRows = ind.root_concentration.map((r) => ({ name: r.root, n: r.claims }));
  const freshRows = [
    { name: "current", n: f.current }, { name: "stale", n: f.stale }, { name: "currency unknown", n: f.currency_unknown },
  ];

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Corpus Audit</div>
        <h1>Attribution corpus overview</h1>
        <p className="lead">Composition, corroboration depth, agreement outcomes and the independence tests, computed from the bundled reference corpus.</p>
      </div>

      <div className="section">
        <div className="grid cols-4">
          <MetricTile label="claims" value={ds.n_claims} help="Every source-asserts-category-for-address statement in the corpus." />
          <MetricTile label="addresses" value={ds.n_addresses} help="Distinct addresses carrying at least one claim." />
          <MetricTile label="sources" value={Object.keys(ds.sources).length} />
          <MetricTile label="multi-dataset addresses" value={a.n_multi_source}
            detail={`${(100 * a.multi_source_rate).toFixed(2)}% of all addresses`}
            help="Addresses named by two or more datasets - counts datasets, not independent sources. See Independence below." />
        </div>
      </div>

      <div className="section">
        <h2>Source coverage</h2>
        <ChartCard height={Math.max(160, sourceRows.length * 34)}>
          <BarChart data={sourceRows} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
            <RTooltip formatter={(v) => v.toLocaleString()} />
            <Bar dataKey="n" fill={BAR} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ChartCard>
      </div>

      <div className="section">
        <h2>
          <Tooltip text="Among addresses with claims from two or more datasets: do the categories agree exactly, refine a generic label, conflict on entity type, or conflict on licit/illicit polarity?">
            Agreement outcomes
          </Tooltip>
        </h2>
        <ChartCard height={220}>
          <BarChart data={outcomeRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={70} />
            <YAxis tick={{ fontSize: 11 }} />
            <RTooltip formatter={(v, k, p) => [`${v.toLocaleString()} (${(100 * p.payload.share).toFixed(1)}%)`, "n"]} />
            <Bar dataKey="n" fill={BAR} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartCard>
        {a.top_polarity_conflicts.length > 0 && (
          <table style={{ marginTop: 14 }}>
            <thead><tr><th>Largest licit/illicit conflicts</th><th></th><th className="num">n</th></tr></thead>
            <tbody>
              {a.top_polarity_conflicts.slice(0, 6).map((p, i) => (
                <tr key={i}>
                  <td>{p.source_a}: {p.label_a}</td>
                  <td>vs {p.source_b}: {p.label_b}</td>
                  <td className="num">{p.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {kappa && kappa.substantial.length > 0 && (
        <div className="section">
          <h2>
            <Tooltip text="Chance-corrected agreement between dataset pairs. Raw agreement alone flatters a corpus dominated by one category; kappa is only shown when the shared region isn't single-class (otherwise it's mathematically undefined, and reported as such rather than forced to a number).">
              Chance-corrected agreement (Cohen's κ)
            </Tooltip>
          </h2>
          <table>
            <thead><tr><th>Pair</th><th className="num">n</th><th className="num">raw agreement</th><th className="num">κ</th></tr></thead>
            <tbody>
              {kappa.substantial.map((r) => (
                <tr key={r.pair}>
                  <td>{r.pair}</td>
                  <td className="num">{r.n.toLocaleString()}</td>
                  <td className="num">{(100 * r.percent_agreement).toFixed(1)}%</td>
                  <td className="num">{r.cohen_kappa.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
            {kappa.n_pairs} overlapping pairs total; {kappa.n_undefined} undefined (single-class overlap), {kappa.n_zero} at zero.
          </p>
        </div>
      )}

      <div className="section">
        <h2>
          <Tooltip text="Where a claim's evidence actually originates - not the dataset that republished it. A root is 'identified' when config traces it to a declared or decoded origin; 'unresolved' roots are never treated as shared with one another.">
            Provenance
          </Tooltip>
        </h2>
        <div className="grid cols-3" style={{ marginBottom: 16 }}>
          <MetricTile label="roots total" value={ind.n_roots_total} />
          <MetricTile label="roots identified" value={ind.n_roots_identified} />
          <MetricTile label="unresolved addresses" value={ind.unresolved_addresses}
            detail={`${(100 * ind.unresolved_addr_share).toFixed(1)}% of the corpus`} />
        </div>
        <ChartCard height={Math.max(160, rootRows.length * 30)}>
          <BarChart data={rootRows} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 11 }} />
            <RTooltip formatter={(v) => v.toLocaleString()} />
            <Bar dataKey="n" fill={BAR} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ChartCard>
        <p className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
          Root concentration among all claims. Apparent multi-dataset corroboration can still be circular —
          see the Provenance Explorer and Address Inspector for which roots collapse together.
        </p>
      </div>

      <div className="section">
        <h2>
          <Tooltip text="A claim with no revision date is CURRENCY UNKNOWN, never STALE. Absence of a date is not evidence of staleness.">
            Freshness
          </Tooltip>
        </h2>
        <ChartCard height={200}>
          <BarChart data={freshRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <RTooltip formatter={(v) => v.toLocaleString()} />
            <Bar dataKey="n" fill={BAR} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartCard>
      </div>

      <div className="section">
        <h2>Reliability profile</h2>
        <ReliabilityProfile profile={data.reliability_profile} />
      </div>

      {limitations.length > 0 && (
        <div className="section">
          <h2>Limitations</h2>
          {limitations.map((l, i) => <div className="callout muted" key={i}>{l}</div>)}
        </div>
      )}
    </>
  );
}

function ChartCard({ height, children }) {
  return (
    <div className="card" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
    </div>
  );
}
