import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { humanize } from "../lib/format.js";
import { Loading, PageHead, Tag } from "../components/ui.jsx";

// The license field is free text ("CC BY 4.0 - confirmed ..."): the badge is its leading phrase,
// the full text stays available underneath.
const licenseBadge = (t) => (t || "").split(/\s+(?:-\s|\()/)[0] || "not stated";

const MODE_TEXT = {
  fixed_root: "every claim traces to one fixed root",
  field_map: "a source field maps each claim to its root",
  contains_rules: "root inferred from text patterns in a field",
  substring_map: "root inferred from substrings of a field",
};

export default function SourcesPage() {
  const { sources } = useAnalysis();
  return (
    <div>
      <PageHead kicker="Source registry" title="Every bundled dataset’s declared provenance rule"
        lead="Read straight from the configuration registry: adding a source is a config change, never an edit to the analysis engine. A source with no rule has an unresolved root, and unresolved is never counted as independent." />
      {!sources && <Loading>Loading source registry…</Loading>}
      {sources && (
        <div className="grid2" style={{ gridTemplateColumns: "1fr" }}>
          {Object.entries(sources).sort().map(([id, s]) => {
            const lic = licenseBadge(s.license);
            const p = s.provenance;
            return (
              <div className="panel" key={id}>
                <div className="panel-head" style={{ textTransform: "none", letterSpacing: 0, fontFamily: "var(--sn)", fontSize: 13 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>{id}</span><span className="mut">{s.display_name}</span>
                  <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <Tag>{s.chain}</Tag>
                    <Tag tone={/^UNCONFIRMED/i.test(lic) ? "flag" : "ok"} title={s.license}>license: {lic}</Tag>
                  </span>
                </div>
                <div className="panel-body">
                  <div className="kv" style={{ gridTemplateColumns: "150px 1fr" }}><span>citation</span><span style={{ fontFamily: "var(--sn)" }}>{s.citation || "—"}</span></div>
                  <div className="kv" style={{ gridTemplateColumns: "150px 1fr" }}><span>confidence semantics</span><span style={{ fontFamily: "var(--sn)" }}>{s.confidence_semantics || "—"}</span></div>
                  <div className="kv" style={{ gridTemplateColumns: "150px 1fr" }}><span>provenance rule</span>
                    <span style={{ fontFamily: "var(--sn)" }}>{p ? <>{humanize(p.mode)}: {MODE_TEXT[p.mode] || ""}{p.field && <> (<span className="mono">{p.field}</span>)</>}{p.root && <> → <span className="mono">{p.root}</span></>}</> : <span className="hot">no rule: root is unresolved</span>}</span></div>
                  {s.known_dependencies?.length > 0 && <div className="kv" style={{ gridTemplateColumns: "150px 1fr" }}><span>known dependencies</span><span>{s.known_dependencies.join(", ")}</span></div>}
                  {s.license && <details className="more"><summary>Full license note</summary><div className="txt">{s.license}</div></details>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
