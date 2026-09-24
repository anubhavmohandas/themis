"""Corpus loading. Works on the bundled sample or on a full local build."""
from __future__ import annotations
import csv, datetime, gzip, json, os, collections, pathlib
from . import provenance, config_io

csv.field_size_limit(10 ** 9)
PKG = pathlib.Path(__file__).resolve().parent.parent
_MISSING = ("No reference corpus found at {path}. The derived observation table is not "
            "redistributed with THEMIS (see THIRD_PARTY_DATA.md): build it from the sources "
            "with scripts/build_corpus.py, then point THEMIS at it with --data-dir DIR or the "
            "THEMIS_DATA_DIR environment variable.")


def data_dir() -> pathlib.Path:
    """Where the reference corpus files live: THEMIS_DATA_DIR if set, else the
    repository's demo_data/ (present in a development checkout, absent from
    the release). Read at call time so the override can be set late."""
    return pathlib.Path(os.environ.get("THEMIS_DATA_DIR") or PKG / "demo_data")

FIELDS = ["address", "source", "raw_label", "canon", "polarity",
          "prov_family", "lastmod", "heuristic", "subcat"]


def _open(path):
    # utf-8-sig: strip a leading UTF-8 BOM if a full local build was
    # exported from Excel; identical to utf-8 when there is none.
    path = str(path)
    return (gzip.open(path, "rt", newline="", encoding="utf-8-sig") if path.endswith(".gz")
            else open(path, newline="", encoding="utf-8-sig"))


class Corpus:
    """One observation table: claims, addresses, roots."""

    def __init__(self, claims, manifest=None, full=False):
        self.claims = claims
        self.manifest = manifest or {}
        self.full = full
        for c in self.claims:
            c.setdefault("raw_address", c.get("address", ""))
            c["address"] = provenance.normalize_address(c)
            r = provenance.resolve(c)
            c["root"] = r["root"]
            c["prov_resolved"] = r["resolved"]
            c["prov_native"] = r["native"]
            c["prov_verified"] = r["verified"]
            c["prov_kind"] = r["kind"]
        self.by_addr = collections.defaultdict(list)
        for c in self.claims:
            self.by_addr[c["address"]].append(c)
        self.src_addr = collections.defaultdict(set)
        for c in self.claims:
            self.src_addr[c["source"]].add(c["address"])

    # -------------------------------------------------------------- loaders
    @classmethod
    def demo(cls):
        d = data_dir()
        if not (d / "manifest.json").is_file() or not (d / "observations_sample.csv.gz").is_file():
            raise FileNotFoundError(_MISSING.format(path=d))
        with open(d / "manifest.json") as fh:
            man = json.load(fh)
        with _open(d / "observations_sample.csv.gz") as f:
            claims = list(csv.DictReader(f))
        return cls(claims, man, full=False)

    @classmethod
    def reference(cls):
        """The corpus the API compares against: the full local build THEMIS_OBSERVATIONS names
        (dated by THEMIS_AS_OF, like the CLI's --observations / --as-of), else the bundled sample."""
        obs = os.environ.get("THEMIS_OBSERVATIONS")
        if not obs:
            return cls.demo()
        c = cls.from_file(obs)
        if os.environ.get("THEMIS_AS_OF"):
            c.manifest["analysis_as_of_date"] = os.environ["THEMIS_AS_OF"]
        return c

    @classmethod
    def from_file(cls, path):
        with _open(path) as f:
            claims = list(csv.DictReader(f))
        return cls(claims, {}, full=True)

    def chain_of(self, claim: dict) -> str | None:
        """The chain a reference claim's identifier lives on, as its source's config declares it
        (None when a source declares none)."""
        return (config_io.load().sources.get(claim.get("source")) or {}).get("chain")

    def for_subject(self, chain: str | None, address: str) -> list:
        """Reference claims about this identifier ON THIS CHAIN. A reference source that declares a
        different chain never speaks about it, whatever the string looks like; a chain of None (the
        asker did not say) or a source that declares none is not filtered."""
        claims = self.by_addr.get(address, [])
        if chain is None:
            return claims
        return [c for c in claims if self.chain_of(c) in (None, chain)]

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
                f"{s.get('addresses', 0):,} addresses, including the "
                f"{s.get('multi_source_addresses', 0):,} multi-dataset addresses it held when it was drawn, before "
                "WatchYourBack's #-prefixed addresses were joined (a full normalized build has more). "
                "Agreement, conflict and circularity figures of the complete sources are exact; "
                "corpus-wide counts and rates come from the manifest or need a full build.")

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

    @property
    def snapshot_date(self):
        """The fixed date a reproduction run treats as "today" when judging
        staleness: the analysis date the corpus's manifest declares (the
        retrieval date the paper reports), else - for a build with no
        manifest - the newest revision date actually present in its claims.
        Never the wall clock, so the same archived corpus reproduces the same
        freshness figures whenever it is re-run.

        The fallback is a lower bound on the real retrieval date, not the date
        itself: a corpus whose newest record is two years old would be judged
        two years too fresh. That is why the bundled sample declares its date
        rather than relying on it, and why `--as-of` exists for a full build.
        """
        declared = self.manifest.get("analysis_as_of_date")
        if declared:
            try:
                return datetime.date.fromisoformat(str(declared)[:10])
            except ValueError:
                pass
        dates = [(c.get("lastmod") or "").strip()[:10] for c in self.claims if (c.get("lastmod") or "").strip()]
        if not dates:
            return None
        try:
            return datetime.date.fromisoformat(max(dates))
        except ValueError:
            return None

    def revenue_rows(self, path=None):
        path = path or data_dir() / "revenue.csv.gz"
        if not pathlib.Path(path).is_file():
            raise FileNotFoundError(_MISSING.format(path=path))
        with _open(path) as f:
            return list(csv.DictReader(f))

    def verified_anchors(self, path=None):
        path = path or data_dir() / "verified_anchors.txt.gz"
        with _open(path) as f:
            return {ln.strip() for ln in f if ln.strip()}

    def ground_truth(self, path=None):
        path = path or data_dir() / "ground_truth.csv"
        with _open(path) as f:
            return {r["address"]: (r["ground_truth_label"], r["ground_truth_source"])
                    for r in csv.DictReader(f)}
