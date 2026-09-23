import { useState } from "react";
import { Link } from "react-router-dom";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, humanize, kappaText, pct } from "../lib/format.js";
import { OUTCOMES, SCOPE_INTRO, SCOPE_LABEL, popNoun, popTag } from "../lib/vocab.js";
import { BarRows, Gate, Legend, Limitations, MetricStrip, PageHead, Section, Status } from "../components/ui.jsx";

// Every figure below is read from the backend's result object. Percentages
// are the backend's shares; each is printed next to its count and denominator.

export default function OverviewPage() {
  return <Gate>{<OverviewBody />}</Gate>;
}

function OverviewBody() {
  const { isPaper } = useAnalysis();
  return isPaper ? <PaperOverview /> : <UploadOverview />;
}

// ---------------------------------------------------------------- shared rows
function agreementRows(outcomes, extraQuery = "") {
  return OUTCOMES.map((o) => {
    const v = outcomes[o.key] || { n: 0, share: 0 };
    return { key: o.key, label: o.label, labelColor: o.tone === "hot" ? "var(--ac)" : undefined,
      share: v.share, pct: pct(v.share), n: fmt(v.n), fill: o.fill, hatch: o.hatch,
      to: o.to(extraQuery), title: "Open the matching records" };
  });
}

const CURRENCY_ROWS = [
  { key: "current", label: "Current", fill: "var(--tl)", q: "current" },
  { key: "stale", label: "Stale", fill: "var(--oc)", q: "stale" },
  { key: "currency_unknown", label: "Currency unknown (no revision date)", hatch: true, q: "currency-unknown" },
];
// parts: [{key, n, share}] from the backend; base: the drill-down path (with its population, if any)
function currencyRows(parts, nLabel, base = "/claims") {
  const sep = base.includes("?") ? "&" : "?";
  return CURRENCY_ROWS.map(({ q, ...row }) => {
    const p = parts.find((x) => x.key === row.key);
    return { ...row, share: p.share, pct: pct(p.share), n: `${fmt(p.n)} / ${nLabel}`, to: `${base}${sep}currency=${q}` };
  });
}

function Cell({ label, big, den, share, fill, to, tone }) {
  const inner = (
    <>
      <div className="cell-label">{label}</div>
      <div className="cell-val"><span className={`big ${tone || ""}`}>{big}</span><span className="den">{den}</span></div>
      <div className="meter"><i style={{ width: `${(share || 0) * 100}%`, background: fill }} /></div>
    </>
  );
  return to ? <Link className="cell" to={to} title="Open the matching records">{inner}</Link> : <div className="cell">{inner}</div>;
}

function Kappa({ kappa }) {
  const [all, setAll] = useState(false);
  const substantial = new Set((kappa.substantial || []).map((s) => s.pair));
  const pairs = kappa.pairs || [];
  const shown = all ? pairs : pairs.slice(0, 6);
  return (
    <>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Source pair</th><th className="num">Shared n</th><th className="num">Raw agreement</th><th className="num">κ</th><th className="num" title="Same definition over the pairs where both sources gave an interpretable label; ‘unknown’ is not treated as a class">κ, interpretable only</th><th>Reading</th></tr></thead>
          <tbody>
            {shown.map((p) => {
              const name = `${p.source_a}-${p.source_b}`;
              const undef = p.cohen_kappa === null || p.cohen_kappa === undefined;
              return (
                <tr key={name}>
                  <td className="mono">{p.source_a} · {p.source_b}</td>
                  <td className="num">{fmt(p.n)}</td>
                  <td className="num">{pct(p.percent_agreement)}</td>
                  <td className={`num ${substantial.has(name) ? "ok" : ""}`}>{kappaText(p.cohen_kappa)}</td>
                  <td className="num" title={p.n_interpretable !== undefined ? `${fmt(p.n_interpretable)} / ${fmt(p.n)} pairs interpretable · ${fmt(p.n_both_unknown)} both-unknown` : undefined}>
                    {p.n_interpretable === undefined ? "n/a" : p.n_interpretable === 0 ? "no pair" : kappaText(p.cohen_kappa_interpretable)}
                    {p.n_interpretable !== undefined && <span className="den"> {fmt(p.n_interpretable)}/{fmt(p.n)}</span>}
                  </td>
                  <td className="small mut">{undef ? (p.note || "undefined: shared region is single-class") : substantial.has(name) ? "substantial" : p.cohen_kappa === 0 ? "no agreement beyond chance" : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="tablefoot">
          {fmt(kappa.n_undefined)} of {fmt(kappa.n_pairs)} pairs are undefined (the shared region is single-class, so κ is reported as undefined rather than forced to 1.0); {fmt(kappa.n_zero)} sit at exactly zero. The headline κ keeps ‘unknown’ as a class, so two sources that both say nothing count as agreeing; the interpretable-only column drops those pairs, with its own denominator beside it.
          {pairs.length > 6 && <> <button type="button" className="chip-btn plain" style={{ marginLeft: 8 }} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${pairs.length} pairs`}</button></>}
        </div>
      </div>
    </>
  );
}

// Generic renderer for the engine's reliability profile: one card per dimension.
function flat(obj) {
  const out = [];
  for (const [k, v] of Object.entries(obj || {})) {
    if (k === "available") continue;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out.push([humanize(k), Object.entries(v).map(([a, b]) => `${humanize(a)}: ${typeof b === "object" && b !== null ? (b.n !== undefined ? fmt(b.n) : JSON.stringify(b)) : fmt(b)}`).join(" · ") || "none"]);
    } else if (Array.isArray(v)) out.push([humanize(k), v.length ? v.join(", ") : "none"]);
    else if (typeof v === "number") out.push([humanize(k), k.endsWith("_share") || k.endsWith("_rate") ? pct(v) : fmt(v)]);
    else out.push([humanize(k), String(v)]);
  }
  return out;
}
function ReliabilityProfile({ profile }) {
  if (!profile) return null;
  return (
    <details className="more" style={{ marginTop: 6 }}>
      <summary>Full reliability profile (every dimension the engine reports)</summary>
      <div className="grid2" style={{ marginTop: 10 }}>
        {Object.entries(profile).map(([dim, body]) => (
          <div key={dim} className="defcard">
            <div><span className="dn">{humanize(dim)}</span>{body?.available === false && <span className="dg">not available</span>}</div>
            <div style={{ marginTop: 6 }}>
              {flat(body).map(([k, v]) => <div key={k} className="kv" style={{ gridTemplateColumns: "150px 1fr" }}><span>{k}</span><span>{v}</span></div>)}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

// ---------------------------------------------------------------------- paper
// Every figure is one backend metric record (result.overview, themis/overview.py) carrying its
// own unit, population and quality; a share is only ever taken inside one population. This page
// words those records, links them, and says which data each was counted over.
const link = (path, m) => `${path}${path.includes("?") ? "&" : "?"}population=${m.population}`;
const has = (m) => m.quality !== "unavailable";

function PaperOverview() {
  const { result: r } = useAnalysis();
  const { independence: ind, kappa } = r;
  const { scope, metrics: M } = r.overview;
  const full = scope === "FULL_CORPUS";
  const { claims, normalized_addresses: norm, raw_address_keys: raw, multi_dataset: multi, single_source: single,
    source_depth: depth, agreement: agr, unresolved_provenance: unres, root_concentration: roots,
    source_contribution: contrib, currency: cur, claims_without_revision: noRev } = M;
  const top = ind.root_concentration?.[0];
  const unknown = cur.parts.find((x) => x.key === "currency_unknown");

  const limits = [
    has(single)
      ? `${popTag(single)} · ${pct(single.share)} of ${popNoun(single)} (${fmt(single.numerator)} / ${fmt(single.denominator)}) carry a claim from exactly one dataset, so no public cross-source comparison is possible for them.`
      : `${popTag(multi)} · The share of addresses with no public cross-source comparison cannot be stated from the sample; it needs the normalized full corpus.`,
    has(unres) && `${popTag(unres)} · ${pct(unres.share)} of ${popNoun(unres)} (${fmt(unres.numerator)} / ${fmt(unres.denominator)}) resolve to no identified provenance root. Unresolved is never scored as independent.`,
    top && `${popTag(roots)} · The largest root, ${top.root}, accounts for ${pct(top.share)} of all claims (${fmt(top.claims)} / ${fmt(roots.denominator)}) and is ${top.resolved ? "identified" : "unresolved"}.`,
    kappa.n_undefined > 0 && `${popTag(agr)} · κ is undefined for ${fmt(kappa.n_undefined)} of ${fmt(kappa.n_pairs)} overlapping pairs because the shared region is single-class.`,
    `${popTag(cur)} · ${pct(unknown.share)} of the ${fmt(cur.value)} claims analysed (${fmt(unknown.n)} / ${fmt(cur.denominator)}) carry no revision date; they are reported as currency-unknown, never as stale.`,
    ...(r.limitations || []),
  ].filter(Boolean);

  return (
    <div>
      <PageHead kicker={`Corpus audit · paper reproduction · ${SCOPE_LABEL[scope].toLowerCase()}`} title="Attribution corpus overview"
        lead={`Composition, corroboration depth, agreement diagnostics and independence. ${SCOPE_INTRO[scope]} Every figure carries its denominator and the population it was counted over; click a figure to open the records behind it.`} />

      <MetricStrip items={[
        { label: "Claims", value: fmt(claims.value), sub: `across ${claims.sources} sources`, tag: popTag(claims) },
        has(norm)
          ? { label: "Normalized addresses", value: fmt(norm.value), sub: "after source-specific normalization", tag: popTag(norm) }
          : { label: "Normalized addresses", value: "not available", text: true, sub: "needs the full corpus loaded", tag: popTag(norm) },
        { label: "Raw address keys", value: fmt(raw.value), sub: "before cross-source normalization", tag: popTag(raw) },
        { label: "Multi-dataset addresses", value: fmt(multi.value), top: true, tag: popTag(multi),
          sub: full ? `${pct(multi.share)} of ${fmt(multi.denominator)} normalized addresses · in ≥2 datasets`
            : "in the bundled sample · the full corpus adds more after normalization",
          to: link("/claims?comparable=yes", multi) },
        { label: "Unresolved provenance", value: pct(unres.share), tone: "hot", top: "hot", tag: popTag(unres),
          sub: <>{fmt(unres.numerator)} / {fmt(unres.denominator)} {popNoun(unres)}<br />{pct(unres.resolved_share)} have a resolved provenance root</>,
          to: link("/claims?provenance=unresolved", unres) },
      ]} />

      <Section title="Reference comparability" sec="5.1" tag={popTag(multi)}
        note="Addresses for which at least one second public attribution claim exists. The remainder is not unreliable; it has no public cross-source comparison available in this corpus.">
        {full ? (
          <div className="split c2">
            <Cell label="Multi-dataset addresses, named by ≥2 datasets" big={pct(multi.share)} tone="ok"
              den={`${fmt(multi.numerator)} / ${fmt(multi.denominator)} ${popNoun(multi)}`} share={multi.share} fill="var(--tl)" to={link("/claims?comparable=yes", multi)} />
            <Cell label="No public cross-source comparison available (single-source)" big={pct(single.share)}
              den={`${fmt(single.numerator)} / ${fmt(single.denominator)} ${popNoun(single)}`} share={single.share} fill="var(--nt2)" to={link("/claims?outcome=single-source", single)} />
          </div>
        ) : (
          <div className="split c2">
            <Cell label="Multi-dataset addresses in the bundled sample" big={fmt(multi.value)} den="sample addresses, no corpus-wide share"
              to={link("/claims?comparable=yes", multi)} />
            <Cell label="No public cross-source comparison available (single-source)" big="—" den="needs the normalized full corpus" />
          </div>
        )}
      </Section>

      <Section title="Agreement diagnostics" sec="5.1" tag={popTag(agr)}
        meta={`n = ${fmt(agr.value)} ${full ? "" : "sample "}multi-dataset addresses`}
        note={full ? "Diagnostic and taxonomy-sensitive, not a headline reliability score."
          : "Diagnostic and taxonomy-sensitive, not a headline reliability score. These outcomes refer to the frozen research sample; the full normalized corpus adds multi-dataset addresses through the WatchYourBack marker join and is available only when it is loaded."}>
        <div className="panel pad">
          <BarRows rows={agreementRows(agr.outcomes, `&population=${agr.population}`)} />
          <Legend items={[
            { label: "agreement", fill: "var(--tl)" }, { label: "refinement", fill: "var(--oc)" },
            { label: "conflict", fill: "var(--ac)" }, { label: "no shared taxonomy path", hatch: true }]} />
        </div>
        <p className="section-note" style={{ marginTop: 11 }}>
          Datasets naming a multi-dataset address: {depth.parts.map((x) => `${x.key} datasets: ${fmt(x.n)}`).join(" · ")} (of {fmt(depth.denominator)}{full ? " normalized" : " sample"} multi-dataset addresses).
        </p>
      </Section>

      <Section title="Chance-corrected agreement" tag={popTag(agr)} meta={`Cohen’s κ · ${kappa.n_pairs} pairs`}
        note="Raw agreement flatters a corpus dominated by one category. κ is shown only where the shared region is not single-class.">
        <Kappa kappa={kappa} />
      </Section>

      <Section title="Provenance concentration" sec="5.2" tag={popTag(roots)} meta={`${roots.value} roots · ${roots.identified} identified`}>
        <div className="panel pad">
          <BarRows cols="250px 1fr 66px 170px" rows={ind.root_concentration.map((x) => ({
            key: x.root, label: x.root, labelMono: true, share: x.share, pct: pct(x.share),
            n: `${fmt(x.claims)} / ${fmt(roots.denominator)}`, fill: "var(--nt)", hatch: !x.resolved }))} />
          <Legend items={[{ label: "resolved root", fill: "var(--nt)" }, { label: "unresolved root", hatch: true }]} />
        </div>
        <p className="section-note" style={{ marginTop: 11 }}>
          Unit: claims. Top {ind.root_concentration.length} of {roots.value} roots by claim count. Apparent multi-dataset corroboration can still collapse into one root; see <Link to="/provenance">Provenance</Link>.
        </p>
      </Section>

      <Section title="Claim contribution by source" tag={popTag(contrib)} meta={`${contrib.parts.length} sources`}
        note="Unit: claims. Each source's claim count over the corpus's total claims; a source's unique-address count is a different unit and is not divided by claims here.">
        <div className="panel pad">
          <BarRows cols="190px 1fr 74px 170px" rows={contrib.parts.map((x) => ({
            key: x.key, label: x.key, labelMono: true, share: x.share, pct: pct(x.share),
            n: `${fmt(x.n)} / ${fmt(contrib.denominator)}`, fill: "var(--nt)", to: link(`/claims?source=${x.key}`, contrib) }))} />
        </div>
      </Section>

      <Section title={full ? "Currency" : "Sample currency diagnostics"} tag={popTag(cur)} meta={`as of ${r.overview.analysis_as_of}`}
        note="A claim with no revision date is currency-unknown, never stale: absence of a date is not evidence of staleness.">
        <div className="panel pad">
          <div className="pophead"><b>{full ? "LIVE FULL CORPUS" : "BUNDLED SAMPLE"}</b> · {fmt(cur.value)} claims</div>
          <BarRows cols="230px 1fr 74px 170px" rows={currencyRows(cur.parts, fmt(cur.denominator), link("/claims", cur))} />
          {!full && (
            <div className="small mut" style={{ marginTop: 10 }}>
              Judged at {r.overview.analysis_as_of} over {fmt(cur.value)} claims in the bundled sample, of {fmt(cur.corpus_n_claims)} in the corpus. Sample proportions are not corpus-wide rates.
              {" "}Claims without a revision field across the full corpus: {has(noRev) ? `${fmt(noRev.numerator)} / ${fmt(noRev.denominator)}` : "not available from the sample; it needs the full corpus."}
            </div>
          )}
        </div>
      </Section>

      <Limitations items={limits} />
      <ReliabilityProfile profile={r.reliability_profile} />
    </div>
  );
}

// --------------------------------------------------------------------- upload
const uploadCurrencyParts = (f) => ["current", "stale", "currency_unknown"].map((k) => ({ key: k, n: f[k], share: f[`${k}_share`] }));

function UploadOverview() {
  const { result: r, meta } = useAnalysis();
  const ta = r.target_audit;
  const p = ta.profile;
  const sh = r.shares;
  const v = r.validation;
  const nT = fmt(ta.n_target_addresses);
  const rc = p.reference_comparability;
  const prov = p.provenance;
  const ind = p.independence;
  const ev = p.evidence_class;
  const hasReference = !!rc?.available;
  const limits = [...(r.limitations || [])];
  for (const l of ta.limitations || []) if (!limits.includes(l)) limits.push(l);

  const caseMeta = r.dataset_preflight?.case_metadata;
  const relProv = r.relational_provenance;
  const deps = r.dependency_candidates;
  const dp = r.dataset_profile;

  return (
    <div>
      <PageHead kicker="Target audit · uploaded dataset" title="Dataset reliability profile"
        lead={`${meta.dataset_name}: provenance, agreement with the reference corpus, independence and currency for the addresses in your file. Every figure carries its denominator; click a figure to open the records behind it.`} />

      <MetricStrip items={[
        { label: "Target claims", value: fmt(ta.n_target_claims), sub: `${fmt(v.n_valid)} of ${fmt(v.n_input)} rows valid` },
        { label: "Target addresses", value: nT, sub: "distinct addresses in the file" },
        hasReference
          ? { label: "Reference match", value: pct(rc.comparable_share), sub: `${fmt(rc.comparable)} / ${nT} also named in the reference corpus`, to: "/claims?comparable=yes", top: true }
          : { label: "Reference match", value: "not run", text: true, sub: "reference comparison was switched off" },
        { label: "Unresolved provenance", value: prov.available ? pct(sh.unresolved_addr_share) : "—", tone: "hot", top: "hot",
          sub: prov.available ? <>{fmt(prov.unresolved)} / {nT} addresses<br />{pct(sh.resolved_addr_share)} have a resolved provenance root</> : "not available",
          to: "/claims?provenance=unresolved" },
      ]} />

      {caseMeta && Object.keys(caseMeta).length > 0 && (
        <div className="inline-note" role="alert" style={{ whiteSpace: "pre-line" }}>
          {(caseMeta.recovery_status || caseMeta.analysis_origin) && (
            <>
              <strong>RECOVERED DATASET SUBSET</strong>
              {"\n"}This analysis does not represent the complete original database.{"\n\n"}
            </>
          )}
          {Object.entries(caseMeta).map(([k, val]) => `${k.replace(/_/g, " ")}: ${val}`).join("\n")}
        </div>
      )}

      {relProv && dp && (
        <Section title="Evidence profile: what this extraction does and does not establish"
          note="Technically valid data is not the same claim as forensically defensible attribution - a valid address and a present label do not by themselves establish resolved, independent provenance.">
          <MetricStrip items={[
            { label: "Address validity", value: v.n_identifiers_checked
                ? `${fmt(v.n_identifiers_checked - v.n_identifiers_invalid)} / ${fmt(v.n_identifiers_checked)} valid`
                : "not checked", sub: "technically valid per the chain's own syntax rules" },
            { label: "Label coverage", value: (r.schema_mapping?.label || r.schema_mapping?.category) ? "available" : "not available",
              sub: `${fmt(dp.scale.unique_labels)} distinct label(s)` },
            { label: "Provenance", value: Object.entries(relProv.counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "unresolved",
              sub: Object.entries(relProv.counts).map(([k2, n2]) => `${k2}: ${fmt(n2)}`).join(" · ") },
            { label: "Independent corroboration", value: ind?.available ? "established" : "not established",
              sub: ind?.available ? `${fmt(ind.confirmed_independent_multi_root)} confirmed independent multi-root` : ind?.reason, tone: ind?.available ? undefined : "hot" },
            { label: "Source descriptors", value: dp.scale.unique_sources ? "present" : "absent",
              sub: `${fmt(dp.scale.unique_sources)} declared source string(s)` },
            { label: "Confirmed independent roots", value: ind?.available ? fmt(ind.confirmed_independent_multi_root) : "not established",
              sub: "a declared source string is not, by itself, a confirmed independent evidential root", tone: ind?.available ? undefined : "hot" },
          ]} />

          {deps && deps.length > 0 && (
            <div className="panel pad" style={{ marginTop: 12 }}>
              <strong>Declared source descriptor vs. confirmed provenance root</strong>
              <p className="mut" style={{ fontSize: 12 }}>
                N distinct declared-source strings are not N independent evidential roots. THEMIS found the
                following potential / documented dependencies among this dataset's own declared-source values
                (never applied to any independence or corroboration count):
              </p>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
                {deps.map((d, i) => <li key={i}><span className="mono">{d.citing}</span> - potential/documented dependency on <span className="mono">{d.cited}</span></li>)}
              </ul>
            </div>
          )}

          {!ind?.available && (
            <p className="mut" style={{ fontSize: 12.5, marginTop: 10 }}>
              <strong>Investigative interpretation.</strong> The dataset contains usable attribution records, but
              the evidence needed to treat its source descriptors as independent forensic corroboration is not established.
            </p>
          )}
        </Section>
      )}

      {hasReference && (
        <Section title="Reference comparability"
          note="In an uploaded analysis, reference match means the address is also named by at least one claim in the reference corpus. It is a different measure from the multi-dataset count in a paper reproduction.">
          <div className="split c2">
            <Cell label="Reference match, also named in the reference corpus" big={pct(rc.comparable_share)} tone="ok"
              den={`${fmt(rc.comparable)} / ${nT}`} share={rc.comparable_share} fill="var(--tl)" to="/claims?comparable=yes" />
            <Cell label="No reference match" big={pct(rc.no_reference_match_share)}
              den={`${fmt(rc.no_reference_match)} / ${nT}`} share={rc.no_reference_match_share} fill="var(--nt2)" to="/claims?comparable=no" />
          </div>
        </Section>
      )}

      {p.agreement?.available && (
        <Section title="Agreement outcomes" meta={`n = ${fmt(p.agreement.n_comparable)} reference-matched addresses`}
          note="Your label for each address against every reference claim for it. Conflicts here are disagreements, not verdicts about which source is right.">
          <div className="panel pad"><BarRows rows={agreementRows(p.agreement.outcomes)} /></div>
        </Section>
      )}

      {prov.available && (
        <Section title="Provenance and independence" meta={`${nT} target addresses`}
          note="Resolved means the evidence origin is identified. Unresolved is never counted as an independent source.">
          <div className="panel pad">
            <BarRows cols="270px 1fr 74px 130px" rows={[
              { key: "res", label: "Resolved provenance root", share: sh.resolved_addr_share, pct: pct(sh.resolved_addr_share), n: `${fmt(prov.resolved)} / ${nT}`, fill: "var(--tl)", to: "/claims?provenance=resolved" },
              { key: "unres", label: "Unresolved provenance", share: sh.unresolved_addr_share, pct: pct(sh.unresolved_addr_share), n: `${fmt(prov.unresolved)} / ${nT}`, hatch: true, labelColor: "var(--ac)", to: "/claims?provenance=unresolved" },
              ...(ind?.available && p.agreement?.n_comparable ? [
                { key: "ci", label: "Confirmed independent multi-root", share: sh.confirmed_independent_share, pct: pct(sh.confirmed_independent_share), n: `${fmt(ind.confirmed_independent_multi_root)} / ${fmt(p.agreement.n_comparable)}`, fill: "var(--tl)" },
                { key: "sh", label: "Shared or inherited only", share: sh.shared_or_inherited_share, pct: pct(sh.shared_or_inherited_share), n: `${fmt(ind.shared_or_inherited_only)} / ${fmt(p.agreement.n_comparable)}`, fill: "var(--ac)" },
                { key: "iu", label: "Independence unresolved", share: sh.independence_unresolved_share, pct: pct(sh.independence_unresolved_share), n: `${fmt(ind.independence_unresolved)} / ${fmt(p.agreement.n_comparable)}`, hatch: true },
              ] : []),
            ]} />
          </div>
        </Section>
      )}

      {p.currency?.available && (
        <Section title="Currency" meta={`as of ${meta.analysis_as_of_date}`}
          note="A claim with no revision date is currency-unknown, never stale.">
          <div className="panel pad"><BarRows cols="230px 1fr 74px 170px" rows={currencyRows(uploadCurrencyParts(p.currency), fmt(p.currency.n_claims ?? ta.n_target_claims))} /></div>
        </Section>
      )}

      {ev?.available && (
        <Section title="Evidence class" meta={`${fmt(ta.n_target_claims)} target claims`}
          note="An upload with no declared methodology stays unknown: it is never silently upgraded to derived.">
          <div className="panel pad">
            <BarRows cols="230px 1fr 74px 170px" rows={[
              ["verified", "Verified", "var(--tl)", "verified"], ["derived", "Derived", "var(--oc)", "derived"],
              ["unverified_report", "Unverified report", "var(--nt)", "unverified-report"], ["unknown", "Unknown", null, "unknown"],
            ].map(([k, label, fill, q]) => ({ key: k, label, share: ev[`${k}_share`], pct: pct(ev[`${k}_share`]), n: `${fmt(ev[k])} / ${fmt(ta.n_target_claims)}`,
              fill, hatch: !fill, to: `/claims?evidence_tier=${q}` }))} />
          </div>
        </Section>
      )}

      {v.n_rejected > 0 && (
        <Section title="Rejected rows" meta={`${fmt(v.n_rejected)} of ${fmt(v.n_input)} input rows`}>
          <div className="tablewrap"><table>
            <thead><tr><th>Row</th><th>Reason</th><th>Address</th></tr></thead>
            <tbody>{v.rejected.slice(0, 10).map((x, i) => <tr key={i}><td className="mono">{x.row}</td><td>{x.reason}</td><td className="mono small">{x.address || "—"}</td></tr>)}</tbody>
          </table>
          {v.rejected.length > 10 && <div className="tablefoot">Showing 10 of {fmt(v.rejected.length)} rejected rows.</div>}
          </div>
        </Section>
      )}

      <Limitations items={limits} />
      <ReliabilityProfile profile={r.reliability_profile || p} />
    </div>
  );
}
