#!/usr/bin/env python3
"""Rebuild THEMIS's normalized observation table from the seven sources' own
files - the from-source path behind `themis --observations FILE`.

    python scripts/build_corpus.py --out build/ \
        --elliptic-classes  PATH/wallets_classes.csv \
        --schnoering        PATH/schnoering_addresses.csv \
        --rodwald-ransom    PATH/BTC_Ransom.csv \
        --rodwald-mixers    PATH/BTC_Mixers.csv \
        --ransomwhere       PATH/ransomwhere.json \
        --tagpack           PATH/graphsense-tagpacks \
        --watchyourback     PATH/data/tagging/btc_resolv.csv \
        --retrieved ransomwhere=2026-09-15 --retrieved tagpack=2026-09-15

Every source is optional; a missing one is a warning, not an error. This
script never downloads anything: fetch each source yourself, from where and
under the terms THIRD_PARTY_DATA.md records, and pass the paths in.

Writes, all deterministic (same inputs -> byte-identical outputs):
  observations.csv.gz      one row per (address, source) claim, corpus.FIELDS
  revenue.csv.gz           per-address USD received (Rodwald ransomware and
                           Ransomwhere), the ransomware-revenue task's input
  verified_anchors.txt.gz  Condition D's anchor set: WatchYourBack's
                           ransomware addresses + TagPack tags whose declared
                           confidence is `forensic`
  build_manifest.json      input hashes (file names, never paths), adapter and
                           normalization versions, retrieval dates, per-source
                           counts, dropped rows, warnings

The label -> category tables below are source-format facts (what each
source's own vocabulary means), which is why they live in the adapters and
not in the analysis engine. They reproduce the frozen paper corpus's `canon`
column; changing one is a methodology change, not a tuning knob.
"""
from __future__ import annotations
import argparse, collections, csv, datetime, glob, gzip, hashlib, io, json, os, pathlib, sys
import yaml

csv.field_size_limit(10 ** 9)
ADAPTER_VERSION = "1.0"
NORMALIZATION_VERSION = "observations-v1"
MIN_ADDRESS_LEN = 20          # shorter strings cannot be a Bitcoin address (paper Sec 4.1)
FIELDS = ["address", "source", "raw_label", "canon", "polarity",
          "prov_family", "lastmod", "heuristic", "subcat"]

SCHNOERING = {"RANSOMWARE": "ransomware", "MIXER": "mixer", "EXCHANGE": "exchange",
              "GAMBLING": "gambling", "BET": "gambling", "MINING": "mining",
              "PONZI": "ponzi", "FAUCET": "faucet", "BRIDGE": "bridge",
              "MARKETPLACE": "darknet_market", "INDIVIDUAL": "individual", "": "unknown"}
TAGPACK = {"exchange": "exchange", "mixing_service": "mixer", "mixer": "mixer",
           "gambling": "gambling", "mining": "mining", "faucet": "faucet",
           "ransomware": "ransomware", "sextortion": "sextortion",
           "scam": "scam", "ponzi_scheme": "ponzi", "phishing": "scam",
           "extremism": "extremism", "terrorism_financing": "terrorism",
           "darknet_market": "darknet_market", "sanctions": "sanctioned",
           "hack": "hack", "malware": "malware",
           "child_abuse_material": "trafficking", "human_trafficking": "trafficking",
           "counterfeiting": "scam", "drug_market": "darknet_market",
           "weapons": "trafficking", "fraudulent_exchange": "scam"}
WATCHYOURBACK = {"ransomware": "ransomware", "ponzi": "ponzi", "mining": "mining",
                 "exchange": "exchange", "gambling": "gambling", "mixer": "mixer",
                 "scam": "scam", "malware": "malware", "darknet": "darknet_market",
                 "market": "darknet_market", "sextortion": "sextortion"}
ELLIPTIC = {"1": "illicit_unspec", "2": "licit_unspec", "3": "unknown"}   # Elliptic's own class codes


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_addr(a) -> str:
    a = (a or "").strip().strip('"')
    return a.lower() if a[:3].lower() in ("bc1", "tb1") else a


def _open(path):
    return open(path, newline="", encoding="utf-8-sig")


class Builder:
    def __init__(self, taxonomy_fill=False):
        self.rows, self.dropped, self.warnings = [], collections.Counter(), []
        self.taxonomy_fill, self.filled = taxonomy_fill, 0
        from themis import taxonomy          # polarity comes from config, not a second table
        self.polarity, self._canonicalize = taxonomy.POLARITY, taxonomy.canonicalize_category

    def emit(self, address, source, raw_label, canon, prov_family, lastmod="", heuristic="", subcat=""):
        a = norm_addr(address)
        if not a or len(a) < MIN_ADDRESS_LEN:
            self.dropped[source] += 1
            return
        if canon == "unknown" and self.taxonomy_fill:
            # a label the source's own map could not place, re-derived through the
            # current taxonomy + structured-label parser. Never touches a label the
            # adapter already placed - those come from source-specific meaning.
            filled = self._canonicalize(raw_label)
            if filled:
                canon, self.filled = filled, self.filled + 1
        self.rows.append(dict(address=a, source=source, raw_label=raw_label, canon=canon,
                              polarity=self.polarity.get(canon, "unknown"), prov_family=prov_family,
                              lastmod=lastmod or "", heuristic=heuristic or "", subcat=subcat or ""))

    # ---------------------------------------------------------------- adapters
    def elliptic(self, path):
        with _open(path) as f:
            for r in csv.DictReader(f):
                c = r["class"]
                if c not in ELLIPTIC:
                    self.warnings.append(f"ellipticpp: unrecognized class code {c!r} skipped")
                    continue
                self.emit(r["address"], "ellipticpp", f"class_{c}", ELLIPTIC[c],
                          "elliptic_undisclosed", heuristic="undisclosed")

    def schnoering(self, path):
        with _open(path) as f:
            for r in csv.DictReader(f):
                src = r["source"].strip()
                self.emit(r["address"], "schnoering", r["category"],
                          SCHNOERING.get(r["category"].strip().upper(), "unknown"),
                          f"schnoering:{src}", subcat=src, heuristic="multi_input")

    def rodwald(self, path, source, canon, delimiter):
        with _open(path) as f:
            for r in csv.DictReader(f, delimiter=delimiter):
                fam = (r.get("family") or "").strip()
                self.emit(r["address"], source, fam, canon,
                          f"rodwald:{(r.get('source') or '').strip()}", subcat=fam, heuristic="inherited")

    def ransomwhere(self, path):
        for x in _ransomwhere_records(path):
                if x.get("blockchain") != "bitcoin":
                    continue
                self.emit(x.get("address"), "ransomwhere", x.get("family"), "ransomware",
                          "ransomwhere:crowd", lastmod=(x.get("updatedAt") or "")[:10],
                          subcat=x.get("family"), heuristic="none")

    @staticmethod
    def tag_canon(pack, tag):
        for k in (tag.get("abuse") or pack.get("abuse") or "", tag.get("category") or pack.get("category") or ""):
            k = str(k).strip().lower()
            if k in TAGPACK:
                return TAGPACK[k]
        lbl = str(tag.get("label") or pack.get("label") or "").lower()
        for k, v in TAGPACK.items():
            if k.replace("_", " ") in lbl:
                return v
        return "unknown"

    def tagpack_files(self, root):
        return sorted(glob.glob(os.path.join(root, "packs", "**", "*.yaml"), recursive=True))

    def tagpack(self, root):
        n_files = 0
        for path in self.tagpack_files(root):
            try:
                pack = yaml.safe_load(open(path, encoding="utf-8"))
            except Exception as e:
                self.warnings.append(f"tagpack: {os.path.relpath(path, root)} unreadable ({type(e).__name__})")
                continue
            if not isinstance(pack, dict) or "tags" not in pack:
                continue
            n_files += 1
            lastmod, creator = str(pack.get("lastmod") or "")[:10], str(pack.get("creator") or "unknown")
            for t in pack["tags"] or []:
                if not isinstance(t, dict) or not t.get("address"):
                    continue
                cur = str(t.get("currency") or pack.get("currency") or "").strip().upper()
                if cur and cur != "BTC":
                    continue
                self.emit(str(t["address"]), "tagpack", str(t.get("label") or pack.get("label") or ""),
                          self.tag_canon(pack, t), f"tagpack:{creator}",
                          lastmod=str(t.get("lastmod") or lastmod)[:10],
                          subcat=str(t.get("confidence") or pack.get("confidence") or ""), heuristic="curated")
        return n_files

    def watchyourback(self, path):
        with _open(path) as f:
            for r in csv.reader(f):
                if len(r) < 4 or r[1].strip().lower() != "btc":
                    continue
                cat = r[2].strip().lower()
                # the address is kept verbatim ("#" and all): normalizing it is
                # provenance.normalize_address's job, driven by config, so the
                # raw upstream value survives as raw_address
                self.emit(r[0], "watchyourback", f"{cat}:{r[3]}", WATCHYOURBACK.get(cat, "unknown"),
                          "wyb:manual", subcat=r[3], heuristic="manual_verified")


def _ransomwhere_records(path):
    """The live API export wraps the list as {"result": [...]}; the Zenodo
    snapshot is the bare list. Same records either way."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return data["result"] if isinstance(data, dict) else data


# -------------------------------------------------- derived task inputs (Condition D)
def revenue_rows(rodwald_ransom, ransomwhere):
    rows = []
    if rodwald_ransom:
        with _open(rodwald_ransom) as f:
            for r in csv.DictReader(f, delimiter=";"):
                try:
                    usd = float(r["SUM_REC_USD"])
                except (KeyError, ValueError):
                    usd = 0.0
                rows.append((r["address"].strip(), "rodwald_ransom", usd,
                             (r.get("family") or "").strip(), (r.get("source") or "").strip()))
    if ransomwhere:
        for x in _ransomwhere_records(ransomwhere):
            if x.get("blockchain") != "bitcoin":
                continue
            usd = sum(float(t.get("amountUSD") or 0) for t in (x.get("transactions") or []))
            rows.append(((x.get("address") or "").strip(), "ransomwhere", usd, x.get("family") or "", ""))
    return rows


def anchor_addresses(builder, wyb_path, tagpack_root):
    """WatchYourBack ransomware addresses united with TagPack tags whose
    declared confidence is `forensic` - the paper's "highest declared
    confidence" set. Raw addresses, exactly as the sources print them."""
    anchors = set()
    if wyb_path:
        with _open(wyb_path) as f:
            for r in csv.reader(f):
                if len(r) >= 3 and r[1].strip().lower() == "btc" and r[2].strip().lower() == "ransomware":
                    anchors.add(r[0].strip())
    if tagpack_root:
        for path in builder.tagpack_files(tagpack_root):
            try:
                pack = yaml.safe_load(open(path, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(pack, dict) or not pack.get("tags"):
                continue
            for t in pack["tags"]:
                if isinstance(t, dict) and str(t.get("confidence") or pack.get("confidence") or "").lower() == "forensic":
                    anchors.add(str(t.get("address") or "").strip())
    anchors.discard("")
    return anchors


# ------------------------------------------------------------------- writing
def write_gz(path, text_writer):
    """gzip with mtime=0 and no embedded file name, so output bytes depend only on content."""
    with open(path, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8", newline="") as t:
        text_writer(t)


def dir_hash(root, files):
    h = hashlib.sha256()
    for p in files:
        h.update(os.path.relpath(p, root).encode() + b"\0" + sha256_file(p).encode() + b"\n")
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory (created)")
    ap.add_argument("--elliptic-classes"); ap.add_argument("--schnoering")
    ap.add_argument("--rodwald-ransom"); ap.add_argument("--rodwald-mixers")
    ap.add_argument("--ransomwhere"); ap.add_argument("--tagpack", help="root of a graphsense-tagpacks checkout")
    ap.add_argument("--watchyourback")
    ap.add_argument("--taxonomy-fill", action="store_true",
                    help="CORRECTED-CANDIDATE build: claims the paper-era adapters left `unknown` are "
                         "re-derived through the current taxonomy and structured-label parser. Default "
                         "off = the paper snapshot's own behaviour; the two are never mixed silently")
    ap.add_argument("--retrieved", action="append", default=[], metavar="SOURCE=YYYY-MM-DD",
                    help="when you retrieved that source (recorded, not checked)")
    a = ap.parse_args(argv)

    retrieved = dict(x.split("=", 1) for x in a.retrieved)
    from themis import __version__, taxonomy, config_io
    b = Builder(taxonomy_fill=a.taxonomy_fill)
    plan = [("ellipticpp", a.elliptic_classes, lambda p: b.elliptic(p)),
            ("schnoering", a.schnoering, lambda p: b.schnoering(p)),
            ("rodwald_ransom", a.rodwald_ransom, lambda p: b.rodwald(p, "rodwald_ransom", "ransomware", ";")),
            ("rodwald_mixers", a.rodwald_mixers, lambda p: b.rodwald(p, "rodwald_mixers", "mixer", ",")),
            ("ransomwhere", a.ransomwhere, lambda p: b.ransomwhere(p)),
            ("tagpack", a.tagpack, lambda p: b.tagpack(p)),
            ("watchyourback", a.watchyourback, lambda p: b.watchyourback(p))]
    inputs = {}
    for name, path, run in plan:
        if not path:
            b.warnings.append(f"{name}: no input given, source absent from this build")
            continue
        if not os.path.exists(path):
            sys.exit(f"{name}: {path} does not exist")
        if name == "tagpack":
            files = b.tagpack_files(path)
            inputs[name] = dict(kind="directory", n_files=len(files), sha256=dir_hash(path, files))
        else:
            inputs[name] = dict(kind="file", name=os.path.basename(path),
                                bytes=os.path.getsize(path), sha256=sha256_file(path))
        inputs[name]["retrieved"] = retrieved.get(name)
        if not retrieved.get(name):
            b.warnings.append(f"{name}: no --retrieved date recorded")
        run(path)
    for name in retrieved:
        if name not in inputs:
            b.warnings.append(f"--retrieved {name}: not a source that was given")

    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    def obs(t):
        w = csv.DictWriter(t, fieldnames=FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(b.rows)
    write_gz(out / "observations.csv.gz", obs)
    outputs = ["observations.csv.gz"]

    rev = revenue_rows(a.rodwald_ransom, a.ransomwhere)
    if rev:
        def rv(t):
            w = csv.writer(t, lineterminator="\n"); w.writerow(["address", "dataset", "usd", "family", "src_letters"])
            for r in rev: w.writerow([r[0], r[1], f"{r[2]:.2f}", r[3], r[4]])
        write_gz(out / "revenue.csv.gz", rv); outputs.append("revenue.csv.gz")
    anchors = anchor_addresses(b, a.watchyourback, a.tagpack) if (a.watchyourback or a.tagpack) else set()
    if anchors:
        write_gz(out / "verified_anchors.txt.gz", lambda t: t.write("".join(x + "\n" for x in sorted(anchors))))
        outputs.append("verified_anchors.txt.gz")

    per = collections.defaultdict(lambda: dict(claims=0, addresses=set()))
    for r in b.rows:
        per[r["source"]]["claims"] += 1; per[r["source"]]["addresses"].add(r["address"])
    manifest = dict(
        builder=dict(script="scripts/build_corpus.py", adapter_version=ADAPTER_VERSION,
                     normalization_version=NORMALIZATION_VERSION + ("+taxonomy-fill" if a.taxonomy_fill else ""),
                     taxonomy_fill=a.taxonomy_fill, claims_rederived_by_taxonomy_fill=b.filled,
                     themis_version=__version__,
                     python=sys.version.split()[0],
                     taxonomy_sha256=sha256_file(config_io.config_dir() / "taxonomy.yml"),
                     script_sha256=sha256_file(__file__)),
        inputs=inputs,
        totals=dict(claims=len(b.rows), addresses=len({r["address"] for r in b.rows})),
        per_source={s: dict(claims=v["claims"], addresses=len(v["addresses"])) for s, v in sorted(per.items())},
        dropped_rows_shorter_than_a_bitcoin_address=dict(sorted(b.dropped.items())),
        outputs={n: sha256_file(out / n) for n in outputs},
        warnings=sorted(b.warnings),
        note="Built by scripts/build_corpus.py from the inputs above; hashes identify the exact files. "
             "Use with: themis --observations observations.csv.gz audit")
    (out / "build_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"{manifest['totals']['claims']:,} claims over {manifest['totals']['addresses']:,} addresses "
          f"from {len(inputs)} of 7 sources -> {out}")
    for w in manifest["warnings"]:
        print("warning:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
