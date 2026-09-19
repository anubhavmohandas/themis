// Display vocabulary only: how backend enum values are worded and toned, and
// where a metric drills down to. No numbers, no analytics.

// Agreement outcome (as the backend names it) -> label, tone, drill-down target.
// exact / incomparable open the filtered Claims table; the three conflict-type
// outcomes open the Conflict Explorer for that kind.
export const OUTCOMES = [
  { key: "exact", label: "Exact agreement", short: "agree", tone: "ok", fill: "var(--tl)",
    to: (o) => `/claims?outcome=exact${o}` },
  { key: "hierarchical refinement", label: "Hierarchical refinement", short: "refinement", tone: "flag", fill: "var(--oc)",
    to: () => "/conflicts?kind=hierarchical" },
  { key: "entity-type conflict", label: "Entity-type conflict", short: "entity-type", tone: "hot", fill: "var(--ac)",
    to: () => "/conflicts?kind=entity" },
  { key: "licit/illicit conflict", label: "Licit / illicit conflict", short: "licit/illicit", tone: "hot", fill: "var(--ac)",
    to: () => "/conflicts?kind=polarity" },
  { key: "incomparable", label: "Incomparable", short: "incomparable", tone: "mut", fill: null, hatch: true,
    to: (o) => `/claims?outcome=incomparable${o}` },
];
export const outcomeOf = (k) => OUTCOMES.find((o) => o.key === k);

export const CONFLICT_KINDS = [
  { key: "", label: "All" },
  { key: "polarity", label: "Licit / illicit" },
  { key: "entity", label: "Entity type" },
  { key: "hierarchical", label: "Hierarchical" },
  { key: "incomparable", label: "Incomparable" },
];

export const RELATIONSHIPS = [
  { key: "", label: "Any" },
  { key: "distinct_roots", label: "Distinct roots" },
  { key: "shared_root", label: "Shared root" },
  { key: "unresolved", label: "Unresolved" },
];
export const RELATIONSHIP_TEXT = {
  distinct_roots: ["Distinct roots", "Every claim traces to a different identified root."],
  shared_root: ["Shared root", "At least two claims trace to the same root: the agreement is not independent."],
  unresolved: ["Unresolved", "At least one claim has no identified root, so independence cannot be confirmed."],
};

// Claim-level provenance status
export const PROVENANCE = {
  resolved: { label: "resolved", tone: "ok" },
  inherited: { label: "inherited", tone: "flag" },
  unresolved: { label: "unresolved", tone: "hot" },
};

export const TIER = {
  verified: { label: "verified", tone: "ok" },
  derived: { label: "derived", tone: "flag" },
  "unverified-report": { label: "unverified report", tone: "mut" },
  unknown: { label: "unknown", tone: "mut" },
};

export const TIER_OPTIONS = [
  ["", "any"], ["verified", "verified"], ["derived", "derived"],
  ["unverified-report", "unverified report"], ["unknown", "unknown"],
];
export const CURRENCY_OPTIONS = [
  ["", "any"], ["current", "current"], ["stale", "stale"], ["currency-unknown", "currency unknown"],
];
export const PROVENANCE_OPTIONS = [
  ["", "any"], ["resolved", "resolved"], ["inherited", "inherited"], ["unresolved", "unresolved"],
];
// Agreement filter on Claims: each choice maps to the query params the backend understands.
export const AGREEMENT_OPTIONS = [
  ["", "any"],
  ["comparable", "multi-dataset addresses"],
  ["single-source", "single-source addresses"],
  ["exact", "exact agreement"],
  ["hierarchical refinement", "hierarchical refinement"],
  ["entity-type conflict", "entity-type conflict"],
  ["licit/illicit conflict", "licit / illicit conflict"],
  ["incomparable", "incomparable"],
];

// Paper section references. Shown in paper-reproduction mode only, and only as a
// section number plus topic title - never a figure, so they cannot drift from
// the numbers the backend computes.
export const PAPER_SECTIONS = {
  "5.1": "Comparability",
  "5.2": "Much of the agreement is circular",
  "5.3": "Conclusion drift",
  "5.4": "Threats to validity",
};

export const ROOT_KIND_TEXT = {
  DECLARED: "declared",
  INFERRED: "inferred",
  UNKNOWN: "unresolved",
};
