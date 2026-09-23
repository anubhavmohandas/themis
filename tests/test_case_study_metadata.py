"""WalletClassification case-study integration (docs/case_studies/walletclassification.md):
generic, dataset-agnostic support for (1) an analysis to carry caller-asserted
provenance/integrity context, and (2) refusing to start analysis on a corrupt
SQLite file. Nothing here is specific to any one dataset - every fixture
below is synthetic, and the two source-descriptor strings used to test the
"declared source is not a confirmed root" guarantee are chosen only because
they mirror the real case study's documented dependency (BABD-13 names
WalletExplorer as one of its own sources); THEMIS treats them as ordinary
strings, not as a known lineage.
"""
import os, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from themis.ingest import relational as rel, sqlite_source as sq
from test_preflight import btc_address
from test_relational import make_relational_db, WALLETS_LABELS_SOURCES


class TestIntegrityGate(unittest.TestCase):
    """No attribution analysis without a defensible schema (540094b) extends
    to the file itself: a malformed/unreadable database is refused before any
    table is even selected, not crashed and not silently analyzed."""

    def test_a_damaged_file_is_refused_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "damaged.db")
            make_relational_db(path)
            with open(path, "r+b") as f:
                f.truncate(f.seek(0, 2) // 3)   # cut off the back half of the file
            res = rel.extract(path, WALLETS_LABELS_SOURCES, "x", confirmed=True)
            self.assertTrue(res["stopped"])
            self.assertEqual(res["claims"], [])
            self.assertIn("DATABASE INTEGRITY CHECK FAILED", res["message"])
            self.assertEqual(res["dataset_preflight"]["blockers"][0]["code"], "database_corrupt")
            self.assertNotEqual(res["dataset_preflight"]["integrity"]["status"], "ok")

    def test_a_file_that_is_not_a_database_at_all_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "not_a_database.db")
            with open(path, "wb") as f:
                f.write(b"not a sqlite file, just bytes" * 50)
            res = rel.extract(path, dict(driving_table="wallets", joins=[]), "x", confirmed=True)
            self.assertTrue(res["stopped"])
            self.assertIn("DATABASE INTEGRITY CHECK FAILED", res["message"])

    def test_a_healthy_database_is_not_gated(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "healthy.db")
            make_relational_db(path)
            res = rel.extract(path, WALLETS_LABELS_SOURCES, "x", confirmed=True)
            self.assertFalse(res["stopped"])

    def test_inspecting_a_damaged_file_reports_integrity_instead_of_raising(self):
        """sqlite_source.inspect() backs the Database page's "2 - Database
        inspection" step; a file too damaged for even sqlite_master to be
        read must still come back as a result (integrity != ok, no tables),
        not an exception - otherwise the UI's integrity-failed gate never
        has anything to key off of."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "damaged.db")
            make_relational_db(path)
            with open(path, "r+b") as f:
                f.truncate(f.seek(0, 2) // 3)
            insp = sq.inspect(path)
            self.assertNotEqual(insp["integrity"]["status"], "ok")
            self.assertEqual(insp["tables"], [])
            self.assertEqual(insp["views"], [])


class TestCaseMetadata(unittest.TestCase):
    """Optional, generic, caller-asserted context (relational.py:CASE_METADATA_FIELDS).
    THEMIS carries it unchanged; it never requires, infers, or scores it."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "case.db")
        make_relational_db(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_recovered_subset_metadata_is_carried_through_unchanged_and_stays_visible(self):
        cm = dict(analysis_origin="recovered_sqlite_subset", integrity_status="source_file_truncated",
                  recovery_status="recovered_subset", source_identity_status="partially_attributed",
                  provenance_resolution_status="unresolved", limitations="partial recovery only")
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "case_test", confirmed=True, case_metadata=cm)
        self.assertEqual(res["dataset_preflight"]["case_metadata"], cm)

    def test_case_metadata_is_absent_for_an_ordinary_analysis(self):
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "ordinary", confirmed=True)
        self.assertNotIn("case_metadata", res["dataset_preflight"])

    def test_an_unknown_case_metadata_field_is_rejected(self):
        with self.assertRaises(ValueError):
            rel.extract(self.db, WALLETS_LABELS_SOURCES, "bad", confirmed=True,
                        case_metadata=dict(not_a_real_field="x"))

    def test_recovered_subset_metadata_never_inflates_the_dataset_s_own_reported_scale(self):
        cm = dict(analysis_origin="recovered_sqlite_subset", recovery_status="recovered_subset")
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "case_test", confirmed=True, case_metadata=cm)
        # THEMIS reports only what it counted in THIS file - never an inferred
        # or backfilled "original/full corpus size"
        self.assertEqual(res["dataset_profile"]["scale"]["total_candidate_records"], 200)
        self.assertNotIn("original_total_records", res["dataset_profile"]["scale"])
        self.assertNotIn("full_corpus_size", res["dataset_profile"]["scale"])


class TestDeclaredSourceIsNotAConfirmedRoot(unittest.TestCase):
    """Valid addresses + present labels + named sources must never be
    silently upgraded into verified labels, resolved provenance, or
    independent evidential roots - the central claim of the case study."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "sources.db")
        con = sqlite3.connect(cls.db)
        con.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, label TEXT, source TEXT)")
        # two declared-source strings, one of which textually names the other -
        # documented dependency, never a verified independent lineage
        rows = [(btc_address(i), "mixer" if i % 2 else "exchange",
                 "BABD-13 (via WalletExplorer)" if i % 2 else "WalletExplorer") for i in range(60)]
        con.executemany("INSERT INTO wallets VALUES (?,?,?)", rows)
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def _extract(self):
        return rel.extract(self.db, dict(driving_table="wallets", joins=[]), "src_test", confirmed=True)

    def test_valid_addresses_do_not_imply_verified_labels(self):
        res = self._extract()
        self.assertEqual(res["validation"]["n_identifiers_invalid"], 0)
        self.assertEqual(res["target_audit"]["profile"]["evidence_class"]["verified"], 0)

    def test_non_empty_source_does_not_imply_resolved_provenance(self):
        res = self._extract()
        self.assertGreater(res["dataset_profile"]["source_coverage"]["claims_with_declared_source"], 0)
        self.assertEqual(res["relational_provenance"]["counts"]["resolved"], 0)

    def test_different_source_strings_are_not_treated_as_independent_roots(self):
        res = self._extract()
        self.assertEqual(res["dataset_profile"]["scale"]["unique_sources"], 2)
        # no reference corpus: independence is never computed, whatever the
        # source strings themselves claim
        self.assertFalse(res["target_audit"]["profile"]["independence"]["available"])

    def test_dependency_candidates_are_surfaced_but_never_change_a_count(self):
        res = self._extract()
        deps = res["dependency_candidates"]
        self.assertTrue(any(d["cited"].lower() in d["citing"].lower() for d in deps))
        before = dict(res["relational_provenance"]["counts"])
        # recomputing with the same dependency candidates must not move
        # anything but resolved/inherited/inferred/unresolved among themselves,
        # and must never touch independence
        after = rel.provenance_states(res["claims"], deps)["counts"]
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertFalse(res["target_audit"]["profile"]["independence"]["available"])


if __name__ == "__main__":
    unittest.main()
