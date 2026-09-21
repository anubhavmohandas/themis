// Thin fetch wrappers around the FastAPI backend (themis/api.py). No analysis
// logic lives here or anywhere in the UI: the backend computes every figure,
// filter, coverage number and pipeline stage; React sends settings and renders
// the response. Every page-facing call is scoped by an analysisId - there is
// no endpoint that silently reads a global corpus.

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:5001";

async function parse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : body.error;
    const err = new Error(detail || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
const getJSON = (path) => fetch(`${BASE}${path}`, { cache: "no-store" }).then(parse);
const postForm = (path, form) => fetch(`${BASE}${path}`, { method: "POST", body: form }).then(parse);
const postEmpty = (path) => fetch(`${BASE}${path}`, { method: "POST" }).then(parse);

// undefined / null / "" params are dropped, so callers can pass filter state as-is.
const qs = (params = {}) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();

function analysisForm({ file, sourceId, useReference, semantics, chain, confirmed }) {
  const form = new FormData();
  form.append("file", file);
  form.append("source_id", sourceId || "uploaded_dataset");
  form.append("use_reference", useReference ? "true" : "false");
  if (semantics && Object.keys(semantics).length) form.append("semantics", JSON.stringify(semantics));
  if (chain) form.append("chain", chain);
  form.append("confirmed", confirmed ? "true" : "false");
  return form;
}

export const api = {
  base: BASE,
  health: () => getJSON("/api/health"),
  sources: () => getJSON("/api/sources"),
  taxonomy: () => getJSON("/api/taxonomy"),

  // Pre-flight: what each column means, the chain, and whether analysis may run. `semantics` is the
  // user's {column: semantic field} corrections; the server re-validates them, it never trusts them.
  preflight: (file, { semantics, chain, confirmed } = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (semantics && Object.keys(semantics).length) form.append("semantics", JSON.stringify(semantics));
    if (chain) form.append("chain", chain);
    form.append("confirmed", confirmed ? "true" : "false");
    return postForm("/api/preflight", form);
  },
  sqliteTables: (db) => getJSON(`/api/sqlite/tables?${qs({ db })}`),
  sqlitePreflight: ({ db, table, semantics, chain, confirmed }) => {
    const form = new FormData();
    form.append("db", db); form.append("table", table);
    if (semantics && Object.keys(semantics).length) form.append("semantics", JSON.stringify(semantics));
    if (chain) form.append("chain", chain);
    form.append("confirmed", confirmed ? "true" : "false");
    return postForm("/api/sqlite/preflight", form);
  },

  // Background jobs: start returns {job_id}; poll job(id) for real stage state.
  startAnalysisJob: (args) => postForm("/api/jobs/analysis", analysisForm(args)),
  startPaperJob: () => postEmpty("/api/jobs/paper"),
  job: (jobId) => getJSON(`/api/jobs/${jobId}`),

  listAnalyses: () => getJSON("/api/analysis"),
  analysisMeta: (id) => getJSON(`/api/analysis/${id}`),
  summary: (id) => getJSON(`/api/analysis/${id}/summary`),
  address: (id, addr) => getJSON(`/api/analysis/${id}/address/${encodeURIComponent(addr)}`),
  claims: (id, params) => getJSON(`/api/analysis/${id}/claims?${qs(params)}`),
  conflicts: (id, params) => getJSON(`/api/analysis/${id}/conflicts?${qs(params)}`),
  trustCoverage: (id, rules) => getJSON(`/api/analysis/${id}/trust-coverage?${qs({ rules: rules.join(",") })}`),
  provenance: (id) => getJSON(`/api/analysis/${id}/provenance`),
  drift: (id) => getJSON(`/api/analysis/${id}/drift`),
  tasks: (id) => getJSON(`/api/analysis/${id}/tasks`),
  runTask: (id, task) => postEmpty(`/api/analysis/${id}/run/${task}`),
  // Paper reproduction: every value shown comes from these; none is typed into the UI.
  paperStatus: () => getJSON("/api/paper/status"),
  startPaperReproduction: () => postEmpty("/api/paper/reproduce"),
  paperClaims: () => getJSON("/api/paper/claims"),
  paperExperiment: (id) => getJSON(`/api/paper/experiments/${id}`),
  paperArtifactUrl: (expId, name) => `${BASE}/api/paper/experiments/${expId}/artifact/${name}`,
  exportUrl: (id, name) => `${BASE}/api/analysis/${id}/export/${name}`,
};
