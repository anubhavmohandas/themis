import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, humanize, pct } from "../lib/format.js";
import { CONFLICT_KINDS, PROVENANCE, RELATIONSHIPS, RELATIONSHIP_TEXT, ROOT_KIND_TEXT } from "../lib/vocab.js";
import { ErrorBox, FilterSelect, Gate, Loading, MetricStrip, PageHead, Pager, RadioRow, SearchBox, Section, Status } from "../components/ui.jsx";

const PAGE = 25;
const OUTCOME_OF_KIND = { polarity: "licit/illicit conflict", entity: "entity-type conflict", hierarchical: "hierarchical refinement", incomparable: "incomparable" };

export default function ConflictsPage() {
  return <Gate><Body /></Gate>;
}

function Body() {
  const { analysisId, result, isPaper } = useAnalysis();
  const [sp, setSp] = useSearchParams();
  const get = (k) => sp.get(k) || "";
  const offset = Number(get("offset")) || 0;
  const kind = get("kind");
  const [qText, setQText] = useState(get("q"));

  function update(patch) {
    const next = new URLSearchParams(sp);
    Object.entries({ offset: "", ...patch }).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setSp(next);
  }
  useEffect(() => {
    if (qText === get("q")) return undefined;
    const t = setTimeout(() => update({ q: qText.trim() }), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qText]);
  useEffect(() => { setQText(get("q")); }, [sp.get("q")]); // eslint-disable-line react-hooks/exhaustive-deps

  const params = { kind, source_a: get("source_a"), source_b: get("source_b"), relationship: get("relationship"), q: get("q"), offset, limit: PAGE };
  const { data, error, loading } = useApiData(() => api.conflicts(analysisId, params), [analysisId, JSON.stringify(params)]);

  // the agreement block (paper: result.agreement; upload: target profile) supplies each kind's share and denominator
  const ag = isPaper ? result.agreement : result.target_audit?.profile?.agreement;
  const nCmp = isPaper ? ag?.n_multi_source : ag?.n_comparable;
  const share = (k) => ag?.outcomes?.[OUTCOME_OF_KIND[k]]?.share;
  const counts = data?.counts;
  const kindCounts = counts;   // per-kind totals straight from the endpoint; "All" shows no count
  const srcOptions = [["", "any"], ...(data?.sources || []).map((s) => [s, s])];
  const pairs = ag?.top_polarity_conflicts;

  const from = data?.total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, data?.total || 0);
  const denom = `of ${fmt(nCmp)}`;

  return (
    <div>
      <PageHead kicker="Conflict Explorer" title="Attribution conflicts"
        lead="Where two public sources disagree about the same address. THEMIS records the disagreement and its provenance context; it does not adjudicate which source is correct." />

      {counts && (
        <MetricStrip items={[
          { label: "Licit / illicit", value: fmt(counts.polarity), tone: "hot", top: "hot", sub: `${pct(share("polarity"))} ${denom}`, to: "/conflicts?kind=polarity" },
          { label: "Entity type", value: fmt(counts.entity), top: "hot", sub: `${pct(share("entity"))} ${denom}`, to: "/conflicts?kind=entity" },
          { label: "Hierarchical", value: fmt(counts.hierarchical), top: true, sub: `${pct(share("hierarchical"))} ${denom} · refinement, not conflict`, to: "/conflicts?kind=hierarchical" },
          { label: "Incomparable", value: fmt(counts.incomparable), top: true, sub: `${pct(share("incomparable"))} ${denom} · no shared taxonomy path`, to: "/conflicts?kind=incomparable" },
        ]} />
      )}

      <div className="panel pad" style={{ marginBottom: 18 }}>
        <div style={{ display: "grid", gap: 14 }}>
          <div><div className="form-label">Kind</div><RadioRow name="Conflict kind" value={kind} options={CONFLICT_KINDS} counts={kindCounts} onChange={(k) => update({ kind: k })} /></div>
          <div className="controls" style={{ margin: 0 }}>
            <FilterSelect label="Source A" value={get("source_a")} onChange={(v) => update({ source_a: v })} options={srcOptions} />
            <span className="fnt">vs</span>
            <FilterSelect label="Source B" value={get("source_b")} onChange={(v) => update({ source_b: v })} options={srcOptions} />
            <SearchBox value={qText} onChange={setQText} placeholder="Filter by address" />
          </div>
          <div><div className="form-label">Provenance relationship</div>
            <RadioRow name="Provenance relationship" value={get("relationship")} options={RELATIONSHIPS} onChange={(v) => update({ relationship: v })} /></div>
        </div>
      </div>

      {kind === "polarity" && pairs?.length > 0 && (
        <Section title="Largest licit / illicit pairings" meta="highest investigative significance"
          note="One source treats the address as lawful activity, another as criminal. The label pairings affecting the most addresses:">
          <div className="tablewrap"><table>
            <thead><tr><th>Source A · label</th><th>Source B · label</th><th className="num">Addresses</th><th /></tr></thead>
            <tbody>{pairs.map((p, i) => (
              <tr key={i}>
                <td><span className="mono small mut">{p.source_a}</span> · {humanize(p.label_a)}</td>
                <td><span className="mono small mut">{p.source_b}</span> · <span className="hot">{humanize(p.label_b)}</span></td>
                <td className="num">{fmt(p.n)}</td>
                <td><button type="button" className="chip-btn plain" onClick={() => update({ source_a: p.source_a, source_b: p.source_b })}>Filter →</button></td>
              </tr>))}</tbody>
          </table></div>
        </Section>
      )}

      <Section title="Per-address conflict records" meta={data ? `${fmt(data.total)} matching addresses` : undefined}>
        {error && <ErrorBox title="Could not load conflicts">{error}</ErrorBox>}
        {loading && !data && <Loading>Loading conflicts…</Loading>}
        {data && (
          <>
            <div className="listhead">
              <span>Showing <span className="mono">{fmt(from)}–{fmt(to)}</span> of <span className="mono">{fmt(data.total)}</span> addresses · {PAGE} per page</span>
              <Pager offset={offset} limit={PAGE} total={data.total} onChange={(o) => update({ offset: o ? String(o) : "" })} />
            </div>
            {data.items.length === 0
              ? <div className="empty" style={{ maxWidth: "none" }}><div className="eyebrow">No matches</div><p>No address matches these filters. Loosen the source, relationship or search filter.</p></div>
              : <div className="records" style={{ opacity: loading ? 0.6 : 1 }}>{data.items.map((it) => <Item key={it.address} it={it} />)}</div>}
          </>
        )}
      </Section>
    </div>
  );
}

function Item({ it }) {
  const [rel, relText] = RELATIONSHIP_TEXT[it.relationship] || [humanize(it.relationship), ""];
  const conflicting = it.kind === "polarity" || it.kind === "entity";
  const tone = (c) => (!conflicting ? undefined : it.kind === "entity" ? "var(--ac)" : c.polarity === "illicit" ? "var(--ac)" : c.polarity === "licit" ? "var(--tl)" : undefined);
  return (
    <article className="record" style={{ cursor: "default" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
        <Link className="mono" to={`/address?q=${encodeURIComponent(it.address)}`}>{it.address}</Link>
        <span className="fnt" style={{ fontSize: 11.5 }}>{it.outcome}{it.circular ? " · circular corroboration" : ""}</span>
      </div>
      <div className="grid3" style={{ gap: 16, gridTemplateColumns: `repeat(${Math.min(it.claims.length + 1, 4)}, 1fr)` }}>
        {it.claims.map((c, i) => {
          const pv = PROVENANCE[c.provenance] || { tone: "mut", label: c.provenance };
          return (
            <div key={i} style={{ borderLeft: "2px solid var(--rl)", paddingLeft: 11 }}>
              <div className="rk">{it.claims.length > 2 ? `Claim ${i + 1}` : i === 0 ? "Source A" : "Source B"}</div>
              <div style={{ fontSize: 12.5 }}>{c.source} — <span style={{ color: tone(c) }}>{humanize(c.canon)}</span></div>
              <div className="rv-sub mono">raw: {c.raw_label}</div>
              <div className="rv-sub">root: <span className="mono">{c.root}</span> ({ROOT_KIND_TEXT[c.root_kind] || humanize(c.root_kind)}, <Status tone={pv.tone}>{pv.label}</Status>)</div>
            </div>
          );
        })}
        <div style={{ borderLeft: "2px solid var(--rl)", paddingLeft: 11 }}>
          <div className="rk">Provenance relationship</div>
          <div style={{ fontSize: 12.5 }}>{rel}</div>
          <div className="rv-sub">{relText}</div>
          <div className="rv-sub mono">{it.independence.apparent} apparent · {it.independence.confirmed} confirmed · {it.independence.unresolved} unresolved</div>
        </div>
      </div>
      <p className="section-note" style={{ margin: "10px 0 0", paddingTop: 8, borderTop: "1px solid var(--rls)", fontSize: 11.5 }}>Both claims and their provenance are shown. THEMIS does not rank the sources.</p>
    </article>
  );
}
