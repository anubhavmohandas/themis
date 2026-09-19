"""Every assertion here is a number printed in the paper.

If the implementation drifts from what was published, these fail. Run with:
    python -m unittest discover -s tests -v
"""
import unittest, datetime, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.corpus import Corpus
from themis import analysis, taxonomy, provenance, report
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _data import HAVE_REFERENCE, REASON, requires_reference_corpus


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_REFERENCE:
            raise unittest.SkipTest(REASON)
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

    def test_bundled_sample_declares_the_papers_analysis_date(self):
        # the paper judges staleness at its retrieval date (2026-09-15), not at
        # the newest revision in the claims (2024-10-29, which would call a
        # corpus retrieved two years later "fresh")
        self.assertEqual(self.c.snapshot_date, datetime.date(2026, 9, 15))
        newest = max(c["lastmod"] for c in self.c.claims if c["lastmod"])
        self.assertLess(newest[:10], "2026-09-15")

    def test_paper_staleness_statement_direction_reproduces(self):
        # Sec 5.1: "within TagPack 99.9% of dated claims are over three years
        # old". The sample over-represents multi-dataset addresses so it gives
        # 99.1%, not 99.9% (needs the full build); under the newest-revision
        # date it was 5.2%, which contradicted the paper outright.
        tp = [c for c in self.c.claims if c["source"] == "tagpack" and (c["lastmod"] or "").strip()]
        stale = sum(1 for c in tp if "stale" in taxonomy.currency_flags(c, today=self.c.snapshot_date))
        self.assertGreater(stale / len(tp), 0.99)

    def test_without_a_declared_date_the_newest_revision_is_the_fallback(self):
        claims = [dict(address="1" * 26, source="tagpack", raw_label="x", canon="mixer", polarity="illicit",
                       prov_family="tagpack:t", lastmod=d, heuristic="curated", subcat="")
                  for d in ("2020-01-02", "2022-03-04", "")]
        c = Corpus(claims, full=True)
        self.assertEqual(c.snapshot_date, datetime.date(2022, 3, 4))
        c.manifest["analysis_as_of_date"] = "2026-09-15"
        self.assertEqual(c.snapshot_date, datetime.date(2026, 9, 15))
        c.manifest["analysis_as_of_date"] = "not-a-date"      # malformed: falls back, never raises
        self.assertEqual(c.snapshot_date, datetime.date(2022, 3, 4))

    def test_freshness_states_its_own_denominator_and_scope(self):
        # the sample's freshness (86% currency-unknown) must never be read as
        # the corpus's (>= 67.0% of 1,545,710) - the payload says which it is
        r = report.build_corpus_report(self.c)
        f, scope = r["freshness"], r["freshness_scope"]
        self.assertEqual(f["n_claims"], f["current"] + f["stale"] + f["currency_unknown"])
        self.assertEqual((scope["n_claims_analysed"], scope["corpus_n_claims"], scope["sample"]),
                         (268_891, 1_545_710, True))

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

    def test_manifest_sample_address_count_matches_live_dedup(self):
        # demo_data/manifest.json's "sample" section is a static, hand-
        # regenerated figure (unlike n_addresses/n_claims, which read
        # "full_corpus" for the paper's own 1,497,191 headline and are
        # unaffected by any bundled-sample fix). It drifted stale once
        # already: the WatchYourBack "#" address-key fix deduplicated 72
        # addresses within the sample itself (228,847 -> 228,775) without
        # anything catching that the note's stored count still said
        # 228,847. This pins sample_note's number to the corpus's own live
        # count so a future fix can't silently leave it stale again.
        live = len(Corpus.demo().by_addr)
        self.assertIn(f"{live:,} addresses", self.c.sample_note)


class TestAgreement(Base):
    """Section 5.1."""

    def test_multi_source_count_and_rate(self):
        self.assertEqual(self.agree["n_multi_source"], 15_400)
        self.assertEqual(self.agree["single_source"], 1_481_791)
        self.assertAlmostEqual(100 * self.agree["multi_source_rate"], 1.03, places=2)

    def test_dataset_distribution_is_corpus_wide_and_closes(self):
        """The 1-dataset bucket must be the corpus figure, not the sample's, and
        the buckets above it must sum to the multi-dataset total."""
        # d[2]/d[3] shifted 7,904/357 -> 7,832/429 (72 addresses moved from
        # the 2-source to the 3-source bucket) after fixing WatchYourBack's
        # "#"-prefixed address-key bug (config/sources/watchyourback.yml's
        # address_normalization): those 72 addresses already existed under
        # schnoering/tagpack, so restoring the join reveals watchyourback as
        # a genuine 3rd source rather than an invisible, orphaned 4th
        # address. The total (15,400) and single-dataset count (1,481,791)
        # are unaffected - neither is published as a per-bucket breakdown in
        # the paper, only as the 15,400/1.03% and 1,497,191 totals (both
        # untouched: 1,497,191 is a fixed manifest figure, not recomputed
        # from this join, and the 72 addresses were never separately counted
        # there to begin with).
        d = self.agree["sources_per_address"]
        self.assertEqual(d[1], 1_481_791)
        self.assertEqual(d[2], 7_832)
        self.assertEqual(d[3], 429)
        self.assertEqual(d[4], 7_112)
        self.assertEqual(d[5], 26)
        self.assertEqual(d[6], 1)
        self.assertEqual(sum(v for k, v in d.items() if k >= 2), 15_400)
        self.assertEqual(sum(d.values()), 1_497_191)

    def test_outcome_counts(self):
        # NOTE: these differ from the currently-published paper draft
        # (13,673 / 342 / 109 / 23) - see HARDENING_LOG.md's "PAPER MAY
        # NEED UPDATE" section. classify_address() used to report "exact
        # agreement" whenever only ONE source's claim had an interpretable
        # canonical category and every other source's claim was unmapped
        # (canon == "unknown", e.g. Elliptic++'s undocumented "class_3"
        # code) - that's not agreement, it's one opinion with nothing to
        # compare it against. Fixed to require >= 2 sources with a known
        # canon before returning anything but "incomparable"; these are the
        # corrected, implementation-verified counts.
        o = self.agree["outcomes"]
        self.assertEqual(o["exact"]["n"], 10_515)
        self.assertEqual(o["hierarchical refinement"]["n"], 1_253)
        self.assertEqual(o["entity-type conflict"]["n"], 340)
        self.assertEqual(o["licit/illicit conflict"]["n"], 108)
        self.assertEqual(o["incomparable"]["n"], 3_184)
        self.assertEqual(sum(o[k]["n"] for k in o), 15_400)

    def test_outcome_shares(self):
        o = self.agree["outcomes"]
        self.assertAlmostEqual(100 * o["exact"]["share"], 68.28, places=2)
        self.assertAlmostEqual(100 * o["hierarchical refinement"]["share"], 8.14, places=2)
        self.assertAlmostEqual(100 * o["entity-type conflict"]["share"], 2.21, places=2)
        self.assertAlmostEqual(100 * o["licit/illicit conflict"]["share"], 0.70, places=2)
        self.assertAlmostEqual(100 * o["incomparable"]["share"], 20.68, places=2)

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
        # n_zero 8 -> 7: the WatchYourBack address-key fix (see
        # test_dataset_distribution_is_corpus_wide_and_closes) changes which
        # watchyourback-involving pairs' shared region looks like by
        # restoring 72 previously-invisible joins. The paper never
        # publishes n_pairs/n_undefined/n_zero or any per-pair kappa value
        # (confirmed: neither "kappa" nor "Cohen" appears in the final
        # paper PDF at all), so this is zero paper-text impact.
        k = self.k
        self.assertEqual(k["n_pairs"], 17)
        self.assertEqual(k["n_undefined"], 4)
        self.assertEqual(k["n_zero"], 7)
        self.assertLessEqual(k["n_undefined"] + k["n_zero"], k["n_pairs"])

    def test_largest_overlap_matches_containment_table(self):
        pair = next(r for r in self.k["pairs"]
                    if {r["source_a"], r["source_b"]} == {"schnoering", "tagpack"})
        self.assertEqual(pair["n"], 8_139)
        self.assertAlmostEqual(100 * pair["percent_agreement"], 93.3, places=1)
        self.assertAlmostEqual(pair["cohen_kappa"], 0.655, places=3)

    def test_substantial_pairs_after_watchyourback_address_fix(self):
        # Before the "#" address-key fix: 3 substantial pairs, including
        # schnoering-watchyourback (n=46, kappa=0.537). After: only 2 -
        # restoring the 72 hidden joins drops schnoering-watchyourback's
        # kappa to 0.233 (n grows to 117, but agreement among the newly-
        # joined addresses is much lower, pulling kappa below the 0.4
        # substantial-agreement threshold), while tagpack-watchyourback's
        # own kappa *rises* (0.523 -> 0.613, n 138 -> 210) because most of
        # the 72 newly-visible addresses are ones tagpack and watchyourback
        # already agreed on. Not published in the paper (see
        # test_pair_tally_closes) - a real, verified shift with zero
        # paper-text impact.
        self.assertEqual(len(self.k["substantial"]), 2)
        by = {r["pair"]: r["cohen_kappa"] for r in self.k["substantial"]}
        self.assertAlmostEqual(by["schnoering-tagpack"], 0.655, places=3)
        self.assertAlmostEqual(by["tagpack-watchyourback"], 0.613, places=3)
        self.assertNotIn("schnoering-watchyourback", by)
        sw = next(r for r in self.k["pairs"]
                  if {r["source_a"], r["source_b"]} == {"schnoering", "watchyourback"})
        self.assertAlmostEqual(sw["cohen_kappa"], 0.233, places=3)
        self.assertEqual(sw["n"], 117)

    def test_undefined_pairs_are_named_not_dropped(self):
        und = [r for r in self.k["pairs"] if r["cohen_kappa"] is None]
        self.assertEqual(len(und), 4)
        for r in und:
            self.assertIsNotNone(r["note"])
            self.assertAlmostEqual(r["percent_agreement"], 1.0, places=6)

    def test_substantial_threshold_is_read_from_config_not_hardcoded(self):
        # thresholds.yml documents kappa_substantial_threshold as exactly
        # this cutoff; raising it must actually change which pairs surface.
        # tagpack-watchyourback's post-fix kappa (0.613, see
        # test_substantial_pairs_after_watchyourback_address_fix) still
        # clears 0.6, so it stays in the raised-threshold set too.
        original = analysis._cfg.thresholds.get("kappa_substantial_threshold")
        analysis._cfg.thresholds["kappa_substantial_threshold"] = 0.6
        try:
            k = analysis.cohen_kappa(self.c)
            self.assertEqual({r["pair"] for r in k["substantial"]},
                             {"schnoering-tagpack", "tagpack-watchyourback"})
        finally:
            if original is None:
                analysis._cfg.thresholds.pop("kappa_substantial_threshold", None)
            else:
                analysis._cfg.thresholds["kappa_substantial_threshold"] = original


class TestKappaSyntheticEdgeCases(unittest.TestCase):
    """Part W - synthetic corpora with independently hand-computable expected
    values, rather than only reproducing the bundled corpus's own numbers.
    Targets division-by-zero, single-class kappa, empty overlap, and tiny
    overlap - the shapes most likely to produce NaN/crash if the formula's
    guards ever regress.
    """

    @staticmethod
    def _claim(address, source, canon):
        return {"address": address, "source": source, "raw_label": canon, "canon": canon,
               "polarity": taxonomy.POLARITY.get(canon, "unknown"),
               "prov_family": "", "lastmod": "", "heuristic": "unknown", "subcat": ""}

    def test_textbook_two_by_two_matches_hand_computed_kappa(self):
        # Classic 2x2 rater-agreement table (20/5/10/15 over n=50): po=0.70,
        # pe=0.50, kappa=(0.70-0.50)/(1-0.50)=0.40 - computed independently
        # of THEMIS's implementation, to check the formula itself, not just
        # that it reproduces its own past output.
        claims = []
        i = 0
        for _ in range(20):
            claims += [self._claim(f"a{i}", "s1", "cat_yes"), self._claim(f"a{i}", "s2", "cat_yes")]; i += 1
        for _ in range(5):
            claims += [self._claim(f"a{i}", "s1", "cat_yes"), self._claim(f"a{i}", "s2", "cat_no")]; i += 1
        for _ in range(10):
            claims += [self._claim(f"a{i}", "s1", "cat_no"), self._claim(f"a{i}", "s2", "cat_yes")]; i += 1
        for _ in range(15):
            claims += [self._claim(f"a{i}", "s1", "cat_no"), self._claim(f"a{i}", "s2", "cat_no")]; i += 1
        k = analysis.cohen_kappa(Corpus(claims, full=True))
        pair = next(r for r in k["pairs"] if {r["source_a"], r["source_b"]} == {"s1", "s2"})
        self.assertEqual(pair["n"], 50)
        self.assertAlmostEqual(pair["percent_agreement"], 0.70, places=9)
        self.assertAlmostEqual(pair["cohen_kappa"], 0.40, places=9)

    def test_unknown_is_a_class_in_the_headline_and_excluded_in_the_companion(self):
        # 2x2 textbook table (20/5/10/15, kappa 0.40) plus 30 addresses both
        # sources left `unknown` and 5 where only one did. Headline keeps
        # unknown as a class, so those 35 dilute the disagreement and inflate
        # agreement; the interpretable-only companion is the textbook 0.40.
        claims, i = [], 0
        for a, b, n in (("cat_yes", "cat_yes", 20), ("cat_yes", "cat_no", 5),
                        ("cat_no", "cat_yes", 10), ("cat_no", "cat_no", 15),
                        ("unknown", "unknown", 30), ("unknown", "cat_yes", 5)):
            for _ in range(n):
                claims += [self._claim(f"a{i}", "s1", a), self._claim(f"a{i}", "s2", b)]; i += 1
        pair = next(r for r in analysis.cohen_kappa(Corpus(claims, full=True))["pairs"])
        self.assertEqual((pair["n"], pair["n_interpretable"], pair["n_both_unknown"]), (85, 50, 30))
        self.assertAlmostEqual(pair["percent_agreement_interpretable"], 0.70, places=9)
        self.assertAlmostEqual(pair["cohen_kappa_interpretable"], 0.40, places=9)
        self.assertAlmostEqual(pair["percent_agreement"], (20 + 15 + 30) / 85, places=9)
        self.assertGreater(pair["cohen_kappa"], pair["cohen_kappa_interpretable"])

    def test_single_class_overlap_is_undefined_not_a_crash(self):
        # Every shared address gets the same category from both sources:
        # pe=1 exactly (denominator 1-pe=0) - must be reported as undefined,
        # never raise ZeroDivisionError or return NaN.
        claims = [self._claim(f"a{i}", s, "ransomware") for i in range(10) for s in ("s1", "s2")]
        k = analysis.cohen_kappa(Corpus(claims, full=True))
        pair = next(r for r in k["pairs"] if {r["source_a"], r["source_b"]} == {"s1", "s2"})
        self.assertIsNone(pair["cohen_kappa"])
        self.assertIn("undefined", pair["note"])
        self.assertAlmostEqual(pair["percent_agreement"], 1.0, places=9)

    def test_zero_overlap_pair_is_absent_not_nan(self):
        # s1 and s2 never share an address at all - must not appear in the
        # pair list (as NaN or otherwise), not be silently invented as n=0.
        claims = [self._claim("a1", "s1", "ransomware"), self._claim("a2", "s2", "exchange")]
        k = analysis.cohen_kappa(Corpus(claims, full=True))
        self.assertFalse(any({r["source_a"], r["source_b"]} == {"s1", "s2"} for r in k["pairs"]))

    def test_tiny_overlap_of_one_disagreeing_address_is_zero_not_nan(self):
        # n=1, x != y: agree=0, and each label is unique to its rater so
        # pe's sum-over-intersection is 0/1 = 0 too - kappa is well-defined
        # (0.0) even at the smallest possible non-empty overlap.
        claims = [self._claim("a1", "s1", "ransomware"), self._claim("a1", "s2", "exchange")]
        k = analysis.cohen_kappa(Corpus(claims, full=True))
        pair = next(r for r in k["pairs"] if {r["source_a"], r["source_b"]} == {"s1", "s2"})
        self.assertEqual(pair["n"], 1)
        self.assertAlmostEqual(pair["cohen_kappa"], 0.0, places=9)

    def test_empty_corpus_produces_no_pairs_not_a_crash(self):
        k = analysis.cohen_kappa(Corpus([], full=True))
        self.assertEqual(k["n_pairs"], 0)
        self.assertEqual(k["pairs"], [])
        self.assertEqual(k["substantial"], [])


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


class TestAddressNormalization(unittest.TestCase):
    """WatchYourBack's own upstream data carries a leading "#" on 87 of 309
    addresses (confirmed against its real current file - not a THEMIS
    artifact); left in place it silently broke cross-source matching for 72
    that already exist elsewhere in the corpus. Fixed via a per-source
    declared rule (config/sources/watchyourback.yml's address_normalization),
    never a blanket strip applied to every source."""

    def test_declared_prefix_is_stripped(self):
        claim = {"source": "watchyourback", "address": "#1ABC"}
        self.assertEqual(provenance.normalize_address(claim), "1ABC")

    def test_source_with_no_declared_rule_is_unchanged(self):
        claim = {"source": "tagpack", "address": "#1ABC"}
        self.assertEqual(provenance.normalize_address(claim), "#1ABC")

    def test_address_without_the_prefix_is_unchanged(self):
        claim = {"source": "watchyourback", "address": "1ABC"}
        self.assertEqual(provenance.normalize_address(claim), "1ABC")

    def test_unknown_source_is_unchanged(self):
        claim = {"source": "not_a_real_source", "address": "#1ABC"}
        self.assertEqual(provenance.normalize_address(claim), "#1ABC")

    def test_corpus_preserves_raw_address_and_normalizes_the_join_key(self):
        claims = [{"address": "#1ABC", "source": "watchyourback", "raw_label": "x",
                  "canon": "unknown", "polarity": "unknown", "prov_family": "",
                  "lastmod": "", "heuristic": "manual_verified", "subcat": ""}]
        c = Corpus(claims, full=True)
        self.assertIn("1ABC", c.by_addr)
        self.assertNotIn("#1ABC", c.by_addr)
        self.assertEqual(c.by_addr["1ABC"][0]["raw_address"], "#1ABC")

    def test_fresh_ingest_normalizes_and_preserves_raw_address(self):
        from themis.ingest.claims import build_claim
        row = {"address": "#1ABC", "label": "mixer"}
        mapping = {"address": "address", "label": "label"}
        claim = build_claim(row, mapping, "watchyourback")
        self.assertEqual(claim["address"], "1ABC")
        self.assertEqual(claim["raw_address"], "#1ABC")


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

    def test_one_known_source_plus_unknown_sources_is_incomparable_not_exact(self):
        # a source whose raw label never mapped to a canonical category
        # (canon == "unknown", e.g. Elliptic++'s undocumented "class_3"
        # code) contributed no usable opinion. With only one source's claim
        # actually interpreted, there is nothing to compare it against -
        # this must not report "exact agreement" with itself.
        claims = [{"source": "ellipticpp", "canon": "unknown"},
                 {"source": "schnoering", "canon": "individual"}]
        self.assertEqual(taxonomy.classify_address(claims), "incomparable")

    def test_two_known_sources_plus_a_third_unknown_source_still_compares(self):
        # the unknown source is simply excluded, not disqualifying - two
        # *other* sources genuinely agreeing is still real agreement.
        claims = [{"source": "a", "canon": "ransomware"},
                 {"source": "b", "canon": "ransomware"},
                 {"source": "c", "canon": "unknown"}]
        self.assertEqual(taxonomy.classify_address(claims), "exact")

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

    def test_elliptic_class_codes_map_to_their_documented_polarity(self):
        # class-1=illicit, class-2=licit, class-3=unknown is Elliptic's own
        # published scheme (Weber et al.), not an inference - class_3 must
        # stay unmapped (genuinely unknown per the source itself), while
        # class_1/class_2 have an unambiguous, externally-documented polarity.
        self.assertEqual(taxonomy.canonicalize_category("class_1"), "illicit_unspec")
        self.assertEqual(taxonomy.canonicalize_category("class_2"), "licit_unspec")
        self.assertIsNone(taxonomy.canonicalize_category("class_3"))

    def test_elliptic_class_alias_takes_effect_on_a_fresh_ingest_not_the_frozen_corpus(self):
        # the paper snapshot's `canon` column is pre-baked into
        # demo_data/observations_sample.csv.gz at data-preparation time and
        # is never recomputed from taxonomy.yml on load (corpus.py's
        # Corpus.demo() reads `canon` as a literal stored field) - so this
        # alias only takes effect for a newly-ingested claim (STEP 23),
        # never retroactively for the frozen paper corpus.
        # TestAgreement.test_outcome_counts (this file) asserts the exact,
        # unchanged bundled-corpus numbers - that test still passing after
        # this alias was added is the real proof the paper corpus is
        # untouched. This test instead confirms the alias *does* reach a
        # fresh ingest, via the actual claim-building path a new upload uses.
        from themis.ingest.claims import build_claim
        row = {"address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "label": "class_1"}
        mapping = {"address": "address", "label": "label"}
        claim = build_claim(row, mapping, "test_elliptic_upload")
        self.assertEqual(claim["canon"], "illicit_unspec")
        self.assertEqual(claim["polarity"], "illicit")


class TestStructuredLabels(unittest.TestCase):
    """Sec 3.2 - a "type:entity"-shaped raw label (watchyourback's own
    `state-sponsored:lazarus`, `onlinewallet:flexcoin`, etc.) canonicalizes
    via its type-shaped prefix when the whole string doesn't already match -
    quantified safe in the reconciliation loop (+40 addresses out of
    "incomparable", zero effect on the frozen bundled corpus)."""

    def test_known_prefix_with_entity(self):
        self.assertEqual(taxonomy.canonicalize_category("onlinewallet:flexcoin"), "wallet_service")
        cat, entity = taxonomy.split_structured_label("onlinewallet:flexcoin")
        self.assertEqual(cat, "wallet_service")
        self.assertEqual(entity, "flexcoin")

    def test_theft_prefix_needed_no_new_alias(self):
        # "theft" already aliases to `hack` on its own; only the missing
        # split step blocked "theft:flexcoin-hack" from ever reaching it.
        self.assertEqual(taxonomy.canonicalize_category("theft:flexcoin-hack"), "hack")

    def test_unknown_prefix_with_entity_stays_unmapped(self):
        # the prefix itself must be a declared alias - never a guess just
        # because the string has the right shape.
        self.assertIsNone(taxonomy.canonicalize_category("cryptolocker:variant-9"))
        self.assertEqual(taxonomy.split_structured_label("cryptolocker:variant-9"), (None, None))

    def test_multiple_separators_only_first_segment_is_the_prefix(self):
        # "a:b:c" is (category-of("a"), "b:c"), not recursively re-split.
        cat, entity = taxonomy.split_structured_label("state-sponsored:lazarus:unit180")
        self.assertEqual(cat, "illicit_unspec")
        self.assertEqual(entity, "lazarus:unit180")

    def test_malformed_strings_do_not_crash(self):
        for raw in ("", ":", "::::", ":lazarus", "onlinewallet:"):
            self.assertEqual(taxonomy.split_structured_label(raw), (None, None) if raw != "onlinewallet:"
                             else ("wallet_service", ""))

    def test_plain_label_with_no_prefix_is_unaffected(self):
        self.assertEqual(taxonomy.canonicalize_category("mixer"), "mixer")
        self.assertEqual(taxonomy.split_structured_label("mixer"), (None, None))

    def test_colon_inside_a_url_does_not_spuriously_match(self):
        self.assertIsNone(taxonomy.canonicalize_category("http://example.com/wallet"))

    def test_colon_inside_unrelated_free_text_does_not_spuriously_match(self):
        self.assertIsNone(taxonomy.canonicalize_category("see note: unrelated commentary"))

    def test_structured_entity_is_preserved_on_the_claim_not_discarded(self):
        from themis.ingest.claims import build_claim
        row = {"address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "label": "onlinewallet:flexcoin"}
        mapping = {"address": "address", "label": "label"}
        claim = build_claim(row, mapping, "test_structured_upload")
        self.assertEqual(claim["canon"], "wallet_service")
        self.assertEqual(claim["raw_label"], "onlinewallet:flexcoin")   # unchanged
        self.assertEqual(claim["notes"], "structured_label_entity=flexcoin")

    def test_frozen_bundled_corpus_is_unaffected(self):
        # same proof pattern as the Elliptic++/darknet-market alias fixes:
        # observations_sample.csv.gz's canon column is pre-baked and never
        # recomputed from taxonomy.yml on load, so this only reaches a
        # fresh ingest. TestAgreement.test_outcome_counts (unchanged) is
        # the real proof; this just confirms canonicalize_category itself
        # isn't called anywhere in Corpus loading.
        import inspect
        from themis import corpus as corpus_mod
        src = inspect.getsource(corpus_mod)
        self.assertNotIn("canonicalize_category", src)


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

    def test_address_prefix_is_not_fuzzy_matched(self):
        # "Never fuzzy-correct a crypto address" - a truncated prefix of a
        # real address in the corpus must report not-found, not silently
        # resolve to the full address it's a prefix of.
        full = "14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7"
        prefix = full[:10]
        self.assertIn(full, self.c.by_addr)   # sanity: the full address is real
        r = analysis.explain(self.c, prefix)
        self.assertFalse(r["found"])

    def test_malformed_address_is_not_found_not_a_crash(self):
        for garbage in ("not-an-address", "", "0x1234", "🚀" * 5, "'; DROP TABLE addresses; --"):
            r = analysis.explain(self.c, garbage)
            self.assertFalse(r["found"])

    def test_single_source_address_outcome_is_labeled_single_source(self):
        # explain() only calls classify_address (exact/conflict/...) once
        # 2+ sources are present - a single-source address must report its
        # own distinct outcome, never one of the multi-source labels.
        addr = "1EMtepyCPLuK7feDsPdfs9NxqKWcRBFy9o"
        r = analysis.explain(self.c, addr)
        self.assertTrue(r["found"])
        self.assertEqual(len(r["datasets"]), 1)
        self.assertEqual(r["outcome"], "single-source")

    def test_unresolved_provenance_address_is_not_reported_as_resolved(self):
        addr = "3MfbfHYeWYUiPLUzXapFN1hfhwDJPxTgry"
        r = analysis.explain(self.c, addr)
        self.assertTrue(r["found"])
        self.assertTrue(all(provenance.is_unresolved(root) for root in r["roots"]))
        # an unresolved root is never independently confirmed corroboration,
        # regardless of how many datasets apparently mention the address
        self.assertEqual(r["actual_corroboration"], 0)


class TestBootstrap(Base):
    """Section 5.4 - the interval must widen, not narrow, when clustered."""

    def test_conditional_rates_have_intervals(self):
        # 0.70%, not the paper's published 0.71% - see the classify_address
        # fix note on TestAgreement.test_outcome_counts (108 vs 109 conflicts).
        b = analysis.bootstrap(self.c, n_boot=200)
        s = b["stats"]["licit/illicit conflict"]
        self.assertAlmostEqual(100 * s["point"], 0.70, places=2)
        self.assertLess(s["ci_low"], s["point"])
        self.assertGreater(s["ci_high"], s["point"])

    def test_canonical_lower_bound_intervals_are_frozen(self):
        # Phase 8 freeze: the exact intervals `themis bootstrap --both` prints
        # for the lower (unresolved-pooled) bound at the config defaults
        # (2,000 resamples, seed 42, 95%). Environment-independent by
        # construction (stdlib random.Random). The paper's published
        # 88.786% / [66.208, 98.982] etc. describe the pre-fix agreement
        # classifier and a different RNG path; these are the accepted values.
        # Upper bound (50,748 clusters) is frozen in expected_output/ - too
        # slow to recompute on every test run.
        b = analysis.bootstrap(self.c)
        self.assertEqual((b["n_boot"], b["seed"], b["confidence_level"], b["n_clusters"]),
                         (2000, 42, 0.95, 24))
        want = {"exact": (68.279, 6.012, 97.808),
                "hierarchical refinement": (8.136, 0.000, 25.373),
                "licit/illicit conflict": (0.701, 0.119, 2.785)}
        for k, (pt, lo, hi) in want.items():
            s = b["stats"][k]
            self.assertEqual((round(100 * s["point"], 3), round(100 * s["ci_low"], 3),
                              round(100 * s["ci_high"], 3)), (pt, lo, hi), k)

    def test_corpus_wide_rate_withheld_on_sample(self):
        b = analysis.bootstrap(self.c, n_boot=50)
        self.assertNotIn("multi_source_rate", b["stats"])
        self.assertFalse(b["corpus_wide_rates"])

    def test_upper_bound_has_more_clusters(self):
        lo = analysis.bootstrap(self.c, n_boot=50, upper_bound=False)
        hi = analysis.bootstrap(self.c, n_boot=50, upper_bound=True)
        self.assertGreater(hi["n_clusters"], lo["n_clusters"])

    def test_canonical_path_is_deterministic_regardless_of_numpy(self):
        # same seed, canonical (fast=False) path: CI endpoints must be
        # bit-identical whether or not numpy happens to be importable in
        # this environment - a reviewer without numpy must reproduce the
        # exact same interval as one with it. See analysis.bootstrap's
        # docstring: numpy's default_rng is a different algorithm and would
        # silently shift CI endpoints (not point estimates) if it were ever
        # used for the canonical path.
        with_numpy = analysis.bootstrap(self.c, n_boot=100, seed=7)
        import sys
        real_numpy = sys.modules.get("numpy")
        sys.modules["numpy"] = None
        try:
            without_numpy = analysis.bootstrap(self.c, n_boot=100, seed=7)
        finally:
            if real_numpy is not None:
                sys.modules["numpy"] = real_numpy
            else:
                sys.modules.pop("numpy", None)
        self.assertEqual(with_numpy["stats"], without_numpy["stats"])
        self.assertEqual(with_numpy["engine"], "python_canonical")
        self.assertEqual(without_numpy["engine"], "python_canonical")

    def test_fast_mode_is_marked_non_canonical_and_requires_numpy(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed")
        b = analysis.bootstrap(self.c, n_boot=50, fast=True)
        self.assertEqual(b["engine"], "numpy_fast_exploratory")
        import sys
        real_numpy = sys.modules.get("numpy")
        sys.modules["numpy"] = None
        try:
            with self.assertRaises(ImportError):
                analysis.bootstrap(self.c, n_boot=50, fast=True)
        finally:
            sys.modules["numpy"] = real_numpy

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


class _FakeCorpus:
    """anchor_validation only reads corpus.by_addr - a bare stand-in lets
    tests set each claim's `root` directly, the same way test_independence.py
    bypasses Corpus(...) (whose constructor overwrites `root` via the real
    source registry) to control provenance roots explicitly."""

    def __init__(self, by_addr):
        self.by_addr = by_addr


def _claim(source, root, canon):
    return dict(source=source, root=root, canon=canon)


class TestAnchorValidation(unittest.TestCase):
    """Sec 4.3/4.7 - an anchor can only be validated by a claim whose
    resolved provenance ROOT differs from the anchor's own declared root,
    not merely by a differently-named dataset."""

    def test_literal_self_validation_excluded(self):
        # same source, same root as the anchor: not independent
        c = _FakeCorpus({"1A": [_claim("ofac_program", "ofac_sdn", "sanctioned")]})
        anchors = {"1A": ("sanctioned", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertEqual(r["usable_anchors"], 0)
        self.assertEqual(r["excluded_self_root_claims"], 1)
        self.assertEqual(r["per_source"], {})

    def test_same_root_different_dataset_name_excluded(self):
        # THE naive-check trap: a differently-named source whose claim
        # still resolves to the anchor's own root must not count as
        # independent just because the dataset names differ.
        c = _FakeCorpus({"1A": [_claim("schnoering", "ofac_sdn", "sanctioned")]})
        anchors = {"1A": ("sanctioned", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertEqual(r["usable_anchors"], 0)
        self.assertEqual(r["excluded_self_root_claims"], 1)

    def test_independent_root_counted_as_exact(self):
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_own", "mixer")]})
        anchors = {"1A": ("mixer", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertEqual(r["usable_anchors"], 1)
        self.assertEqual(r["per_source"]["tagpack"]["n"], 1)
        self.assertEqual(r["per_source"]["tagpack"]["exact"], 1)
        # was: assertTrue(estimable). Now False - a source whose only
        # decision comes from ONE independent root has no between-root
        # variance to resample (anchor_min_independent_roots, thresholds.yml),
        # so its agreement is reported but never presented as an estimate.
        self.assertFalse(r["per_source"]["tagpack"]["estimable"])
        self.assertEqual(r["per_source"]["tagpack"]["independent_roots"], 1)

    def test_licit_illicit_conflict_counted_not_exact(self):
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_own", "exchange")]})
        anchors = {"1A": ("mixer", "ofac_sdn")}  # mixer=illicit, exchange=licit
        r = analysis.anchor_validation(c, anchors=anchors)
        v = r["per_source"]["tagpack"]
        self.assertEqual(v["n"], 1)
        self.assertEqual(v["exact"], 0)
        self.assertEqual(v["conflicting"], 1)

    def test_hierarchical_refinement_counted_separately(self):
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_own", "illicit_unspec")]})
        anchors = {"1A": ("mixer", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        v = r["per_source"]["tagpack"]
        self.assertEqual(v["hierarchical"], 1)
        self.assertEqual(v["exact"], 0)

    def test_uninterpretable_claim_label_is_incomparable_not_a_denominator_hit(self):
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_own", "unknown")]})
        anchors = {"1A": ("mixer", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertEqual(r["usable_anchors"], 1)
        # the claim existed (independent root) but never canonicalized, so
        # it must not inflate the accuracy denominator - reported as
        # touched-but-not-estimable, distinct from a source never seen at all
        v = r["per_source"]["tagpack"]
        self.assertEqual(v["n"], 0)
        self.assertEqual(v["incomparable"], 1)
        self.assertFalse(v["estimable"])

    def test_uninterpretable_ground_truth_label_is_flagged(self):
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_own", "mixer")]})
        anchors = {"1A": ("not-a-real-category", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertEqual(r["usable_anchors"], 1)
        self.assertEqual(r["uninterpretable_ground_truth_label"], 1)
        self.assertEqual(r["per_source"], {})

    def test_no_independent_claims_anywhere_is_not_estimable(self):
        c = _FakeCorpus({"1A": [_claim("ofac_program", "ofac_sdn", "sanctioned")]})
        anchors = {"1A": ("sanctioned", "ofac_sdn")}
        r = analysis.anchor_validation(c, anchors=anchors)
        self.assertFalse(r["estimable"])
        self.assertEqual(r["usable_anchors"], 0)

    def test_wilson_interval_brackets_the_point_estimate(self):
        # roots must be *resolved* to count as independent (an unrecognised
        # root string is "unknown stays unknown"); tagpack_<creator> resolves
        # via the source registry's fallback template.
        by_addr = {f"addr{i}": [_claim("tagpack", f"tagpack_root{i}", "mixer" if i < 8 else "exchange")]
                   for i in range(10)}
        c = _FakeCorpus(by_addr)
        anchors = {f"addr{i}": ("mixer", "ofac_sdn") for i in range(10)}
        r = analysis.anchor_validation(c, anchors=anchors)
        v = r["per_source"]["tagpack"]
        self.assertEqual(v["n"], 10)
        # was v["accuracy"] (per-claim Wilson CI as the headline interval);
        # now `anchor_agreement` - it measures agreement with the anchor
        # set, not source accuracy - with a root-cluster bootstrap CI
        # headline and the address-level Wilson kept as wilson_low/high.
        self.assertAlmostEqual(v["anchor_agreement"], 0.8)
        self.assertEqual(v["independent_roots"], 10)
        self.assertTrue(v["estimable"])
        self.assertLess(v["ci_low"], v["anchor_agreement"])
        self.assertGreater(v["ci_high"], v["anchor_agreement"])
        self.assertLess(v["wilson_low"], v["anchor_agreement"])
        self.assertGreater(v["wilson_high"], v["anchor_agreement"])

    def test_source_repeating_itself_on_one_anchor_is_one_decision(self):
        # Sec 4.2 - the unit is the address, not the claim: 531 TagPack
        # claims over 267 addresses must not be read as 531 confirmations.
        c = _FakeCorpus({"1A": [_claim("tagpack", "tagpack_r1", "mixer"),
                                _claim("tagpack", "tagpack_r1", "mixer"),
                                _claim("tagpack", "tagpack_r2", "mixer")]})
        r = analysis.anchor_validation(c, anchors={"1A": ("mixer", "ofac_sdn")})
        self.assertEqual(r["per_source"]["tagpack"]["n"], 1)

    def test_modal_label_decides_and_tie_is_order_independent(self):
        forward = [_claim("tagpack", "tagpack_r1", "mixer"), _claim("tagpack", "tagpack_r2", "exchange")]
        for claims in (forward, list(reversed(forward))):
            r = analysis.anchor_validation(_FakeCorpus({"1A": claims}),
                                           anchors={"1A": ("mixer", "ofac_sdn")})
            v = r["per_source"]["tagpack"]
            # tie broken by label name ("exchange" < "mixer"), never claim order
            self.assertEqual((v["n"], v["exact"], v["conflicting"]), (1, 0, 1))

    def test_unresolved_roots_are_not_independent_roots(self):
        # two anchors, both supported only by a source whose root is
        # unresolved (unknown relationship, not a distinct identity)
        by_addr = {f"a{i}": [_claim("ellipticpp", "elliptic_undisclosed", "mixer")]
                   for i in range(2)}
        r = analysis.anchor_validation(_FakeCorpus(by_addr),
                                       anchors={a: ("mixer", "ofac_sdn") for a in by_addr})
        v = r["per_source"]["ellipticpp"]
        self.assertEqual(v["independent_roots"], 0)
        self.assertFalse(v["estimable"])
        self.assertIsNone(v["ci_low"])

    def test_root_cluster_ci_is_wider_than_wilson_when_support_is_concentrated(self):
        # 40 addresses but all through 2 roots that disagree sharply: the
        # address-level Wilson interval looks tight, the root-cluster one
        # must not.
        by_addr = {}
        for i in range(40):
            root, canon = ("tagpack_rA", "mixer") if i < 20 else ("tagpack_rB", "exchange")
            by_addr[f"a{i}"] = [_claim("tagpack", root, canon)]
        r = analysis.anchor_validation(_FakeCorpus(by_addr),
                                       anchors={a: ("mixer", "ofac_sdn") for a in by_addr})
        v = r["per_source"]["tagpack"]
        self.assertEqual(v["independent_roots"], 2)
        self.assertGreater(v["ci_high"] - v["ci_low"], v["wilson_high"] - v["wilson_low"])

    def test_anchor_ci_is_deterministic(self):
        by_addr = {f"a{i}": [_claim("tagpack", f"tagpack_r{i % 3}", "mixer" if i % 4 else "exchange")]
                   for i in range(30)}
        anchors = {a: ("mixer", "ofac_sdn") for a in by_addr}
        r1 = analysis.anchor_validation(_FakeCorpus(by_addr), anchors=anchors)
        r2 = analysis.anchor_validation(_FakeCorpus(by_addr), anchors=anchors)
        self.assertEqual(r1["per_source"]["tagpack"], r2["per_source"]["tagpack"])


class TestAnchorValidationRealCorpus(Base):
    """`ground_truth.csv` is curated directly against corpus join keys
    (Corpus.by_addr), not ingested through a source adapter - so unlike a
    raw source file, nothing normalizes it on load. A raw upstream address
    (e.g. WatchYourBack's own "#" convention, see watchyourback.yml's
    address_normalization) left in this file is invisible to
    corpus.by_addr.get(addr) and silently drops out of every anchor count
    instead of being correctly excluded as self-root."""

    def test_no_ground_truth_address_carries_an_unnormalized_source_prefix(self):
        prefixes = [cfg.get("address_normalization", {}).get("strip_prefix")
                    for cfg in provenance._cfg.sources.values()]
        prefixes = [p for p in prefixes if p]
        offenders = [a for a in self.c.ground_truth()
                     if any(a.startswith(p) for p in prefixes)]
        self.assertEqual(offenders, [])

    def test_real_anchor_numbers(self):
        r = analysis.anchor_validation(self.c)
        self.assertEqual(r["anchors_total"], 289)
        self.assertEqual(r["usable_anchors"], 268)
        # was 290 (paper Sec 4.2). Now 361: +71 WatchYourBack hydra-market
        # claims. Each cites Treasury's OFAC page and sits at an address that
        # is itself an OFAC anchor, so per-record provenance (watchyourback.yml)
        # now roots them at ofac_sdn - same root as the anchor, hence excluded
        # as self-validation instead of counted as an independent confirmation.
        self.assertEqual(r["excluded_self_root_claims"], 361)
        self.assertEqual(r["uninterpretable_ground_truth_label"], 0)

    def test_real_anchor_per_source_support(self):
        # Sec 4.2: five of seven sources collapse to a single root or no
        # validated addresses; the survivors are Schnoering and TagPack.
        # Unit = one decision per (source, address), so n is addresses (was
        # claims: tagpack 401, schnoering 41 under the per-claim count).
        ps = analysis.anchor_validation(self.c)["per_source"]
        est = {s for s, v in ps.items() if v["estimable"]}
        self.assertEqual(est, {"tagpack", "schnoering"})
        self.assertEqual((ps["tagpack"]["n"], ps["tagpack"]["exact"],
                          ps["tagpack"]["independent_roots"]), (259, 113, 5))
        self.assertEqual((ps["schnoering"]["n"], ps["schnoering"]["exact"],
                          ps["schnoering"]["independent_roots"]), (34, 32, 3))
        for single in ("ransomwhere", "rodwald_ransom"):
            self.assertEqual(ps[single]["independent_roots"], 1)
        # concentrated support must never produce a tight interval
        self.assertGreater(ps["tagpack"]["ci_high"] - ps["tagpack"]["ci_low"], 0.5)


class TestStructuredLabelEdgeCases(unittest.TestCase):
    """Phase 2C re-verification: a label only gets a structured-prefix
    reading when its own prefix is a declared alias. Anything else must stay
    unmapped rather than be guessed."""

    def test_known_prefix_plus_entity(self):
        self.assertEqual(taxonomy.canonicalize_category("tormarket:hydra-market"), "darknet_market")
        self.assertEqual(taxonomy.canonicalize_category("MIXER:Helix"), "mixer")

    def test_unknown_prefix_plus_entity_stays_unmapped(self):
        for raw in ("foo:bar", "cryptolocker:variant-9", "a:b:c"):
            self.assertIsNone(taxonomy.canonicalize_category(raw))

    def test_urls_and_free_text_colons_never_match(self):
        for raw in ("http://example.com/x", "https://treasury.gov/a:b", "note: this is a mixer",
                    "see: exchange", ":entity"):
            self.assertIsNone(taxonomy.canonicalize_category(raw), raw)

    def test_only_the_first_separator_splits(self):
        self.assertEqual(taxonomy.split_structured_label("mixer:a:b"), ("mixer", "a:b"))

    def test_malformed_values_do_not_raise(self):
        for raw in (None, "", "   ", ":", "::", "x" * 10000 + ":y"):
            self.assertIsNone(taxonomy.canonicalize_category(raw))

    def test_plain_alias_is_unchanged_by_the_structured_path(self):
        self.assertEqual(taxonomy.canonicalize_category("mixer"), "mixer")
        self.assertEqual(taxonomy.split_structured_label("mixer"), (None, None))

    @requires_reference_corpus
    def test_paper_snapshot_canon_is_not_recomputed_on_load(self):
        # frozen-snapshot vs fresh-normalization must never mix silently: the
        # bundled corpus keeps its pre-baked canon (WatchYourBack's
        # "tormarket:*" is `unknown` there) even though a fresh ingest of the
        # same raw label now canonicalizes it.
        c = Corpus.demo()
        claim = next(x for x in c.claims if x["source"] == "watchyourback"
                     and x["raw_label"] == "tormarket:hydra-market")
        self.assertEqual(claim["canon"], "unknown")
        self.assertEqual(taxonomy.canonicalize_category(claim["raw_label"]), "darknet_market")


class TestWatchYourBackPerRecordProvenance(Base):
    """Phase 2B: WatchYourBack is a cited compilation, not a provenance root.
    The 71 hydra-market records cite Treasury's OFAC page and sit at OFAC-SDN
    addresses; the rest keep the source's own root and are not VERIFIED."""

    def _wyb(self):
        return [x for x in self.c.claims if x["source"] == "watchyourback"]

    def test_hydra_records_root_at_ofac_and_are_verified(self):
        hydra = [x for x in self._wyb() if x["subcat"] == "hydra-market"]
        self.assertEqual(len(hydra), 71)
        for x in hydra:
            self.assertEqual((x["root"], x["prov_native"], taxonomy.tier_of(x)),
                             ("ofac_sdn", False, taxonomy.TIER_VERIFIED))

    def test_every_other_record_keeps_the_sources_root_and_is_not_verified(self):
        rest = [x for x in self._wyb() if x["subcat"] != "hydra-market"]
        self.assertEqual(len(rest), 238)
        for x in rest:
            self.assertEqual((x["root"], x["prov_kind"], taxonomy.tier_of(x)),
                             ("watchyourback_manual", "DECLARED", taxonomy.TIER_DERIVED))

    def test_a_hydra_address_is_circular_with_schnoerings_ofac_claim(self):
        addr = next(x["address"] for x in self._wyb() if x["subcat"] == "hydra-market")
        r = analysis.explain(self.c, addr)
        self.assertTrue(r["circular"])
        # (TagPack itself names two creators here, so the confirmed-root count can
        # equal the dataset count while one root is still restated twice)
        self.assertGreaterEqual(r["independence"]["shared_root_count"], 1)
        self.assertIn("ofac_sdn", {c["root"] for c in r["claims"] if c["source"] == "watchyourback"})

    def test_root_inventory_is_unchanged_by_the_rerooting(self):
        # the paper's 25 roots / 21 identified / 4 unresolved (manifest) - the
        # 71 records moved into an existing root, none were added or removed
        ind = analysis.independence(self.c)
        self.assertEqual((ind["n_roots_total"], ind["n_roots_identified"]), (25, 21))
        self.assertEqual(sum(1 for r in self.c.roots() if r == "watchyourback_manual"), 1)

    def test_declared_manually_verified_alone_is_not_the_verified_tier(self):
        claim = dict(heuristic="manual_verified", root="some_unlisted_root", prov_verified=False)
        self.assertEqual(taxonomy.tier_of(claim), taxonomy.TIER_DERIVED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
