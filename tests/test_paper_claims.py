"""Every assertion here is a number printed in the paper.

If the implementation drifts from what was published, these fail. Run with:
    python -m unittest discover -s tests -v
"""
import unittest, datetime, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.corpus import Corpus
from themis import analysis, taxonomy, provenance, report


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = Corpus.demo()
        cls.agree = analysis.agreement(cls.c)
        cls.indep = analysis.independence(cls.c)
        cls.drift = analysis.drift(cls.c)


class TestAsOfDate(Base):
    """Loop 2 STEP 16/28 - paper reproduction freezes freshness to the
    corpus's own snapshot date, not the wall clock at report time."""

    def test_snapshot_date_is_fixed_not_todays_date(self):
        snap = self.c.snapshot_date
        self.assertIsNotNone(snap)
        self.assertNotEqual(snap, datetime.date.today())

    def test_report_freshness_matches_explicit_snapshot_date(self):
        r1 = report.build_corpus_report(self.c)
        r2 = report.build_corpus_report(self.c, analysis_as_of_date=self.c.snapshot_date)
        self.assertEqual(r1["freshness"], r2["freshness"])
        self.assertEqual(r1["analysis_as_of_date"], str(self.c.snapshot_date))

    def test_missing_date_claim_is_currency_unknown_regardless_of_as_of(self):
        flags = taxonomy.currency_flags({"lastmod": ""}, today=self.c.snapshot_date)
        self.assertEqual(flags, ["currency-unknown"])

    def test_explain_freezes_currency_flags_to_snapshot_date_by_default(self):
        # explain() must default to the corpus's snapshot date, not
        # datetime.date.today(), or the same archived address flips "stale"
        # as real time passes even though the corpus itself never changed.
        dated = next(c for c in self.c.claims if (c.get("lastmod") or "").strip())
        r = analysis.explain(self.c, dated["address"])
        expected = {f for cl in self.c.by_addr[dated["address"]]
                    for f in taxonomy.currency_flags(cl, today=self.c.snapshot_date)}
        got = {f for cl in r["claims"] for f in cl["flags"]}
        self.assertEqual(got, expected)

    def test_explain_honors_an_explicit_as_of_override(self):
        dated = next(c for c in self.c.claims if (c.get("lastmod") or "").strip())
        far_future = datetime.date.fromisoformat(dated["lastmod"][:10]) + datetime.timedelta(days=365 * 10)
        r = analysis.explain(self.c, dated["address"], as_of=far_future)
        flags = {f for cl in r["claims"] if cl["source"] == dated["source"] for f in cl["flags"]}
        self.assertIn("stale", flags)

    def test_drift_threads_snapshot_date_into_a_current_only_policy(self):
        # none of the four bundled paper conditions use current_only, and
        # the revenue task's own claims carry no lastmod field at all (so
        # this can't discriminate wall-clock-vs-snapshot the way
        # TestCurrentOnlyIsDeterministic in test_trust_engine.py does
        # directly against the predicate) - this only proves the wiring
        # itself: drift()'s new as_of parameter reaches the policy context
        # without raising, and its default agrees with an explicit
        # snapshot_date, for any custom policy a real dataset might define.
        original = analysis._cfg.trust_rules
        patched = dict(original)
        patched["policies"] = dict(patched["policies"])
        patched["policies"]["fresh_only"] = {
            "label": "current only", "aggregation": "dedup_max_per_address",
            "eligibility": ["current_only"],
        }
        analysis._cfg.trust_rules = patched
        try:
            d_default = analysis.drift(self.c)
            d_explicit = analysis.drift(self.c, as_of=self.c.snapshot_date)
        finally:
            analysis._cfg.trust_rules = original
        self.assertEqual(d_default["conditions"]["fresh_only"]["observations"],
                         d_explicit["conditions"]["fresh_only"]["observations"])
        self.assertGreater(d_default["conditions"]["fresh_only"]["observations"], 0)


class TestCorpus(Base):
    def test_totals(self):
        self.assertEqual(self.c.n_claims, 1_545_710)
        self.assertEqual(self.c.n_addresses, 1_497_191)

    def test_source_sizes(self):
        self.assertEqual(self.c.source_sizes(), {
            "ellipticpp": 822_937, "tagpack": 483_296, "schnoering": 101_387,
            "rodwald_mixers": 57_817, "rodwald_ransom": 50_322,
            "ransomwhere": 11_186, "watchyourback": 309})

    def test_roots(self):
        self.assertEqual(self.indep["n_roots_total"], 25)
        self.assertEqual(self.indep["n_roots_identified"], 21)

    def test_unresolved_provenance(self):
        self.assertEqual(self.indep["unresolved_addresses"], 853_583)
        self.assertAlmostEqual(self.indep["unresolved_addr_share"], 0.570, places=3)


class TestAgreement(Base):
    """Section 5.1."""

    def test_multi_source_count_and_rate(self):
        self.assertEqual(self.agree["n_multi_source"], 15_400)
        self.assertEqual(self.agree["single_source"], 1_481_791)
        self.assertAlmostEqual(100 * self.agree["multi_source_rate"], 1.03, places=2)

    def test_dataset_distribution_is_corpus_wide_and_closes(self):
        """The 1-dataset bucket must be the corpus figure, not the sample's, and
        the buckets above it must sum to the multi-dataset total."""
        d = self.agree["sources_per_address"]
        self.assertEqual(d[1], 1_481_791)
        self.assertEqual(d[2], 7_904)
        self.assertEqual(d[3], 357)
        self.assertEqual(d[4], 7_112)
        self.assertEqual(d[5], 26)
        self.assertEqual(d[6], 1)
        self.assertEqual(sum(v for k, v in d.items() if k >= 2), 15_400)
        self.assertEqual(sum(d.values()), 1_497_191)

    def test_outcome_counts(self):
        o = self.agree["outcomes"]
        self.assertEqual(o["exact"]["n"], 13_673)
        self.assertEqual(o["hierarchical refinement"]["n"], 1_253)
        self.assertEqual(o["entity-type conflict"]["n"], 342)
        self.assertEqual(o["licit/illicit conflict"]["n"], 109)
        self.assertEqual(o["incomparable"]["n"], 23)

    def test_outcome_shares(self):
        o = self.agree["outcomes"]
        self.assertAlmostEqual(100 * o["exact"]["share"], 88.79, places=2)
        self.assertAlmostEqual(100 * o["hierarchical refinement"]["share"], 8.14, places=2)
        self.assertAlmostEqual(100 * o["entity-type conflict"]["share"], 2.22, places=2)
        self.assertAlmostEqual(100 * o["licit/illicit conflict"]["share"], 0.71, places=2)

    def test_named_conflict_pairs(self):
        pairs = {(p["source_a"], p["label_a"], p["source_b"], p["label_b"]): p["n"]
                 for p in self.agree["top_polarity_conflicts"]}
        self.assertEqual(pairs[("schnoering", "exchange", "tagpack", "sanctioned")], 23)
        self.assertEqual(pairs[("ellipticpp", "licit_unspec", "rodwald_mixers", "mixer")], 30)


class TestIndependence(Base):
    """Section 5.2 - the circularity result."""

    def test_field_decode_is_a_clean_split(self):
        """Every group large enough and well-formed enough to judge falls at one
        extreme: wholly inside Ransomwhere, or disjoint from it. Groups too small
        to establish containment, and the one malformed value the dataset ships,
        are reported separately rather than forced to a verdict."""
        fd = self.indep["field_decodes"][0]
        self.assertTrue(fd["clean_split"], "R-groups must split cleanly at 100%/0%")
        for v, g in fd["groups"].items():
            if g["verdict"] in ("malformed", "insufficient"):
                continue
            if "R" in v:
                self.assertEqual(g["verdict"], "inherited", f"group {v}")
                self.assertAlmostEqual(g["share_in_candidate"], 1.0, places=6)
            else:
                self.assertEqual(g["verdict"], "independent", f"group {v}")
                self.assertAlmostEqual(g["share_in_candidate"], 0.0, places=6)

    def test_malformed_group_is_named_not_silently_judged(self):
        fd = self.indep["field_decodes"][0]
        self.assertEqual(fd["groups"]["H,S"]["verdict"], "malformed")
        self.assertIn("H,S", fd["inconclusive_groups"])

    def test_tiny_groups_are_insufficient_not_conclusive(self):
        fd = self.indep["field_decodes"][0]
        for v, g in fd["groups"].items():
            if g["n"] < 5 and v.isalpha():
                self.assertEqual(g["verdict"], "insufficient", f"group {v}")

    def test_decoded_group_sizes(self):
        g = self.indep["field_decodes"][0]["groups"]
        self.assertEqual(g["RSH"]["n"], 6_546)
        self.assertEqual(g["RS"]["n"], 494)
        self.assertEqual(g["R"]["n"], 400)
        self.assertEqual(g["S"]["n"], 28_684)
        self.assertEqual(g["H"]["n"], 11_738)
        self.assertEqual(g["SH"]["n"], 2_367)

    def test_inherited_total(self):
        self.assertEqual(self.indep["field_decodes"][0]["inherited_addresses"], 7_508)

    def test_naming_residue(self):
        nr = self.indep["naming_residues"][0]
        self.assertEqual(nr["total"], 50_322)
        self.assertEqual(nr["attributed"], 11_796)
        self.assertAlmostEqual(100 * nr["share"], 23.44, places=2)
        self.assertEqual(nr["by_root"]["princeton_huang_2018"], 9_176)
        self.assertEqual(nr["by_root"]["padua_conti_2018"], 1_801)
        self.assertEqual(nr["by_root"]["montreal_paquet_clouston_2019"], 819)

    def test_montreal_set_propagation(self):
        m = self.indep["notable_root_propagation"][0]
        self.assertEqual(m["size"], 7_222)
        self.assertEqual(m["propagation"]["ransomwhere"], 7_208)
        self.assertEqual(m["propagation"]["tagpack"], 7_208)
        self.assertEqual(m["propagation"]["rodwald_ransom"], 7_122)

    def test_root_concentration(self):
        rc = {r["root"]: r["share"] for r in self.indep["root_concentration"]}
        self.assertAlmostEqual(100 * rc["elliptic_undisclosed"], 53.2, places=1)
        self.assertAlmostEqual(100 * rc["tagpack_GraphSense Core Team"], 24.8, places=1)


class TestKappa(Base):
    """Section 5.1 - chance-corrected agreement, now produced by released code
    rather than traced to an external script."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.k = analysis.cohen_kappa(cls.c)

    def test_pair_tally_closes(self):
        k = self.k
        self.assertEqual(k["n_pairs"], 17)
        self.assertEqual(k["n_undefined"], 4)
        self.assertEqual(k["n_zero"], 8)
        self.assertLessEqual(k["n_undefined"] + k["n_zero"], k["n_pairs"])

    def test_largest_overlap_matches_containment_table(self):
        pair = next(r for r in self.k["pairs"]
                    if {r["source_a"], r["source_b"]} == {"schnoering", "tagpack"})
        self.assertEqual(pair["n"], 8_139)
        self.assertAlmostEqual(100 * pair["percent_agreement"], 93.3, places=1)
        self.assertAlmostEqual(pair["cohen_kappa"], 0.655, places=3)

    def test_three_pairs_are_substantial(self):
        self.assertEqual(len(self.k["substantial"]), 3)
        by = {r["pair"]: r["cohen_kappa"] for r in self.k["substantial"]}
        self.assertAlmostEqual(by["schnoering-tagpack"], 0.655, places=3)
        self.assertAlmostEqual(by["schnoering-watchyourback"], 0.537, places=3)
        self.assertAlmostEqual(by["tagpack-watchyourback"], 0.523, places=3)

    def test_undefined_pairs_are_named_not_dropped(self):
        und = [r for r in self.k["pairs"] if r["cohen_kappa"] is None]
        self.assertEqual(len(und), 4)
        for r in und:
            self.assertIsNotNone(r["note"])
            self.assertAlmostEqual(r["percent_agreement"], 1.0, places=6)

    def test_substantial_threshold_is_read_from_config_not_hardcoded(self):
        # thresholds.yml documents kappa_substantial_threshold as exactly
        # this cutoff; raising it must actually change which pairs surface.
        original = analysis._cfg.thresholds.get("kappa_substantial_threshold")
        analysis._cfg.thresholds["kappa_substantial_threshold"] = 0.6
        try:
            k = analysis.cohen_kappa(self.c)
            self.assertEqual({r["pair"] for r in k["substantial"]}, {"schnoering-tagpack"})
        finally:
            if original is None:
                analysis._cfg.thresholds.pop("kappa_substantial_threshold", None)
            else:
                analysis._cfg.thresholds["kappa_substantial_threshold"] = original


class TestDrift(Base):
    """Section 5.3 - the headline. Cent-level tolerance: the bundled revenue
    file stores USD rounded to two decimals."""

    def test_condition_values(self):
        c = self.drift["conditions"]
        self.assertAlmostEqual(c["A"]["usd"], 1_367_997_318, delta=5)
        self.assertAlmostEqual(c["B"]["usd"], 1_101_304_945, delta=5)
        self.assertAlmostEqual(c["C"]["usd"], 1_045_637_069, delta=5)
        self.assertAlmostEqual(c["D"]["usd"], 112_426_902, delta=5)

    def test_condition_counts(self):
        c = self.drift["conditions"]
        self.assertEqual(c["A"]["observations"], 61_508)
        self.assertEqual(c["A"]["addresses"], 54_000)
        self.assertEqual(c["B"]["observations"], 54_000)
        self.assertEqual(c["C"]["observations"], 42_237)
        self.assertEqual(c["D"]["observations"], 7_457)

    def test_spread_and_coverage(self):
        self.assertAlmostEqual(self.drift["spread_B_over_D"], 9.8, places=1)
        self.assertAlmostEqual(self.drift["spread_A_over_D"], 12.2, places=1)
        self.assertAlmostEqual(
            100 * self.drift["conditions"]["D"]["coverage_vs_B"], 13.8, places=1)
        self.assertAlmostEqual(
            100 * self.drift["conditions"]["A"]["coverage_vs_B"], 113.9, places=1)

    def test_naive_inflation_and_collapse(self):
        c = self.drift["conditions"]
        self.assertAlmostEqual(100 * (c["A"]["usd"] / c["B"]["usd"] - 1), 24.2, places=1)
        self.assertAlmostEqual(100 * (1 - c["C"]["observations"] / c["B"]["observations"]),
                               21.8, places=1)
        self.assertAlmostEqual(100 * (1 - c["C"]["usd"] / c["B"]["usd"]), 5.1, places=1)

    def test_double_counted_addresses(self):
        self.assertEqual(self.drift["shared_addresses"], 7_508)


class TestTaxonomy(unittest.TestCase):
    """Section 3.2 - the rules the reviewer asked us to tighten."""

    def test_missing_date_is_currency_unknown_never_stale(self):
        f = taxonomy.currency_flags({"lastmod": ""})
        self.assertIn("currency-unknown", f)
        self.assertNotIn("stale", f)

    def test_old_date_is_stale(self):
        f = taxonomy.currency_flags({"lastmod": "2019-01-01"},
                                    today=datetime.date(2026, 9, 16))
        self.assertEqual(f, ["stale"])

    def test_recent_date_is_neither(self):
        f = taxonomy.currency_flags({"lastmod": "2026-01-01"},
                                    today=datetime.date(2026, 9, 16))
        self.assertEqual(f, [])

    def test_generic_vs_specific_is_refinement_not_conflict(self):
        claims = [{"source": "a", "canon": "illicit_unspec"},
                  {"source": "b", "canon": "ransomware"}]
        self.assertEqual(taxonomy.classify_address(claims), "hierarchical refinement")

    def test_opposed_polarity_is_conflict(self):
        claims = [{"source": "a", "canon": "exchange"},
                  {"source": "b", "canon": "ransomware"}]
        self.assertEqual(taxonomy.classify_address(claims), "licit/illicit conflict")

    def test_same_polarity_different_entity_is_entity_conflict(self):
        claims = [{"source": "a", "canon": "exchange"},
                  {"source": "b", "canon": "gambling"}]
        self.assertEqual(taxonomy.classify_address(claims), "entity-type conflict")

    def test_unresolved_is_not_a_root(self):
        self.assertTrue(provenance.is_unresolved("elliptic_undisclosed"))
        self.assertTrue(provenance.is_unresolved("rodwald_own_S"))
        self.assertFalse(provenance.is_unresolved("ofac_sdn"))


class TestHierarchyAdversarial(unittest.TestCase):
    """Part N - the bundled taxonomy.yml is only ever 2 levels deep (every
    specific category's parent is directly illicit_unspec/licit_unspec), so
    classify_address's generic N-level ancestor walk is never actually
    exercised past that incidental case by the paper corpus. These tests
    swap in a synthetic 3-level tree to prove the walk is structural (via
    `parent:` links only) rather than name-based, and that only a genuine
    ancestor/descendant pair reads as refinement - siblings under a shared
    non-root parent, or categories in unrelated branches, must not.
    """
    SYNTHETIC = {
        "illicit_unspec": {"polarity": "illicit"},
        "service": {"polarity": "illicit", "parent": "illicit_unspec"},
        "exchange_service": {"polarity": "illicit", "parent": "service"},
        "otc_desk": {"polarity": "illicit", "parent": "service"},
        "unrelated_branch": {"polarity": "illicit", "parent": "illicit_unspec"},
    }

    def setUp(self):
        self._orig_categories = taxonomy.CATEGORIES
        self._orig_polarity = taxonomy.POLARITY
        self._orig_generic = taxonomy.GENERIC
        taxonomy.CATEGORIES = self.SYNTHETIC
        taxonomy.POLARITY = {c: n.get("polarity", "unknown") for c, n in self.SYNTHETIC.items()}
        taxonomy.GENERIC = {c for c, n in self.SYNTHETIC.items()
                            if n.get("parent") is None and n.get("polarity") in ("licit", "illicit")}

    def tearDown(self):
        taxonomy.CATEGORIES = self._orig_categories
        taxonomy.POLARITY = self._orig_polarity
        taxonomy.GENERIC = self._orig_generic

    def _classify(self, a, b):
        return taxonomy.classify_address([{"source": "a", "canon": a}, {"source": "b", "canon": b}])

    def test_grandparent_grandchild_is_a_genuine_refinement(self):
        # "service" is a real 2-hop ancestor of "exchange_service", not just
        # the generic polarity root - this only passes if ancestors() walks
        # the full parent chain rather than checking one hop.
        self.assertEqual(self._classify("service", "exchange_service"), "hierarchical refinement")

    def test_siblings_under_a_shared_non_root_parent_are_not_refinement(self):
        # neither is an ancestor of the other - a common non-root parent
        # must not be mistaken for a direct relationship.
        self.assertEqual(self._classify("exchange_service", "otc_desk"), "entity-type conflict")

    def test_unrelated_branches_are_not_refinement(self):
        self.assertEqual(self._classify("exchange_service", "unrelated_branch"), "entity-type conflict")


class TestExplain(Base):
    """The per-address demonstration."""

    def test_circular_address_is_flagged(self):
        r = analysis.explain(self.c, "14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7")
        self.assertTrue(r["found"])
        self.assertTrue(r["circular"])
        self.assertLess(r["actual_corroboration"], r["apparent_corroboration"])
        self.assertIn("circular", r["flags"])

    def test_conflicting_address_is_flagged(self):
        r = analysis.explain(self.c, "34kWCKF2wCbe6uinit2uL4ND6d8yxsuxKM")
        self.assertEqual(r["outcome"], "licit/illicit conflict")
        self.assertIn("conflicting", r["flags"])

    def test_unknown_address_reports_not_found(self):
        r = analysis.explain(self.c, "1NotARealBitcoinAddressAtAll00000")
        self.assertFalse(r["found"])


class TestBootstrap(Base):
    """Section 5.4 - the interval must widen, not narrow, when clustered."""

    def test_conditional_rates_have_intervals(self):
        b = analysis.bootstrap(self.c, n_boot=200)
        s = b["stats"]["licit/illicit conflict"]
        self.assertAlmostEqual(100 * s["point"], 0.71, places=2)
        self.assertLess(s["ci_low"], s["point"])
        self.assertGreater(s["ci_high"], s["point"])

    def test_corpus_wide_rate_withheld_on_sample(self):
        b = analysis.bootstrap(self.c, n_boot=50)
        self.assertNotIn("multi_source_rate", b["stats"])
        self.assertFalse(b["corpus_wide_rates"])

    def test_upper_bound_has_more_clusters(self):
        lo = analysis.bootstrap(self.c, n_boot=50, upper_bound=False)
        hi = analysis.bootstrap(self.c, n_boot=50, upper_bound=True)
        self.assertGreater(hi["n_clusters"], lo["n_clusters"])

    def test_empty_corpus_does_not_crash_with_or_without_numpy(self):
        # K=0 clusters: the numpy path computed 1.0/K directly (a
        # ZeroDivisionError before numpy ever ran), while the no-numpy path
        # avoided it by accident (range(K) with K=0 never calls
        # randrange(K)). Every stat must degrade to None, not raise,
        # regardless of which backend is active in this environment.
        empty = Corpus([], full=True)
        b = analysis.bootstrap(empty, n_boot=20)
        self.assertEqual(b["n_clusters"], 0)
        for s in b["stats"].values():
            self.assertIsNone(s["point"])
            self.assertIsNone(s["ci_low"])
            self.assertIsNone(s["ci_high"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
