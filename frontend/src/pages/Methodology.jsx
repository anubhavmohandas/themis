import { Link } from "react-router-dom";
import { PageHead, Section, Tag } from "../components/ui.jsx";

// Vocabulary and scope statements only: no figures live on this page.
const VOCAB = [
  { group: "Claim provenance", items: [
    ["resolved", "The claim’s evidence origin (its root) is identified and native to the dataset that made it."],
    ["inherited", "The root is identified, but it belongs to another dataset: the claim restates existing evidence."],
    ["unresolved", "No identified root. Unresolved is never counted as independent and never as shared: it is simply unverifiable."],
  ] },
  { group: "Provenance edges", items: [
    ["declared", "The source registry states the root."],
    ["inferred", "The root is decoded or matched from a field. Recorded as inferred; never upgraded to declared."],
    ["unresolved", "No rule identifies the root."],
  ] },
  { group: "Evidence tier", items: [
    ["verified", "Independently re-checkable evidence. Manual annotation without retained evidence does not qualify."],
    ["derived", "Produced by a stated method, but not independently re-checkable."],
    ["unverified report", "A crowd or third-party report with no method attached."],
    ["unknown", "No declared methodology. Never silently upgraded to derived."],
  ] },
  { group: "Agreement outcome", items: [
    ["exact", "Every dataset gives the same canonical category."],
    ["hierarchical refinement", "One label is a more specific case of the other. A refinement, not a conflict."],
    ["entity-type conflict", "Comparable labels name different entity types."],
    ["licit / illicit conflict", "Comparable labels sit on opposite sides of the licit / illicit line."],
    ["incomparable", "No shared taxonomy path between the labels, so agreement cannot be judged."],
  ] },
  { group: "Currency", items: [
    ["current", "A revision date exists and is within the staleness threshold."],
    ["stale", "A revision date exists and is older than the threshold."],
    ["currency unknown", "No revision date. Absence of a date is not evidence of staleness."],
  ] },
  { group: "Provenance relationship (per address)", items: [
    ["shared root", "At least two claims trace to the same root. Reported first when it applies."],
    ["unresolved", "No shared root, but at least one claim has no identified root."],
    ["distinct roots", "Every claim traces to a different identified root."],
  ] },
];

const NOT_CLAIMED = [
  "Which source is correct. THEMIS measures the strength, independence, traceability and limits of the evidence behind a label, not the label’s truth.",
  "That agreement is confirmation. Datasets that share a root agree once, however many of them repeat it.",
  "That overlap proves copying. High containment and a clean field split are recorded as inferred inheritance, with the evidence shown.",
  "That unresolved provenance is unreliable. It is unverifiable, and reported as such.",
  "That coverage is accuracy. Evidence retained under a trust rule is not evidence that is right, and evidence dropped is not evidence that is wrong.",
  "That an interval is an error bar. Cluster-bootstrap and anchor intervals bound what a small number of independent roots can support.",
];

const SCREENS = [
  ["New Analysis", "POST /api/preflight · POST /api/jobs/analysis · GET /api/jobs/{id}", "File inspection, schema inference, and the analysis pipeline with its real stage progress."],
  ["Overview", "GET /api/analysis/{id}/summary", "Every headline figure, share and denominator."],
  ["Claims", "GET …/claims?source&canon&evidence_tier&currency&outcome&comparable&provenance&q", "Server-side filtering and paging."],
  ["Address Inspector", "GET …/address/{address}", "Claims, roots and the independence range for one address."],
  ["Provenance", "GET …/provenance", "Lineage graph with measured evidence attached to each edge."],
  ["Conflicts", "GET …/conflicts?kind&source_a&source_b&relationship&q", "Per-address disagreement records."],
  ["Trust Analysis", "GET …/drift (paper) · GET …/trust-coverage?rules (upload)", "Trust-rule sensitivity, or evidence retention under chosen rules."],
  ["Reproduce Paper", "POST /api/jobs/paper · GET …/tasks · POST …/run/{drift|bootstrap|anchors}", "Full reproduction and on-demand runs."],
  ["Exports", "GET …/export/{name}", "Five serialized artifacts."],
  ["Sources", "GET /api/sources", "The provenance registry."],
];

export default function MethodologyPage() {
  return (
    <div>
      <PageHead kicker="Method" title="How to read THEMIS"
        lead="THEMIS audits the evidence behind public cryptocurrency attribution labels. This page fixes the vocabulary used on every screen and states what the tool does not claim." />

      <Section title="Vocabulary">
        <div style={{ display: "grid", gap: 20 }}>
          {VOCAB.map((g) => (
            <div key={g.group}>
              <div className="form-label">{g.group}</div>
              <div className="grid2">
                {g.items.map(([name, text]) => (
                  <div key={name} className="defcard"><span className="dn">{name}</span><p>{text}</p></div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Two readings of “comparable”">
        <div className="grid2">
          <div className="defcard"><span className="dn">Multi-dataset address</span><span className="dg">paper reproduction</span>
            <p>An address named by at least two of the bundled datasets. The rest of the corpus has no second public claim to compare against.</p></div>
          <div className="defcard"><span className="dn">Reference match</span><span className="dg">uploaded dataset</span>
            <p>An address in your file that also carries at least one claim in the bundled reference corpus. The two measures are not interchangeable.</p></div>
        </div>
      </Section>

      <Section title="What THEMIS does not claim">
        <div className="callout"><ul>{NOT_CLAIMED.map((t) => <li key={t}>{t}</li>)}</ul></div>
      </Section>

      <Section title="Where each screen’s numbers come from"
        note="The interface never computes an analytic figure. Every share, count, filter, coverage number and progress stage is returned by the backend; the screens only send settings and render the response.">
        <div className="tablewrap"><table>
          <thead><tr><th>Screen</th><th>Endpoint</th><th>Provides</th></tr></thead>
          <tbody>{SCREENS.map(([s, e, w]) => (
            <tr key={s}><td>{s}</td><td className="mono small">{e}</td><td className="small mut">{w}</td></tr>))}</tbody>
        </table></div>
        <p className="section-note" style={{ marginTop: 10 }}>
          Paper-section badges (<Tag>§5.2</Tag>) appear only in a paper reproduction and name a section of the manuscript; they never carry a figure. Numbers here are recomputed from the bundled corpus and can differ from figures quoted in a manuscript draft. See <Link to="/sources">Sources</Link> for the corpus and its licenses.
        </p>
      </Section>
    </div>
  );
}
