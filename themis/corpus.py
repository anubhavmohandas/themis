"""Corpus loading. Works on the bundled sample or on a full local build."""
from __future__ import annotations
import csv, gzip, json, os, collections, pathlib
from . import provenance

csv.field_size_limit(10 ** 9)
PKG = pathlib.Path(__file__).resolve().parent.parent
DEMO = PKG / "demo_data"

FIELDS = ["address", "source", "raw_label", "canon", "polarity",
          "prov_family", "lastmod", "heuristic", "subcat"]


def _open(path):
    path = str(path)
    return gzip.open(path, "rt", newline="") if path.endswith(".gz") else open(path, newline="")


class Corpus:
    """One observation table: claims, addresses, roots."""

    def __init__(self, claims, manifest=None, full=False):
        self.claims = claims
        self.manifest = manifest or {}
        self.full = full
        for c in self.claims:
            c["root"] = provenance.root_of(c)
        self.by_addr = collections.defaultdict(list)
        for c in self.claims:
            self.by_addr[c["address"]].append(c)
        self.src_addr = collections.defaultdict(set)
        for c in self.claims:
            self.src_addr[c["source"]].add(c["address"])

    # -------------------------------------------------------------- loaders
    @classmethod
    def demo(cls):
        with open(DEMO / "manifest.json") as fh:
            man = json.load(fh)
        with _open(DEMO / "observations_sample.csv.gz") as f:
            claims = list(csv.DictReader(f))
        return cls(claims, man, full=False)

    @classmethod
    def from_file(cls, path):
        with _open(path) as f:
            claims = list(csv.DictReader(f))
        return cls(claims, {}, full=True)

    # ------------------------------------------------------------ accessors
    @property
    def n_claims(self):
        if self.full:
            return len(self.claims)
        return self.manifest.get("full_corpus", {}).get("claims", len(self.claims))

    @property
    def n_addresses(self):
        if self.full:
            return len(self.by_addr)
        return self.manifest.get("full_corpus", {}).get("addresses", len(self.by_addr))

    @property
    def sample_note(self):
        if self.full:
            return None
        s = self.manifest.get("sample", {})
        return (f"bundled sample: {s.get('claims', 0):,} claims over "
                f"{s.get('addresses', 0):,} addresses, including every one of the "
                f"{s.get('multi_source_addresses', 0):,} multi-dataset addresses. "
                "Agreement, conflict and circularity figures are exact; "
                "corpus-wide rates use full-corpus counts from the manifest.")

    def source_sizes(self):
        if self.full:
            return {s: len(v) for s, v in
                    sorted(self.src_addr.items(), key=lambda kv: -len(kv[1]))}
        per = self.manifest.get("full_corpus", {}).get("per_source", {})
        return {s: per[s]["addresses"] for s in
                sorted(per, key=lambda s: -per[s]["addresses"])}

    def multi_source_addresses(self):
        return [a for a, v in self.by_addr.items() if len({c["source"] for c in v}) >= 2]

    def roots(self):
        return collections.Counter(c["root"] for c in self.claims)

    def corpus_roots(self):
        """Corpus-wide provenance figures. Exact on a full build; taken from the
        manifest on the bundled sample, where the two big sources are sampled."""
        if self.full:
            r = self.roots()
            from . import provenance as _p
            unres_a = sum(1 for a, v in self.by_addr.items()
                          if _p.is_unresolved(collections.Counter(
                              c["root"] for c in v).most_common(1)[0][0]))
            return dict(total=len(r),
                        identified=len([k for k in r if not _p.is_unresolved(k)]),
                        unresolved_addresses=unres_a,
                        unresolved_addr_share=unres_a / len(self.by_addr),
                        root_claims=dict(r.most_common()))
        f = self.manifest.get("full_corpus", {})
        return dict(total=f.get("roots_total"), identified=f.get("roots_identified"),
                    unresolved_addresses=f.get("unresolved_addresses"),
                    unresolved_addr_share=f.get("unresolved_addr_share"),
                    root_claims=f.get("root_claims", {}))

    def revenue_rows(self, path=None):
        path = path or DEMO / "revenue.csv.gz"
        with _open(path) as f:
            return list(csv.DictReader(f))

    def verified_anchors(self, path=None):
        path = path or DEMO / "verified_anchors.txt.gz"
        with _open(path) as f:
            return {ln.strip() for ln in f if ln.strip()}

    def ground_truth(self, path=None):
        path = path or DEMO / "ground_truth.csv"
        with _open(path) as f:
            return {r["address"]: (r["ground_truth_label"], r["ground_truth_source"])
                    for r in csv.DictReader(f)}
