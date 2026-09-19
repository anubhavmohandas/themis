"""Loop 2 STEP 5/6/28 - confirmed independence must never inflate unresolved
provenance into distinct roots, and known-shared roots must collapse to one
confirmed root regardless of how many datasets restate them.
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis import provenance, taxonomy, analysis
from themis.trust import predicates


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


class _Corpus:
    """explain() only reads by_addr; a bare stand-in lets each case set the
    provenance roots directly (Corpus(...) would overwrite them from the
    real source registry)."""

    def __init__(self, by_addr):
        self.by_addr = by_addr


def _full(source, root, resolved):
    return dict(source=source, root=root, canon="mixer", raw_label="mixer", lastmod="",
                heuristic="curated", prov_resolved=resolved, prov_native=False,
                address="1X")


class TestIndependenceCasesAcrossEverySurface(unittest.TestCase):
    """Phase 2F - the canonical cases A-G, checked against every place the
    codebase surfaces independence: provenance.address_independence (the
    source of truth), analysis.explain (CLI + API + Address Inspector),
    taxonomy.flags_for_address (the `circular` flag) and the trust
    predicate non_circular. They must never disagree, and an unresolved root
    string must never become a confirmed independent root on any of them.
    X, Y are resolved roots; U1, U2 are unresolved (root strings differ)."""

    X, Y = "montreal_paquet_clouston_2019", "ofac_sdn"
    U1, U2 = "elliptic_undisclosed", "rodwald_own_S"

    #  name: (claims as (source, root), apparent, confirmed, unresolved_sources, min, max, circular)
    CASES = {
        "A same root":            ([("a", X), ("b", X)],                  2, 1, 0, 1, 1, True),
        "B distinct roots":       ([("a", X), ("b", Y)],                  2, 2, 0, 2, 2, False),
        "C resolved+unresolved":  ([("a", X), ("b", U1)],                 2, 1, 1, 1, 2, False),
        "D both unresolved":      ([("a", U1), ("b", U2)],                2, 0, 2, 1, 2, False),
        "E one source, 2 roots":  ([("a", X), ("a", Y)],                  1, 2, 0, 2, 2, False),
        "F many sources 1 root":  ([("a", X), ("b", X), ("c", X)],        3, 1, 0, 1, 1, True),
        "G mixed":                ([("a", X), ("b", X), ("c", U1)],       3, 1, 1, 1, 2, True),
    }

    def test_every_surface_agrees_on_every_case(self):
        for name, (spec, apparent, confirmed, unres, lo, hi, circ) in self.CASES.items():
            with self.subTest(case=name):
                claims = [_full(s, r, not provenance.is_unresolved(r)) for s, r in spec]
                ind = provenance.address_independence(claims)
                self.assertEqual((ind["apparent_dataset_count"], ind["confirmed_independent_root_count"],
                                  ind["unresolved_source_count"], ind["independence_min"],
                                  ind["independence_max"], ind["circular"]),
                                 (apparent, confirmed, unres, lo, hi, circ))

                ex = analysis.explain(_Corpus({"1X": claims}), "1X")
                self.assertEqual((ex["apparent_corroboration"], ex["actual_corroboration"], ex["circular"]),
                                 (apparent, confirmed, circ))
                self.assertEqual(ex["independence"], ind)
                self.assertEqual("circular" in ex["flags"], circ)
                self.assertEqual("circular" in taxonomy.flags_for_address(claims), circ)
                self.assertEqual(predicates.non_circular(claims[0], {"claims_by_address": {"1X": claims}}),
                                 not circ)

    def test_unresolved_strings_never_create_confirmed_independence(self):
        # the invariant behind D and G: however many unresolved sources
        # there are, they add to independence_max only, never to the
        # confirmed count, and are never called circular against each other
        for n in (1, 2, 5):
            claims = [_full(f"s{i}", f"unresolved_root_{i}", False) for i in range(n)]
            ind = provenance.address_independence(claims)
            self.assertEqual(ind["confirmed_independent_root_count"], 0)
            self.assertEqual(ind["independence_max"], n)
            self.assertFalse(ind["circular"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
