import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

// Loop 2 STEP 19 - the single shared "active analysis" pointer every page
// reads through. Persisted to localStorage so a refresh re-attaches to the
// same analysis_id instead of silently falling back to nothing; if the
// backend no longer knows that id (e.g. it restarted), we drop it rather
// than pretend it's still active.
const STORAGE_KEY = "themis.active_analysis_id";
const AnalysisCtx = createContext(null);

export function AnalysisProvider({ children }) {
  const [analysisId, setAnalysisId] = useState(null);
  const [meta, setMeta] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let stored = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch { /* private mode etc. */ }
    if (!stored) { setReady(true); return; }
    api.analysisMeta(stored)
      .then((m) => { setAnalysisId(stored); setMeta(m); })
      .catch(() => { try { localStorage.removeItem(STORAGE_KEY); } catch { /* noop */ } })
      .finally(() => setReady(true));
  }, []);

  const activate = useCallback((id, m) => {
    setAnalysisId(id);
    setMeta(m || null);
    try { localStorage.setItem(STORAGE_KEY, id); } catch { /* noop */ }
    if (!m) {
      api.analysisMeta(id).then(setMeta).catch(() => {});
    }
  }, []);

  const clear = useCallback(() => {
    setAnalysisId(null);
    setMeta(null);
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* noop */ }
  }, []);

  return (
    <AnalysisCtx.Provider value={{ analysisId, meta, ready, activate, clear }}>
      {children}
    </AnalysisCtx.Provider>
  );
}

export function useAnalysis() {
  const ctx = useContext(AnalysisCtx);
  if (!ctx) throw new Error("useAnalysis must be used within AnalysisProvider");
  return ctx;
}
