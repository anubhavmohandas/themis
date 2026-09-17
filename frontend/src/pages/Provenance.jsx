import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import "reactflow/dist/style.css";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import StatusBadge from "../components/StatusBadge.jsx";

const KIND_COLOR = { DECLARED: "#2c6350", INFERRED: "#8a5e12", UNKNOWN: "#8c2f1f" };

function layout(graph) {
  const datasets = graph.nodes.filter((n) => n.type === "dataset");
  const roots = graph.nodes.filter((n) => n.type === "root" || n.type === "root_unresolved");
  const claims = graph.nodes.filter((n) => n.type === "claims");

  const nodes = [];
  claims.forEach((n) => nodes.push({
    id: n.id, position: { x: 0, y: (datasets.length * 78) / 2 - 20 },
    data: { label: n.label }, style: baseStyle("#1f4e79", "#ffffff"),
  }));
  datasets.forEach((n, i) => nodes.push({
    id: n.id, position: { x: 300, y: i * 78 },
    data: { label: n.label }, style: baseStyle("#e3ecf5", "#14181e"),
  }));
  roots.forEach((n, i) => nodes.push({
    id: n.id, position: { x: 660, y: i * 46 },
    data: { label: n.label },
    style: baseStyle(n.type === "root" ? "#e2efe9" : "#f6e7e3", "#14181e"),
  }));

  const edges = graph.edges.map((e, i) => ({
    id: `e${i}`, source: e.source, target: e.target,
    label: e.kind, labelStyle: { fontSize: 9, fill: KIND_COLOR[e.kind] },
    style: { stroke: KIND_COLOR[e.kind], strokeWidth: 1.4, strokeDasharray: e.kind === "DECLARED" ? undefined : "4 3" },
    markerEnd: { type: MarkerType.ArrowClosed, color: KIND_COLOR[e.kind], width: 14, height: 14 },
  }));

  return { nodes, edges };
}

function baseStyle(bg, color) {
  return {
    background: bg, color, border: "1px solid #dde1e7", borderRadius: 6,
    padding: "6px 10px", fontSize: 12, fontFamily: "IBM Plex Mono, monospace", width: 220,
  };
}

export default function ProvenanceExplorerPage() {
  const { data: graph, error, loading } = useApiData(() => api.graph(), []);
  const { data: sources } = useApiData(() => api.sources(), []);
  const [selected, setSelected] = useState(null);

  const flow = useMemo(() => (graph ? layout(graph) : null), [graph]);

  if (loading) return <p className="muted">Loading provenance graph…</p>;
  if (error) return <div className="callout warn">{error}</div>;
  if (!flow) return null;

  const selectedInfo = selected && graph
    ? {
        node: graph.nodes.find((n) => n.id === selected),
        incoming: graph.edges.filter((e) => e.target === selected),
        outgoing: graph.edges.filter((e) => e.source === selected),
      }
    : null;

  return (
    <>
      <div className="pageintro">
        <div className="kicker">Provenance Explorer</div>
        <h1>Claims → datasets → declared sources → roots</h1>
        <p className="lead">
          Built directly from the source registry — no edge is shown as fact beyond what config
          states. Click a node for its evidence.
        </p>
      </div>

      <div className="section" style={{ display: "flex", gap: 16 }}>
        <div className="card" style={{ flex: 1, height: 560, padding: 0 }}>
          <ReactFlow
            nodes={flow.nodes}
            edges={flow.edges}
            onNodeClick={(_, n) => setSelected(n.id)}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#dde1e7" gap={20} />
            <Controls />
          </ReactFlow>
        </div>

        <div className="card" style={{ width: 300, flexShrink: 0 }}>
          <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 10 }}>
            Legend
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 18 }}>
            <StatusBadge label="DECLARED" /><span className="muted" style={{ fontSize: 12 }}>the source config states this root outright</span>
            <StatusBadge label="INFERRED" /><span className="muted" style={{ fontSize: 12 }}>decoded from an undocumented code, or a residue/fallback guess</span>
            <StatusBadge label="UNKNOWN" /><span className="muted" style={{ fontSize: 12 }}>no provenance rule configured for this source</span>
          </div>

          <div className="k" style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 10 }}>
            Selected node
          </div>
          {!selectedInfo ? (
            <p className="muted" style={{ fontSize: 13 }}>Click a dataset or root node.</p>
          ) : (
            <SelectedPanel info={selectedInfo} sources={sources} />
          )}
        </div>
      </div>
    </>
  );
}

function SelectedPanel({ info, sources }) {
  const { node, incoming } = info;
  const srcCfg = sources && node.type === "dataset" ? sources[node.id.replace("dataset:", "")] : null;
  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6, wordBreak: "break-word" }}>{node.label}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>type: {node.type.replace("_", " ")}</div>
      {srcCfg && (
        <table style={{ marginBottom: 10 }}>
          <tbody>
            <tr><td style={{ border: "none", color: "var(--muted)" }}>chain</td><td style={{ border: "none" }}>{srcCfg.chain}</td></tr>
            <tr><td style={{ border: "none", color: "var(--muted)" }}>mode</td><td style={{ border: "none" }}>{(srcCfg.provenance || {}).mode || "none"}</td></tr>
            <tr><td style={{ border: "none", color: "var(--muted)" }}>citation</td><td style={{ border: "none" }}>{srcCfg.citation}</td></tr>
          </tbody>
        </table>
      )}
      {node.type !== "dataset" && incoming.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>asserted by:</div>
          {incoming.map((e, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
              <span>{e.source.replace("dataset:", "").replace("claims", "(root cause)")}</span>
              <StatusBadge label={e.kind} />
            </div>
          ))}
        </>
      )}
    </div>
  );
}
