"""RQ1 - the paper's claim taxonomy, proved as rules rather than as corpus numbers.

Every test builds its own tiny claims: none needs the reference corpus, so this
file runs (and `themis reproduce-paper` runs it) in a release with no data.
Section 3: verified / derived / unverified-report tiers; currency-unknown, stale,
conflicting and circular flags; agreement, refinement, conflict, incomparable.
"""
import datetime, pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis import provenance, taxonomy
from themis.corpus import Corpus

TODAY = datetime.date(2026, 9, 15)


def claim(source="s", canon="ransomware", **kw):
    return dict(dict(source=source, canon=canon, address="1" * 26, raw_label=canon, polarity="illicit",
                     prov_family="", lastmod="", heuristic="", subcat=""), **kw)


class TestClaimIsTheUnit(unittest.TestCase):
    def test_two_claims_by_one_source_about_one_address_stay_two_claims(self):
        a = "1" * 26
        c = Corpus([claim("tagpack", "exchange", address=a), claim("tagpack", "mixer", address=a)], full=True)
        self.assertEqual(len(c.by_addr[a]), 2)          # disagreement is not merged away
        self.assertEqual({x["canon"] for x in c.by_addr[a]}, {"exchange", "mixer"})

    def test_a_claim_keeps_the_fields_the_method_names(self):
        c = Corpus([claim(raw_label="Locky", lastmod="2022-01-01", heuristic="curated")], full=True).claims[0]
        for k in ("address", "source", "raw_label", "canon", "root", "lastmod", "heuristic"):
            self.assertIn(k, c)


class TestTiers(unittest.TestCase):
    def test_manual_annotation_is_not_automatically_verified(self):
        self.assertNotEqual(taxonomy.tier_of(claim(heuristic="manual_verified", root="watchyourback_manual")),
                            taxonomy.TIER_VERIFIED)

    def test_a_source_calling_itself_verified_is_still_only_a_declaration(self):
        self.assertEqual(taxonomy.tier_of(claim(heuristic="manual_verified")), taxonomy.TIER_DERIVED)

    def test_verified_needs_a_root_that_ends_in_recheckable_evidence(self):
        self.assertTrue(taxonomy.VERIFIED_ROOTS, "no root is declared verified in config")
        root = sorted(taxonomy.VERIFIED_ROOTS)[0]
        self.assertEqual(taxonomy.tier_of(claim(root=root)), taxonomy.TIER_VERIFIED)
        self.assertEqual(taxonomy.tier_of(claim(prov_verified=True)), taxonomy.TIER_VERIFIED)

    def test_derived_requires_a_declared_heuristic_dependency(self):
        for h in ("multi_input", "inherited", "curated"):
            self.assertEqual(taxonomy.tier_of(claim(heuristic=h)), taxonomy.TIER_DERIVED, h)
        self.assertNotEqual(taxonomy.tier_of(claim(heuristic="")), taxonomy.TIER_DERIVED)

    def test_crowd_or_report_evidence_without_confirmation_is_an_unverified_report(self):
        self.assertEqual(taxonomy.tier_of(claim(heuristic="none")), taxonomy.TIER_REPORT)
        # even when several datasets repeat it: repetition is not confirmation
        two = [claim("a", heuristic="none", root="ransomwhere_crowd"), claim("b", heuristic="none", root="ransomwhere_crowd")]
        self.assertEqual(taxonomy.best_tier(two), taxonomy.TIER_REPORT)

    def test_undeclared_methodology_is_unknown_not_silently_derived(self):
        self.assertEqual(taxonomy.tier_of(claim(heuristic="unknown")), taxonomy.TIER_UNKNOWN)


class TestCurrencyFlags(unittest.TestCase):
    def test_missing_date_is_currency_unknown(self):
        self.assertEqual(taxonomy.currency_flags(claim(lastmod=""), today=TODAY), ["currency-unknown"])

    def test_missing_date_is_never_stale_however_late_it_is_judged(self):
        self.assertNotIn("stale", taxonomy.currency_flags(claim(lastmod=""), today=datetime.date(2100, 1, 1)))

    def test_an_unparseable_date_is_unknown_not_stale(self):
        self.assertEqual(taxonomy.currency_flags(claim(lastmod="sometime"), today=TODAY), ["currency-unknown"])

    def test_only_a_real_old_date_is_stale(self):
        self.assertEqual(taxonomy.currency_flags(claim(lastmod="2019-01-01"), today=TODAY), ["stale"])
        self.assertEqual(taxonomy.currency_flags(claim(lastmod="2026-01-01"), today=TODAY), [])

    def test_staleness_is_judged_at_the_supplied_date_not_the_wall_clock(self):
        c = claim(lastmod="2023-09-01")
        self.assertEqual(taxonomy.currency_flags(c, today=datetime.date(2025, 1, 1)), [])
        self.assertEqual(taxonomy.currency_flags(c, today=datetime.date(2027, 1, 1)), ["stale"])


class TestCircularAndUnresolved(unittest.TestCase):
    def test_several_datasets_on_one_root_are_circular(self):
        r = provenance.address_independence([claim("a", root="ransomwhere_crowd"), claim("b", root="ransomwhere_crowd")])
        self.assertTrue(r["circular"])
        self.assertEqual(r["confirmed_independent_root_count"], 1)
        self.assertIn("circular", taxonomy.flags_for_address(
            [claim("a", root="ransomwhere_crowd"), claim("b", root="ransomwhere_crowd")], today=TODAY))

    def test_unresolved_roots_are_not_confirmed_independence(self):
        r = provenance.address_independence([claim("a", root="a:unresolved"), claim("b", root="b:unresolved")])
        self.assertEqual(r["confirmed_independent_root_count"], 0)
        self.assertEqual((r["independence_min"], r["independence_max"]), (1, 2))
        self.assertFalse(r["circular"])                 # unknown is neither shared nor independent

    def test_distinct_resolved_roots_are_confirmed_independent(self):
        r = provenance.address_independence([claim("a", root="ransomwhere_crowd"),
                                             claim("b", root="montreal_paquet_clouston_2019")])
        self.assertEqual(r["confirmed_independent_root_count"], 2)
        self.assertFalse(r["circular"])


class TestAgreementClasses(unittest.TestCase):
    def cls(self, *cats):
        return taxonomy.classify_address([claim(f"s{i}", c) for i, c in enumerate(cats)])

    def test_exact(self):
        self.assertEqual(self.cls("mixer", "mixer"), "exact")

    def test_licit_illicit_conflict_is_kept_separate_from_entity_type_conflict(self):
        self.assertEqual(self.cls("exchange", "ransomware"), "licit/illicit conflict")
        self.assertEqual(self.cls("exchange", "gambling"), "entity-type conflict")   # same polarity, different entity
        self.assertNotEqual(self.cls("exchange", "ransomware"), self.cls("mixer", "ransomware"))

    def test_entity_type_conflict_keeps_the_polarity(self):
        self.assertEqual(self.cls("mixer", "ransomware"), "entity-type conflict")    # both illicit, unrelated

    def test_hierarchical_refinement_needs_a_taxonomy_relationship(self):
        self.assertEqual(self.cls("illicit_unspec", "ransomware"), "hierarchical refinement")   # declared parent
        self.assertEqual(self.cls("mixer", "darknet_market"), "entity-type conflict")           # unrelated siblings
        self.assertIn("illicit_unspec", taxonomy.ancestors("ransomware"))
        self.assertNotIn("mixer", taxonomy.ancestors("ransomware"))

    def test_incomparable_when_fewer_than_two_datasets_have_a_usable_category(self):
        self.assertEqual(self.cls("mixer", "unknown"), "incomparable")
        self.assertEqual(self.cls("unknown", "unknown"), "incomparable")
        self.assertEqual(taxonomy.classify_address([claim("s", "mixer")]), "incomparable")

    def test_one_dataset_repeating_itself_is_not_agreement(self):
        self.assertEqual(taxonomy.classify_address([claim("s", "mixer"), claim("s", "mixer")]), "incomparable")


if __name__ == "__main__":
    unittest.main()
