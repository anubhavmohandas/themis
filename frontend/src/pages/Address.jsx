import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, humanize } from "../lib/format.js";
import { PROVENANCE, ROOT_KIND_TEXT, TIER, outcomeOf } from "../lib/vocab.js";
import { Empty, ErrorBox, Gate, Loading, MetricStrip, PageHead, Section, SearchBox, Status, Tag } from "../components/ui.jsx";

export default function AddressPage() {
  return <Gate><AddressBody /></Gate>;
}

function AddressBody() {
  const { analysisId } = useAnalysis();
  const [sp, setSp] = useSearchParams();
  const q = (sp.get("q") || "").trim();
  const chainParam = (sp.get("chain") || "").trim();
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  const submit = () => setSp(text.trim() ? { q: text.trim() } : {});

  const { data, error, loading } = useApiData(() => (q ? api.address(analysisId, q, chainParam || undefined) : null), [analysisId, q, chainParam]);

  return (
    <div>
      <PageHead kicker="Address Inspector" mono={!!(q && data?.found)} title={q && data?.found ? q : "Inspect one address"}
        lead={q && data?.found ? undefined : "Every attribution claim for one address, side by side and never merged, with the provenance root each claim traces to."}>
        {q && data?.found && <>
          {data.chain && <Tag>{data.chain}</Tag>}
          <button type="button" className="chip-btn plain" onClick={() => { try { navigator.clipboard.writeText(q); } catch { /* clipboard unavailable */ } }}>Copy</button>
        </>}
      </PageHead>

      <div className="controls">
        <SearchBox value={text} onChange={setText} onSubmit={submit} placeholder="Paste an address to inspect" />
        <button type="button" className="btn" onClick={submit} disabled={!text.trim()}>Inspect</button>
      </div>

      {!q && <StartFromConflict />}
      {q && loading && <Loading>Reading claims…</Loading>}
      {error && <ErrorBox title="Could not inspect this address">{error}</ErrorBox>}
      {q && data?.ambiguous && (
        <div className="inline-note" role="alert">
          <strong>This address string is on more than one chain.</strong> {data.message}
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            {data.chains.map((c) => <Link key={c} className="btn secondary" to={`/address?q=${encodeURIComponent(q)}&chain=${encodeURIComponent(c)}`}>{c}</Link>)}
          </div>
        </div>
      )}
      {q && data && !data.found && !data.ambiguous && (
        <Empty eyebrow="Address not found" action={<Link className="btn secondary" to="/claims">Browse claims</Link>}>
          No claim in this analysis names this address. THEMIS only knows addresses that appear in the loaded claims; a missing address is absence of evidence, not evidence of absence.
        </Empty>
      )}
      {q && data?.found && <Found data={data} />}
    </div>
  );
}

// Real starting points, taken from this analysis's own conflicts.
function StartFromConflict() {
  const { analysisId } = useAnalysis();
  const { data } = useApiData(() => api.conflicts(analysisId, { kind: "polarity", limit: 5 }), [analysisId]);
  if (!data?.items?.length) return null;
  return (
    <div className="panel pad" style={{ maxWidth: 640 }}>
      <div className="form-label">Start from a licit / illicit conflict in this analysis</div>
      {data.items.map((it) => (
        <div key={it.address} style={{ padding: "4px 0" }}><Link className="mono" to={`/address?q=${encodeURIComponent(it.address)}`}>{it.address}</Link></div>
      ))}
    </div>
  );
}

// -------------------------------------------------------------------- found
function normalize(data) {
  // paper mode returns one claims list; an uploaded analysis splits target/reference
  if (data.claims) return data.claims.map((c) => ({ ...c, side: null }));
  return [...(data.target_claims || []).map((c) => ({ ...c, side: "target" })),
    ...(data.reference_claims || []).map((c) => ({ ...c, side: "reference" }))];
}

function Found({ data }) {
  const { sources } = useAnalysis();
  const claims = useMemo(() => normalize(data), [data]);
  const [sel, setSel] = useState(null);           // {kind: 'root'|'dataset'|'label', id}
  useEffect(() => setSel(null), [data.address]);
  const toggle = (kind, id) => setSel((s) => (s && s.kind === kind && s.id === id ? null : { kind, id }));
  const isSel = (c) => sel && ((sel.kind === "root" && c.root === sel.id) || (sel.kind === "dataset" && c.source === sel.id) || (sel.kind === "label" && c.label === sel.id));

  const ind = data.independence || {};
  const outcome = outcomeOf(data.outcome);
  const isConflict = outcome?.tone === "hot";
  const withDates = claims.filter((c) => c.lastmod);

  return (
    <div className="two-col">
      <div>
        <MetricStrip items={[
          { label: "Apparent datasets", value: fmt(ind.apparent_dataset_count ?? data.apparent_corroboration) },
          { label: "Confirmed independent roots", value: fmt(ind.confirmed_independent_root_count ?? data.actual_corroboration),
            tone: (ind.confirmed_independent_root_count ?? 0) < (ind.apparent_dataset_count ?? 0) ? "hot" : "" },
          { label: "Unresolved relationships", value: fmt(ind.unresolved_source_count) },
          { label: "Conflict", value: outcome ? (isConflict ? "Yes" : "No") : "No", tone: isConflict ? "hot" : "",
            sub: outcome ? outcome.label : "single-source: nothing to compare" },
        ]} />

        <Section title="Apparent vs. independent corroboration">
          <div className="panel pad">
            <Corroboration claims={claims} sel={sel} onSelect={toggle} />
            <Legend />
            {(ind.circular || ind.shared_root_count > 0) && (
              <div className="inline-note" role="note">
                <strong>Circularity detected.</strong> {fmt(ind.apparent_dataset_count)} datasets name this address, but they resolve to {fmt(ind.resolved_root_count)} distinct root{ind.resolved_root_count === 1 ? "" : "s"}.
                {ind.collapsed_claims?.length > 0 && <> Restating a root already counted: {ind.collapsed_claims.map((c, i) => <span key={`${c.source}${c.root}`}>{i > 0 && "; "}<span className="mono">{c.source}</span> → <span className="mono">{c.root}</span></span>)}.</>}
                {" "}Independence range: {ind.independence_min}–{ind.independence_max}.
              </div>
            )}
            {ind.unresolved_source_count > 0 && (
              <div className="inline-note quiet">
                {fmt(ind.unresolved_source_count)} claim source{ind.unresolved_source_count === 1 ? " has" : "s have"} no identified root. Unresolved is never counted as independent, so the range above is a lower and an upper bound, not a point estimate.
              </div>
            )}
          </div>
        </Section>

        <Section title="Attribution claims" meta={`${claims.length} record${claims.length === 1 ? "" : "s"} · not merged`}>
          <div className="records">
            {claims.map((c, i) => {
              const t = TIER[c.tier] || { label: c.tier, tone: "mut" };
              const pv = PROVENANCE[c.provenance] || { label: c.provenance, tone: "mut" };
              return (
                <article key={i} className={`record${isSel(c) ? " sel" : ""} ${c.provenance === "resolved" ? "ok" : c.provenance === "inherited" ? "flag" : ""}`}
                  onClick={() => setSel({ kind: "root", id: c.root })} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") setSel({ kind: "root", id: c.root }); }}>
                  <div className="record-grid">
                    <div><div className="rk">Source</div><div className="rv" style={{ fontWeight: 500 }}>{c.source}</div>
                      {c.side && <div className="rv-sub">{c.side === "target" ? "your dataset" : "reference corpus"}</div>}</div>
                    <div><div className="rk">Raw label</div><div className="rv mono">{c.raw}</div><div className="rv-sub">category: {humanize(c.label)}</div></div>
                    <div><div className="rk">Evidence tier</div><div className="rv"><Status tone={t.tone}>{t.label}</Status></div></div>
                    <div><div className="rk">Provenance root</div><div className="rv mono">{c.root}</div>
                      <div className="rv-sub">{ROOT_KIND_TEXT[c.root_kind] || humanize(c.root_kind)} · <Status tone={pv.tone}>{pv.label}</Status></div></div>
                    <div><div className="rk">Last revised</div><div className="rv mono">{c.lastmod || "no date"}</div>
                      {!c.lastmod && <div className="rv-sub">currency-unknown</div>}</div>
                  </div>
                </article>
              );
            })}
          </div>
        </Section>

        {outcome && data.outcome !== "exact" && <Disagreement data={data} claims={claims} sel={sel} onSelect={toggle} outcome={outcome} />}

        <Section title="Attribution-evidence chronology" meta="not transaction history">
          <div className="panel pad">
            {withDates.length === 0
              ? <p className="mut" style={{ margin: 0 }}>None of these claims carries a revision date, so there is nothing to place on a timeline. Undated claims are currency-unknown and are never placed by guesswork.</p>
              : <div className="tl">
                {[...withDates].sort((a, b) => a.lastmod.localeCompare(b.lastmod)).map((c, i) => (
                  <Row key={i} year={c.lastmod}>
                    <span className="mono">{c.source}</span> revised its <span className="mono">{c.raw}</span> claim ({humanize(c.label)}), root <span className="mono">{c.root}</span>.
                  </Row>))}
              </div>}
            <p className="section-note" style={{ margin: "12px 0 0", paddingTop: 10, borderTop: "1px solid var(--rls)" }}>
              Built from each claim’s declared revision field.{" "}
              {claims.length - withDates.length > 0 && `${claims.length - withDates.length} of ${claims.length} claims have no revision date and are omitted.`}
            </p>
          </div>
        </Section>
      </div>

      <aside style={{ position: "sticky", top: 66, display: "flex", flexDirection: "column", gap: 12 }}>
        <SelectionPanel sel={sel} claims={claims} sources={sources} onClear={() => setSel(null)} />
      </aside>
    </div>
  );
}

const Row = ({ year, children }) => (<><div className="yr">{year}</div><div>{children}</div></>);

// --------------------------------------------------- corroboration diagram
const trunc = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
function Corroboration({ claims, sel, onSelect }) {
  const srcs = [...new Set(claims.map((c) => c.source))];
  const roots = [...new Set(claims.map((c) => c.root))];
  const edges = [];
  for (const c of claims) {
    if (!edges.some((e) => e.source === c.source && e.root === c.root)) edges.push({ source: c.source, root: c.root, kind: c.root_kind, prov: c.provenance });
  }
  const rootInfo = Object.fromEntries(roots.map((r) => {
    const cs = claims.filter((c) => c.root === r);
    return [r, { unresolved: cs.some((c) => c.provenance === "unresolved"), shared: new Set(cs.map((c) => c.source)).size > 1 }];
  }));
  const STEP = 36;
  const rows = Math.max(srcs.length, roots.length);
  const H = 28 + rows * STEP;
  const yS = (s) => 22 + srcs.indexOf(s) * STEP;
  const yR = (r) => 22 + roots.indexOf(r) * STEP;
  const dim = (e) => sel && !((sel.kind === "root" && e.root === sel.id) || (sel.kind === "dataset" && e.source === sel.id) ||
    (sel.kind === "label" && claims.some((c) => c.label === sel.id && c.source === e.source && c.root === e.root)));
  const dimNode = (kind, id) => sel && !(sel.kind === kind && sel.id === id) && !edges.some((e) => !dim(e) && (kind === "root" ? e.root === id : e.source === id));
  return (
    <svg viewBox={`0 0 700 ${H}`} className="svgfig" style={{ width: "100%", maxWidth: 720, height: "auto" }} role="img"
      aria-label={`${srcs.length} datasets resolving to ${roots.length} provenance roots`}>
      <text x="0" y="11" fontSize="9" letterSpacing="1.2" fill="var(--mut)">APPARENT: {srcs.length} DATASET{srcs.length === 1 ? "" : "S"}</text>
      <text x="420" y="11" fontSize="9" letterSpacing="1.2" fill="var(--mut)">PROVENANCE ROOTS: {roots.length}</text>
      {edges.map((e) => {
        const stroke = e.prov === "unresolved" ? "var(--nt2)" : e.kind === "INFERRED" ? "var(--oc)" : "var(--tl)";
        const dash = e.prov === "unresolved" ? "1.5 3" : e.kind === "INFERRED" ? "4 3" : undefined;
        const a = yS(e.source) + 13, b = yR(e.root) + 13, mid = 300 + (srcs.indexOf(e.source) % 3) * 14;
        return <path key={`${e.source}|${e.root}`} d={`M190 ${a} H${mid} V${b} H420`} fill="none" stroke={stroke} strokeWidth="1.3"
          strokeDasharray={dash} opacity={dim(e) ? 0.18 : 1} />;
      })}
      {srcs.map((s) => (
        <g key={s} style={{ cursor: "pointer" }} opacity={dimNode("dataset", s) ? 0.4 : 1} onClick={() => onSelect("dataset", s)} tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") onSelect("dataset", s); }} role="button" aria-label={`Dataset ${s}`}>
          <rect x="0" y={yS(s)} width="190" height="26" fill="var(--sfa)" stroke={sel?.kind === "dataset" && sel.id === s ? "var(--ac)" : "var(--rl)"} strokeWidth={sel?.kind === "dataset" && sel.id === s ? 1.6 : 1} />
          <text x="10" y={yS(s) + 17} fontSize="11" fill="var(--ink)">{trunc(s, 24)}</text>
        </g>
      ))}
      {roots.map((r) => {
        const info = rootInfo[r];
        const on = sel?.kind === "root" && sel.id === r;
        return (
          <g key={r} style={{ cursor: "pointer" }} opacity={dimNode("root", r) ? 0.4 : 1} onClick={() => onSelect("root", r)} tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter") onSelect("root", r); }} role="button" aria-label={`Root ${r}`}>
            <rect x="420" y={yR(r)} width="270" height="26" fill={info.unresolved ? "var(--bg)" : info.shared ? "var(--acs)" : "var(--tls)"}
              stroke={on || info.shared ? "var(--ac)" : info.unresolved ? "var(--nt2)" : "var(--tl)"} strokeWidth={on ? 1.8 : 1}
              strokeDasharray={info.unresolved ? "3 3" : undefined} />
            <text x="430" y={yR(r) + 17} fontSize="11" fill={info.unresolved ? "var(--mut)" : "var(--ink)"}>
              {trunc(`${r}${info.unresolved ? " · unresolved" : info.shared ? " · shared" : ""}`, 40)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Legend() {
  const L = ({ dash, color, label }) => (
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <svg width="26" height="6" aria-hidden="true"><line x1="0" y1="3" x2="26" y2="3" stroke={color} strokeWidth="1.4" strokeDasharray={dash} /></svg>{label}
    </span>
  );
  return (
    <div className="legend">
      <L color="var(--tl)" label="declared" /><L color="var(--oc)" dash="4 3" label="inferred (decoded field)" />
      <L color="var(--nt2)" dash="1.5 3" label="unresolved" />
      <span><span className="sw" style={{ background: "var(--acs)", border: "1px solid var(--ac)" }} />root shared by ≥2 datasets</span>
      <span className="fnt">Click a dataset or root to trace it.</span>
    </div>
  );
}

// --------------------------------------------------------- disagreement
function Disagreement({ data, claims, sel, onSelect, outcome }) {
  const groups = [];
  for (const c of claims) {
    let g = groups.find((x) => x.label === c.label);
    if (!g) { g = { label: c.label, polarity: c.polarity, sources: [], roots: [] }; groups.push(g); }
    if (!g.sources.includes(c.source)) g.sources.push(c.source);
    if (!g.roots.includes(c.root)) g.roots.push(c.root);
  }
  const kind = { "licit/illicit conflict": "polarity", "entity-type conflict": "entity", "hierarchical refinement": "hierarchical", incomparable: "incomparable" }[data.outcome];
  return (
    <Section title={outcome.tone === "hot" ? "Conflict record" : "How the labels relate"} meta={outcome.label}>
      <div className="panel pad">
        <div className="grid3">
          {groups.map((g) => (
            <button type="button" key={g.label} className="cell" onClick={() => onSelect("label", g.label)}
              style={{ border: 0, background: "transparent", borderLeft: `2px solid ${sel?.kind === "label" && sel.id === g.label ? "var(--ac)" : "var(--rl)"}`, paddingLeft: 11, cursor: "pointer" }}>
              <div className="rk">Labelled by {g.sources.length} source{g.sources.length === 1 ? "" : "s"}</div>
              <div className={outcome.tone === "hot" ? "hot" : ""} style={{ fontSize: 12.5 }}>{humanize(g.label)}</div>
              <div className="rv-sub">{g.sources.join(", ")}</div>
              <div className="rv-sub mono">root: {g.roots.join(", ")}</div>
            </button>
          ))}
        </div>
        <p className="section-note" style={{ margin: "12px 0 0", paddingTop: 10, borderTop: "1px solid var(--rls)" }}>
          THEMIS presents both claims and their provenance. It does not rank the sources.{" "}
          {kind && <Link to={`/conflicts?kind=${kind}&q=${encodeURIComponent(data.address)}`}>Open in the Conflict Explorer →</Link>}
        </p>
      </div>
    </Section>
  );
}

// ------------------------------------------------------- selection panel
function SelectionPanel({ sel, claims, sources, onClear }) {
  if (!sel) {
    return (
      <div className="panel pad">
        <div className="form-label">Selection</div>
        <p className="mut" style={{ margin: 0, fontSize: 12, lineHeight: 1.6 }}>Click a root or a dataset in the diagram, or a claim record, to trace it. Selecting a root shows every dataset that resolves to it; selecting a dataset shows its source metadata.</p>
      </div>
    );
  }
  if (sel.kind === "dataset") {
    const s = sources?.[sel.id];
    const mine = claims.filter((c) => c.source === sel.id);
    return (
      <div className="panel pad">
        <div className="form-label">Dataset <button type="button" className="x" style={{ float: "right" }} onClick={onClear} aria-label="Clear selection">×</button></div>
        <div style={{ fontWeight: 500 }}>{s?.display_name || sel.id}</div>
        {s ? <>
          <div className="kv" style={{ gridTemplateColumns: "90px 1fr" }}><span>chain</span><span>{s.chain}</span></div>
          <div className="kv" style={{ gridTemplateColumns: "90px 1fr" }}><span>citation</span><span style={{ fontFamily: "var(--sn)" }}>{s.citation}</span></div>
          <div className="kv" style={{ gridTemplateColumns: "90px 1fr" }}><span>semantics</span><span style={{ fontFamily: "var(--sn)" }}>{s.confidence_semantics}</span></div>
          {s.known_dependencies?.length > 0 && <div className="kv" style={{ gridTemplateColumns: "90px 1fr" }}><span>depends on</span><span>{s.known_dependencies.join(", ")}</span></div>}
        </> : <p className="mut" style={{ fontSize: 12 }}>This dataset is not in the source registry (it is your uploaded file), so its methodology is undeclared.</p>}
        <p className="section-note" style={{ margin: "8px 0 0" }}>{mine.length} claim{mine.length === 1 ? "" : "s"} for this address. <Link to={`/sources`}>All sources →</Link></p>
      </div>
    );
  }
  const mine = claims.filter((c) => (sel.kind === "root" ? c.root === sel.id : c.label === sel.id));
  const sourcesOf = [...new Set(mine.map((c) => c.source))];
  return (
    <div className="panel pad">
      <div className="form-label">{sel.kind === "root" ? "Provenance root" : "Label"} <button type="button" className="x" style={{ float: "right" }} onClick={onClear} aria-label="Clear selection">×</button></div>
      <div className="mono" style={{ fontSize: 12.5, wordBreak: "break-all" }}>{sel.id}</div>
      <p className="section-note" style={{ margin: "8px 0 0" }}>
        {sel.kind === "root"
          ? `${sourcesOf.length} dataset${sourcesOf.length === 1 ? "" : "s"} trace${sourcesOf.length === 1 ? "s" : ""} to this root: ${sourcesOf.join(", ")}.${sourcesOf.length > 1 ? " Their agreement on this address is one observation, not several." : ""}`
          : `Asserted by ${sourcesOf.join(", ")}.`}
      </p>
    </div>
  );
}
