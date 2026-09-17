"""Loop 2 STEP 3/28 - target-vs-reference auditing must never let
reference-reference relationships leak into a target dataset's numbers.
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.corpus import Corpus
from themis import target_audit


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

    def test_no_reference_match_is_unverifiable_not_incorrect(self):
        target_claims = [_claim("orphan_addr", "uploaded", "ransomware")]
        reference = Corpus([_claim("some_other_addr", "ref_a", "ransomware")], full=True)
        result = target_audit.audit_target_against_reference(target_claims, reference)
        self.assertEqual(result["address_comparability"]["orphan_addr"], target_audit.NO_REFERENCE_MATCH)
        self.assertEqual(result["profile"]["reference_comparability"]["no_reference_match"], 1)
        self.assertEqual(result["profile"]["reference_comparability"]["comparable"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
