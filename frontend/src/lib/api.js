// Every function here is a thin fetch wrapper around the FastAPI backend
// (themis/api.py), which itself is a thin wrapper around the Python
// engine. No analysis logic belongs in this file - only request/response
// plumbing, per the "UI never contains analytical business logic" rule.

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:5001";

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  base: BASE,
  health: () => getJSON("/api/health"),
  sources: () => getJSON("/api/sources"),
  report: (bootstrap = false) => getJSON(`/api/report${bootstrap ? "?bootstrap=true" : ""}`),
  drift: () => getJSON("/api/drift"),
  graph: () => getJSON("/api/graph"),
  address: (addr) => getJSON(`/api/address/${encodeURIComponent(addr)}`),
  exportUrl: (name) => `${BASE}/api/export/${name}`,
  async ingest({ file, sourceId, useReference, mapping }) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_id", sourceId || "uploaded");
    form.append("use_reference", useReference ? "true" : "false");
    if (mapping) form.append("mapping", JSON.stringify(mapping));
    const res = await fetch(`${BASE}/api/ingest`, { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || body.error || `${res.status} ${res.statusText}`);
    }
    return res.json();
  },
};
