import Tooltip from "./Tooltip.jsx";

function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (!Number.isInteger(v)) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return v.toLocaleString();
  }
  return String(v);
}

export default function MetricTile({ label, value, help, detail }) {
  return (
    <div className="tile">
      <div className="k">
        {help ? <Tooltip text={help}><span>{label}</span></Tooltip> : <span>{label}</span>}
      </div>
      <div className="v">{fmt(value)}</div>
      {detail ? <div className="d">{detail}</div> : null}
    </div>
  );
}
