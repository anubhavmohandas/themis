// Every function here is a thin fetch wrapper around the FastAPI backend
// (themis/api.py), which itself is a thin wrapper around the Python
// engine. No analysis logic belongs in this file - only request/response
// plumbing, per the "UI never contains analytical business logic" rule.
//
// Loop 2: every page-facing call is scoped by an analysisId - there is no
// endpoint that silently reads a global/default corpus.

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:5001";

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.detail || body.error || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function postForm(path, form) {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.detail || body.error || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  base: BASE,
  health: () => getJSON("/api/health"),
  sources: () => getJSON("/api/sources"),

  preflight: (file) => {
    const form = new FormData();
    form.append("file", file);
    return postForm("/api/preflight", form);
  },

  createAnalysis({ file, sourceId, useReference, mapping }) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_id", sourceId || "uploaded_dataset");
    form.append("use_reference", useReference ? "true" : "false");
    if (mapping) form.append("mapping", JSON.stringify(mapping));
    return postForm("/api/analysis", form);
  },

  reproducePaper: () => postForm("/api/analysis/paper", new FormData()),

  listAnalyses: () => getJSON("/api/analysis"),
  analysisMeta: (id) => getJSON(`/api/analysis/${id}`),
  summary: (id) => getJSON(`/api/analysis/${id}/summary`),
  address: (id, addr) => getJSON(`/api/analysis/${id}/address/${encodeURIComponent(addr)}`),
  claims: (id, params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    return getJSON(`/api/analysis/${id}/claims?${q}`);
  },
  provenance: (id) => getJSON(`/api/analysis/${id}/provenance`),
  drift: (id) => getJSON(`/api/analysis/${id}/drift`),
  exportUrl: (id, name) => `${BASE}/api/analysis/${id}/export/${name}`,
};
