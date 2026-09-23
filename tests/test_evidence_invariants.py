"""What THEMIS may and may not conclude from a dataset's own say-so (Phase 11/12
of the release closure). Every fixture is synthetic; no source string below is a
real lineage claim - THEMIS must treat each as an opaque piece of text.

    different source strings   != independent roots
    same source string         != necessarily the same root
    valid identifier           != verified label
    label agreement            != provenance independence
    agreement                  != truth
    unknown                    != false
    unresolved                 != inherited
    dependency candidate       != confirmed lineage
    declared source            != confirmed root
"""
import os, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis import provenance, taxonomy, config_io
from themis.api import app
from themis.ingest import relational as rel
from test_preflight import btc_address, to_csv

client = TestClient(app, base_url="http://localhost")
X, Y = "montreal_paquet_clouston_2019", "ofac_sdn"          # two confirmed (resolved) roots in the bundled registry


def claim(source, root, canon="exchange", addr="1X"):
    return dict(source=source, root=root, canon=canon, address=addr, raw_label=canon, heuristic="",
                polarity=taxonomy.POLARITY.get(canon, "unknown"))


def sqlite_db(dirpath, source_values, name="s.db"):
    """wallets(address, label, source): one row per entry of `source_values`, addresses all distinct."""
    path = os.path.join(dirpath, name)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, label TEXT, source TEXT)")
    con.executemany("INSERT INTO wallets VALUES (?,?,?)",
                    [(btc_address(i), "exchange", s) for i, s in enumerate(source_values)])
    con.commit()
    con.close()
    return path


def extract(path):
    return rel.extract(path, dict(driving_table="wallets", joins=[]), "case_x", confirmed=True)


class TestSourceDescriptorCases(unittest.TestCase):
    """Cases A-F, on the two surfaces that ever see a declared source string."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    # ---- the engine (a resolved root is a fact from config; an unresolved one is not a root at all)
    def test_A_two_unresolved_descriptors_do_not_corroborate(self):
        ind = provenance.address_independence([claim("a", "a:unresolved"), claim("b", "b:unresolved")])
        self.assertEqual(ind["confirmed_independent_root_count"], 0)
        self.assertEqual((ind["independence_min"], ind["independence_max"]), (1, 2))   # a range, never "2 independent"
        self.assertFalse(ind["circular"])                                             # and not "the same" either

    def test_B_two_descriptors_on_one_confirmed_root_are_shared_provenance(self):
        ind = provenance.address_independence([claim("a", X), claim("b", X)])
        self.assertEqual((ind["apparent_dataset_count"], ind["confirmed_independent_root_count"]), (2, 1))
        self.assertTrue(ind["circular"])

    def test_C_two_descriptors_on_different_confirmed_roots_are_independent(self):
        ind = provenance.address_independence([claim("a", X), claim("b", Y)])
        self.assertEqual(ind["confirmed_independent_root_count"], 2)
        self.assertFalse(ind["circular"])

    def test_D_one_confirmed_and_one_unresolved_leaves_independence_open(self):
        ind = provenance.address_independence([claim("a", X), claim("b", "b:unresolved")])
        self.assertEqual(ind["confirmed_independent_root_count"], 1)
        self.assertEqual((ind["independence_min"], ind["independence_max"]), (1, 2))
        self.assertEqual(ind["unresolved_source_count"], 1)

    def test_E_a_documented_dependency_between_two_of_three_descriptors_never_yields_three_roots(self):
        claims = [claim("a", "a:unresolved"), claim("b", "b:unresolved"), claim("c", "c:unresolved")]
        ind = provenance.address_independence(claims)
        self.assertEqual(ind["confirmed_independent_root_count"], 0)       # not 3, and not even 1: none is confirmed
        self.assertEqual(ind["apparent_dataset_count"], 3)                  # the apparent count stays labelled "apparent"

    def test_F_one_source_disagreeing_with_itself_is_not_cross_source_evidence(self):
        same_source = [claim("a", "a:unresolved", "exchange"), claim("a", "a:unresolved", "mixer")]
        self.assertEqual(taxonomy.classify_address(same_source), "incomparable")   # not a conflict, not agreement
        self.assertEqual(provenance.address_independence(same_source)["apparent_dataset_count"], 1)
        self.assertNotIn("conflicting", taxonomy.flags_for_address(same_source))

    # ---- a real extraction: the strings a database declares about itself
    def test_E_extraction_reports_the_dependency_as_a_candidate_and_moves_no_claim(self):
        path = sqlite_db(self.dir.name, ["Alpha", "Beta (compiled from Alpha)", "Gamma"] * 20)
        res = extract(path)
        self.assertEqual({(d["citing"], d["cited"]) for d in res["dependency_candidates"]},
                         {("Beta (compiled from Alpha)", "Alpha")})
        states = res["relational_provenance"]
        self.assertEqual(states["counts"], {"resolved": 0, "inherited": 0, "inferred": 0, "unresolved": 60})
        self.assertEqual(states["dependency_candidate_claims"], 20)          # reported on its own line
        self.assertEqual(res["dataset_profile"]["scale"]["unique_sources"], 3)   # 3 strings ...
        self.assertFalse(res["target_audit"]["profile"]["independence"]["available"])   # ... and no independence claimed
        for c in res["claims"]:
            self.assertFalse(provenance.resolve(c)["resolved"])               # declared source != confirmed root

    def test_dependency_candidates_are_the_same_with_or_without_a_reference_and_change_no_count(self):
        path = sqlite_db(self.dir.name, ["Alpha", "Beta (compiled from Alpha)"] * 10)
        res = extract(path)
        deps = res["dependency_candidates"]
        with_deps = rel.provenance_states(res["claims"], deps)["counts"]
        without = rel.provenance_states(res["claims"], [])["counts"]
        self.assertEqual(with_deps, without)

    def test_a_declared_source_that_merely_looks_like_a_bundled_source_resolves_nothing(self):
        names = sorted(config_io.load().sources) + [Y, X, "tagpack_anything", "ransomwhere"]
        path = sqlite_db(self.dir.name, names * 2)
        res = extract(path)
        self.assertEqual(res["relational_provenance"]["counts"]["resolved"], 0)
        self.assertFalse(any(provenance.resolve(c)["resolved"] for c in res["claims"]))
        self.assertEqual(res["target_audit"]["profile"]["evidence_class"]["verified"], 0)

    def test_the_same_descriptor_string_is_one_descriptor_not_one_root(self):
        path = sqlite_db(self.dir.name, ["SameName"] * 30)
        res = extract(path)
        self.assertEqual(res["dataset_profile"]["scale"]["unique_sources"], 1)
        self.assertEqual(res["relational_provenance"]["counts"]["resolved"], 0)

    def test_empty_and_whitespace_descriptors_are_absence_not_a_source(self):
        path = sqlite_db(self.dir.name, ["", "   ", "\t", "Real"] * 5)
        res = extract(path)
        self.assertEqual(res["dataset_profile"]["scale"]["unique_sources"], 1)
        self.assertEqual(res["dataset_profile"]["source_coverage"]["claims_without_source"], 15)

    def test_a_huge_descriptor_string_is_handled_and_still_unresolved(self):
        path = sqlite_db(self.dir.name, ["Z" * 200_000, "Y" * 10])
        res = extract(path)
        self.assertFalse(res["stopped"])
        self.assertEqual(res["relational_provenance"]["counts"]["unresolved"], 2)


class TestUploadedCsvNeverPromotesItself(unittest.TestCase):
    """A CSV can name any source and any 'verification' it likes; none of it is evidence to THEMIS."""

    def _upload(self, rows, fields):
        r = client.post("/api/analysis", files={"file": ("u.csv", to_csv(rows, fields), "text/csv")},
                        data={"source_id": "invariant_upload", "use_reference": "false"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["analysis_id"]

    def test_valid_identifiers_and_confident_labels_are_not_verified_labels(self):
        rows = [dict(address=btc_address(i), label="exchange", source="OFAC SDN list", confidence="1.0",
                     heuristic="manual_verified", verified="true") for i in range(12)]
        aid = self._upload(rows, ["address", "label", "source", "confidence", "heuristic", "verified"])
        claims = client.get(f"/api/analysis/{aid}/claims", params=dict(limit=500)).json()["claims"]
        self.assertEqual(len(claims), 12)
        self.assertNotIn("verified", {c["evidence_tier"] for c in claims})
        self.assertEqual({c["provenance"] for c in claims}, {"unresolved"})

    def test_two_descriptor_strings_in_one_file_stay_one_unresolved_root(self):
        rows = [dict(address=btc_address(i), label="exchange", source=("Src One" if i % 2 else "Src Two"))
                for i in range(10)]
        aid = self._upload(rows, ["address", "label", "source"])
        prov = client.get(f"/api/analysis/{aid}/provenance").json()["uploaded_dataset"]
        self.assertEqual(prov["n_distinct_declared_sources"], 2)             # two strings ...
        self.assertEqual([r["resolved"] for r in prov["roots"]], [False])    # ... one root, unresolved
        shares = client.get(f"/api/analysis/{aid}/summary").json()["result"]["shares"]
        self.assertNotIn("confirmed_independent_share", shares)

    def test_the_same_claim_from_two_declared_sources_is_kept_and_still_confirms_no_independence(self):
        """Duplicate-claim identity: (address, label, declared source). Keeping both claims preserves
        provenance; it must not turn two descriptor strings into two independent roots."""
        a = btc_address(1)
        rows = [dict(address=a, label="exchange", source=s, seen=str(i)) for i, s in enumerate(["Src One", "Src Two", "Src One"])]
        aid = self._upload(rows, ["address", "label", "source", "seen"])
        self.assertEqual(len(client.get(f"/api/analysis/{aid}/claims", params=dict(limit=500)).json()["claims"]), 2)
        prov = client.get(f"/api/analysis/{aid}/provenance").json()["uploaded_dataset"]
        self.assertEqual({d["value"]: d["n_claims"] for d in prov["declared_sources"]}, {"Src One": 1, "Src Two": 1})
        self.assertEqual(prov["n_distinct_declared_sources"], 2)
        self.assertEqual([r["resolved"] for r in prov["roots"]], [False])          # still one unresolved root
        shares = client.get(f"/api/analysis/{aid}/summary").json()["result"]["shares"]
        self.assertNotIn("confirmed_independent_share", shares)
        ind = provenance.address_independence([claim("case", "case:unresolved", addr=a)] * 2)
        self.assertEqual(ind["confirmed_independent_root_count"], 0)

    def test_unknown_labels_stay_unknown_and_are_neither_licit_nor_illicit(self):
        rows = [dict(address=btc_address(i), label=lab) for i, lab in
                enumerate(["totally-made-up", "class_9", "???", "Ünï©ödé", "<b>x</b>", "'; DROP TABLE claims;--"])]
        aid = self._upload(rows, ["address", "label"])
        claims = client.get(f"/api/analysis/{aid}/claims", params=dict(limit=500)).json()["claims"]
        self.assertEqual({c["canon"] for c in claims}, {"unknown"})
        self.assertEqual({c["polarity"] for c in claims}, {"unknown"})
        self.assertEqual({c["raw_label"] for c in claims}, {r["label"] for r in rows})   # raw evidence preserved verbatim


class TestAgreementIsNotIndependenceOrTruth(unittest.TestCase):
    def test_exact_agreement_on_one_confirmed_root_is_agreement_and_still_circular(self):
        claims = [claim("a", X), claim("b", X)]
        self.assertEqual(taxonomy.classify_address(claims), "exact")
        self.assertIn("circular", taxonomy.flags_for_address(claims))

    def test_exact_agreement_between_unresolved_descriptors_confirms_no_independence(self):
        claims = [claim("a", "a:unresolved"), claim("b", "b:unresolved")]
        self.assertEqual(taxonomy.classify_address(claims), "exact")
        self.assertEqual(provenance.address_independence(claims)["confirmed_independent_root_count"], 0)

    def test_no_outcome_name_claims_truth(self):
        for name in taxonomy.OUTCOMES:
            self.assertNotRegex(name, r"(?i)true|correct|verified|valid|confirmed")


class TestTaxonomyInvariants(unittest.TestCase):
    """Phase 12: the agreement classes, on adversarial label sets."""

    def out(self, *labels):
        return taxonomy.classify_address([claim(f"s{i}", f"s{i}:unresolved", c) for i, c in enumerate(labels)])

    def test_unknown_labels_never_make_agreement(self):
        self.assertEqual(self.out("exchange", "unknown"), "incomparable")
        self.assertEqual(self.out("exchange", "unknown", "unknown"), "incomparable")
        self.assertEqual(self.out("unknown", "unknown"), "incomparable")          # two shrugs are not agreement

    def test_unknown_never_turns_a_conflict_into_agreement_or_vice_versa(self):
        self.assertEqual(self.out("exchange", "mixer", "unknown"), "licit/illicit conflict")
        self.assertEqual(self.out("mixer", "mixer", "unknown"), "exact")

    def test_parent_and_child_is_refinement(self):
        self.assertEqual(self.out("illicit_unspec", "ransomware"), "hierarchical refinement")
        self.assertEqual(self.out("licit_unspec", "exchange"), "hierarchical refinement")

    def test_siblings_are_a_conflict_not_a_refinement(self):
        self.assertEqual(self.out("ransomware", "mixer"), "entity-type conflict")
        self.assertEqual(self.out("exchange", "mining"), "entity-type conflict")

    def test_opposite_polarity_is_a_polarity_conflict(self):
        self.assertEqual(self.out("exchange", "ransomware"), "licit/illicit conflict")
        self.assertEqual(self.out("licit_unspec", "illicit_unspec"), "licit/illicit conflict")

    def test_generic_placeholders_of_opposite_polarity_are_not_a_refinement(self):
        self.assertNotEqual(self.out("licit_unspec", "ransomware"), "hierarchical refinement")

    def test_a_deeper_hierarchy_is_walked_not_special_cased(self):
        """A three-level tree the bundled config does not have: grandparent > parent > child."""
        cats = dict(taxonomy.CATEGORIES)
        cats.update(l1=dict(polarity="illicit", parent="illicit_unspec"), l2=dict(polarity="illicit", parent="l1"),
                    l2b=dict(polarity="illicit", parent="l1"))
        saved_cats = taxonomy.CATEGORIES
        taxonomy.CATEGORIES = cats
        saved_pol = dict(taxonomy.POLARITY)
        taxonomy.POLARITY.update({k: v["polarity"] for k, v in cats.items()})
        try:
            self.assertEqual(self.out("l1", "l2"), "hierarchical refinement")     # parent / child
            self.assertEqual(self.out("illicit_unspec", "l2"), "hierarchical refinement")   # grandparent / grandchild
            self.assertEqual(self.out("l2", "l2b"), "entity-type conflict")       # siblings under one parent
        finally:
            taxonomy.CATEGORIES = saved_cats
            taxonomy.POLARITY.clear()
            taxonomy.POLARITY.update(saved_pol)

    def test_no_source_name_appears_in_the_alias_table(self):
        """An alias that names a dataset would map its labels to agree by construction."""
        sources = {s.lower() for s in config_io.load().sources}
        self.assertFalse(sources & set(taxonomy.ALIASES), sources & set(taxonomy.ALIASES))

    def test_elliptic_class_codes_map_only_at_fresh_ingestion_and_never_rewrite_a_frozen_claim(self):
        self.assertEqual(taxonomy.canonicalize_category("class_1"), "illicit_unspec")
        self.assertEqual(taxonomy.canonicalize_category("class_2"), "licit_unspec")
        self.assertIsNone(taxonomy.canonicalize_category("class_3"))               # the dataset's own "unknown"
        frozen = dict(claim("ellipticpp", "elliptic_undisclosed", "unknown"), raw_label="class_1")
        before = dict(frozen)
        taxonomy.classify_address([frozen, claim("b", "b:unresolved", "exchange")])
        self.assertEqual(frozen, before)                                            # classification reads, never writes


if __name__ == "__main__":
    unittest.main()
