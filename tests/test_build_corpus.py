"""scripts/build_corpus.py - the from-source rebuild path. Synthetic fixtures
in each source's real file shape (no third-party data is shipped): the point is
the adapters' mapping, determinism, provenance of the build itself, and that
the output loads straight into `themis --observations`."""
import csv, gzip, importlib.util, json, pathlib, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("build_corpus", ROOT / "scripts" / "build_corpus.py")
bc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bc)
from themis.corpus import Corpus

A = [f"1{c}" * 12 + "AAAAAAAAAAAA" for c in "abcdefghij"]     # 26-char stand-ins, only length matters here


class TestBuildCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = pathlib.Path(self.tmp.name)
        (self.d / "classes.csv").write_text(f"address,class\n{A[0]},1\n{A[1]},2\n{A[2]},3\nshort,1\n")
        (self.d / "schn.csv").write_text(f"address,category,source\n{A[0]},MARKETPLACE,Montréal\n{A[3]},BET,BitcoinTalk\n")
        (self.d / "ransom.csv").write_text(f"address;family;source;SUM_REC_USD\n{A[4]};Locky;RSH;12.5\n{A[5]};Cerber;S;bad\n")
        (self.d / "mixers.csv").write_text(f"address,family,source\n{A[6]},HelixMixer,S\n")
        (self.d / "rw.json").write_text(json.dumps({"result": [
            {"address": A[4], "blockchain": "bitcoin", "family": "Locky", "updatedAt": "2024-05-06T01:02:03Z",
             "transactions": [{"amountUSD": 10}, {"amountUSD": 5.5}]},
            {"address": "0xETH", "blockchain": "ethereum", "family": "x"}]}))
        pk = self.d / "tp" / "packs" / "a"; pk.mkdir(parents=True)
        (pk / "one.yaml").write_text(
            "creator: Team\nlastmod: 2023-01-02\nlabel: pack\ntags:\n"
            f"  - {{address: {A[7]}, label: 'x mixing_service y', category: mixing_service, confidence: forensic}}\n"
            f"  - {{address: {A[8]}, label: Antpool, currency: ETH}}\n")
        (self.d / "wyb.csv").write_text(
            f"#{A[9]},btc,tormarket,hydra-market,,http://x\n{A[7]},btc,ransomware,locky,,http://y\n{A[8]},eth,ransomware,z,,http://z\n")
        self.args = ["--out", str(self.d / "out"), "--elliptic-classes", str(self.d / "classes.csv"),
                     "--schnoering", str(self.d / "schn.csv"), "--rodwald-ransom", str(self.d / "ransom.csv"),
                     "--rodwald-mixers", str(self.d / "mixers.csv"), "--ransomwhere", str(self.d / "rw.json"),
                     "--tagpack", str(self.d / "tp"), "--watchyourback", str(self.d / "wyb.csv"),
                     "--retrieved", "ransomwhere=2026-09-15"]

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        with gzip.open(self.d / "out" / "observations.csv.gz", "rt", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_adapters_map_each_sources_own_vocabulary(self):
        bc.main(self.args); rows = self._rows()
        by = {(r["source"], r["address"]): r for r in rows}
        self.assertEqual(by[("ellipticpp", A[0])]["canon"], "illicit_unspec")
        self.assertEqual(by[("ellipticpp", A[1])]["canon"], "licit_unspec")
        self.assertEqual(by[("ellipticpp", A[2])]["canon"], "unknown")          # class 3 stays uninterpretable
        self.assertEqual(by[("schnoering", A[0])]["canon"], "darknet_market")   # Schnoering's own MARKETPLACE meaning
        self.assertEqual(by[("schnoering", A[3])]["canon"], "gambling")
        self.assertEqual(by[("rodwald_mixers", A[6])]["canon"], "mixer")
        self.assertEqual(by[("ransomwhere", A[4])]["lastmod"], "2024-05-06")
        self.assertEqual(by[("tagpack", A[7])]["canon"], "mixer")
        self.assertEqual(by[("tagpack", A[7])]["subcat"], "forensic")           # confidence id preserved raw
        self.assertEqual(by[("watchyourback", "#" + A[9])]["canon"], "unknown")  # raw "#" kept; canon unmapped
        self.assertEqual(by[("watchyourback", A[7])]["canon"], "ransomware")
        self.assertNotIn(("tagpack", A[8]), by)      # non-BTC currency skipped
        self.assertNotIn(("watchyourback", A[8]), by)  # non-btc chain skipped
        self.assertNotIn("0xETH", {r["address"] for r in rows})

    def test_polarity_comes_from_the_taxonomy_not_a_second_table(self):
        bc.main(self.args)
        from themis import taxonomy
        for r in self._rows():
            self.assertEqual(r["polarity"], taxonomy.POLARITY.get(r["canon"], "unknown"))

    def test_output_is_byte_deterministic(self):
        bc.main(self.args)
        first = {n: (self.d / "out" / n).read_bytes() for n in ("observations.csv.gz", "build_manifest.json")}
        bc.main(self.args)
        for n, b in first.items():
            self.assertEqual((self.d / "out" / n).read_bytes(), b, n)

    def test_manifest_records_inputs_versions_and_warnings_without_paths(self):
        bc.main(self.args)
        text = (self.d / "out" / "build_manifest.json").read_text(); m = json.loads(text)
        self.assertNotIn(str(self.d), text)                        # no path of the machine that ran it
        self.assertEqual(m["builder"]["adapter_version"], bc.ADAPTER_VERSION)
        self.assertEqual(m["builder"]["normalization_version"], bc.NORMALIZATION_VERSION)
        self.assertEqual(m["inputs"]["ransomwhere"]["retrieved"], "2026-09-15")
        self.assertEqual(len(m["inputs"]["ellipticpp"]["sha256"]), 64)
        self.assertEqual(m["dropped_rows_shorter_than_a_bitcoin_address"], {"ellipticpp": 1})
        self.assertTrue(any("no --retrieved date" in w for w in m["warnings"]))
        self.assertEqual(m["totals"]["claims"], len(self._rows()))

    def test_a_missing_source_is_a_warning_not_an_error(self):
        bc.main(["--out", str(self.d / "o2"), "--schnoering", str(self.d / "schn.csv")])
        m = json.loads((self.d / "o2" / "build_manifest.json").read_text())
        self.assertEqual(set(m["per_source"]), {"schnoering"})
        self.assertTrue(any("ellipticpp: no input given" in w for w in m["warnings"]))

    def test_derived_task_inputs(self):
        bc.main(self.args)
        with gzip.open(self.d / "out" / "revenue.csv.gz", "rt", encoding="utf-8") as f:
            rev = list(csv.DictReader(f))
        self.assertEqual({(r["dataset"], r["address"]): r["usd"] for r in rev},
                         {("rodwald_ransom", A[4]): "12.50", ("rodwald_ransom", A[5]): "0.00",
                          ("ransomwhere", A[4]): "15.50"})
        with gzip.open(self.d / "out" / "verified_anchors.txt.gz", "rt") as f:
            self.assertEqual(set(f.read().split()), {A[7]})      # WYB ransomware ∪ TagPack forensic

    def test_output_loads_straight_into_themis(self):
        bc.main(self.args)
        c = Corpus.from_file(self.d / "out" / "observations.csv.gz")
        self.assertEqual(len(c.claims), len(self._rows()))
        self.assertIn(A[9], c.by_addr)                 # "#" normalized by config, raw preserved
        self.assertEqual(c.by_addr[A[9]][0]["raw_address"], "#" + A[9])

    def test_taxonomy_fill_is_opt_in_and_only_touches_unknown_labels(self):
        bc.main(self.args)
        plain = {(r["source"], r["address"]): r["canon"] for r in self._rows()}
        bc.main(self.args + ["--taxonomy-fill"])
        filled = {(r["source"], r["address"]): r["canon"] for r in self._rows()}
        # WatchYourBack's "tormarket:hydra-market" was `unknown` in the paper snapshot
        self.assertEqual(plain[("watchyourback", "#" + A[9])], "unknown")
        self.assertEqual(filled[("watchyourback", "#" + A[9])], "darknet_market")
        # Elliptic++ class_3 has no taxonomy alias: stays unknown; placed labels never change
        self.assertEqual(filled[("ellipticpp", A[2])], "unknown")
        self.assertEqual({k: v for k, v in filled.items() if plain[k] != "unknown"},
                         {k: v for k, v in plain.items() if v != "unknown"})
        m = json.loads((self.d / "out" / "build_manifest.json").read_text())
        self.assertTrue(m["builder"]["taxonomy_fill"])
        self.assertEqual(m["builder"]["claims_rederived_by_taxonomy_fill"], 1)
        self.assertIn("taxonomy-fill", m["builder"]["normalization_version"])

    def test_nonexistent_input_stops_with_a_clear_message(self):
        with self.assertRaises(SystemExit) as cm:
            bc.main(["--out", str(self.d / "o3"), "--schnoering", str(self.d / "nope.csv")])
        self.assertIn("does not exist", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
