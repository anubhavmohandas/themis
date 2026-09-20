import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, humanize } from "../lib/format.js";
import { AGREEMENT_OPTIONS, CURRENCY_OPTIONS, PROVENANCE, PROVENANCE_OPTIONS, TIER, TIER_OPTIONS, outcomeOf } from "../lib/vocab.js";
import { ErrorBox, FilterSelect, Gate, Loading, PageHead, Pager, RecordsNote, SearchBox, Status } from "../components/ui.jsx";

const PAGE = 100;

// Filters live in the URL, so every drill-down from another page (a bar row, a
// metric) lands here as a shareable, reloadable view. The backend does all
// filtering; this page only sends the parameters and renders the page it returns.
export default function ClaimsPage() {
  return <Gate><ClaimsBody /></Gate>;
}

function ClaimsBody() {
  const { analysisId, sources, isPaper, meta, result } = useAnalysis();
  const [sp, setSp] = useSearchParams();
  const get = (k) => sp.get(k) || "";
  const offset = Number(get("offset")) || 0;
  const [qText, setQText] = useState(get("q"));

  const taxonomy = useApiData(() => api.taxonomy(), []);
  const categories = taxonomy.data ? Object.keys(taxonomy.data) : [];

  // one select maps onto the backend's `outcome` / `comparable` params
  const agreement = get("outcome") || (get("comparable") === "yes" ? "comparable" : get("comparable") === "no" ? "not-comparable" : "");
  const setAgreement = (v) => update({
    outcome: v && v !== "comparable" && v !== "not-comparable" ? v : "",
    comparable: v === "comparable" ? "yes" : v === "not-comparable" ? "no" : "",
  });

  function update(patch) {
    const next = new URLSearchParams(sp);
    Object.entries({ offset: "", ...patch }).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setSp(next, { replace: false });
  }

  // debounce the free-text box into the URL
  useEffect(() => {
    if (qText === get("q")) return undefined;
    const t = setTimeout(() => update({ q: qText.trim() }), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qText]);
  useEffect(() => { setQText(get("q")); }, [sp.get("q")]); // eslint-disable-line react-hooks/exhaustive-deps

  const params = useMemo(() => ({
    q: get("q"), source: get("source"), canon: get("canon"), evidence_tier: get("evidence_tier"),
    currency: get("currency"), provenance: get("provenance"),
    outcome: get("outcome"), comparable: get("comparable"), offset, limit: PAGE,
  }), [sp]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, error, loading } = useApiData(() => api.claims(analysisId, params), [analysisId, JSON.stringify(params)]);

  const sourceOptions = [["", "any"], ...Object.keys(sources || {}).map((s) => [s, s]),
    ...(!isPaper && result?.source_id ? [[result.source_id, `${result.source_id} (uploaded)`]] : [])];
  const agreementOptions = AGREEMENT_OPTIONS.map(([v, l]) =>
    v === "comparable" ? [v, isPaper ? "multi-dataset addresses" : "reference match"] : [v, l]);
  agreementOptions.splice(3, 0, ["not-comparable", isPaper ? "not multi-dataset" : "no reference match"]);

  const chips = [
    ["q", get("q") && `search “${get("q")}”`], ["source", get("source") && `source: ${get("source")}`],
    ["canon", get("canon") && `category: ${humanize(get("canon"))}`],
    ["evidence_tier", get("evidence_tier") && `evidence: ${get("evidence_tier")}`],
    ["currency", get("currency") && `currency: ${get("currency")}`],
    ["provenance", get("provenance") && `provenance: ${get("provenance")}`],
    ["agreement", agreement && `agreement: ${agreementOptions.find(([v]) => v === agreement)?.[1] || agreement}`],
  ].filter(([, t]) => t);
  const clearChip = (k) => (k === "agreement" ? setAgreement("") : update({ [k]: "" }));

  // which records these are; an agreement filter on the sample is "sample agreement records"
  const recordsLabel = data?.population === "bundled_sample" ? (get("outcome") || get("comparable") ? "sample agreement records" : "bundled sample records")
    : data?.population === "normalized_full_corpus" ? "full corpus records" : "";
  const total = data?.total ?? 0;
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, total);

  return (
    <div>
      <PageHead kicker={`Record table${recordsLabel ? ` · ${recordsLabel}` : ""}`} title="Claims"
        lead="One bounded, server-filtered page at a time, never the whole corpus. Use Exports for the full normalized claim set. Each address links to its evidence in the Address Inspector." />

      {isPaper && (
        <RecordsNote table={data?.population} asked={get("population")}
          sampleDetail={`It holds ${fmt(meta.n_claims)} of the corpus’s ${fmt(result.overview.metrics.claims.value)} claims, including the multi-dataset addresses it was drawn with.`} />
      )}

      <div className="controls">
        <SearchBox value={qText} onChange={setQText} placeholder="Search address, raw label or source" />
        <FilterSelect label="Category" value={get("canon")} onChange={(v) => update({ canon: v })}
          options={[["", "any"], ...categories.map((c) => [c, humanize(c)])]} />
        <FilterSelect label="Source" value={get("source")} onChange={(v) => update({ source: v })} options={sourceOptions} />
        <FilterSelect label="Evidence" value={get("evidence_tier")} onChange={(v) => update({ evidence_tier: v })} options={TIER_OPTIONS} />
        <FilterSelect label="Currency" value={get("currency")} onChange={(v) => update({ currency: v })} options={CURRENCY_OPTIONS} />
        <FilterSelect label="Agreement" value={agreement} onChange={setAgreement} options={agreementOptions} />
        <FilterSelect label="Provenance" value={get("provenance")} onChange={(v) => update({ provenance: v })} options={PROVENANCE_OPTIONS} />
      </div>
      {chips.length > 0 && (
        <div className="chips" style={{ marginBottom: 12 }}>
          {chips.map(([k, t]) => <button key={k} type="button" className="fchip" title="Remove filter" onClick={() => clearChip(k)}>{t} ×</button>)}
          <button type="button" className="chip-btn plain" onClick={() => setSp(new URLSearchParams())}>Clear all</button>
        </div>
      )}

      {error && <ErrorBox title="Could not load claims">{error}</ErrorBox>}
      {loading && !data && <Loading>Loading claims…</Loading>}

      {data && (
        <>
          <div className="listhead">
            <span>
              Showing <span className="mono">{fmt(from)}–{fmt(to)}</span> of <span className="mono">{fmt(total)}</span> matching claims
              {" "}· <span className="mono">{fmt(data.n_addresses)}</span> addresses · {PAGE} per page
            </span>
            <Pager offset={offset} limit={PAGE} total={total} onChange={(o) => update({ offset: o ? String(o) : "" })} />
          </div>
          {data.claims.length === 0 ? (
            <div className="empty" style={{ maxWidth: "none" }}><div className="eyebrow">No matches</div><p>No claims match these filters. Remove a filter above.</p></div>
          ) : (
            <div className="tablewrap" style={{ opacity: loading ? 0.6 : 1 }}>
              <table>
                <thead><tr>
                  <th>Address</th><th>Raw label</th><th>Category</th><th>Source</th><th>Evidence</th><th>Provenance</th><th>Last revised</th><th>Agreement</th>
                </tr></thead>
                <tbody>
                  {data.claims.map((c, i) => {
                    const o = outcomeOf(c.outcome);
                    const t = TIER[c.evidence_tier] || { label: c.evidence_tier, tone: "mut" };
                    const pv = PROVENANCE[c.provenance] || { label: c.provenance, tone: "mut" };
                    return (
                      <tr key={`${c.address}-${c.source}-${i}`}>
                        <td className="mono"><Link to={`/address?q=${encodeURIComponent(c.address)}`}>{c.address}</Link></td>
                        <td className="mono small mut">{c.raw_label}</td>
                        <td>{humanize(c.canon)}</td>
                        <td>{c.source}</td>
                        <td><Status tone={t.tone}>{t.label}</Status></td>
                        <td title={c.root ? `root: ${c.root}` : undefined}><Status tone={pv.tone}>{pv.label}</Status></td>
                        <td className="small mono mut">{c.lastmod || "no date"}</td>
                        <td>{o ? <Status tone={o.tone}>{o.short}</Status> : <Status tone="mut">single-source</Status>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="listhead" style={{ marginTop: 10 }}>
            <span className="fnt">Agreement is a property of the address, not the row: it is the outcome across every dataset that names it.</span>
            <Pager offset={offset} limit={PAGE} total={total} onChange={(o) => update({ offset: o ? String(o) : "" })} />
          </div>
        </>
      )}
    </div>
  );
}
