import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, ReactFlowProvider, useReactFlow } from "reactflow";
import "reactflow/dist/style.css";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, pct } from "../lib/format.js";
import { Drawer, ErrorBox, Gate, Loading, PageHead, RadioRow, Section, Status, Tag } from "../components/ui.jsx";

export default function ProvenancePage() {
  return <Gate><ReactFlowProvider><Body /></ReactFlowProvider></Gate>;
}

// ----------------------------------------------------------------- helpers
const rootMatches = (label, root) => (label.endsWith("*") ? root.startsWith(label.slice(0, -1)) : label === root);

// An edge is "unresolved" when it has no rule at all (UNKNOWN) or points at a root
// the registry marks unresolved; otherwise its class is its declared/inferred kind.
function edgeClass(e, nodeById) {
  if (e.kind === "UNKNOWN" || nodeById[e.target]?.type === "root_unresolved") return "unresolved";
  return e.kind === "INFERRED" ? "inferred" : "declared";
}
const STROKE = { declared: "var(--tl)", inferred: "var(--oc)", unresolved: "var(--nt2)" };
const DASH = { declared: undefined, inferred: "5 4", unresolved: "1.5 4" };
const CLASS_LABEL = { declared: "Declared", inferred: "Inferred", unresolved: "Unresolved" };

function layout(nodes, edges) {
  const ds = nodes.filter((n) => n.type === "dataset").sort((a, b) => a.label.localeCompare(b.label));
  const dsIndex = Object.fromEntries(ds.map((n, i) => [n.id, i]));
  const roots = nodes.filter((n) => n.type !== "dataset").map((n) => {
    const idx = edges.filter((e) => e.target === n.id).map((e) => dsIndex[e.source]).filter((i) => i !== undefined);
    return { n, k: idx.length ? idx.reduce((a, b) => a + b, 0) / idx.length : 99 };
  }).sort((a, b) => a.k - b.k || a.n.label.localeCompare(b.n.label)).map((x) => x.n);
  const pos = {};
  ds.forEach((n, i) => { pos[n.id] = { x: 0, y: i * (roots.length > ds.length ? (roots.length * 42) / Math.max(ds.length, 1) : 64) }; });
  roots.forEach((n, i) => { pos[n.id] = { x: 440, y: i * 42 }; });
  return pos;
}

function Body() {
  const { analysisId, sources, isPaper } = useAnalysis();
  const { data, error, loading } = useApiData(() => api.provenance(analysisId), [analysisId]);
  const { fitView } = useReactFlow();

  const [show, setShow] = useState({ declared: true, inferred: true, unresolved: true });
  const [circularOnly, setCircularOnly] = useState(false);
  const [isoText, setIsoText] = useState("");
  const [iso, setIso] = useState(null);          // {address, datasets, roots} or {error}
  const [selNode, setSelNode] = useState(null);
  const [selEdge, setSelEdge] = useState(null);
  // an uploaded file's own provenance and THEMIS's bundled reference corpus are different subjects
  const [view, setView] = useState("uploaded");
  const showRef = !isPaper && view === "reference";
  const up = data?.uploaded_dataset;

  const graph = showRef ? data?.reference_corpus?.graph : data?.graph;
  const nodeById = useMemo(() => Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n])), [graph]);

  // visible edges = class filter AND circular-only AND isolated address
  const visibleEdges = useMemo(() => {
    if (!graph) return [];
    return graph.edges.filter((e) => {
      if (e.source === "claims") return false;
      const cls = edgeClass(e, nodeById);
      if (!show[cls]) return false;
      if (circularOnly && !e.shared_root) return false;
      if (iso && !iso.error) {
        const ds = e.source.slice("dataset:".length), rl = nodeById[e.target]?.label || "";
        if (!iso.datasets.includes(ds) || !iso.roots.some((r) => rootMatches(rl, r))) return false;
      }
      return true;
    });
  }, [graph, show, circularOnly, iso, nodeById]);

  const visibleNodes = useMemo(() => {
    if (!graph) return [];
    const ids = new Set(visibleEdges.flatMap((e) => [e.source, e.target]));
    return graph.nodes.filter((n) => ids.has(n.id));
  }, [graph, visibleEdges]);

  const positions = useMemo(() => layout(visibleNodes, visibleEdges), [visibleNodes, visibleEdges]);

  const focus = selNode; // highlight the neighbourhood of the clicked node
  const touches = (e) => !focus || e.source === focus || e.target === focus;

  const rfNodes = visibleNodes.map((n) => {
    const isDs = n.type === "dataset";
    const unres = n.type === "root_unresolved";
    const dimmed = focus && n.id !== focus && !visibleEdges.some((e) => touches(e) && (e.source === n.id || e.target === n.id));
    return {
      id: n.id, position: positions[n.id], data: { label: `${n.label}${unres ? " · unresolved" : n.shared ? ` · shared by ${n.datasets.length}` : ""}` },
      draggable: true, selectable: true,
      sourcePosition: "right", targetPosition: "left",
      style: {
        width: isDs ? 190 : 310, whiteSpace: "nowrap", fontFamily: "var(--mn)", fontSize: 11, padding: "7px 10px", borderRadius: 2, textAlign: "left",
        background: isDs ? "var(--sfa)" : unres ? "var(--bg)" : n.shared ? "var(--acs)" : "var(--sfa)",
        color: unres ? "var(--mut)" : "var(--ink)",
        border: `${n.id === selNode ? 2 : 1.4}px ${unres ? "dashed" : "solid"} ${n.id === selNode ? "var(--ac)" : isDs ? "var(--rl)" : unres ? "var(--nt2)" : n.shared ? "var(--ac)" : "var(--nt)"}`,
        opacity: dimmed ? 0.35 : 1,
      },
    };
  });
  const rfEdges = visibleEdges.map((e, i) => {
    const cls = edgeClass(e, nodeById);
    return {
      id: `${e.source}>${e.target}>${i}`, source: e.source, target: e.target, type: "smoothstep", interactionWidth: 20,
      label: e.evidence ? "evidence ▸" : undefined, labelStyle: { fontFamily: "var(--mn)", fontSize: 9.5, fill: "var(--oc)" },
      labelBgStyle: { fill: "var(--sf)" }, labelBgPadding: [4, 2], labelBgBorderRadius: 3,
      data: { edge: e, cls },
      style: { stroke: STROKE[cls], strokeWidth: selEdge === e ? 2.4 : 1.4, strokeDasharray: DASH[cls], opacity: touches(e) ? 1 : 0.15 },
    };
  });

  // refit whenever the visible set changes
  useEffect(() => { const t = setTimeout(() => fitView({ padding: 0.12, duration: 250 }), 60); return () => clearTimeout(t); },
    [fitView, visibleNodes.length, visibleEdges.length]);

  const isolate = async () => {
    const a = isoText.trim();
    if (!a) { setIso(null); return; }
    try {
      const r = await api.address(analysisId, a);
      if (!r.found) { setIso({ error: "No claim in this analysis names that address." }); return; }
      setIso({ address: a, datasets: r.datasets, roots: [...new Set((r.claims || [...(r.target_claims || []), ...(r.reference_claims || [])]).map((c) => c.root))] });
    } catch (e) { setIso({ error: e.message }); }
  };

  const ev = data?.evidence;
  return (
    <div>
      <PageHead kicker={isPaper ? "Provenance Explorer · THEMIS Reference Corpus" : showRef ? "Provenance Explorer · THEMIS Reference Corpus" : "Provenance Explorer · uploaded dataset"}
        title="Datasets → declared sources → roots"
        lead={showRef || isPaper
          ? "Built from the source registry. No edge is drawn as fact beyond what the registry states; inferred and unresolved edges differ by line style, not colour alone. Pan, zoom, click a node to trace it, click an edge for its evidence."
          : "Only what your file itself declares, and what was measured between its addresses and the reference corpus, is shown as its provenance. A source THEMIS has never seen has no provenance rule, so its root is unresolved: it is never borrowed from a bundled source."} />
      {!isPaper && data && (
        <div className="controls" style={{ marginBottom: 14 }}>
          <RadioRow name="Provenance subject" value={view} onChange={setView}
            options={[{ key: "uploaded", label: "Uploaded dataset provenance" }, { key: "reference", label: "THEMIS Reference Corpus" }]} />
        </div>
      )}
      {showRef && (
        <div className="callout" style={{ marginBottom: 18 }}><div className="co-body">
          <span className="eyebrow" style={{ display: "block", marginBottom: 7, color: "var(--ink)" }}>Not your file</span>
          {data.reference_corpus.note}{data.reference_corpus.scope ? ` Loaded scope: ${data.reference_corpus.scope.toLowerCase().replace("_", " ")}.` : ""}
        </div></div>
      )}
      {!isPaper && !showRef && up && <UploadedProvenance u={up} />}
      {loading && <Loading>Loading provenance graph…</Loading>}
      {error && <ErrorBox title="Could not load provenance">{error}</ErrorBox>}

      {graph && (
        <div className="grid-aside">
          <div className="grow">
            <div className="graphbox">
              <div className="graphbar">
                <span className="fnt">{visibleNodes.filter((n) => n.type === "dataset").length} datasets · {visibleNodes.filter((n) => n.type !== "dataset").length} roots · {visibleEdges.length} edges shown</span>
                <button type="button" className="chip-btn plain" style={{ marginLeft: "auto" }} onClick={() => fitView({ padding: 0.12, duration: 250 })}>Fit graph</button>
              </div>
              <div style={{ height: 680 }}>
                {visibleEdges.length === 0
                  ? <div className="empty" style={{ margin: 30, maxWidth: "none" }}><div className="eyebrow">Nothing to draw</div><p>No edge passes the current filters.</p></div>
                  : <ReactFlow nodes={rfNodes} edges={rfEdges} fitView minZoom={0.3} maxZoom={2} nodesConnectable={false} proOptions={{ hideAttribution: true }}
                    onNodeClick={(_, n) => setSelNode((s) => (s === n.id ? null : n.id))}
                    onEdgeClick={(_, e) => setSelEdge(e.data.edge)}
                    onPaneClick={() => setSelNode(null)}>
                    <Background gap={22} size={1} />
                    <Controls showInteractive={false} />
                  </ReactFlow>}
              </div>
            </div>
          </div>

          <aside>
            <div className="panel pad">
              <div className="form-label">View</div>
              <div className="legend-list" style={{ gap: 7 }}>
                {["declared", "inferred", "unresolved"].map((c) => (
                  <label key={c} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={show[c]} onChange={() => setShow({ ...show, [c]: !show[c] })} />
                    <svg width="28" height="8" aria-hidden="true"><line x1="0" y1="4" x2="28" y2="4" stroke={STROKE[c]} strokeWidth="1.5" strokeDasharray={DASH[c]} /></svg>
                    {CLASS_LABEL[c]}
                  </label>
                ))}
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                  <input type="checkbox" checked={circularOnly} onChange={() => setCircularOnly(!circularOnly)} />
                  Circular only <span className="fnt">(roots named by ≥2 datasets)</span>
                </label>
              </div>
              <div className="form-label" style={{ marginTop: 14 }}>Isolate an address</div>
              <form className="field" onSubmit={(e) => { e.preventDefault(); isolate(); }}>
                <input type="text" value={isoText} placeholder="address" spellCheck={false} onChange={(e) => setIsoText(e.target.value)} aria-label="Isolate address" />
              </form>
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button type="button" className="btn small" onClick={isolate}>Isolate</button>
                {iso && <button type="button" className="btn small secondary" onClick={() => { setIso(null); setIsoText(""); }}>Clear</button>}
              </div>
              {iso?.error && <div className="hot" style={{ fontSize: 11.5, marginTop: 6 }}>{iso.error}</div>}
              {iso && !iso.error && <div className="fnt" style={{ fontSize: 11.5, marginTop: 6 }}>Showing only the datasets and roots named for <span className="mono">{iso.address.slice(0, 10)}…</span>. Roots outside the registry graph are not drawn.</div>}
            </div>

            <div className="panel pad">
              <div className="form-label">Legend</div>
              <div className="legend-list">
                {["declared", "inferred", "unresolved"].map((c) => (
                  <div key={c}><svg width="28" height="8" aria-hidden="true"><line x1="0" y1="4" x2="28" y2="4" stroke={STROKE[c]} strokeWidth="1.5" strokeDasharray={DASH[c]} /></svg>
                    <span>{CLASS_LABEL[c]} <span className="mut">{c === "declared" ? "— registry states the root" : c === "inferred" ? "— decoded or matched from a field" : "— no rule, or root unidentified"}</span></span></div>
                ))}
                <div style={{ height: 1, background: "var(--rls)" }} />
                <div><svg width="28" height="14" aria-hidden="true"><rect x="0" y="1" width="28" height="12" fill="var(--sfa)" stroke="var(--rl)" /></svg><span>Dataset</span></div>
                <div><svg width="28" height="14" aria-hidden="true"><rect x="0" y="1" width="28" height="12" fill="var(--sfa)" stroke="var(--nt)" strokeWidth="1.4" /></svg><span>Resolved root</span></div>
                <div><svg width="28" height="14" aria-hidden="true"><rect x="0" y="1" width="28" height="12" fill="var(--acs)" stroke="var(--ac)" strokeWidth="1.4" /></svg><span>Root named by ≥2 datasets</span></div>
                <div><svg width="28" height="14" aria-hidden="true"><rect x="0" y="1" width="28" height="12" fill="var(--bg)" stroke="var(--nt2)" strokeDasharray="3 3" /></svg><span>Unresolved root</span></div>
              </div>
            </div>

            <NodePanel node={selNode ? nodeById[selNode] : null} sources={sources} onClear={() => setSelNode(null)} edges={graph.edges} nodeById={nodeById} />
          </aside>
        </div>
      )}

      {ev && <PaperEvidence ev={ev} />}
      {!isPaper && !showRef && data && <Inheritance items={data.inheritance_candidates} />}
      {selEdge && <EdgeDrawer edge={selEdge} nodeById={nodeById} cls={edgeClass(selEdge, nodeById)} onClose={() => setSelEdge(null)} />}
    </div>
  );
}

// ------------------------------------------------------------ node panel
function NodePanel({ node, sources, onClear, edges, nodeById }) {
  if (!node) return (
    <div className="panel pad"><div className="form-label">Selection</div>
      <p className="mut" style={{ margin: 0, fontSize: 12, lineHeight: 1.6 }}>Click a dataset or root to trace it. The rest of the graph dims.</p></div>);
  const isDs = node.type === "dataset";
  const sid = isDs ? node.id.slice("dataset:".length) : null;
  const s = isDs ? sources?.[sid] : null;
  const roots = isDs ? edges.filter((e) => e.source === node.id).map((e) => nodeById[e.target]) : [];
  return (
    <div className="panel pad">
      <div className="form-label">{isDs ? "Dataset" : "Root"} <button type="button" className="x" style={{ float: "right" }} onClick={onClear} aria-label="Clear selection">×</button></div>
      <div className="mono" style={{ fontSize: 12.5, wordBreak: "break-all" }}>{node.label}</div>
      {isDs && s && <>
        <p className="section-note" style={{ margin: "8px 0 4px" }}>{s.citation}</p>
        <div className="kv" style={{ gridTemplateColumns: "84px 1fr" }}><span>points at</span><span>{roots.length} root{roots.length === 1 ? "" : "s"}</span></div>
      </>}
      {!isDs && <>
        <div className="kv" style={{ gridTemplateColumns: "84px 1fr" }}><span>status</span><span>{node.type === "root_unresolved" ? "unresolved" : "identified"}</span></div>
        <div className="kv" style={{ gridTemplateColumns: "84px 1fr" }}><span>named by</span><span>{node.datasets?.join(", ") || "—"}</span></div>
        {node.owner && <div className="kv" style={{ gridTemplateColumns: "84px 1fr" }}><span>owner</span><span>{node.owner}</span></div>}
        {node.shared && <p className="section-note" style={{ margin: "8px 0 0" }}>{node.datasets.length} datasets point at this root, so agreement between them is one observation, not {node.datasets.length}.</p>}
      </>}
    </div>
  );
}

// ---------------------------------------------------------- edge drawer
function EdgeDrawer({ edge, nodeById, cls, onClose }) {
  const ev = edge.evidence || {};
  const src = nodeById[edge.source]?.label, dst = nodeById[edge.target]?.label;
  const tagTone = { declared: "ok", inferred: "flag", unresolved: "" }[cls];
  return (
    <Drawer title="Relationship evidence" onClose={onClose}
      foot="Served by GET /api/analysis/{id}/provenance: graph edges carry independence.field_decodes, containment_top, naming_residues and notable_root_propagation where the engine measured them.">
      <div className="mono" style={{ fontSize: 13, lineHeight: 1.7 }}>{src}</div>
      <div className="mut" style={{ fontSize: 14, margin: "2px 0" }}>↓</div>
      <div className="mono" style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 14 }}>{dst}</div>
      <Tag tone={tagTone}>{CLASS_LABEL[cls]}{ev.decode ? " · field decode" : ""}{ev.decode?.clean_split ? ", clean split" : ""}</Tag>
      <div className="form-label" style={{ margin: "18px 0 10px" }}>Evidence</div>

      {ev.containment?.map((c, i) => (
        <div key={i} className="evid"><h4>Directional containment</h4>
          <div className="fig">{fmt(c.n)} addresses · {pct(c.share_of_a)} of <span>{c.source}</span></div>
          <p>Share of <span className="mono">{c.source}</span>’s addresses that sit inside <span className="mono">{c.inside}</span>. Containment is directional: the reverse share is a different number.</p></div>
      ))}
      {ev.decode && (
        <div className="evid"><h4>Field decode</h4>
          <div className="fig">{ev.decode.dataset}.{ev.decode.field} → {ev.decode.candidate}</div>
          <p>
            {ev.decode.clean_split ? "Clean split: every group either sits fully inside the candidate or fully outside it." : "Not a clean split."}{" "}
            Inherited groups: <span className="mono">{ev.decode.inherited_groups?.join(", ") || "none"}</span>. Independent groups: <span className="mono">{ev.decode.independent_groups?.join(", ") || "none"}</span>.
            {ev.decode.inconclusive_groups?.length > 0 && <> Inconclusive: <span className="mono">{ev.decode.inconclusive_groups.join(", ")}</span>.</>}
            {" "}{fmt(ev.decode.inherited_addresses)} addresses classed inherited.
          </p></div>
      )}
      {ev.naming_residue && (
        <div className="evid"><h4>Naming residue</h4>
          <div className="fig">{fmt(ev.naming_residue.count)} records name this root · {fmt(ev.naming_residue.attributed)} / {fmt(ev.naming_residue.total)} records name any known study ({pct(ev.naming_residue.share)})</div>
          <p>The <span className="mono">{ev.naming_residue.field}</span> field names its upstream study: {Object.entries(ev.naming_residue.by_root).map(([r, n]) => `${r} ${fmt(n)}`).join(" · ")}.</p></div>
      )}
      {ev.propagation && (
        <div className="evid"><h4>Measured propagation</h4>
          <div className="fig">{ev.propagation.into_dataset === null || ev.propagation.into_dataset === undefined ? "not measured for this dataset" : `${fmt(ev.propagation.into_dataset)} / ${fmt(ev.propagation.size)} addresses`}</div>
          <p>{ev.propagation.label} holds {fmt(ev.propagation.size)} addresses; this is how many of them appear in this dataset.</p></div>
      )}
      {!edge.evidence && (
        <div className="evid"><h4>{cls === "declared" ? "Stated by the registry" : cls === "inferred" ? "Matched by a registry rule" : "No identified root"}</h4>
          <p>{cls === "declared" ? "The source registry states this root. No further measurement is attached to this edge."
            : cls === "inferred" ? "The registry maps a field pattern to this root. THEMIS has measured no decode, containment or naming residue for this specific edge."
              : "The registry has no rule that identifies this root, so it is never counted as independent of any other root."}</p></div>
      )}
      <div className="evid" style={{ borderColor: "var(--ink)", marginTop: 16 }}><h4 className="eyebrow" style={{ fontWeight: 500 }}>Limitations</h4>
        <p style={{ color: "var(--ink)" }}>Containment and a clean split demonstrate record overlap and a consistent encoding. They do not by themselves prove copying. THEMIS records such a link as inferred and never upgrades it to declared.</p></div>
    </Drawer>
  );
}

// ------------------------------------------------- paper-mode evidence tables
function PaperEvidence({ ev }) {
  const cont = ev.containment_top || [];
  const reverse = (c) => cont.find((x) => x.source === c.inside && x.inside === c.source);
  return (
    <>
      <Section title="Directional containment" sec="5.2" meta={`top ${cont.length} pairs`}
        note="The share of the first source contained in the second. The relation is deliberately asymmetric: one percentage alone would misstate it. Only the strongest pairs are reported by the engine.">
        <div className="tablewrap"><table>
          <thead><tr><th>Source</th><th>Contained in</th><th className="num">Addresses shared</th><th className="num">Share of source</th><th className="num">Reverse share</th></tr></thead>
          <tbody>{cont.map((c) => { const r = reverse(c); return (
            <tr key={`${c.source}|${c.inside}`}><td className="mono">{c.source}</td><td className="mono">{c.inside}</td><td className="num">{fmt(c.n)}</td>
              <td className="num">{pct(c.share_of_a)}</td><td className="num mut">{r ? pct(r.share_of_a) : `not in top ${cont.length}`}</td></tr>); })}</tbody>
        </table></div>
        <p className="section-note" style={{ marginTop: 10 }}>High overlap is not proof of copying. It is the observation that prompts the field decode below.</p>
      </Section>

      {ev.field_decodes?.length > 0 && (
        <Section title="Field decodes" sec="5.2" meta={`${ev.field_decodes.length} decoded field${ev.field_decodes.length === 1 ? "" : "s"}`}>
          {ev.field_decodes.map((d) => (
            <div key={`${d.dataset}.${d.field}`} className="panel pad" style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, marginBottom: 8 }}><span className="mono">{d.dataset}.{d.field}</span> decoded against <span className="mono">{d.candidate}</span>
                {" "}<Status tone={d.clean_split ? "ok" : "flag"}>{d.clean_split ? "clean split" : "not a clean split"}</Status></div>
              <div className="tablewrap"><table>
                <thead><tr><th>Group</th><th className="num">Addresses</th><th className="num">Inside {d.candidate}</th><th>Verdict</th></tr></thead>
                <tbody>{Object.entries(d.groups).map(([g, v]) => (
                  <tr key={g}><td className="mono">{g}</td><td className="num">{fmt(v.n)}</td><td className="num">{pct(v.share_in_candidate)}</td>
                    <td><Status tone={v.verdict === "inherited" ? "hot" : v.verdict === "independent" ? "ok" : "flag"}>{v.verdict}</Status></td></tr>))}</tbody>
              </table></div>
              <p className="section-note" style={{ margin: "10px 0 0" }}>{fmt(d.inherited_addresses)} addresses classed inherited. A group that sits fully inside the candidate is treated as restating it; a group fully outside is treated as independent of it.</p>
            </div>))}
        </Section>
      )}

      {ev.naming_residues?.length > 0 && (
        <Section title="Naming residue" meta="upstream studies named in label text">
          {ev.naming_residues.map((r) => (
            <div key={`${r.dataset}.${r.field}`} className="panel pad">
              <div style={{ fontSize: 13 }}><span className="mono">{r.dataset}.{r.field}</span>: {fmt(r.attributed)} / {fmt(r.total)} records ({pct(r.share)}) name a known upstream study.</div>
              <div className="fnt" style={{ marginTop: 6, fontFamily: "var(--mn)", fontSize: 11.5 }}>{Object.entries(r.by_root).map(([k, n]) => `${k} ${fmt(n)}`).join(" · ")}</div>
            </div>))}
        </Section>
      )}

      {ev.notable_root_propagation?.length > 0 && (
        <Section title="Root propagation" sec="5.2" meta="measured reach into each dataset">
          {ev.notable_root_propagation.map((p) => (
            <div key={p.root} className="panel pad">
              <p className="section-note" style={{ margin: "0 0 10px" }}>{p.label} holds {fmt(p.size)} addresses. Measured reach into each dataset:</p>
              <div className="barrows" style={{ gridTemplateColumns: "180px 1fr 130px" }}>
                {Object.entries(p.propagation).sort((a, b) => b[1] - a[1]).map(([ds, n]) => (
                  <div key={ds} className="barrow"><span className="bar-label mono">{ds}</span>
                    <div className="bar-track"><i style={{ width: `${(n / p.size) * 100}%`, background: "var(--ac)" }} /></div>
                    <span className="bar-n">{fmt(n)} / {fmt(p.size)}</span></div>))}
              </div>
            </div>))}
        </Section>
      )}
    </>
  );
}

function UploadedProvenance({ u }) {
  const st = u.state;
  return (
    <Section title="Provenance of this file’s claims" meta={`${fmt(u.n_claims)} claims`}>
      <div className="panel pad">
        {st && st.state !== "computed"
          ? <p style={{ margin: 0 }}><strong>{st.state === "insufficient_data" ? "Insufficient data — " : "Not applicable — "}{st.reason}.</strong></p>
          : <p style={{ margin: 0 }}>{st?.reason}. {fmt(u.n_distinct_declared_sources)} distinct declared source value{u.n_distinct_declared_sources === 1 ? "" : "s"}.</p>}
        {u.declared_sources.length > 0 && (
          <div className="tablewrap" style={{ marginTop: 12 }}><table>
            <thead><tr><th>Declared source (as written in the file)</th><th className="num">Claims</th></tr></thead>
            <tbody>{u.declared_sources.map((d) => <tr key={d.value}><td className="mono small" style={{ wordBreak: "break-all" }}>{d.value}</td><td className="num">{fmt(d.n_claims)}</td></tr>)}</tbody>
          </table></div>
        )}
        <div className="tablewrap" style={{ marginTop: 12 }}><table>
          <thead><tr><th>Provenance root</th><th>Status</th><th className="num">Claims</th></tr></thead>
          <tbody>{u.roots.map((r) => <tr key={r.root}><td className="mono small">{r.root}</td><td><Status tone={r.resolved ? "ok" : "mut"}>{r.resolved ? "identified" : "unresolved"}</Status></td><td className="num">{fmt(r.n_claims)}</td></tr>)}</tbody>
        </table></div>
      </div>
    </Section>
  );
}

function Inheritance({ items }) {
  return (
    <Section title="Inheritance candidates" meta="target dataset vs reference corpus"
      note="Directional containment of your addresses in each reference source, plus reference sources named in your own declared-source text. A candidate is a signal, never a declaration of copying.">
      {!items?.length
        ? <div className="panel pad mut">No reference source contains enough of this dataset’s addresses, and none is named in its declared-source text, to raise an inheritance candidate.</div>
        : <div className="tablewrap"><table>
          <thead><tr><th>Reference source</th><th className="num">Shared addresses</th><th className="num">Share of your addresses</th><th>Status</th><th>Evidence</th></tr></thead>
          <tbody>{items.map((c) => (
            <tr key={c.source}><td className="mono">{c.source}</td><td className="num">{fmt(c.n_shared_addresses)}</td><td className="num">{pct(c.share_of_target_in_reference)}</td>
              <td><Status tone="flag">{c.status.toLowerCase()}</Status></td><td className="small">{c.evidence.join(" · ")}</td></tr>))}</tbody>
        </table></div>}
    </Section>
  );
}
