import { api } from "../lib/api.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { dateTime, fmt, shortId } from "../lib/format.js";
import { Gate, MetricStrip, PageHead, Section } from "../components/ui.jsx";

const FILES = [
  { name: "preflight.json", desc: "What the pre-flight decided and on what evidence: input hash, original columns, each column’s semantic meaning and confidence, your confirmations, the chain and how it was determined, rejected-record counts, blockers, and the parser / schema version. Uploaded datasets only.", uploadOnly: true },
  { name: "analysis_summary.json", desc: "Meta, the canonical result object and the audit trail for this analysis: the same object every screen renders." },
  { name: "normalized_claims.csv", desc: "Every claim after schema mapping and normalization: address, source, raw label, canonical category, polarity, provenance root and last-revised date. In a paper reproduction this is the bundled sample’s claims." },
  { name: "conflicts.csv", desc: "One row per conflicting or refined address, with both claims and their provenance relationship." },
  { name: "provenance_relationships.json", desc: "The lineage graph plus the measured field decodes, directional containment, naming residue and root propagation behind each inferred edge." },
  { name: "limitations.json", desc: "Every limitation stated for this analysis, as generated from its own data." },
];

export default function ExportPage() {
  return <Gate needSummary={false}><Body /></Gate>;
}

function Body() {
  const { analysisId, meta, summary, isPaper } = useAnalysis();
  const at = summary?.audit_trail;
  return (
    <div>
      <PageHead kicker="Evidence package" title="Export analysis"
        lead="Every figure on every screen comes from one result object. These are the same numbers, serialized with the metadata needed to re-run them." />
      <MetricStrip items={[
        { label: "Analysis ID", value: shortId(analysisId), sub: analysisId },
        { label: "Mode", value: isPaper ? "Paper reproduction" : "Uploaded dataset", text: true },
        { label: "Analysis date", value: meta.analysis_as_of_date || "—", sub: `run ${dateTime(meta.created_at)}` },
        { label: "Claims", value: fmt(meta.n_claims), sub: isPaper ? "browsable sample; full-corpus totals are on Overview" : "normalized target claims" },
      ]} />

      <Section title="Files">
        <div className="panel">
          <div className="rowlist">
            {FILES.filter((f) => !(f.uploadOnly && isPaper)).map((f) => (
              <div key={f.name}>
                <div><div className="rl-title mono">{f.name}</div><div className="rl-desc">{f.desc}</div></div>
                <a className="btn small secondary" href={api.exportUrl(analysisId, f.name)} download={f.name}>Download</a>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {at && (
        <Section title="Reproducibility metadata" meta="from the audit trail">
          <div className="panel pad">
            <div className="kv"><span>software version</span><span>{at.software_version}</span></div>
            <div className="kv"><span>analysis timestamp</span><span>{dateTime(at.analysis_timestamp)}</span></div>
            <div className="kv"><span>configuration hash</span><span>{at.config_hash}</span></div>
            <div className="kv"><span>configuration</span><span>{at.config_dir}</span></div>
            {at.input_file_hash && <div className="kv"><span>input file sha-256</span><span>{at.input_file_hash}</span></div>}
            {at.parameters && Object.keys(at.parameters).length > 0 && <div className="kv"><span>parameters</span><span>{JSON.stringify(at.parameters)}</span></div>}
            <div className="kv"><span>warnings</span><span>{at.warnings?.length ? at.warnings.length : "none"}</span></div>
          </div>
        </Section>
      )}

      <p className="section-note">
        CLI equivalents: <span className="mono">themis report --bootstrap --json out.json</span>, <span className="mono">themis drift --json out.json</span>, <span className="mono">themis explain &lt;address&gt; --json out.json</span>.
      </p>
    </div>
  );
}
