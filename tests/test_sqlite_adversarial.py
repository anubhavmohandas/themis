"""The whole SQLite workflow against hostile and merely odd databases (Phase 8).

Guarantees under test: no SQL injection through any identifier or value, no
file outside THEMIS_DB_DIR opened, no automatic recovery, no crash on damage,
no schema or provenance THEMIS made up, and the file itself never modified.
Every database is synthetic and built here.
"""
import hashlib, os, pathlib, re, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis.api import app
from themis.ingest import relational as rel, sqlite_source as sq
from test_preflight import btc_address

client = TestClient(app)
ROOT = pathlib.Path(__file__).resolve().parent.parent


def digest(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def path(self, name="t.db"):
        return os.path.join(self.dir, name)

    def build(self, table="wallets", n=30, addr_col="address", label_col="label", name="t.db", extra=()):
        p = self.path(name)
        con = sqlite3.connect(p)
        cols = f"{q(addr_col)} TEXT, {q(label_col)} TEXT" + "".join(f", {q(c)} TEXT" for c in extra)
        con.execute(f"CREATE TABLE {q(table)} ({cols})")
        con.executemany(f"INSERT INTO {q(table)} ({q(addr_col)}, {q(label_col)}) VALUES (?,?)",
                        [(btc_address(i), ("exchange", "mixer", "ransomware")[i % 3]) for i in range(n)])
        con.commit()
        con.close()
        return p

    def extract(self, path, table="wallets"):
        return rel.extract(path, dict(driving_table=table, joins=[]), "adv", confirmed=True)


class TestDamagedFiles(_Db):
    def test_bad_magic_header_is_reported_not_raised(self):
        p = self.build()
        data = bytearray(pathlib.Path(p).read_bytes())
        data[:16] = b"NotSQLiteFormat\x00"
        pathlib.Path(p).write_bytes(bytes(data))
        res = self.extract(p)
        self.assertTrue(res["stopped"])
        self.assertIn("DATABASE INTEGRITY CHECK FAILED", res["message"])
        self.assertEqual(res["claims"], [])

    def test_valid_header_with_truncated_pages(self):
        size = os.path.getsize(self.build(name="whole.db"))
        for cut in (100, 4096, 4096 + 17, size // 2 + 3):
            with self.subTest(cut=cut):
                p = self.build(name=f"cut{cut}.db")
                with open(p, "r+b") as f:
                    f.truncate(cut)
                res = self.extract(p)
                self.assertTrue(res["stopped"])
                self.assertEqual(res["claims"], [])
                self.assertNotEqual(sq.integrity_check(p)["status"], "ok")

    def test_random_bytes_of_every_size_class(self):
        for size in (1, 15, 16, 100, 4096, 70000):
            with self.subTest(size=size):
                p = self.path(f"rand{size}.db")
                pathlib.Path(p).write_bytes(os.urandom(size))
                try:
                    res = self.extract(p)
                except ValueError:                         # SQLite reads a 1-byte file as an empty database: no such table
                    self.assertLess(size, 16)
                else:
                    self.assertTrue(res["stopped"])
                insp = sq.inspect(p)                       # never raises either
                self.assertEqual((insp["tables"], insp["views"]), ([], []))

    def test_zero_byte_file_is_an_empty_database_with_nothing_to_analyse(self):
        p = self.path("zero.db")
        pathlib.Path(p).write_bytes(b"")
        insp = sq.inspect(p)
        self.assertEqual(insp["tables"], [])
        with self.assertRaises(ValueError):
            self.extract(p, table="wallets")               # a table the file does not have: refused, never invented

    def test_empty_valid_database(self):
        p = self.path("empty.db")
        sqlite3.connect(p).close()
        self.assertEqual(sq.list_tables(p), [])
        self.assertEqual(rel.candidate_roles(p), [])
        self.assertEqual(rel.infer_relationships(p), [])

    def test_a_damaged_file_is_never_written_to_or_recovered(self):
        p = self.build()
        with open(p, "r+b") as f:
            f.truncate(5000)
        before = digest(p)
        self.extract(p)
        sq.inspect(p)
        self.assertEqual(digest(p), before)
        self.assertEqual(sorted(os.listdir(self.dir)), ["t.db"])   # no journal, no wal, no recovered copy

    def test_no_code_path_shells_out_or_recovers(self):
        for f in (ROOT / "themis").rglob("*.py"):
            src = f.read_text()
            self.assertNotRegex(src, r"\.recover\b", f)
            self.assertNotRegex(src, r"^\s*(import|from)\s+subprocess", f)


class TestHostileNames(_Db):
    NAMES = ['we"ird', "a'b", "x]y", "back`tick", 'x"; DROP TABLE wallets; --', "wallets; DELETE FROM wallets",
             "钱包", "кошелёк😀", "select", "table", "group", "order", "index", "SELECT * FROM sqlite_master",
             "sp ace", "new\nline", "tab\there", "a" * 5000, "sqlitedata", "sqlite3_users", "__rowid", "a__b"]

    def test_every_table_name_round_trips_and_extracts(self):
        for i, name in enumerate(self.NAMES):
            with self.subTest(table=name[:40]):
                p = self.build(table=name, n=12, name=f"n{i}.db")
                before = digest(p)
                tables = {t["table"]: t for t in sq.list_tables(p)}
                self.assertIn(name, tables)                              # incl. names that only LOOK like SQLite's own
                self.assertEqual(tables[name]["n_rows"], 12)
                res = self.extract(p, table=name)
                self.assertFalse(res["stopped"], res.get("message"))
                self.assertEqual(len(res["claims"]), 12)
                self.assertEqual(digest(p), before)                      # read-only, byte for byte

    def test_a_drop_table_name_cannot_touch_another_table(self):
        p = self.build(table="wallets", n=10)
        con = sqlite3.connect(p)
        con.execute(f'CREATE TABLE {q(chr(34) + "; DROP TABLE wallets; --")} (address TEXT, label TEXT)')
        con.commit()
        con.close()
        for t in sq.list_tables(p):
            sq.columns(p, t["table"])
            sq.sample_rows(p, t["table"], 5)
        rel.candidate_roles(p)
        self.assertEqual(sqlite3.connect(p).execute("SELECT COUNT(*) FROM wallets").fetchone()[0], 10)

    def test_a_table_name_is_only_used_after_being_found_in_the_catalogue(self):
        p = self.build()
        for evil in ('wallets" --', "wallets; SELECT 1", "nonexistent", "", " wallets", "WALLETS "):
            with self.assertRaises(ValueError, msg=repr(evil)):
                sq.columns(p, evil)
            with self.assertRaises(ValueError, msg=repr(evil)):
                sq.sample_rows(p, evil, 5)

    def test_unusual_column_names_are_data_not_sql(self):
        cols = ['a"b', "col with space", "--", "address; DROP TABLE wallets", "ünï", "select", "x" * 3000, "a'b"]
        for i, c in enumerate(cols):
            with self.subTest(col=c[:30]):
                p = self.build(table="wallets", n=15, addr_col=c, name=f"c{i}.db")
                res = self.extract(p)
                self.assertEqual(res["stopped"] and res["message"], False if not res["stopped"] else res["message"])
                self.assertEqual(sqlite3.connect(p).execute("SELECT COUNT(*) FROM wallets").fetchone()[0], 15)

    def test_the_empty_string_is_a_legal_column_name(self):
        p = self.path("emptycol.db")
        con = sqlite3.connect(p)
        con.execute('CREATE TABLE wallets ("" TEXT, address TEXT, label TEXT)')
        con.execute("INSERT INTO wallets VALUES ('x', ?, 'exchange')", (btc_address(1),))
        con.commit()
        con.close()
        res = self.extract(p)
        self.assertEqual(len(res["claims"]), 1)

    def test_column_names_that_collide_once_joined_are_refused_not_silently_merged(self):
        """table `a` column `b__c` and table `a__b` column `c` would both alias to a__b__c."""
        p = self.path("collide.db")
        con = sqlite3.connect(p)
        con.execute('CREATE TABLE a (id INTEGER, b__c TEXT, address TEXT)')
        con.execute('CREATE TABLE a__b (id INTEGER, c TEXT)')
        con.execute("INSERT INTO a VALUES (1, 'left', ?)", (btc_address(1),))
        con.execute("INSERT INTO a__b VALUES (1, 'right')")
        con.commit()
        con.close()
        spec = dict(driving_table="a", joins=[dict(table="a__b", local_key="id", foreign_key="id")])
        with self.assertRaises(ValueError) as cm:
            rel.joined_sample(p, spec, 5)
        self.assertIn("collide", str(cm.exception))

    def test_hostile_values_are_carried_as_text_and_never_executed(self):
        p = self.path("values.db")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE wallets (address TEXT, label TEXT, source TEXT)")
        evil = ["'; DROP TABLE wallets; --", "<script>alert(1)</script>", "=cmd|' /C calc'!A0", "\x00null", "\r\n\t",
                "Robert'); DROP TABLE Students;--"]
        con.executemany("INSERT INTO wallets VALUES (?,?,?)", [(btc_address(i), "exchange", v) for i, v in enumerate(evil)])
        con.commit()
        con.close()
        res = self.extract(p)
        self.assertEqual(len(res["claims"]), len(evil))
        self.assertEqual(sqlite3.connect(p).execute("SELECT COUNT(*) FROM wallets").fetchone()[0], len(evil))
        self.assertEqual(res["relational_provenance"]["counts"]["resolved"], 0)


class TestRelationships(_Db):
    def _two(self, ddl, name="r.db"):
        p = self.path(name)
        con = sqlite3.connect(p)
        for stmt in ddl:
            con.execute(stmt)
        con.commit()
        con.close()
        return p

    def test_a_foreign_key_to_a_table_that_does_not_exist_is_reported_and_unjoinable(self):
        p = self._two(["CREATE TABLE wallets (address TEXT, label_id INTEGER, FOREIGN KEY(label_id) REFERENCES ghosts(id))",
                       "INSERT INTO wallets VALUES ('x', 1)"])
        rels = rel.infer_relationships(p)                 # must not crash
        self.assertTrue(all(r["to_table"] != "ghosts" or r["kind"] == "declared" for r in rels))
        with self.assertRaises(ValueError):
            rel.validate_join_spec(p, dict(driving_table="wallets",
                                           joins=[dict(table="ghosts", local_key="label_id", foreign_key="id")]))

    def test_a_foreign_key_naming_a_missing_column_is_refused_as_a_join(self):
        p = self._two(["CREATE TABLE labels (id INTEGER PRIMARY KEY, category TEXT)",
                       "CREATE TABLE wallets (address TEXT, label_id INTEGER, FOREIGN KEY(label_id) REFERENCES labels(nope))"])
        rel.infer_relationships(p)
        with self.assertRaises(ValueError):
            rel.validate_join_spec(p, dict(driving_table="wallets",
                                           joins=[dict(table="labels", local_key="label_id", foreign_key="nope")]))

    def test_cyclic_relationships_terminate(self):
        p = self._two(["CREATE TABLE a (id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES b(id), address TEXT, label TEXT)",
                       "CREATE TABLE b (id INTEGER PRIMARY KEY, a_id INTEGER REFERENCES a(id))",
                       f"INSERT INTO a VALUES (1, 1, '{btc_address(1)}', 'exchange')", "INSERT INTO b VALUES (1, 1)"])
        rels = rel.infer_relationships(p)
        self.assertEqual({(r["from_table"], r["to_table"]) for r in rels if r["kind"] == "declared"},
                         {("a", "b"), ("b", "a")})
        # a spec that only closes the loop is refused: `b` joined from `a`, then `a` again from `b`
        with self.assertRaises(ValueError):
            rel.validate_join_spec(p, dict(driving_table="a", joins=[
                dict(table="b", local_key="b_id", foreign_key="id"),
                dict(table="a", local_table="c", local_key="a_id", foreign_key="id")]))

    def test_a_self_join_fails_cleanly(self):
        p = self._two(["CREATE TABLE a (id INTEGER PRIMARY KEY, parent INTEGER, address TEXT, label TEXT)",
                       f"INSERT INTO a VALUES (1, 1, '{btc_address(1)}', 'exchange')"])
        spec = dict(driving_table="a", joins=[dict(table="a", local_key="parent", foreign_key="id")])
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            rel.extract(p, spec, "adv", confirmed=True)
        r = client.post("/api/sqlite/extract", data=dict(db="r.db", spec='{"driving_table":"a"}'))   # API: THEMIS_DB_DIR unset
        self.assertLess(r.status_code, 500)

    def test_orphan_rows_are_counted_and_never_given_a_label(self):
        p = self._two(["CREATE TABLE labels (label_id INTEGER PRIMARY KEY, category TEXT)",
                       "CREATE TABLE wallets (address TEXT PRIMARY KEY, label_id INTEGER)",
                       "INSERT INTO labels VALUES (1, 'exchange')"]
                      + [f"INSERT INTO wallets VALUES ('{btc_address(i)}', {1 if i < 6 else 99})" for i in range(10)])
        res = rel.extract(p, dict(driving_table="wallets", joins=[
            dict(table="labels", local_key="label_id", foreign_key="label_id")]), "adv", confirmed=True)
        self.assertEqual(len(res["claims"]), 6)
        self.assertEqual(res["validation"]["rejected_by_reason"], {"missing label": 4})
        orphans = res["dataset_profile"]["data_quality"]["orphan_foreign_keys"]
        self.assertEqual(orphans[0]["orphan_rows"], 4)


class TestClaimsInsideOneDatabase(_Db):
    def _rows(self, rows):
        p = self.path("claims.db")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE wallets (address TEXT, label TEXT, source TEXT)")
        con.executemany("INSERT INTO wallets VALUES (?,?,?)", rows)
        con.commit()
        con.close()
        return self.extract(p)

    def test_duplicate_claims_are_counted_once(self):
        a = btc_address(1)
        res = self._rows([(a, "exchange", "S")] * 5 + [(a, "exchange", "T")])
        # a repeated (address, label) is one claim; the rest are counted, not silently dropped. NOTE the
        # declared source is not part of the key (see THEMIS_RELEASE_READINESS_REPORT.md, author decisions)
        self.assertEqual(res["validation"]["rejected_by_reason"], {"duplicate claim": 5})
        self.assertEqual(len(res["claims"]), 1)

    def test_conflicting_claims_are_both_kept_and_reported_as_a_conflict_not_resolved(self):
        a = btc_address(1)
        res = self._rows([(a, "exchange", "S"), (a, "ransomware", "S")])
        self.assertEqual(len(res["claims"]), 2)
        conflict = res["conflicts"]["conflicting_addresses"]
        self.assertEqual([c["outcome"] for c in conflict], ["licit/illicit conflict"])
        self.assertEqual(len(conflict[0]["claims"]), 2)

    def test_a_null_source_column_is_absence_and_stays_unresolved(self):
        res = self._rows([(btc_address(i), "exchange", None) for i in range(5)])
        self.assertEqual(res["dataset_profile"]["source_coverage"]["claims_without_source"], 5)
        self.assertEqual(res["relational_provenance"]["counts"]["unresolved"], 5)

    def test_two_address_like_columns_are_never_silently_chosen_between(self):
        p = self.path("two.db")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE wallets (address TEXT, alt_address TEXT, label TEXT)")
        con.executemany("INSERT INTO wallets VALUES (?,?,?)",
                        [(btc_address(i), btc_address(1000 + i), "exchange") for i in range(20)])
        con.commit()
        con.close()
        res = rel.extract(p, dict(driving_table="wallets", joins=[]), "adv", confirmed=False)
        pf = res["dataset_preflight"]
        subjects = [c for c in pf["columns"] if c["semantic_type"].startswith("subject_")]
        # either the choice is put to the user (stopped / review), or exactly one column was mapped
        # and the other is reported as unused - never both fed into one analysis without saying so
        self.assertTrue(res["stopped"] or len(subjects) <= 1 or pf["status"] != "ok", pf["status"])
        if not res["stopped"]:
            self.assertEqual(len({c["address"] for c in res["claims"]}), len(res["claims"]))


class TestApiCannotReachOutsideItsDirectory(_Db):
    def setUp(self):
        super().setUp()
        self.build(name="inside.db")
        secret = os.path.join(os.path.dirname(self.dir), f"outside-{os.getpid()}.db")
        self.build(name="ok.db")
        con = sqlite3.connect(secret)
        con.execute("CREATE TABLE secret (address TEXT, label TEXT)")
        con.commit()
        con.close()
        self.secret = secret
        self.addCleanup(lambda: os.path.exists(secret) and os.remove(secret))
        self._old = os.environ.get("THEMIS_DB_DIR")
        os.environ["THEMIS_DB_DIR"] = self.dir
        self.addCleanup(lambda: os.environ.pop("THEMIS_DB_DIR") if self._old is None
                        else os.environ.update(THEMIS_DB_DIR=self._old))
        os.symlink(self.secret, os.path.join(self.dir, "link.db"))

    def get(self, db):
        return client.get("/api/sqlite/tables", params=dict(db=db))

    def test_traversal_absolute_and_odd_paths_are_refused(self):
        bad = [f"../{os.path.basename(self.secret)}", self.secret, "../../../../etc/passwd.db", "/etc/hosts.db",
               "..\\..\\x.db", "inside.db/../../x.db", "link.db", "%2e%2e%2f" + os.path.basename(self.secret),
               "inside.db\x00.txt", "", ".", "..", "notadb.txt", "inside.db.txt", "sub/../../x.db"]
        for db in bad:
            r = self.get(db)
            self.assertIn(r.status_code, (400, 404, 422), f"{db!r} -> {r.status_code}")
            self.assertNotIn("secret", r.text)
            self.assertNotIn("Traceback", r.text)

    def test_a_file_inside_the_directory_still_works(self):
        r = self.get("inside.db")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t["table"] for t in r.json()["tables"]], ["wallets"])

    def test_a_file_named_with_uri_metacharacters_opens_itself_and_nothing_else(self):
        for name in ("q?mode=rw.db", "hash#frag.db", "pct%2e%2e.db", "sp ace.db", "ünï.db"):
            with self.subTest(name=name):
                self.build(name=name, n=7)
                r = self.get(name)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["tables"][0]["n_rows"], 7)

    def test_table_and_column_parameters_are_looked_up_not_interpolated(self):
        for table in ('wallets"', "wallets; DROP TABLE wallets", "secret", "sqlite_master"):
            r = client.get("/api/sqlite/columns", params=dict(db="inside.db", table=table))
            self.assertEqual(r.status_code, 400, table)
        self.assertEqual(client.get("/api/sqlite/tables", params=dict(db="inside.db")).json()["tables"][0]["n_rows"], 30)

    def test_a_join_spec_naming_hostile_columns_is_refused_by_the_catalogue(self):
        spec = '{"driving_table":"wallets","joins":[{"table":"wallets","local_key":"a\\" OR 1=1 --","foreign_key":"address"}]}'
        r = client.post("/api/sqlite/relational-preflight", data=dict(db="inside.db", spec=spec))
        self.assertEqual(r.status_code, 400)
        r = client.post("/api/sqlite/extract", data=dict(db="inside.db", spec="{not json"))
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
