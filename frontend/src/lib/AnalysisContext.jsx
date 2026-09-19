import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

// The single shared "active analysis" pointer every page reads through.
// Persisted to localStorage so a refresh re-attaches to the same analysis_id;
// if the backend no longer knows that id (e.g. it restarted) it is dropped
// rather than pretending it is still active.
const STORAGE_KEY = "themis.active_analysis_id";
const THEME_KEY = "themis.theme";
const Ctx = createContext(null);

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode etc. */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* noop */ } },
};

export function AnalysisProvider({ children }) {
  const [analysisId, setAnalysisId] = useState(null);
  const [meta, setMeta] = useState(null);
  const [summary, setSummary] = useState(null);      // GET /summary -> {meta, result, audit_trail}
  const [summaryError, setSummaryError] = useState(null);
  const [sources, setSources] = useState(null);      // source registry (config), for names/chain/citations
  const [analyses, setAnalyses] = useState([]);
  const [ready, setReady] = useState(false);
  const [theme, setTheme] = useState(() => store.get(THEME_KEY) === "dark" ? "dark" : "light");

  // theme: light is the default; the <html> attribute is also set pre-render in index.html
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    store.set(THEME_KEY, theme);
  }, [theme]);
  const toggleTheme = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);

  const refreshAnalyses = useCallback(
    () => api.listAnalyses().then(setAnalyses).catch(() => setAnalyses([])), []);

  // first load: registry, the analyses list, and re-attach to the stored id
  useEffect(() => {
    api.sources().then(setSources).catch(() => {});
    refreshAnalyses();
    const stored = store.get(STORAGE_KEY);
    if (!stored) { setReady(true); return; }
    api.analysisMeta(stored)
      .then((m) => { setAnalysisId(stored); setMeta(m); })
      .catch(() => store.del(STORAGE_KEY))
      .finally(() => setReady(true));
  }, [refreshAnalyses]);

  // the summary follows the active analysis id
  useEffect(() => {
    setSummary(null);
    setSummaryError(null);
    if (!analysisId) return undefined;
    let cancelled = false;
    api.summary(analysisId)
      .then((s) => { if (!cancelled) setSummary(s); })
      .catch((e) => { if (!cancelled) setSummaryError(e.message); });
    return () => { cancelled = true; };
  }, [analysisId]);

  const activate = useCallback((id, m) => {
    setAnalysisId(id);
    setMeta(m || null);
    store.set(STORAGE_KEY, id);
    if (!m) api.analysisMeta(id).then(setMeta).catch(() => {});
    refreshAnalyses();
  }, [refreshAnalyses]);

  const clear = useCallback(() => {
    setAnalysisId(null); setMeta(null); store.del(STORAGE_KEY);
  }, []);

  const value = useMemo(() => {
    const isPaper = meta?.mode === "PAPER_REPRODUCTION";
    const result = summary?.result || null;
    const chains = sources ? [...new Set(Object.values(sources).map((s) => s.chain).filter(Boolean))] : [];
    const chain = isPaper ? chains.join(", ") || null : meta?.blockchain || null;
    const audit = result?.target_audit || null;
    return {
      analysisId, meta, summary, result, summaryError, sources, analyses, ready, theme,
      isPaper, isUpload: !!meta && !isPaper, chain,
      stopped: !!result?.stopped,
      // the numbers the sidebar shows, straight from the result object
      nClaims: isPaper ? result?.dataset_summary?.n_claims : audit?.n_target_claims ?? meta?.n_claims,
      nAddresses: isPaper ? result?.dataset_summary?.n_addresses : audit?.n_target_addresses,
      activate, clear, refreshAnalyses, toggleTheme,
    };
  }, [analysisId, meta, summary, summaryError, sources, analyses, ready, theme,
      activate, clear, refreshAnalyses, toggleTheme]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAnalysis() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAnalysis must be used within AnalysisProvider");
  return ctx;
}
