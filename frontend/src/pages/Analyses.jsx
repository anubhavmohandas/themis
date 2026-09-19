import { useNavigate } from "react-router-dom";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { dateTime, fmt, shortId } from "../lib/format.js";
import { Empty, PageHead } from "../components/ui.jsx";
import { Link } from "react-router-dom";

export default function AnalysesPage() {
  const { analyses, analysisId, activate, refreshAnalyses } = useAnalysis();
  const nav = useNavigate();
  return (
    <div>
      <PageHead kicker="Workspace" title="Recent analyses"
        lead="Every analysis lives in this session’s workspace under its own id. Open one to make it the active analysis: every page then reads from it. Analyses are held in memory and are cleared when the server restarts." />
      <div className="controls"><button type="button" className="btn small secondary" onClick={refreshAnalyses}>Refresh</button></div>
      {analyses.length === 0
        ? <Empty eyebrow="No analyses yet" action={<Link className="btn" to="/">New analysis</Link>}>Upload a dataset or reproduce the paper to create one.</Empty>
        : <div className="tablewrap"><table>
          <thead><tr><th>Analysis</th><th>Mode</th><th>Id</th><th className="num">Claims</th><th>Run</th><th /></tr></thead>
          <tbody>{[...analyses].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((a) => (
            <tr key={a.analysis_id}>
              <td>{a.dataset_name}{a.analysis_id === analysisId && <span className="tag ok" style={{ marginLeft: 8 }}>active</span>}</td>
              <td>{a.mode === "PAPER_REPRODUCTION" ? "Paper reproduction" : "Uploaded dataset"}</td>
              <td className="mono">{shortId(a.analysis_id)}</td>
              <td className="num">{fmt(a.n_claims)}</td>
              <td className="mono small">{dateTime(a.created_at)}</td>
              <td><button type="button" className="btn small secondary" onClick={() => { activate(a.analysis_id, a); nav("/overview"); }}>Open</button></td>
            </tr>))}</tbody>
        </table></div>}
    </div>
  );
}
