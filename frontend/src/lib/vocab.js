// Display vocabulary only: how backend enum values are worded and toned, and
// where a metric drills down to. No numbers, no analytics.

// Agreement outcome (as the backend names it) -> label, tone, drill-down target.
// exact / incomparable open the filtered Claims table; the three conflict-type
// outcomes open the Conflict Explorer for that kind.
export const OUTCOMES = [
  { key: "exact", label: "Exact agreement", short: "agree", tone: "ok", fill: "var(--tl)",
    to: (o) => `/claims?outcome=exact${o}` },
  { key: "hierarchical refinement", label: "Hierarchical refinement", short: "refinement", tone: "flag", fill: "var(--oc)",
    to: (o) => `/conflicts?kind=hierarchical${o}` },
  { key: "entity-type conflict", label: "Entity-type conflict", short: "entity-type", tone: "hot", fill: "var(--ac)",
    to: (o) => `/conflicts?kind=entity${o}` },
  { key: "licit/illicit conflict", label: "Licit / illicit conflict", short: "licit/illicit", tone: "hot", fill: "var(--ac)",
    to: (o) => `/conflicts?kind=polarity${o}` },
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

// ---- metric population wording. The backend (themis/overview.py) labels every metric with
// {unit, population, quality}; these only say it in words. No numbers, no analytics.
const BASIS = { live: "LIVE FULL CORPUS", manifest: "FULL-CORPUS MANIFEST" };
const POP_SUFFIX = { normalized_full_corpus: "NORMALIZED ADDRESSES", raw_address_keys: "RAW ADDRESS KEYS", claims_full_corpus: "CLAIM BASED" };
const POP_NOUN = { normalized_full_corpus: "normalized addresses", raw_address_keys: "raw address keys", claims_full_corpus: "claims" };

// "LIVE FULL CORPUS · NORMALIZED ADDRESSES", "BUNDLED SAMPLE", "NOT AVAILABLE"
export function popTag(m) {
  if (m.quality === "unavailable") return "NOT AVAILABLE";
  if (m.population === "bundled_sample") return "BUNDLED SAMPLE";
  return `${BASIS[m.quality] || "UNVERIFIED"} · ${POP_SUFFIX[m.population]}`;
}
// what a metric's denominator counts, in words
export const popNoun = (m) => (m.population === "bundled_sample" ? `bundled-sample ${m.unit}` : POP_NOUN[m.population]);

// the records table a drill-down lands on, keyed like a metric's population
export const scopePopulation = (scope) => (scope === "FULL_CORPUS" ? "normalized_full_corpus" : scope === "BUNDLED_SAMPLE" ? "bundled_sample" : null);
export const SCOPE_LABEL = { FULL_CORPUS: "Full corpus", BUNDLED_SAMPLE: "Bundled sample" };
// Overview introduction, by the corpus the analysis actually loaded
export const SCOPE_INTRO = {
  FULL_CORPUS: "Computed from the reconstructed seven-source research corpus used for the verified paper reproduction.",
  BUNDLED_SAMPLE: "Sample-backed view. Corpus-wide values are identified separately; full paper reproduction requires the external research corpus.",
};
