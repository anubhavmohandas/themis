"""Loop 2 STEP 5/6/28 - confirmed independence must never inflate unresolved
provenance into distinct roots, and known-shared roots must collapse to one
confirmed root regardless of how many datasets restate them.
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis import provenance


def _claim(source, root):
    return {"source": source, "root": root}


class TestAddressIndependence(unittest.TestCase):
    def test_two_unresolved_sources_are_not_two_confirmed_roots(self):
        claims = [_claim("mystery_one", "mystery_one:unresolved"),
                 _claim("mystery_two", "mystery_two:unresolved")]
        r = provenance.address_independence(claims)
        self.assertEqual(r["apparent_dataset_count"], 2)
        self.assertEqual(r["confirmed_independent_root_count"], 0)
        self.assertEqual(r["unresolved_source_count"], 2)
        self.assertFalse(r["circular"])   # nothing is *known* to share a root either
        self.assertEqual(r["independence_max"], 2)

    def test_known_shared_root_counts_once(self):
        # three datasets, one shared *resolved* root
        claims = [_claim("a", "ransomwhere_crowd"), _claim("b", "ransomwhere_crowd"),
                 _claim("c", "ransomwhere_crowd")]
        r = provenance.address_independence(claims)
        self.assertEqual(r["apparent_dataset_count"], 3)
        self.assertEqual(r["confirmed_independent_root_count"], 1)
        self.assertEqual(r["shared_root_count"], 2)
        self.assertTrue(r["circular"])
        self.assertEqual(len(r["collapsed_claims"]), 2)

    def test_mixed_roots_two_confirmed_one_shared(self):
        # A + B -> root X (shared/resolved); C -> root Y (resolved, distinct)
        claims = [_claim("a", "ransomwhere_crowd"), _claim("b", "ransomwhere_crowd"),
                 _claim("c", "montreal_paquet_clouston_2019")]
        r = provenance.address_independence(claims)
        self.assertEqual(r["apparent_dataset_count"], 3)
        self.assertEqual(r["confirmed_independent_root_count"], 2)
        self.assertEqual(r["shared_root_count"], 1)

    def test_one_confirmed_plus_two_unresolved_gives_min_1_max_3(self):
        claims = [_claim("a", "ransomwhere_crowd"),
                 _claim("b", "b:unresolved"), _claim("c", "c:unresolved")]
        r = provenance.address_independence(claims)
        self.assertEqual(r["independence_min"], 1)
        self.assertEqual(r["independence_max"], 3)
        self.assertEqual(r["confirmed_independent_root_count"], 1)

    def test_one_source_two_claims_different_roots_both_count(self):
        # a single dataset can assert two claims about the same address
        # (e.g. two TagPack records from different creators); collapsing to
        # the last claim per source would silently drop a confirmed root.
        claims = [_claim("schnoering", "montreal_paquet_clouston_2019"),
                 _claim("tagpack", "tagpack_GraphSense Core Team"),
                 _claim("tagpack", "montreal_paquet_clouston_2019")]
        r = provenance.address_independence(claims)
        self.assertEqual(r["apparent_dataset_count"], 2)
        self.assertEqual(r["confirmed_independent_root_count"], 2)
        self.assertEqual(r["shared_root_count"], 1)
        self.assertTrue(r["circular"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
