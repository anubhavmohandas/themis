"""Provenance roots and the three independence tests.

A *root* is where a claim's evidence actually originates, which is not the same
as the dataset that republished it. Every assignment below traces either to a
field the publisher declares, or to the containment decode in `decode_field`.
Nothing is guessed: `UNRESOLVED` marks lineage we could not establish, and is
deliberately distinct from "shares a root with everything else unresolved".
"""
from __future__ import annotations
import collections

UNRESOLVED_PREFIXES = ("elliptic_undisclosed", "rodwald_own_")

SCHNOERING_ROOT = {
    "Montréal": "montreal_paquet_clouston_2019",
    "Padua": "padua_conti_2018",
    "PaduaSextorsion": "padua_sextortion_2020",
    "BitcoinTalk": "bitcointalk_forum",
    "SDN": "ofac_sdn",
    "CoinbaseMessages": "coinbase_messages",
    "WBTC": "wbtc_disclosure",
    "Exchange": "exchange_self_disclosure",
}
MIN_GROUP = 5   # below this a group cannot establish containment either way

FAMILY_MARKERS = [("princeton", "princeton_huang_2018"),
                  ("padua", "padua_conti_2018"),
                  ("montreal", "montreal_paquet_clouston_2019")]


def root_of(claim: dict) -> str:
    src = claim["source"]
    fam = claim.get("prov_family", "")
    sub = claim.get("subcat", "")
    if src == "ellipticpp":
        return "elliptic_undisclosed"
    if src == "schnoering":
        return SCHNOERING_ROOT.get(sub, "schnoering_other")
    if src == "ransomwhere":
        return "ransomwhere_crowd"
    if src == "watchyourback":
        return "watchyourback_manual"
    if src == "rodwald_ransom":
        letters = fam.split(":", 1)[1] if ":" in fam else ""
        if "R" in letters:                      # decoded: R denotes Ransomwhere
            return "ransomwhere_crowd"
        f = sub.lower()
        for pre, root in FAMILY_MARKERS:
            if f.startswith(pre):
                return root
        return f"rodwald_own_{letters or 'unknown'}"
    if src == "rodwald_mixers":
        letters = fam.split(":", 1)[1] if ":" in fam else ""
        return "walletexplorer" if "W" in letters else "rodwald_mixers_own"
    if src == "tagpack":
        creator = fam.split(":", 1)[1] if ":" in fam else "unknown"
        if "paquet-clouston" in creator.lower():
            return "montreal_paquet_clouston_2019"
        return f"tagpack_{creator}"
    return src


def is_unresolved(root: str) -> bool:
    return root.startswith(UNRESOLVED_PREFIXES)


# ------------------------------------------------------------ test 1: containment
def containment(src_addr: dict[str, set]) -> dict:
    """Share of each source contained in each other source."""
    out = {}
    for a in src_addr:
        for b in src_addr:
            if a == b or not src_addr[a]:
                continue
            inter = len(src_addr[a] & src_addr[b])
            if inter:
                out[(a, b)] = dict(n=inter, share_of_a=inter / len(src_addr[a]))
    return out


# --------------------------------------------- test 2: provenance-field decoding
def decode_field(claims: list[dict], dataset: str, candidate: str,
                 candidate_addrs: set) -> dict:
    """Decode an undocumented provenance field by testing each value group for
    containment in a candidate upstream source.

    A value group either lies wholly inside the candidate or is disjoint from
    it; anything in between is inconclusive. Returns the verdict per group.
    """
    groups = collections.defaultdict(set)
    for c in claims:
        if c["source"] != dataset:
            continue
        fam = c.get("prov_family", "")
        val = fam.split(":", 1)[1] if ":" in fam else ""
        groups[val].add(c["address"])
    res = {}
    for val, addrs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        share = len(addrs & candidate_addrs) / len(addrs)
        if not val.isalpha():
            verdict = "malformed"          # e.g. a stray separator in the field
        elif len(addrs) < MIN_GROUP:
            verdict = "insufficient"       # too few rows to establish containment
        elif share > 0.999:
            verdict = "inherited"
        elif share < 0.001:
            verdict = "independent"
        else:
            verdict = "mixed"
        res[val] = dict(n=len(addrs), share_in_candidate=share, verdict=verdict)

    inherited = [v for v, r in res.items() if r["verdict"] == "inherited"]
    independent = [v for v, r in res.items() if r["verdict"] == "independent"]
    inconclusive = [v for v, r in res.items()
                    if r["verdict"] in ("mixed", "malformed", "insufficient")]
    # the decode is clean when every conclusive group falls at one extreme
    clean = bool(inherited) and bool(independent) and not [
        v for v, r in res.items() if r["verdict"] == "mixed"]
    # groups too small to judge still inherit if they sit inside the candidate
    carried = sum(r["n"] for v, r in res.items()
                  if r["verdict"] in ("insufficient", "malformed")
                  and r["share_in_candidate"] > 0.999)
    return dict(dataset=dataset, candidate=candidate, groups=res,
                clean_split=clean,
                inherited_groups=inherited, independent_groups=independent,
                inconclusive_groups=inconclusive,
                inherited_addresses=sum(res[v]["n"] for v in inherited) + carried)


# ------------------------------------------------------- test 3: naming residue
def naming_residue(claims: list[dict], dataset: str) -> dict:
    """Claims whose own label text names the upstream study they came from."""
    marked = collections.Counter()
    total = 0
    for c in claims:
        if c["source"] != dataset:
            continue
        total += 1
        f = (c.get("subcat") or "").lower()
        hit = next((root for pre, root in FAMILY_MARKERS if f.startswith(pre)), None)
        marked[hit or "unmarked"] += 1
    attributed = sum(v for k, v in marked.items() if k != "unmarked")
    return dict(dataset=dataset, total=total, attributed=attributed,
                share=attributed / total if total else 0.0,
                by_root={k: v for k, v in marked.items() if k != "unmarked"})
