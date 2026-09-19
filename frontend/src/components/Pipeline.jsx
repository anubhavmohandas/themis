// Renders a backend job's stage list as-is: status, label, detail and timing
// all come from GET /api/jobs/{id}. Nothing is animated beyond a pulsing
// marker on the stage the backend reports as running.
const MARK = { pending: "·", running: "▸", complete: "✓", failed: "✕" };

export default function Pipeline({ job, title = "Pipeline" }) {
  if (!job) return null;
  const stages = job.stages || [];
  return (
    <div className="panel">
      <div className="panel-head">
        {title}
        <span style={{ marginLeft: "auto", color: "var(--mut)", textTransform: "none", letterSpacing: 0 }}>
          {job.status === "running" ? "running" : job.status}
          {job.elapsed_s !== undefined && job.elapsed_s !== null ? ` · ${job.elapsed_s.toFixed(1)} s` : ""}
        </span>
      </div>
      <div className="panel-body">
        {stages.length === 0 && <div className="loading">Starting…</div>}
        <div className="steps" aria-live="polite">
          {stages.map((s) => (
            <div key={s.id} className={`step ${s.status}`}>
              <span className="mk">{MARK[s.status] || "·"}</span>
              <div>
                <div>{s.label}</div>
                {s.detail && <div className="d">{s.detail}</div>}
              </div>
              <span className="t">{s.elapsed_s !== null && s.elapsed_s !== undefined ? `${s.elapsed_s.toFixed(2)} s` : s.status === "running" ? "running" : ""}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
