"""STEP 37 - the generic trust-rule policy engine, independent of the
ransomware-revenue task it happens to be reproduced against in the paper,
plus a config-loader test proving taxonomy/thresholds are genuinely
data-driven (STEP 3: configurable, not buried constants).
"""
import datetime, sys, pathlib, unittest, tempfile, shutil
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis import config_io
from themis.trust import policy as trust_policy, predicates
from themis.trust.drift import run as run_drift


class TestPolicyEngine(unittest.TestCase):
    """A tiny synthetic task: three claims across two addresses, none of
    them ransomware or Bitcoin-specific, to prove the engine has no
    dataset knowledge baked in."""

    def _claims(self):
        return [
            {"address": "addr1", "source": "origin_src", "value": 10.0,
             "root": "r1", "prov_resolved": True, "prov_native": True},
            {"address": "addr1", "source": "copy_src", "value": 7.0,
             "root": "r1", "prov_resolved": True, "prov_native": False},
            {"address": "addr2", "source": "lone_src", "value": 5.0,
             "root": "r2", "prov_resolved": False, "prov_native": False},
        ]

    @staticmethod
    def _aggregate(claims, mode):
        if mode == "raw_sum":
            return dict(observations=len(claims), addresses=len({c["address"] for c in claims}),
                        value=sum(c["value"] for c in claims))
        if mode == "dedup_max_per_address":
            best = {}
            for c in claims:
                best[c["address"]] = max(best.get(c["address"], 0.0), c["value"])
            return dict(observations=len(best), addresses=len(best), value=sum(best.values()))
        raise ValueError(mode)

    def test_no_eligibility_keeps_every_claim(self):
        policies, baseline = trust_policy.load_policies({
            "baseline": "all",
            "policies": {"all": {"label": "all", "aggregation": "raw_sum", "eligibility": []}}})
        out = run_drift(self._claims(), policies, baseline, self._aggregate)
        self.assertEqual(out["results"]["all"]["observations"], 3)
        self.assertEqual(out["results"]["all"]["value"], 22.0)

    def test_root_independent_or_native_drops_uncorroborated_copy_only(self):
        """addr1 has a native claim, so BOTH its claims survive (dedup picks
        the max); addr2's sole claim is unresolved, so it survives too -
        nothing here should ever be dropped for this synthetic corpus."""
        policies, baseline = trust_policy.load_policies({
            "baseline": "b", "policies": {
                "b": {"label": "dedup", "aggregation": "dedup_max_per_address", "eligibility": []},
                "collapsed": {"label": "collapsed", "aggregation": "dedup_max_per_address",
                              "eligibility": ["root_independent_or_native"]}}})
        out = run_drift(self._claims(), policies, baseline, self._aggregate)
        self.assertEqual(out["results"]["collapsed"]["addresses"], 2)
        self.assertEqual(out["results"]["collapsed"]["value"], 15.0)   # max(10,7) + 5

    def test_lone_resolved_non_native_claim_is_excluded(self):
        """Change addr2's claim to a resolved, non-native root with nothing
        else at that address to corroborate it: it must be dropped."""
        claims = self._claims()
        claims[2]["prov_resolved"] = True
        policies, baseline = trust_policy.load_policies({
            "baseline": "b", "policies": {
                "b": {"label": "dedup", "aggregation": "dedup_max_per_address", "eligibility": []},
                "collapsed": {"label": "collapsed", "aggregation": "dedup_max_per_address",
                              "eligibility": ["root_independent_or_native"]}}})
        out = run_drift(claims, policies, baseline, self._aggregate)
        self.assertEqual(out["results"]["collapsed"]["addresses"], 1)   # addr2 dropped
        self.assertEqual(out["results"]["collapsed"]["value"], 10.0)

    def test_ratio_and_coverage_are_reported_against_the_baseline(self):
        policies, baseline = trust_policy.load_policies({
            "baseline": "b", "policies": {
                "b": {"label": "dedup", "aggregation": "dedup_max_per_address", "eligibility": []},
                "collapsed": {"label": "collapsed", "aggregation": "dedup_max_per_address",
                              "eligibility": ["root_independent_or_native"]}}})
        out = run_drift(self._claims(), policies, baseline, self._aggregate)
        r = out["results"]["collapsed"]
        self.assertIsNotNone(r["ratio_vs_baseline"])
        self.assertIsNotNone(r["coverage_vs_baseline"])


class TestAnchorSelfValidation(unittest.TestCase):
    """STEP 14 - a claim cannot validate itself through its own provenance
    root: anchor_membership must require an externally supplied set and
    never fall back to the claim's own verified/native flags."""

    def test_no_anchor_set_supplied_means_nothing_is_eligible(self):
        claim = {"address": "x", "prov_resolved": True, "prov_native": True, "prov_verified": True}
        self.assertFalse(predicates.anchor_membership(claim, {}))

    def test_verified_native_claim_not_anchor_listed_is_not_eligible(self):
        """Being independently 'verified' by its own root is not the same
        as appearing in the anchor set - the two must not be conflated."""
        claim = {"address": "x", "prov_resolved": True, "prov_native": True, "prov_verified": True}
        ctx = {"anchor_addresses": {"some_other_address"}}
        self.assertFalse(predicates.anchor_membership(claim, ctx))

    def test_anchor_listed_address_is_eligible(self):
        claim = {"address": "x"}
        ctx = {"anchor_addresses": {"x"}}
        self.assertTrue(predicates.anchor_membership(claim, ctx))


class TestCurrentOnlyIsDeterministic(unittest.TestCase):
    """current_only must honor an explicit as_of from context rather than
    always falling back to the live wall clock - otherwise a policy using
    it would report a different eligible set on different days for the
    exact same archived corpus (Loop 2 STEP 16's determinism requirement,
    same one analysis.explain()/drift() already freeze to snapshot_date)."""

    def test_honors_explicit_as_of_from_context(self):
        claim = {"lastmod": "2019-01-01"}
        self.assertFalse(predicates.current_only(claim, {"as_of": datetime.date(2026, 1, 1)}))
        self.assertTrue(predicates.current_only(claim, {"as_of": datetime.date(2019, 6, 1)}))

    def test_falls_back_to_today_only_when_context_has_no_as_of(self):
        claim = {"lastmod": str(datetime.date.today())}
        self.assertTrue(predicates.current_only(claim, {}))


class TestConfigIsDataDriven(unittest.TestCase):
    """STEP 3 - taxonomy/thresholds/trust rules must load from arbitrary
    config, proving nothing is a buried constant in the engine."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        (pathlib.Path(self.tmp) / "sources").mkdir()
        (pathlib.Path(self.tmp) / "taxonomy.yml").write_text(
            "categories:\n  widget: {polarity: licit}\n  gadget: {polarity: illicit}\n")
        (pathlib.Path(self.tmp) / "thresholds.yml").write_text("staleness_years: 1.5\n")
        (pathlib.Path(self.tmp) / "trust_rules.yml").write_text(
            "baseline: b\npolicies:\n  b: {label: b, aggregation: raw_sum, eligibility: []}\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_arbitrary_categories_load_from_config(self):
        cfg = config_io.Config(pathlib.Path(self.tmp))
        self.assertEqual(cfg.taxonomy["widget"]["polarity"], "licit")
        self.assertEqual(cfg.taxonomy["gadget"]["polarity"], "illicit")
        self.assertNotIn("ransomware", cfg.taxonomy)   # nothing paper-specific leaked in

    def test_custom_threshold_overrides_default(self):
        cfg = config_io.Config(pathlib.Path(self.tmp))
        self.assertEqual(cfg.thresholds["staleness_years"], 1.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
