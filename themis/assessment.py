"""The closing verdict on an uploaded dataset: is this public source dataset
reliable enough to use, and why.

It reads only what the pipeline already measured (validation, internal
consistency, the target-vs-reference audit, provenance, currency) and applies
the cut-offs in config/assessment.yml. It computes nothing new about the data,
so the verdict can never disagree with the tables above it.

    TRUSTWORTHY               measured, and no problem found at any level
    TRUSTWORTHY WITH CAVEATS  same, but limits the reader must carry are listed
    NOT ESTABLISHED           nothing measured is wrong, yet too little independent
                              evidence exists to say it is right (absence of evidence
                              is never promoted to trust)
    NOT TRUSTWORTHY           a measured problem large enough to rule the labels out
    CANNOT ASSESS             the dataset did not pass pre-flight; nothing was analysed

The verdict speaks about the evidence for the labels (consistency, corroboration,
independence, currency). It does not prove any single label correct: coverage is
not accuracy.
"""
from __future__ import annotations
import collections, hashlib, json

from . import config_io, target_audit

TRUSTWORTHY = "TRUSTWORTHY"
WITH_CAVEATS = "TRUSTWORTHY WITH CAVEATS"
NOT_ESTABLISHED = "NOT ESTABLISHED"
NOT_TRUSTWORTHY = "NOT TRUSTWORTHY"
CANNOT_ASSESS = "CANNOT ASSESS"

MEANING = {
    TRUSTWORTHY: "The file is internally sound and independent public evidence agrees with it; no problem was measured.",
    WITH_CAVEATS: "The file is internally sound and public evidence agrees with it, but the limits listed below apply to any use of it.",
    NOT_ESTABLISHED: "Nothing measured is wrong, but there is not enough independent evidence to say the labels are right.",
    NOT_TRUSTWORTHY: "A measured problem is large enough that the labels should not be relied on until it is resolved.",
    CANNOT_ASSESS: "The dataset did not pass pre-flight, so nothing was analysed and no verdict on its labels exists.",
}
SCOPE = ("This is a judgement of the evidence behind the labels (consistency, corroboration, independence, "
         "currency), not proof that any single label is correct: coverage is not accuracy.")

OK, CAVEAT, FAIL = "ok", "caveat", "fail"


def _level(cfg: dict, name: str, share: float) -> str:
    th = cfg[name]
    return FAIL if "fail" in th and share >= th["fail"] else CAVEAT if share >= th["caveat"] else OK


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%" if x >= 0.001 or x == 0 else f"{100 * x:.2f}%"


def _internal(result: dict) -> dict | None:
    return result.get("internal_consistency") or (result.get("conflicts") or {}).get("internal_consistency")


def _cfg_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()


def assess(result: dict) -> dict:
    cfg = config_io.load().assessment
    if result.get("stopped"):
        return _pack(CANNOT_ASSESS, [dict(level=FAIL, text=(result.get("message") or "The dataset did not pass pre-flight.").split("\n")[0])], cfg)

    findings: list[dict] = []          # level: ok | caveat | fail | info

    def add(level, text):
        findings.append(dict(level=level, text=text))

    ta = result["target_audit"]
    profile = ta["profile"]
    n_addr, n_claims = ta["n_target_addresses"], ta["n_target_claims"]
    v = result.get("validation") or {}

    # --- the file itself
    if v.get("n_input"):
        rej = v["n_rejected"]
        lvl = _level(cfg, "rejected_row_share", rej / v["n_input"])
        add(lvl,
            f"{rej:,} of {v['n_input']:,} rows ({_pct(rej / v['n_input'])}) failed identifier validation and were rejected."
            if rej else f"All {v['n_input']:,} rows carried a valid identifier.")

    ic = _internal(result)
    if ic and n_addr:
        n_contra = ic["internal contradiction"]["n"]
        lvl = _level(cfg, "internal_contradiction_share", n_contra / n_addr)
        add(lvl, f"{n_contra:,} of {n_addr:,} addresses ({_pct(n_contra / n_addr)}) carry labels in this file that contradict each other."
            if n_contra else f"No address in the file contradicts itself ({n_addr:,} checked).")

    claims = result.get("claims") or []
    if claims:
        n_unk = sum(1 for c in claims if c.get("canon") == "unknown")
        lvl = _level(cfg, "uninterpretable_label_share", n_unk / len(claims))
        if lvl != OK:
            add(lvl, f"{n_unk:,} of {len(claims):,} claims ({_pct(n_unk / len(claims))}) use a label THEMIS's taxonomy cannot place, "
                     "so they can be neither confirmed nor contradicted.")

    # --- against public reference evidence
    rc = profile.get("reference_comparability") or {}
    comparable = rc.get("comparable", 0) if rc.get("available") else 0
    enough = comparable >= cfg["min_comparable_addresses"]
    if not rc.get("available"):
        add("info", "No reference corpus was supplied, so the labels were not tested against any other public source.")
    elif not enough:
        add("info", f"Only {comparable:,} of {n_addr:,} addresses appear in the reference corpus "
                    f"(at least {cfg['min_comparable_addresses']:,} are needed); the labels were not meaningfully tested against other public sources.")
    else:
        lvl = _level(cfg, "no_reference_match_share", rc["no_reference_match_share"])
        add(lvl,
            f"{comparable:,} of {n_addr:,} addresses ({_pct(rc['comparable_share'])}) can be checked against other public sources."
            if lvl == OK else
            f"Only {comparable:,} of {n_addr:,} addresses ({_pct(rc['comparable_share'])}) can be checked against other public sources; "
            "the rest are unverifiable here.")
        outcomes = profile["agreement"]["outcomes"]
        judged = sum(o["n"] for k, o in outcomes.items() if k != "incomparable")
        if judged:
            agree = outcomes["exact"]["n"] + outcomes["hierarchical refinement"]["n"]
            conflict = outcomes["entity-type conflict"]["n"] + outcomes["licit/illicit conflict"]["n"]
            lvl = _level(cfg, "reference_conflict_share", conflict / judged)
            add(lvl, f"{agree:,} of {judged:,} comparable addresses ({_pct(agree / judged)}) agree with the reference; "
                     f"{conflict:,} ({_pct(conflict / judged)}) conflict.")
        same = collections.Counter((ta.get("address_comparability") or {}).values()).get(target_audit.SAME_PROVENANCE, 0)
        if same:
            lvl = _level(cfg, "same_provenance_share", same / comparable)
            if lvl != OK:
                add(lvl, f"{same:,} of {comparable:,} matched addresses ({_pct(same / comparable)}) trace to the same underlying "
                         "provenance as the reference, so that agreement is inherited, not independent confirmation.")

    prov = profile.get("provenance") or {}
    if prov.get("available") and n_addr:
        lvl = _level(cfg, "unresolved_provenance_share", prov["unresolved"] / n_addr)
        if lvl != OK:
            add(lvl, f"The provenance of {prov['unresolved']:,} of {n_addr:,} addresses ({_pct(prov['unresolved'] / n_addr)}) could not be "
                     "established, so independence from other sources cannot be shown.")

    # --- age
    cur = profile.get("currency") or {}
    if cur.get("available") and (result.get("analysis_states") or {}).get("staleness", {}).get("state") == "computed":
        lvl = _level(cfg, "stale_share", cur["stale_share"])
        add(lvl,
            f"{cur['stale']:,} of {cur['n_claims']:,} claims ({_pct(cur['stale_share'])}) are stale by the configured rule."
            if lvl != OK else f"Attributions are current: {_pct(cur['stale_share'])} are stale by the configured rule.")
    else:
        add("info", "Currency was not assessed: no attribution date is available for this dataset.")

    levels = {f["level"] for f in findings}
    if FAIL in levels:
        verdict = NOT_TRUSTWORTHY
    elif not enough:
        verdict = NOT_ESTABLISHED
    elif CAVEAT in levels:
        verdict = WITH_CAVEATS
    else:
        verdict = TRUSTWORTHY
    return _pack(verdict, findings, cfg)


def _pack(verdict: str, findings: list[dict], cfg: dict) -> dict:
    # the reasons that decided the verdict come first: fails, then caveats, then the good news, then gaps
    order = {FAIL: 0, CAVEAT: 1, OK: 2, "info": 3}
    findings = sorted(findings, key=lambda f: order[f["level"]])
    if verdict in (TRUSTWORTHY, WITH_CAVEATS):
        # a "trustworthy" verdict is justified by what held up, and (with caveats) qualified by what did not
        because = [f["text"] for f in findings if f["level"] in (OK, CAVEAT)]
    else:
        because = [f["text"] for f in findings if f["level"] in (FAIL, CAVEAT, "info")] or [f["text"] for f in findings]
    statement = (f"According to the THEMIS report, this dataset is {verdict}, because: "
                 + " ".join(because)) if because else f"According to the THEMIS report, this dataset is {verdict}."
    return dict(verdict=verdict, meaning=MEANING[verdict], statement=statement, findings=findings,
                scope=SCOPE, config_hash=_cfg_hash(cfg))
