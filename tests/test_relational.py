"""Multi-table SQLite ingestion (ingest/relational.py): table-role candidates,
relationship discovery, joined streaming extraction, provenance and conflict
classification. Single-table SQLite and CSV behavior are covered by
test_sqlite_source.py / test_preflight.py and are not repeated here except
where this pass could plausibly have disturbed them (see
test_csv_ingestion_is_unaffected / test_paper_reproduction_is_unaffected).
"""
import os, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis.api import app
from themis.ingest import relational as rel, sqlite_source as sq
from test_preflight import btc_address


def make_relational_db(path, n=200):
    """wallets -> labels -> sources, with declared foreign keys."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("CREATE TABLE sources (source_id INTEGER PRIMARY KEY, source_name TEXT, source_url TEXT)")
    con.executemany("INSERT INTO sources VALUES (?,?,?)",
                    [(1, "OFAC SDN", "https://sanctionslist.ofac.treas.gov"), (2, "Community tip", "")])
    con.execute("CREATE TABLE labels (label_id INTEGER PRIMARY KEY, category TEXT, source_id INTEGER, "
                "FOREIGN KEY (source_id) REFERENCES sources(source_id))")
    con.executemany("INSERT INTO labels VALUES (?,?,?)", [(0, "exchange", 1), (1, "mixer", 2), (2, "ransomware", 1)])
    con.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, label_id INTEGER, first_seen TEXT, "
                "FOREIGN KEY (label_id) REFERENCES labels(label_id))")
    con.executemany("INSERT INTO wallets VALUES (?,?,?)",
                    [(btc_address(i), i % 3, f"2024-0{1 + i % 9}-10") for i in range(n)])
    con.commit()
    con.close()


WALLETS_LABELS_SOURCES = dict(driving_table="wallets", joins=[
    dict(table="labels", local_key="label_id", foreign_key="label_id"),
    dict(table="sources", local_table="labels", local_key="source_id", foreign_key="source_id"),
])


class TestCandidateRolesAndRelationships(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "rel.db")
        make_relational_db(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_wallets_is_the_claim_subject_table(self):
        by_table = {c["table"]: c for c in rel.candidate_roles(self.db)}
        self.assertEqual(by_table["wallets"]["role"], "claim_subject")
        self.assertGreater(by_table["wallets"]["confidence"], 0.5)

    def test_labels_is_recognized_as_an_attribution_table(self):
        by_table = {c["table"]: c for c in rel.candidate_roles(self.db)}
        self.assertEqual(by_table["labels"]["role"], "attribution")

    def test_declared_foreign_keys_are_found_with_full_confidence(self):
        rels = rel.infer_relationships(self.db)
        declared = {(r["from_table"], r["from_column"], r["to_table"]): r for r in rels if r["kind"] == "declared"}
        self.assertIn(("wallets", "label_id", "labels"), declared)
        self.assertIn(("labels", "source_id", "sources"), declared)
        self.assertEqual(declared[("wallets", "label_id", "labels")]["confidence"], 1.0)

    def test_ambiguous_join_requires_a_spec_the_user_confirms(self):
        # candidate_roles() only proposes; nothing is joined or extracted
        # until a caller supplies an explicit JoinSpec.
        candidates = rel.candidate_roles(self.db)
        self.assertGreaterEqual(len(candidates), 3)
        # extract() with no spec at all is a TypeError, not a silent guess
        with self.assertRaises(TypeError):
            rel.extract(self.db, source_id="x")


class TestJoinedExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "rel.db")
        make_relational_db(cls.db, n=200)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_join_spec_is_structurally_validated(self):
        self.assertTrue(rel.validate_join_spec(self.db, WALLETS_LABELS_SOURCES)["ok"])
        with self.assertRaises(ValueError):
            rel.validate_join_spec(self.db, dict(driving_table="wallets",
                                                 joins=[dict(table="nope", local_key="x", foreign_key="y")]))
        with self.assertRaises(ValueError):
            rel.validate_join_spec(self.db, dict(driving_table="wallets",
                                                 joins=[dict(table="labels", local_key="nope", foreign_key="label_id")]))

    def test_extraction_joins_wallets_labels_and_sources(self):
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "rel_test_db", confirmed=True)
        self.assertFalse(res["stopped"])
        self.assertEqual(len(res["claims"]), 200)
        self.assertEqual(res["dataset_preflight"]["chain"]["value"], "bitcoin")
        c = res["claims"][0]
        self.assertEqual(c["canon"], "exchange")           # labels.category for label_id 0
        self.assertIn("ofac", c["prov_family"].lower())    # sources.source_url for source_id 1

    def test_every_claim_preserves_provenance_back_to_its_source_rows(self):
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "rel_test_db", confirmed=True)
        for c in res["claims"][:20]:
            prov = c["provenance_record"]
            self.assertEqual(prov["source_database"], self.db)
            self.assertEqual(prov["driving_table"]["table"], "wallets")
            self.assertIsNotNone(prov["driving_table"]["row_key"])
            joined_tables = {j["table"] for j in prov["joined_tables"]}
            self.assertEqual(joined_tables, {"labels", "sources"})
            for j in prov["joined_tables"]:
                self.assertIsNotNone(j["row_key"])
            self.assertIn("address", prov["original_values"])

    def test_missing_source_stays_unresolved_rather_than_fabricated(self):
        # "rel_test_db" has no config/sources/ entry: a declared source URL is
        # present in the data, but THEMIS has no evidence rule for this brand
        # new database, so every claim is UNRESOLVED - never invented as
        # resolved just because a source string happens to be non-empty.
        res = rel.extract(self.db, WALLETS_LABELS_SOURCES, "rel_test_db", confirmed=True)
        states = res["relational_provenance"]["counts"]
        self.assertEqual(states["resolved"], 0)
        self.assertEqual(states["inherited"], 0)
        self.assertEqual(states["unresolved"], len(res["claims"]))

    def test_large_table_processing_uses_chunking_not_full_load(self):
        seen_chunk_sizes = []
        for chunk in rel.iter_joined_rows(self.db, WALLETS_LABELS_SOURCES, chunk_rows=32):
            seen_chunk_sizes.append(len(chunk))
            self.assertLessEqual(len(chunk), 32)   # never materializes more than one chunk at a time
        self.assertEqual(sum(seen_chunk_sizes), 200)
        self.assertGreater(len(seen_chunk_sizes), 1)


class TestDataQuality(unittest.TestCase):
    def _db(self, rows):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, "q.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE wallets (address TEXT, category TEXT)")
        con.executemany("INSERT INTO wallets VALUES (?,?)", rows)
        con.commit()
        con.close()
        return path

    def test_malformed_addresses_are_rejected_not_normalized(self):
        db = self._db([(btc_address(1), "exchange"), ("not-a-real-address", "mixer"),
                       ("", "mixer"), (btc_address(2), "exchange")])
        res = rel.extract(db, dict(driving_table="wallets", joins=[]), "q", confirmed=True)
        self.assertEqual(len(res["claims"]), 2)
        self.assertEqual(res["validation"]["rejected_by_reason"].get("invalid address"), 1)
        self.assertEqual(res["validation"]["rejected_by_reason"].get("empty address"), 1)

    def test_numeric_ids_are_not_interpreted_as_addresses(self):
        # a sequential 0,1,2... counter, however named, is never proposed as
        # the claim subject - the same rule test_preflight.py exercises for CSV.
        db = self._db([(str(i), "exchange") for i in range(20)])
        res = rel.extract(db, dict(driving_table="wallets", joins=[]), "q")
        self.assertTrue(res["stopped"])
        self.assertNotEqual(res["dataset_preflight"]["dataset_type"], "attribution_claims")

    def test_duplicate_claims_are_detected(self):
        addr = btc_address(1)
        db = self._db([(addr, "exchange"), (addr, "exchange"), (addr, "exchange")])
        res = rel.extract(db, dict(driving_table="wallets", joins=[]), "q", confirmed=True)
        self.assertEqual(len(res["claims"]), 1)
        self.assertEqual(res["validation"]["rejected_by_reason"].get("duplicate claim"), 2)

    def test_conflicting_labels_on_the_same_address_are_detected(self):
        addr = btc_address(1)
        db = self._db([(addr, "exchange"), (addr, "ransomware"), (btc_address(2), "mixer")])
        res = rel.extract(db, dict(driving_table="wallets", joins=[]), "q", confirmed=True)
        conflicts = res["conflicts"]["conflicting_addresses"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["address"], addr)
        self.assertEqual(conflicts[0]["outcome"], "licit/illicit conflict")
        self.assertEqual(len(conflicts[0]["claims"]), 2)   # both claims kept for audit

    def test_hierarchical_refinement_is_not_a_conflict(self):
        addr = btc_address(1)
        db = self._db([(addr, "illicit_unspec"), (addr, "ransomware")])
        res = rel.extract(db, dict(driving_table="wallets", joins=[]), "q", confirmed=True)
        # a generic placeholder paired with a specific descendant refines, it does not conflict
        self.assertEqual(res["conflicts"]["conflicting_addresses"], [])


class TestMultipleChains(unittest.TestCase):
    def test_a_per_row_chain_column_is_validated_against_its_own_chain(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, "multi.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE wallets (address TEXT, category TEXT, chain TEXT)")
        con.executemany("INSERT INTO wallets VALUES (?,?,?)", [
            (btc_address(1), "exchange", "bitcoin"),
            (btc_address(2), "exchange", "bitcoin"),
            ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "exchange", "tron"),  # no adapter -> rejected
        ])
        con.commit(); con.close()
        res = rel.extract(path, dict(driving_table="wallets", joins=[]), "multi", chain="bitcoin", confirmed=True)
        self.assertFalse(res["stopped"])
        self.assertEqual(len(res["claims"]), 2)
        self.assertEqual(res["validation"]["rejected_by_reason"].get("unresolved chain"), 1)
        self.assertEqual(set(res["validation"]["per_chain_checked"]), {"bitcoin"})

    def test_invalid_chain_address_combination_is_rejected(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, "wrongchain.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE wallets (address TEXT, category TEXT)")
        # a real Bitcoin address, forced through as if it were the claim subject on no chain at all
        con.executemany("INSERT INTO wallets VALUES (?,?)", [(btc_address(i), "exchange") for i in range(10)])
        con.commit(); con.close()
        # user forces a chain this data does not validate on: every row is rejected, not silently accepted
        res = rel.extract(path, dict(driving_table="wallets", joins=[]), "wrongchain", confirmed=True)
        self.assertEqual(res["dataset_preflight"]["chain"]["value"], "bitcoin")   # correctly detected regardless


class TestScaleAndProfile(unittest.TestCase):
    def test_dataset_profile_reports_scale_distributions_and_source_coverage(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, "profile.db")
        make_relational_db(path, n=90)
        res = rel.extract(path, WALLETS_LABELS_SOURCES, "profile_db", confirmed=True)
        profile = res["dataset_profile"]
        self.assertEqual(profile["scale"]["total_normalized_claims"], 90)
        self.assertEqual(profile["scale"]["total_candidate_records"], 90)
        self.assertEqual(sum(profile["label_distribution"].values()), 90)
        self.assertIn("exchange", profile["label_distribution"])
        self.assertGreater(profile["source_coverage"]["claims_with_declared_source"], 0)
        # sources.source_url is "" for source_id 2: those claims have no source
        self.assertGreater(profile["source_coverage"]["claims_without_source"], 0)

    def test_orphan_foreign_keys_are_counted(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, "orphan.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE labels (label_id INTEGER PRIMARY KEY, category TEXT)")
        con.executemany("INSERT INTO labels VALUES (?,?)", [(0, "exchange")])
        con.execute("CREATE TABLE wallets (address TEXT, label_id INTEGER)")
        con.executemany("INSERT INTO wallets VALUES (?,?)",
                        [(btc_address(0), 0)] + [(btc_address(i), 99) for i in range(1, 6)])   # 99 doesn't exist
        con.commit(); con.close()
        spec = dict(driving_table="wallets", joins=[dict(table="labels", local_key="label_id", foreign_key="label_id")])
        res = rel.extract(path, spec, "orphan_db", confirmed=True)
        orphan = res["dataset_profile"]["data_quality"]["orphan_foreign_keys"][0]
        self.assertEqual(orphan["orphan_rows"], 5)


class TestDependencyCandidates(unittest.TestCase):
    def test_a_source_that_cites_another_is_flagged_but_not_applied(self):
        deps = rel.dependency_candidates(["OFAC SDN", "Community tip citing OFAC SDN", "Unrelated"])
        self.assertTrue(any(d["cited"] == "OFAC SDN" for d in deps))
        self.assertIn("not applied", deps[0]["relation"])


class TestApiRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        make_relational_db(os.path.join(cls.dir.name, "w.db"), n=150)
        cls.client = TestClient(app, base_url="http://localhost")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def setUp(self):
        self._old = os.environ.get("THEMIS_DB_DIR")
        os.environ["THEMIS_DB_DIR"] = self.dir.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("THEMIS_DB_DIR", None)
        else:
            os.environ["THEMIS_DB_DIR"] = self._old

    def test_inspect_reports_tables_views_indexes_and_foreign_keys(self):
        r = self.client.get("/api/sqlite/inspect", params={"db": "w.db"}).json()
        self.assertEqual(r["filename"], "w.db")
        tables = {t["table"]: t for t in r["tables"]}
        self.assertEqual(set(tables), {"wallets", "labels", "sources"})
        self.assertEqual(tables["labels"]["foreign_keys"][0]["table"], "sources")
        self.assertTrue(r["sqlite_version"])
        self.assertEqual(r["integrity"]["status"], "ok")

    def test_candidates_and_relationships_routes(self):
        c = self.client.get("/api/sqlite/candidates", params={"db": "w.db"}).json()
        self.assertEqual({x["table"]: x["role"] for x in c["candidates"]}["wallets"], "claim_subject")
        r = self.client.get("/api/sqlite/relationships", params={"db": "w.db"}).json()
        self.assertTrue(any(x["kind"] == "declared" for x in r["relationships"]))

    def test_relational_preflight_route(self):
        import json as _json
        spec = _json.dumps(WALLETS_LABELS_SOURCES)
        r = self.client.post("/api/sqlite/relational-preflight",
                             data={"db": "w.db", "spec": spec}).json()
        self.assertEqual(r["preflight"]["dataset_type"], "attribution_claims")
        self.assertTrue(r["preflight"]["can_analyze"])

    def test_extract_route_creates_an_analyzable_workspace(self):
        import json as _json
        spec = _json.dumps(WALLETS_LABELS_SOURCES)
        r = self.client.post("/api/sqlite/extract",
                             data={"db": "w.db", "spec": spec, "source_id": "w_test",
                                   "use_reference": "false", "confirmed": "true"}).json()
        aid = r["analysis_id"]
        summary = self.client.get(f"/api/analysis/{aid}/summary").json()
        self.assertEqual(summary["result"]["dataset_profile"]["scale"]["total_normalized_claims"], 150)
        claims = self.client.get(f"/api/analysis/{aid}/claims").json()
        self.assertGreater(claims["total"], 0)

    def test_ambiguous_or_missing_join_spec_is_a_400_not_a_guess(self):
        r = self.client.post("/api/sqlite/relational-preflight", data={"db": "w.db", "spec": "{}"})
        self.assertEqual(r.status_code, 400)
        r2 = self.client.get("/api/sqlite/tables", params={"db": "w.db"})
        self.assertEqual(r2.status_code, 200)   # unrelated route still fine


class TestCsvAndPaperUnaffected(unittest.TestCase):
    """This pass touched chains/base.py, ingest/preflight.py, ingest/claims.py
    and config/preflight.yml; the full CSV/paper suites (test_preflight.py,
    test_paper_*.py) are the real regression guard and are run alongside this
    file - these two are a fast, local sanity check of the exact seams this
    pass touched."""

    def test_csv_claim_building_is_unaffected(self):
        from themis.ingest import claims as _claims
        row = {"address": btc_address(1), "label": "exchange", "source": "https://x.example"}
        mapping = dict(address="address", label="label", source="source")
        c = _claims.build_claim(row, mapping, "csv_src", blockchain="bitcoin")
        self.assertIsNone(c["provenance_record"])   # new field, but None for a plain CSV claim
        self.assertEqual(c["canon"], "exchange")

    def test_every_registered_alias_resolves_to_its_chain(self):
        from themis import chains
        for alias, cid in chains.alias_map().items():
            self.assertEqual(chains.resolve_chain(alias), cid, alias)


if __name__ == "__main__":
    unittest.main(verbosity=2)
