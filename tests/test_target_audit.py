"""Loop 2 STEP 3/28 - target-vs-reference auditing must never let
reference-reference relationships leak into a target dataset's numbers.
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.corpus import Corpus
from themis import target_audit, provenance


def _claim(address, source, canon, polarity=None):
    from themis import taxonomy
    return {"address": address, "source": source, "raw_label": canon, "canon": canon,
           "polarity": polarity or taxonomy.POLARITY.get(canon, "unknown"),
           "prov_family": "", "lastmod": "", "heuristic": "unknown", "subcat": ""}


class TestTargetReferenceIsolation(unittest.TestCase):
    def test_reference_reference_conflicts_do_not_affect_target_metrics(self):
        # two reference sources disagree with each other on addresses the
        # target never mentions at all
        reference_claims = []
        for i in range(20):
            addr = f"ref_only_{i}"
            reference_claims.append(_claim(addr, "ref_a", "ransomware"))
            reference_claims.append(_claim(addr, "ref_b", "licit_unspec"))  # polarity conflict
        reference = Corpus(reference_claims, full=True)

        # the target only ever touches its own, unrelated address, which
        # agrees cleanly with the one reference claim it happens to match
        target_claims = [_claim("target_addr_1", "uploaded", "ransomware")]
        reference_claims_for_target = [_claim("target_addr_1", "ref_a", "ransomware")]
        reference_with_target_addr = Corpus(reference_claims + reference_claims_for_target, full=True)

        result = target_audit.audit_target_against_reference(target_claims, reference_with_target_addr)
        outcomes = result["profile"]["agreement"]["outcomes"]

        self.assertEqual(outcomes["licit/illicit conflict"]["n"], 0)
        self.assertEqual(outcomes["exact"]["n"], 1)
        self.assertEqual(result["n_target_addresses"], 1)

    def test_reference_sources_agreeing_with_each_other_on_untouched_addresses_do_not_leak(self):
        # Part O's "reference sources share roots" isolation case - the
        # mirror of the test above (agreement, not conflict) on addresses
        # the target never mentions.
        reference_claims = []
        for i in range(15):
            addr = f"ref_shared_root_{i}"
            reference_claims.append(_claim(addr, "ref_a", "exchange"))
            reference_claims.append(_claim(addr, "ref_b", "exchange"))

        target_claims = [_claim("target_addr_2", "uploaded", "exchange")]
        reference_claims_for_target = [_claim("target_addr_2", "ref_a", "exchange")]
        reference = Corpus(reference_claims + reference_claims_for_target, full=True)

        result = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(result["n_target_addresses"], 1)
        self.assertEqual(result["profile"]["agreement"]["outcomes"]["exact"]["n"], 1)
        self.assertEqual(result["profile"]["reference_comparability"]["comparable"], 1)

    def test_no_reference_match_is_unverifiable_not_incorrect(self):
        target_claims = [_claim("orphan_addr", "uploaded", "ransomware")]
        reference = Corpus([_claim("some_other_addr", "ref_a", "ransomware")], full=True)
        result = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(result["address_comparability"]["orphan_addr"], target_audit.NO_REFERENCE_MATCH)
        self.assertEqual(result["profile"]["reference_comparability"]["no_reference_match"], 1)
        self.assertEqual(result["profile"]["reference_comparability"]["comparable"], 0)


class TestProvenanceIndependenceCases(unittest.TestCase):
    """Part P - the canonical apparent-vs-confirmed independence cases,
    exercised through the actual target-vs-reference audit rather than
    address_independence() directly, using synthetic fixed_root sources so
    the results don't depend on which bundled dataset happens to have which
    quirk. Patches provenance's config *and* its derived is_unresolved()
    ledger together (see provenance._root_ledger) - patching config alone
    leaves the ledger, built once at import time, out of sync.
    """
    def setUp(self):
        self._orig_sources = provenance._cfg.sources
        self._orig_exact, self._orig_prefix = provenance._EXACT_ROOTS, provenance._PREFIX_ROOTS
        patched = dict(self._orig_sources)

        def fixed(root):
            return {"provenance": {"mode": "fixed_root", "root": root,
                                   "resolved": True, "native": True, "verified": False}}
        patched["src_x1"] = fixed("synthetic_root_x")
        patched["src_x2"] = fixed("synthetic_root_x")
        patched["src_y"] = fixed("synthetic_root_y")
        patched["src_y2"] = fixed("synthetic_root_y")
        provenance._cfg.sources = patched
        provenance._EXACT_ROOTS, provenance._PREFIX_ROOTS = provenance._root_ledger(patched)

    def tearDown(self):
        provenance._cfg.sources = self._orig_sources
        provenance._EXACT_ROOTS, provenance._PREFIX_ROOTS = self._orig_exact, self._orig_prefix

    def _audit(self, addr, target_source, ref_source):
        target_claims = [_claim(addr, target_source, "ransomware")]
        reference = Corpus([_claim(addr, ref_source, "ransomware")], full=True)
        return target_audit.audit_target_against_reference(target_claims, reference)

    def test_case1_same_confirmed_root_is_same_provenance_not_unresolved(self):
        # A -> Root X, B -> Root X: apparent=2, confirmed roots=1. The two
        # sources are directly proven to be the same evidence, so this must
        # not be reported as an unresolved relationship.
        r = self._audit("a1", "src_x1", "src_x2")
        self.assertEqual(r["address_comparability"]["a1"], target_audit.SAME_PROVENANCE)
        self.assertEqual(r["profile"]["independence"]["shared_or_inherited_only"], 1)
        self.assertEqual(r["profile"]["independence"]["confirmed_independent_multi_root"], 0)

    def test_case2_different_confirmed_roots_is_distinct_provenance(self):
        # A -> Root X, B -> Root Y: confirmed roots=2.
        r = self._audit("a2", "src_x1", "src_y")
        self.assertEqual(r["address_comparability"]["a2"], target_audit.DISTINCT_PROVENANCE)
        self.assertEqual(r["profile"]["independence"]["confirmed_independent_multi_root"], 1)

    def test_case3_one_confirmed_one_unresolved_stays_unresolved(self):
        # A -> Root X, B -> unresolved: genuinely unknown whether B is the
        # same evidence as A or something else - must not be guessed either way.
        r = self._audit("a3", "src_x1", "an_unconfigured_source")
        self.assertEqual(r["address_comparability"]["a3"], target_audit.RELATIONSHIP_UNRESOLVED)
        self.assertEqual(r["profile"]["independence"]["independence_unresolved"], 1)

    def test_case4_two_unresolved_sources_are_not_confirmed_independent(self):
        # A -> unknown_A, B -> unknown_B: two different unresolved-source
        # names must not be silently treated as two confirmed independent roots.
        r = self._audit("a4", "mystery_a", "mystery_b")
        self.assertEqual(r["address_comparability"]["a4"], target_audit.RELATIONSHIP_UNRESOLVED)
        self.assertEqual(r["profile"]["independence"]["confirmed_independent_multi_root"], 0)

    def test_target_internal_root_sharing_does_not_leak_into_same_provenance(self):
        # the target itself asserts two claims that share a confirmed root;
        # the one reference claim for this address is unresolved and shares
        # nothing with the target. SAME_PROVENANCE must reflect a target<->
        # reference relationship, never sharing that is purely internal to
        # the target's own claims.
        target_claims = [_claim("a5", "src_x1", "ransomware"), _claim("a5", "src_x2", "ransomware")]
        reference = Corpus([_claim("a5", "an_unconfigured_source", "ransomware")], full=True)
        r = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(r["address_comparability"]["a5"], target_audit.RELATIONSHIP_UNRESOLVED)

    def test_many_reference_matches_any_one_shared_root_makes_it_same_provenance(self):
        # Part O "target has many reference matches", mixed roots: one ref
        # source shares the target's root, one has a different confirmed
        # root, one is unresolved. Comparability is deliberately conservative
        # - ANY shared root marks the relationship SAME_PROVENANCE, even
        # though other matched sources are independently confirmed.
        target_claims = [_claim("a6", "src_x1", "ransomware")]
        reference = Corpus([_claim("a6", "src_x2", "ransomware"),   # same root as target
                            _claim("a6", "src_y", "ransomware"),    # different confirmed root
                            _claim("a6", "mystery_c", "ransomware")],  # unresolved
                           full=True)
        r = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(r["address_comparability"]["a6"], target_audit.SAME_PROVENANCE)
        # independence is a separate, pooled question ("how many distinct
        # confirmed roots touch this address at all") and is not
        # contradicted by the target-specific SAME_PROVENANCE label above -
        # root Y is still an independently-confirmed root regardless of
        # whether the target's own source happens to share root X with src_x2.
        self.assertEqual(r["profile"]["independence"]["confirmed_independent_multi_root"], 1)

    def test_reference_sources_sharing_a_root_with_each_other_but_not_target_stays_distinct(self):
        # Part O "reference sources share roots [with each other]": two ref
        # sources agree on root Y; neither matches the target's root X. Their
        # mutual agreement must not be mistaken for agreement with the target.
        target_claims = [_claim("a7", "src_x1", "ransomware")]
        reference = Corpus([_claim("a7", "src_y", "ransomware"),
                            _claim("a7", "src_y2", "ransomware")], full=True)
        r = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(r["address_comparability"]["a7"], target_audit.DISTINCT_PROVENANCE)


class TestReferenceIndependenceIsNotCreditedToTheTarget(unittest.TestCase):
    """Two distinct roots that both belong to reference sources do not make the target's own,
    unresolved provenance distinct, and must not appear as the target's confirmed independence."""

    def test_an_unresolved_target_claim_next_to_two_reference_roots_stays_unresolved(self):
        from themis import corpus as corpus_mod
        base = dict(polarity="illicit", prov_family="", lastmod="", heuristic="", subcat="")
        ref = corpus_mod.Corpus([dict(base, address="a1", source="ransomwhere", raw_label="x", canon="ransomware"),
                                 dict(base, address="a1", source="tagpack", raw_label="x", canon="ransomware")])
        roots = {c["root"] for c in ref.by_addr["a1"]}
        self.assertEqual(len(roots), 2)                       # two resolved, distinct reference roots
        mine = [dict(base, address="a1", blockchain="bitcoin", source="upload", raw_label="x", canon="ransomware")]
        r = target_audit.audit_target_against_reference(mine, ref)
        self.assertEqual(r["address_comparability"]["bitcoin:a1"], target_audit.RELATIONSHIP_UNRESOLVED)
        ind = r["profile"]["independence"]
        self.assertEqual(ind["confirmed_independent_multi_root"], 0)
        self.assertEqual(ind["independence_unresolved"], 1)
        self.assertEqual(ind["apparent_multi_source"], 1)


class TestUninterpretedTargetIsNotAgreement(unittest.TestCase):
    """A target whose labels THEMIS could not map (`canon == "unknown"`) said nothing THEMIS understood, so the
    address is `incomparable` for the target however the reference sources treat each other. Their mutual
    agreement or conflict is reference-reference evidence and must not be reported as the target's own outcome
    (found on an external file whose vocabulary was entirely unmapped: 1,508 "exact" outcomes came from two
    reference sources agreeing with each other)."""

    BASE = dict(polarity="unknown", prov_family="", lastmod="", heuristic="", subcat="")

    def _ref(self, second="ransomware"):
        from themis import corpus as corpus_mod
        b = dict(self.BASE, polarity="illicit")
        return corpus_mod.Corpus([dict(b, address="a1", source="ref_a", raw_label="x", canon="ransomware"),
                                  dict(b, address="a1", source="ref_b", raw_label="x", canon=second,
                                       polarity="licit" if second == "exchange" else "illicit")])

    def _mine(self, canon="unknown"):
        return [dict(self.BASE, address="a1", blockchain="bitcoin", source="upload", raw_label="some opaque code",
                     canon=canon)]

    def _ws(self, ref, mine):
        from themis import workspace
        return workspace.AnalysisWorkspace(analysis_id="t", mode=workspace.MODE_UPLOADED, dataset_name="t.csv",
                                           created_at="", analysis_as_of_date="2026-01-01",
                                           reference_corpus=ref, claims=mine)

    def test_target_audit_counts_no_agreement_when_target_label_is_unmapped(self):
        for second in ("ransomware", "exchange"):            # reference sources agree / conflict with each other
            r = target_audit.audit_target_against_reference(self._mine(), self._ref(second))
            outcomes = r["profile"]["agreement"]["outcomes"]
            self.assertEqual(outcomes["incomparable"]["n"], 1, second)
            for k in ("exact", "licit/illicit conflict", "entity-type conflict", "hierarchical refinement"):
                self.assertEqual(outcomes[k]["n"], 0, (second, k))
            self.assertEqual(r["profile"]["reference_comparability"]["comparable"], 1)   # still matched

    def test_claims_and_conflicts_views_agree_with_the_audit(self):
        from themis import views
        for second in ("ransomware", "exchange"):
            mine = self._mine()
            ws = self._ws(self._ref(second), mine)
            self.assertEqual(views.outcome_for(ws, mine[0]), "incomparable", second)

    def test_address_inspector_does_not_report_a_reference_only_outcome_for_the_target(self):
        from themis import api
        for second in ("ransomware", "exchange"):
            ws = self._ws(self._ref(second), self._mine())
            self.assertEqual(api._explain_in_workspace(ws, "a1", "bitcoin")["outcome"], "incomparable", second)

    def test_an_interpreted_target_label_is_still_compared(self):
        # control: the same reference, but the target's label maps, so its own opinion is compared
        r = target_audit.audit_target_against_reference(self._mine("ransomware"), self._ref("ransomware"))
        self.assertEqual(r["profile"]["agreement"]["outcomes"]["exact"]["n"], 1)
        r = target_audit.audit_target_against_reference(self._mine("exchange"), self._ref("ransomware"))
        self.assertEqual(r["profile"]["agreement"]["outcomes"]["licit/illicit conflict"]["n"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
