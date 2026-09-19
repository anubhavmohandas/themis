import { useState } from "react";
import { Link } from "react-router-dom";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, humanize, kappaText, pct } from "../lib/format.js";
import { OUTCOMES } from "../lib/vocab.js";
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

function currencyRows(f, nLabel) {
  return [
    { key: "current", label: "Current", n: f.current, share: f.current_share, fill: "var(--tl)", to: "/claims?currency=current" },
    { key: "stale", label: "Stale", n: f.stale, share: f.stale_share, fill: "var(--oc)", to: "/claims?currency=stale" },
    { key: "unknown", label: "Currency unknown (no revision date)", n: f.currency_unknown, share: f.currency_unknown_share,
      hatch: true, to: "/claims?currency=currency-unknown" },
  ].map((r) => ({ ...r, pct: pct(r.share), n: `${fmt(r.n)} / ${nLabel}` }));
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
function PaperOverview() {
  const { result: r } = useAnalysis();
  const { dataset_summary: ds, agreement: ag, independence: ind, kappa, freshness: f, shares: sh } = r;
  const nAddr = fmt(ds.n_addresses);
  const nSources = Object.keys(ds.sources).length;
  const top = ind.root_concentration?.[0];

  const limits = [
    `${pct(sh.single_source_share)} of addresses (${fmt(ag.single_source)} / ${nAddr}) carry a claim from exactly one dataset, so no public cross-source comparison is possible for them.`,
    `${pct(ind.unresolved_addr_share)} of addresses (${fmt(ind.unresolved_addresses)} / ${nAddr}) resolve to no identified provenance root. Unresolved is never scored as independent.`,
    top && `The largest root, ${top.root}, accounts for ${pct(top.share)} of all claims (${fmt(top.claims)} / ${fmt(ds.n_claims)}) and is ${top.resolved ? "identified" : "unresolved"}.`,
    kappa.n_undefined > 0 && `κ is undefined for ${fmt(kappa.n_undefined)} of ${fmt(kappa.n_pairs)} overlapping pairs because the shared region is single-class.`,
    `${pct(f.currency_unknown_share)} of the ${fmt(f.n_claims)} claims analysed (${fmt(f.currency_unknown)} / ${fmt(f.n_claims)}${r.freshness_scope?.sample ? ", bundled sample" : ""}) carry no revision date; they are reported as currency-unknown, never as stale.`,
    ...(r.limitations || []),
  ].filter(Boolean);

  return (
    <div>
      <PageHead kicker="Corpus audit · paper reproduction" title="Attribution corpus overview"
        lead="Composition, corroboration depth, agreement outcomes and independence, computed from the bundled seven-source reference corpus. Every figure carries its denominator; click a figure to open the records behind it." />

      <MetricStrip items={[
        { label: "Claims", value: fmt(ds.n_claims), sub: `across ${nSources} sources` },
        { label: "Addresses", value: nAddr, sub: "distinct, at least one claim" },
        { label: "Multi-dataset addresses", value: pct(ag.multi_source_rate),
          sub: `${fmt(ag.n_multi_source)} / ${nAddr} · appear in ≥2 datasets`, to: "/claims?comparable=yes", top: true },
        { label: "Unresolved provenance", value: pct(ind.unresolved_addr_share), tone: "hot", top: "hot",
          sub: <>{fmt(ind.unresolved_addresses)} / {nAddr} addresses<br />{pct(sh.resolved_addr_share)} have a resolved provenance root</>,
          to: "/claims?provenance=unresolved" },
      ]} />

      <Section title="Reference comparability" sec="5.1"
        note="Addresses for which at least one second public attribution claim exists. The remainder is not unreliable: it is unverifiable against any other public source.">
        <div className="split c2">
          <Cell label="Multi-dataset addresses, named by ≥2 datasets" big={pct(ag.multi_source_rate)} tone="ok"
            den={`${fmt(ag.n_multi_source)} / ${nAddr}`} share={ag.multi_source_rate} fill="var(--tl)" to="/claims?comparable=yes" />
          <Cell label="No public comparison available (single-source)" big={pct(sh.single_source_share)}
            den={`${fmt(ag.single_source)} / ${nAddr}`} share={sh.single_source_share} fill="var(--nt2)" to="/claims?outcome=single-source" />
        </div>
      </Section>

      <Section title="Agreement outcomes" sec="5.1" meta={`n = ${fmt(ag.n_multi_source)} multi-dataset addresses`}>
        <div className="panel pad">
          <BarRows rows={agreementRows(ag.outcomes)} />
          <Legend items={[
            { label: "agreement", fill: "var(--tl)" }, { label: "refinement", fill: "var(--oc)" },
            { label: "conflict", fill: "var(--ac)" }, { label: "no shared taxonomy path", hatch: true }]} />
        </div>
        {ag.sources_per_address && (
          <p className="section-note" style={{ marginTop: 11 }}>
            Datasets naming a multi-dataset address: {Object.entries(ag.sources_per_address).filter(([k]) => Number(k) > 1)
              .map(([k, n]) => `${k} datasets: ${fmt(n)}`).join(" · ")} (of {fmt(ag.n_multi_source)}).
          </p>
        )}
      </Section>

      <Section title="Chance-corrected agreement" meta={`Cohen’s κ · ${kappa.n_pairs} pairs`}
        note="Raw agreement flatters a corpus dominated by one category. κ is shown only where the shared region is not single-class.">
        <Kappa kappa={kappa} />
      </Section>

      <Section title="Provenance concentration" sec="5.2" meta={`${ind.n_roots_total} roots · ${ind.n_roots_identified} identified`}>
        <div className="panel pad">
          <BarRows cols="250px 1fr 66px 170px" rows={ind.root_concentration.map((x) => ({
            key: x.root, label: x.root, labelMono: true, share: x.share, pct: pct(x.share),
            n: `${fmt(x.claims)} / ${fmt(ds.n_claims)}`, fill: "var(--nt)", hatch: !x.resolved }))} />
          <Legend items={[{ label: "resolved root", fill: "var(--nt)" }, { label: "unresolved root", hatch: true }]} />
        </div>
        <p className="section-note" style={{ marginTop: 11 }}>
          Top {ind.root_concentration.length} of {ind.n_roots_total} roots by claim count. Apparent multi-dataset corroboration can still collapse into one root; see <Link to="/provenance">Provenance</Link>.
        </p>
      </Section>

      <Section title="Source coverage" meta={`${nSources} sources`}>
        <div className="panel pad">
          <BarRows cols="190px 1fr 74px 170px" rows={Object.entries(ds.sources).map(([name, n]) => ({
            key: name, label: name, labelMono: true, share: sh.source_claim_shares[name], pct: pct(sh.source_claim_shares[name]),
            n: `${fmt(n)} / ${fmt(ds.n_claims)}`, fill: "var(--nt)", to: `/claims?source=${name}` }))} />
        </div>
      </Section>

      <Section title="Currency" meta={`as of ${r.analysis_as_of_date}`}
        note="A claim with no revision date is currency-unknown, never stale: absence of a date is not evidence of staleness.">
        <div className="panel pad">
          <BarRows cols="230px 1fr 74px 170px" rows={currencyRows(f, fmt(f.n_claims))} />
          {r.freshness_scope && (
            <div className="small mut" style={{ marginTop: 10 }}>
              Judged at {r.analysis_as_of_date} over {fmt(r.freshness_scope.n_claims_analysed)} claims
              {r.freshness_scope.sample ? ` in the bundled sample, of ${fmt(r.freshness_scope.corpus_n_claims)} in the corpus. Sample proportions are not corpus-wide rates.` : "."}
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

  return (
    <div>
      <PageHead kicker="Target audit · uploaded dataset" title="Dataset reliability profile"
        lead={`${meta.dataset_name}: provenance, agreement with the bundled reference corpus, independence and currency for the addresses in your file. Every figure carries its denominator; click a figure to open the records behind it.`} />

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

      {hasReference && (
        <Section title="Reference comparability"
          note="In an uploaded analysis, reference match means the address is also named by at least one claim in the bundled reference corpus. It is a different measure from the multi-dataset count in a paper reproduction.">
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
          <div className="panel pad"><BarRows cols="230px 1fr 74px 170px" rows={currencyRows(p.currency, fmt(p.currency.n_claims ?? ta.n_target_claims))} /></div>
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
