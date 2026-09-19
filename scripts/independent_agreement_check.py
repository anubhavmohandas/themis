"""Phase 2D - second, independent calculation of the agreement breakdown.

Deliberately imports NOTHING from themis: it reads the bundled CSV and the
YAML config directly and re-implements the outcome rule from the paper's
definition (Sec 3, "Conflict logic"), so an error in themis.taxonomy /
themis.corpus cannot hide in both. Compares against `themis` afterwards.
"""
import csv, gzip, yaml, collections, json, sys, pathlib
ROOT = pathlib.Path(".")
tax = yaml.safe_load(open(ROOT / "themis/config/taxonomy.yml"))["categories"]
pol = {k: (v.get("polarity") or "unknown") for k, v in tax.items()}
par = {k: v.get("parent") for k, v in tax.items()}
generic = {k for k in tax if par[k] is None and pol[k] in ("licit", "illicit")}
alias = {}
for k, v in tax.items():
    alias[k.lower()] = k
    for a in v.get("aliases") or []:
        alias[str(a).lower()] = k
strip = {}
for f in (ROOT / "themis/config/sources").glob("*.yml"):
    c = yaml.safe_load(open(f)); n = (c.get("address_normalization") or {}).get("strip_prefix")
    if n: strip[c["id"]] = n


def anc(k):
    out = []
    while k in tax and k not in out:
        out.append(k); k = par[k]
    return set(out)


def canon_fresh(raw):
    raw = (raw or "").strip().lower()
    if raw in alias: return alias[raw]
    if ":" in raw:
        pre = raw.split(":", 1)[0].strip()
        return alias.get(pre)
    return None


def outcome(cats_by_source):
    pos = {s: c for s, c in cats_by_source.items() if c}
    if len(pos) < 2: return "incomparable"
    cats = set().union(*pos.values())
    if len(cats) == 1: return "exact"
    if {"licit", "illicit"} <= {pol.get(c, "unknown") for c in cats}: return "licit/illicit conflict"
    spec = cats - generic
    if len(spec) <= 1: return "hierarchical refinement"
    A = {c: anc(c) for c in spec}
    return "hierarchical refinement" if all(a in A[b] or b in A[a] for a in spec for b in spec) else "entity-type conflict"


def run(mode):
    by = collections.defaultdict(lambda: collections.defaultdict(set))
    with gzip.open(ROOT / "demo_data/observations_sample.csv.gz", "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            a = r["address"]; p = strip.get(r["source"])
            if p and a.startswith(p): a = a[len(p):]
            c = r["canon"]
            if c == "unknown" and mode == "candidate":
                c = canon_fresh(r["raw_label"]) or "unknown"
            by[a][r["source"]].add(c if c != "unknown" else None)
    tally = collections.Counter(); multi = 0
    for a, srcs in by.items():
        if len(srcs) < 2: continue
        multi += 1
        tally[outcome({s: {c for c in cs if c} for s, cs in srcs.items()})] += 1
    return multi, dict(tally)


if __name__ == "__main__":
    # run from the repository root: python scripts/independent_agreement_check.py [OUT.json]
    res = {m: run(m) for m in ("frozen", "candidate")}
    if len(sys.argv) > 1:
        json.dump(res, open(sys.argv[1], "w"), indent=1)
    for m, (n, t) in res.items():
        print(m, n, {k: t.get(k, 0) for k in ["exact", "hierarchical refinement", "entity-type conflict", "licit/illicit conflict", "incomparable"]})
