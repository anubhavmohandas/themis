const KIND_BY_LABEL = {
  exact: "ok", "hierarchical refinement": "ok",
  "entity-type conflict": "warn", "licit/illicit conflict": "warn", incomparable: "muted",
  circular: "warn", conflicting: "warn", stale: "flag", "currency-unknown": "muted",
  DECLARED: "ok", INFERRED: "flag", UNKNOWN: "muted",
  verified: "ok", derived: "flag", "unverified-report": "muted",
};

export default function StatusBadge({ label, kind }) {
  const cls = kind || KIND_BY_LABEL[label] || "muted";
  return <span className={`badge ${cls}`}>{label}</span>;
}
