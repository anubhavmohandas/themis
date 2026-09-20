"""SOURCE -> ARTIFACT validation: is the observation table built correctly from
each source's own file? These tests say nothing about the manuscript; they are
deliberately separate from the ARTIFACT -> MANUSCRIPT checks (paper_claims.yml,
test_paper_reproduction.py). A consistent artifact can still be consistently
wrong, so the parser is checked against synthetic files in each source's real
shape (no third-party data is shipped)."""
import csv, gzip, importlib.util, json, pathlib, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("build_corpus", ROOT / "scripts" / "build_corpus.py")
bc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bc)
from themis.corpus import Corpus

ADDR = lambda ch: ch * 26          # 26-char stand-ins: only length and identity matter here


class Build(unittest.TestCase):
    def build(self, **files):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        d = pathlib.Path(tmp.name)
        args = ["--out", str(d / "out")]
        for flag, (name, text) in files.items():
            (d / name).write_text(text)
            args += [f"--{flag.replace('_', '-')}", str(d / name)]
        bc.main(args)
        with gzip.open(d / "out" / "observations.csv.gz", "rt", encoding="utf-8", newline="") as f:
            self.rows = list(csv.DictReader(f))
        self.manifest = json.loads((d / "out" / "build_manifest.json").read_text())
        self.out = d / "out"
        return {(r["source"], r["address"]): r for r in self.rows}


class TestWatchYourBackMarker(Build):
    def test_marker_is_kept_raw_and_removed_only_by_the_source_declared_rule(self):
        by = self.build(watchyourback=("w.csv", f"#{ADDR('a')},btc,ransomware,locky,,http://x\n{ADDR('b')},btc,mixer,helix,,http://y\n"))
        self.assertIn(("watchyourback", "#" + ADDR("a")), by)            # the artifact keeps upstream's literal
        corpus = Corpus.from_file(self.out / "observations.csv.gz")
        self.assertIn(ADDR("a"), corpus.by_addr)                          # ...and the join key is clean
        self.assertNotIn("#" + ADDR("a"), corpus.by_addr)
        self.assertEqual(corpus.by_addr[ADDR("a")][0]["raw_address"], "#" + ADDR("a"))

    def test_marker_no_longer_hides_a_cross_source_join(self):
        self.build(watchyourback=("w.csv", f"#{ADDR('a')},btc,ransomware,locky,,http://x\n"),
                   schnoering=("s.csv", f"address,category,source\n{ADDR('a')},RANSOMWARE,Montréal\n"))
        corpus = Corpus.from_file(self.out / "observations.csv.gz")
        self.assertEqual({c["source"] for c in corpus.by_addr[ADDR("a")]}, {"watchyourback", "schnoering"})


class TestEllipticInvalidAddress(Build):
    def test_strings_shorter_than_a_bitcoin_address_are_rejected_and_counted(self):
        by = self.build(elliptic_classes=("c.csv", f"address,class\n{ADDR('a')},1\nshort,1\n1abc,2\n"))
        self.assertEqual({a for _, a in by}, {ADDR("a")})
        self.assertEqual(self.manifest["dropped_rows_shorter_than_a_bitcoin_address"], {"ellipticpp": 2})

    def test_class_three_is_uninterpretable_not_licit(self):
        by = self.build(elliptic_classes=("c.csv", f"address,class\n{ADDR('a')},1\n{ADDR('b')},2\n{ADDR('c')},3\n"))
        self.assertEqual([by[("ellipticpp", ADDR(c))]["canon"] for c in "abc"], ["illicit_unspec", "licit_unspec", "unknown"])


class TestTagPackSchemaMapping(Build):
    PACK = ("creator: Team\nlastmod: 2023-01-02\nlabel: pack\ntags:\n"
            "  - {{address: {a}, label: 'x mixing_service y', category: mixing_service, confidence: forensic}}\n"
            "  - {{address: {b}, label: Antpool, currency: ETH}}\n"
            "  - {{address: {c}, label: Locky, abuse: ransomware, confidence: authority_data, lastmod: 2020-05-06}}\n")

    def test_category_confidence_creator_and_date_are_mapped_each_to_its_own_field(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        d = pathlib.Path(tmp.name); (d / "tp" / "packs" / "a").mkdir(parents=True)
        (d / "tp" / "packs" / "a" / "one.yaml").write_text(self.PACK.format(a=ADDR("a"), b=ADDR("b"), c=ADDR("c")))
        bc.main(["--out", str(d / "out"), "--tagpack", str(d / "tp")])
        with gzip.open(d / "out" / "observations.csv.gz", "rt", encoding="utf-8", newline="") as f:
            by = {r["address"]: r for r in csv.DictReader(f)}
        self.assertEqual(by[ADDR("a")]["canon"], "mixer")
        self.assertEqual(by[ADDR("a")]["subcat"], "forensic")              # the source's own confidence id, unmodified
        self.assertEqual(by[ADDR("c")]["subcat"], "authority_data")        # never collapsed onto one THEMIS tier
        self.assertEqual(by[ADDR("a")]["prov_family"], "tagpack:Team")
        self.assertEqual(by[ADDR("a")]["lastmod"], "2023-01-02")
        self.assertEqual(by[ADDR("c")]["lastmod"], "2020-05-06")          # a tag's own date beats the pack's
        self.assertNotIn(ADDR("b"), by)                                    # a non-BTC tag is not a Bitcoin claim


class TestRodwaldProvenanceCodes(Build):
    def test_source_letters_are_preserved_verbatim_including_a_malformed_value(self):
        by = self.build(rodwald_ransom=("r.csv", f"address;family;source;SUM_REC_USD\n{ADDR('a')};Locky;RSH;12.5\n"
                                                 f"{ADDR('b')};Cerber;\"H,S\";3\n{ADDR('c')};x;;1\n"))
        self.assertEqual(by[("rodwald_ransom", ADDR("a"))]["prov_family"], "rodwald:RSH")
        self.assertEqual(by[("rodwald_ransom", ADDR("b"))]["prov_family"], "rodwald:H,S")     # not repaired, not guessed
        self.assertEqual(by[("rodwald_ransom", ADDR("c"))]["prov_family"], "rodwald:")        # blank stays blank
        self.assertEqual(by[("rodwald_ransom", ADDR("a"))]["subcat"], "Locky")


class TestRansomwhereParsing(Build):
    def test_bitcoin_records_only_date_family_and_revenue(self):
        rw = json.dumps({"result": [
            {"address": ADDR("a"), "blockchain": "bitcoin", "family": "Locky", "updatedAt": "2024-05-06T01:02:03Z",
             "transactions": [{"amountUSD": 10}, {"amountUSD": 5.5}]},
            {"address": "0x" + "e" * 40, "blockchain": "ethereum", "family": "x"}]})
        by = self.build(ransomwhere=("rw.json", rw))
        self.assertEqual(list(by), [("ransomwhere", ADDR("a"))])
        r = by[("ransomwhere", ADDR("a"))]
        self.assertEqual((r["canon"], r["lastmod"], r["subcat"], r["prov_family"]), ("ransomware", "2024-05-06", "Locky", "ransomwhere:crowd"))
        with gzip.open(self.out / "revenue.csv.gz", "rt", encoding="utf-8") as f:
            self.assertEqual([(x["dataset"], x["usd"]) for x in csv.DictReader(f)], [("ransomwhere", "15.50")])


if __name__ == "__main__":
    unittest.main()
