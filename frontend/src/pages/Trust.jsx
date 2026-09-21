import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useApiData } from "../lib/useApi.js";
import { useAnalysis } from "../lib/AnalysisContext.jsx";
import { fmt, pct, usd } from "../lib/format.js";
import { BarRows, ErrorBox, Gate, Loading, PageHead, Section } from "../components/ui.jsx";

export default function TrustPage() {
  return <Gate><Body /></Gate>;
}
function Body() {
  const { isPaper } = useAnalysis();
  return isPaper ? <PaperTrust /> : <UploadTrust />;
}

// ---------------------------------------------------------------- paper (A-D)
const ACCENT = { A: "var(--nt2)", B: "var(--nt)", C: "var(--tl)", D: "var(--ac)" };

function PaperTrust() {
  const { analysisId } = useAnalysis();
  const { data, error, loading } = useApiData(() => api.drift(analysisId), [analysisId]);
  const conds = data ? Object.entries(data.conditions) : [];
  const maxRatio = Math.max(...conds.map(([, c]) => c.ratio_vs_B), 0.0001);
  const D = data?.conditions?.D;

  return (
    <div>
      <PageHead kicker="Trust-rule sensitivity" title="Same corpus, same procedure, four trust rules"
        lead="The bundled forensic task is ransomware revenue estimation. Coverage always travels with the figure: a revenue number without its retained address count is an incomplete result." />
      {loading && <Loading>Computing trust-rule sensitivity…</Loading>}
      {error && <ErrorBox title="Could not load drift">{error}</ErrorBox>}
      {data && (
        <>
          <Section title="Ransomware revenue under four rules" sec="5.3" meta="USD, identical arithmetic">
            <div className="panel pad">
              {conds.map(([letter, c]) => (
                <div key={letter} style={{ display: "grid", gridTemplateColumns: "26px minmax(150px,1fr) minmax(220px,2fr) minmax(130px,auto)", gap: 16, alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--rls)" }}>
                  <div className="mono" style={{ fontSize: 15, fontWeight: 600, color: ACCENT[letter] }}>{letter}</div>
                  <div><div style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.35 }}>{c.label}</div>
                    <div className="mono mut" style={{ fontSize: 11, marginTop: 3 }}>{fmt(c.addresses)} addresses · {fmt(c.observations)} observations</div></div>
                  <div>
                    <div className="bar-track" style={{ height: 16 }}><i style={{ width: `${(c.ratio_vs_B / maxRatio) * 100}%`, background: ACCENT[letter] }} /></div>
                    <div className="mono mut" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", marginTop: 5, fontSize: 11 }}>
                      <span>coverage {pct(c.coverage_vs_B, 1)} of baseline B</span><span>{c.ratio_vs_B.toFixed(2)}× vs. baseline B</span></div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="mono" style={{ fontSize: 17, fontWeight: 500, whiteSpace: "nowrap" }} title={`$${Math.round(c.usd).toLocaleString("en-US")}`}>{usd(c.usd)}</div>
                    <div className="mut" style={{ fontSize: 11, marginTop: 2 }}>at {pct(c.coverage_vs_B, 1)} coverage</div></div>
                </div>
              ))}
              <div style={{ display: "flex", gap: 26, flexWrap: "wrap", marginTop: 16, fontSize: 12, color: "var(--mut)" }}>
                <span>Spread B / D <span className="mono" style={{ color: "var(--ink)" }}>{data.spread_B_over_D.toFixed(1)}×</span></span>
                <span>Spread A / D <span className="mono" style={{ color: "var(--ink)" }}>{data.spread_A_over_D.toFixed(1)}×</span></span>
                <span>Addresses named by more than one dataset <span className="mono" style={{ color: "var(--ink)" }}>{fmt(data.shared_addresses)}</span></span>
              </div>
            </div>
          </Section>

          <div className="callout" style={{ marginBottom: 26 }}>
            <div className="co-body">
              <span className="eyebrow" style={{ display: "block", marginBottom: 7, color: "var(--ink)" }}>Reading this correctly</span>
              The interpretation is not that the lowest- or highest-coverage condition is right. It is that the forensic conclusion moves by an order of magnitude depending on which labels are considered sufficiently trustworthy.
              {D && <> Condition D retains {pct(D.coverage_vs_B, 1)} of the baseline’s addresses ({fmt(D.addresses)} / {fmt(data.conditions.B.addresses)}); that is a coverage trade-off, not a better estimate for the rest. It uses the highest <em>declared</em> confidence tier, which is not independently verified ground truth.</>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------ uploaded: policy preview
function UploadTrust() {
  const { analysisId } = useAnalysis();
  const [selected, setSelected] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(true);

  // Coverage is computed by the backend for exactly the rules ticked here.
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    api.trustCoverage(analysisId, selected)
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [analysisId, selected.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div>
      <PageHead kicker="Trust-policy preview" title="How much of this evidence survives a trust rule?"
        lead="An uploaded dataset has no ransomware-revenue task, so this screen reports evidence retention: how many of your claims and addresses remain eligible under the rules you choose. Retained does not mean correct, and dropped does not mean wrong." />
      {error && <ErrorBox title="Could not compute coverage">{error}</ErrorBox>}
      {!data && !error && <Loading>Loading trust rules…</Loading>}
      {data && (
        <div className="two-col">
          <div>
            <Section title="Policy" meta={`${selected.length} of ${data.rules.length} rules selected`}>
              <div className="panel">
                {data.rules.map((r) => (
                  <label key={r.id} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "12px 18px", borderBottom: "1px solid var(--rls)", cursor: "pointer" }}>
                    <input type="checkbox" checked={selected.includes(r.id)} onChange={() => toggle(r.id)} style={{ marginTop: 3 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 500 }}>{r.label}</div>
                      <div className="rl-desc">{r.help}</div>
                      {r.state === "computed"
                        ? <div className="mono mut" style={{ fontSize: 11, marginTop: 4 }}>alone keeps {fmt(r.claims)} / {fmt(data.universe.claims)} claims ({pct(r.claims_share)})</div>
                        : <div className="hot" style={{ fontSize: 11.5, marginTop: 4 }}>Not applicable — {r.reason}. This rule is skipped, not counted as keeping every claim.</div>}
                    </div>
                  </label>
                ))}
              </div>
            </Section>

            <Section title="Retention under each rule on its own" meta={`${fmt(data.universe.claims)} claims`}>
              <div className="panel pad">
                <BarRows cols="260px 1fr 74px 130px" rows={data.rules.filter((r) => r.state === "computed").map((r) => ({
                  key: r.id, label: r.label, share: r.claims_share, pct: pct(r.claims_share), n: `${fmt(r.claims)} / ${fmt(data.universe.claims)}`,
                  fill: selected.includes(r.id) ? "var(--ac)" : "var(--nt2)" }))} />
              </div>
            </Section>
          </div>

          <aside style={{ position: "sticky", top: 66, display: "flex", flexDirection: "column", gap: 12, opacity: busy ? 0.6 : 1 }}>
            <div className="panel pad">
              <div className="form-label">Eligible claims</div>
              <div className="mono" style={{ fontSize: 24, fontWeight: 500 }}>{fmt(data.eligible.claims)}<span className="mut" style={{ fontSize: 14 }}> / {fmt(data.universe.claims)}</span></div>
              <div className="mono" style={{ fontSize: 13, marginTop: 4 }}>coverage {pct(data.eligible.claims_share)}</div>
              <div className="meter"><i style={{ width: `${data.eligible.claims_share * 100}%`, background: "var(--tl)" }} /></div>
              <div className="form-label" style={{ marginTop: 16 }}>Eligible addresses</div>
              <div className="mono" style={{ fontSize: 16 }}>{fmt(data.eligible.addresses)}<span className="mut" style={{ fontSize: 12 }}> / {fmt(data.universe.addresses)}</span> · {pct(data.eligible.addresses_share)}</div>
            </div>
            {data.steps.length > 0 && (
              <div className="panel pad">
                <div className="form-label">Applied in order</div>
                <div className="steps">
                  {data.steps.map((s) => (
                    <div key={s.rule} className="step"><span className="mk">→</span>
                      <div>{data.rules.find((r) => r.id === s.rule)?.label}<div className="d">{s.state === "computed" ? `${fmt(s.claims)} claims · ${fmt(s.addresses)} addresses remain` : `not applicable — ${s.reason}; skipped`}</div></div></div>
                  ))}
                </div>
              </div>
            )}
            <div className="sample-banner" style={{ margin: 0 }}>{data.note}</div>
          </aside>
        </div>
      )}
    </div>
  );
}
