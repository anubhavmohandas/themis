"""The Overview's metric contract (themis/overview.py): every figure carries ONE unit and ONE
population, so a share can only be taken inside a single universe, and a sample count is never
presented as the corpus's. Three layers: a synthetic full build (runs everywhere), the bundled
sample, and a real full build (each skipped, with a reason, when its data is absent)."""
import csv, gzip, os, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
import themis.api as api
from themis import overview, report
from themis.corpus import Corpus
from _data import requires_full_corpus, requires_reference_corpus

ADDRESS_POPS = {overview.NORMALIZED, overview.RAW_KEYS, overview.SAMPLE}
CLAIM_POPS = {overview.CLAIMS_FULL, overview.SAMPLE}


def _claim(source, address, canon="ransomware", lastmod=""):
    return dict(address=address, source=source, raw_label=canon, canon=canon, polarity="illicit",
                prov_family="", lastmod=lastmod, heuristic="", subcat="")


def synthetic() -> Corpus:
    """5 claims over 4 raw address keys, 3 normalized addresses: WatchYourBack's `#1B` joins `1B`.
    `1A` is named by tagpack twice (claims != addresses); `1B` is named by two datasets after the join."""
    claims = [_claim("tagpack", "1A"), _claim("tagpack", "1A", lastmod="2020-01-01"),
              _claim("tagpack", "1B"), _claim("watchyourback", "#1B"), _claim("ransomwhere", "1C")]
    return Corpus(claims, {"analysis_as_of_date": "2026-09-15"}, full=True)


def metrics_of(corpus):
    return report.build_corpus_report(corpus)["overview"]["metrics"]


def assert_contract(tc: unittest.TestCase, metrics: dict):
    """Structural rules every metric must obey, whatever the corpus."""
    for name, m in metrics.items():
        with tc.subTest(metric=name):
            pops = ADDRESS_POPS if m["unit"] == "addresses" else CLAIM_POPS
            tc.assertIn(m["unit"], ("addresses", "claims"))
            tc.assertIn(m["population"], pops, "a unit must not be counted over the other unit's population")
            tc.assertIn(m["quality"], ("live", "manifest", "sample_observed", "unavailable"))
            if m["value"] is None:
                tc.assertEqual(m["quality"], "unavailable")
            if m["numerator"] is not None:
                tc.assertLessEqual(m["numerator"], m["denominator"])
                tc.assertAlmostEqual(m["share"], m["numerator"] / m["denominator"])
            if "parts" in m:                                # a distribution partitions its own denominator
                tc.assertEqual(sum(p["n"] for p in m["parts"]), m["denominator"])


class TestSyntheticFullBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = synthetic()
        cls.m = metrics_of(cls.c)

    def test_contract_holds(self):
        assert_contract(self, self.m)

    def test_normalized_addresses_are_distinct_from_raw_address_keys(self):
        self.assertEqual(self.m["raw_address_keys"]["value"], 4)
        self.assertEqual(self.m["normalized_addresses"]["value"], 3)
        self.assertEqual(self.m["raw_address_keys"]["population"], overview.RAW_KEYS)
        self.assertEqual(self.m["normalized_addresses"]["population"], overview.NORMALIZED)

    def test_multi_and_single_share_the_normalized_denominator(self):
        multi, single = self.m["multi_dataset"], self.m["single_source"]
        self.assertEqual(multi["numerator"], 1)           # 1B, joined across the `#`
        self.assertEqual(multi["denominator"], single["denominator"])
        self.assertEqual(multi["denominator"], self.m["normalized_addresses"]["value"])
        self.assertEqual(multi["numerator"] + single["numerator"], multi["denominator"])
        self.assertEqual(multi["population"], single["population"])

    def test_source_contribution_is_claims_over_claims_not_addresses(self):
        sc = self.m["source_contribution"]
        self.assertEqual(sc["unit"], "claims")
        self.assertEqual(sc["denominator"], self.m["claims"]["value"])
        by = {p["key"]: p["n"] for p in sc["parts"]}
        self.assertEqual(by["tagpack"], 3)                # 3 claims on 2 addresses: the address count is not used
        self.assertEqual(sum(by.values()), sc["denominator"])

    def test_unresolved_provenance_uses_the_matching_universe(self):
        u = self.m["unresolved_provenance"]
        self.assertEqual((u["population"], u["denominator"]), (overview.NORMALIZED, 3))
        self.assertEqual(u["numerator"] + u["resolved"], u["denominator"])

    def test_claims_without_revision_is_live_over_all_claims(self):
        r = self.m["claims_without_revision"]
        self.assertEqual((r["numerator"], r["denominator"], r["quality"]), (4, 5, "live"))

    def test_reference_loader_reads_the_named_build_and_its_date(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "obs.csv.gz"
            with gzip.open(path, "wt", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["address", "source", "raw_label", "canon", "polarity", "prov_family", "lastmod", "heuristic", "subcat"])
                w.writeheader(); w.writerows(_claim("tagpack", "1A") for _ in range(2))
            old = {k: os.environ.get(k) for k in ("THEMIS_OBSERVATIONS", "THEMIS_AS_OF")}
            os.environ.update(THEMIS_OBSERVATIONS=str(path), THEMIS_AS_OF="2026-09-15")
            try:
                c = Corpus.reference()
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            self.assertTrue(c.full)
            self.assertEqual(str(c.snapshot_date), "2026-09-15")


@requires_reference_corpus
class TestBundledSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = metrics_of(Corpus.demo())

    def test_contract_holds(self):
        assert_contract(self, self.m)

    def test_sample_multi_dataset_is_labelled_sample_and_has_no_corpus_share(self):
        m = self.m["multi_dataset"]
        self.assertEqual((m["value"], m["population"], m["quality"]), (15400, overview.SAMPLE, "sample_observed"))
        self.assertIsNone(m["share"])
        for k in ("normalized_addresses", "single_source", "claims_without_revision"):
            self.assertEqual(self.m[k]["quality"], "unavailable", k)

    def test_sample_agreement_denominator_stays_the_sample_15400(self):
        a = self.m["agreement"]
        self.assertEqual((a["value"], a["population"], a["quality"]), (15400, overview.SAMPLE, "sample_observed"))
        self.assertEqual(sum(o["n"] for o in a["outcomes"].values()), 15400)

    def test_currency_is_labelled_sample(self):
        c = self.m["currency"]
        self.assertEqual((c["value"], c["population"], c["quality"]), (268891, overview.SAMPLE, "sample_observed"))
        self.assertEqual(c["corpus_n_claims"], 1545710)

    def test_raw_keys_and_unresolved_come_from_the_manifest_in_one_universe(self):
        raw, u = self.m["raw_address_keys"], self.m["unresolved_provenance"]
        self.assertEqual((raw["value"], raw["quality"]), (1497191, "manifest"))
        self.assertEqual((u["population"], u["denominator"]), (overview.RAW_KEYS, raw["value"]))

    def test_source_contribution_uses_manifest_claim_counts(self):
        by = {p["key"]: p["n"] for p in self.m["source_contribution"]["parts"]}
        self.assertEqual(by["tagpack"], 499327)           # claims; 483,296 is TagPack's address count
        self.assertEqual(sum(by.values()), 1545710)


@requires_full_corpus
class TestRealFullCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = Corpus.reference()
        c.manifest["analysis_as_of_date"] = os.environ.get("THEMIS_AS_OF", "2026-09-15")
        cls.m = metrics_of(c)

    def test_contract_holds(self):
        assert_contract(self, self.m)

    def test_multi_dataset_and_two_dataset_counts(self):
        self.assertEqual(self.m["multi_dataset"]["value"], 15413)
        depth = {p["key"]: p["n"] for p in self.m["source_depth"]["parts"]}
        self.assertEqual(depth["2"], 7845)
        self.assertEqual((depth["3"], depth["4"]), (429, 7112))
        self.assertEqual(sum(depth.values()), 15413)      # the distribution sums to the multi-dataset count

    def test_normalized_and_raw_counts_are_distinct(self):
        self.assertEqual(self.m["normalized_addresses"]["value"], 1497106)
        self.assertEqual(self.m["raw_address_keys"]["value"], 1497191)

    def test_single_source_and_unresolved_use_the_normalized_denominator(self):
        self.assertEqual(self.m["single_source"]["value"], 1481693)
        self.assertEqual(self.m["single_source"]["denominator"], 1497106)
        self.assertEqual(self.m["unresolved_provenance"]["numerator"], 853583)
        self.assertEqual(self.m["unresolved_provenance"]["denominator"], 1497106)

    def test_agreement_is_live_over_the_full_multi_dataset_set(self):
        a = self.m["agreement"]
        self.assertEqual((a["value"], a["quality"], a["population"]), (15413, "live", overview.NORMALIZED))
        self.assertEqual(sum(o["n"] for o in a["outcomes"].values()), 15413)

    def test_claims_without_revision_field(self):
        r = self.m["claims_without_revision"]
        self.assertEqual((r["numerator"], r["denominator"]), (1035420, 1545710))


@requires_reference_corpus
class TestApiSurface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app, base_url="http://localhost")
        cls.aid = cls.client.post("/api/analysis/paper").json()["analysis_id"]
        cls.summary = cls.client.get(f"/api/analysis/{cls.aid}/summary").json()

    def test_meta_and_result_state_the_corpus_scope(self):
        scope = "FULL_CORPUS" if api._reference_corpus().full else "BUNDLED_SAMPLE"
        self.assertEqual(self.summary["meta"]["corpus_scope"], scope)
        self.assertEqual(self.summary["result"]["overview"]["scope"], scope)

    def test_no_address_numerator_over_a_claims_denominator_in_shares(self):
        # the old source_claim_shares divided per-source ADDRESS counts by the CLAIM total
        self.assertNotIn("source_claim_shares", self.summary["result"]["shares"])
        assert_contract(self, self.summary["result"]["overview"]["metrics"])

    def test_claims_endpoint_names_the_population_of_its_records(self):
        r = self.client.get(f"/api/analysis/{self.aid}/claims", params={"limit": 1}).json()
        want = overview.NORMALIZED if api._reference_corpus().full else overview.SAMPLE
        self.assertEqual(r["population"], want)


if __name__ == "__main__":
    unittest.main()
