"""SQLite inputs: inspected read-only through metadata and read in bounded chunks,
never loaded whole. Analysis of a whole table is not implemented, and the
pre-flight says so as a blocker rather than pretending."""
import os, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis.api import app
from themis.ingest import preflight, sqlite_source as sq
from test_preflight import btc_address


def make_db(path, n=300):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wallets (address TEXT, category TEXT, updated_at TEXT)")
    con.executemany("INSERT INTO wallets VALUES (?,?,?)",
                    [(btc_address(i), ["exchange", "mixer", "ransomware"][i % 3], f"2025-0{1 + i % 9}-10") for i in range(n)])
    con.execute("CREATE TABLE prices (open_time TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume REAL)")
    con.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?)",
                    [(f"2020-01-{1 + i % 28:02d} 00:00:00", 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 5.0 + i) for i in range(n)])
    con.execute("CREATE TABLE nokey (a TEXT, b TEXT, PRIMARY KEY (a)) WITHOUT ROWID")
    con.executemany("INSERT INTO nokey VALUES (?,?)", [(f"k{i}", "v") for i in range(40)])
    con.commit()
    con.close()


class TestSqliteSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "WalletClassification.db")
        make_db(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def wallet_rows(self):
        return {x["table"]: x for x in sq.list_tables(self.db)}["wallets"]["n_rows"]

    def test_extensions(self):
        for n in ("a.db", "a.sqlite", "a.SQLITE3"):
            self.assertTrue(sq.is_sqlite_path(n))
        self.assertFalse(sq.is_sqlite_path("a.csv"))

    def test_tables_with_row_counts_and_columns(self):
        t = {x["table"]: x for x in sq.list_tables(self.db)}
        self.assertEqual((t["wallets"]["n_rows"], t["wallets"]["n_columns"]), (300, 3))
        self.assertEqual(t["wallets"]["row_count_status"], "exact")
        self.assertEqual([c["name"] for c in sq.columns(self.db, "wallets")], ["address", "category", "updated_at"])
        self.assertIsNone(sq.list_tables(self.db, count=False)[0]["n_rows"])

    def test_opened_read_only(self):
        with sq.open_readonly(self.db) as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("DELETE FROM wallets")
        self.assertEqual(self.wallet_rows(), 300)                      # untouched
        self.assertFalse(os.path.exists(self.db + "-journal"))

    def test_a_table_name_is_only_used_after_it_is_found_in_the_catalogue(self):
        for hostile in ('wallets; DROP TABLE wallets', 'wallets" --', "nope"):
            with self.assertRaises(ValueError):
                sq.columns(self.db, hostile)
            with self.assertRaises(ValueError):
                sq.sample_rows(self.db, hostile, 5)
        self.assertEqual(self.wallet_rows(), 300)

    def test_sample_is_spread_across_the_table_not_just_its_head(self):
        rows, names = sq.sample_rows(self.db, "wallets", 50)
        self.assertEqual(names, ["address", "category", "updated_at"])
        self.assertEqual(len(rows), 50)
        head = {btc_address(i) for i in range(50)}
        self.assertGreater(len({r["address"] for r in rows} - head), 20)
        rows2, _ = sq.sample_rows(self.db, "nokey", 10)            # WITHOUT ROWID falls back to the head
        self.assertEqual(len(rows2), 10)

    def test_iter_rows_streams_bounded_chunks_covering_the_whole_table(self):
        sizes = [len(c) for c in sq.iter_rows(self.db, "wallets", chunk_rows=64)]
        self.assertEqual(sizes, [64, 64, 64, 64, 44])
        self.assertEqual(sum(sizes), 300)

    def test_wallet_table_preflights_on_its_sample_and_analysis_is_now_supported(self):
        # SQLite streaming extraction exists (ingest/relational.py): a single
        # table is just a JoinSpec with no joins, so this dataset is no longer
        # blocked on "input type unsupported" the way it was before that
        # module existed.
        rows, names = sq.sample_rows(self.db, "wallets", 100)
        pf = preflight.run(rows, names, filename="WalletClassification.db", input_type="sqlite", table="wallets", total_rows=300)
        self.assertEqual(pf["dataset_type"], "attribution_claims")
        self.assertEqual(pf["chain"]["value"], "bitcoin")
        self.assertEqual(pf["input"]["n_rows"], 300)
        self.assertEqual(pf["input"]["n_rows_profiled"], 100)
        self.assertTrue(pf["can_analyze"])
        self.assertEqual(pf["blockers"], [])

    def test_price_table_is_refused_like_a_price_csv(self):
        rows, names = sq.sample_rows(self.db, "prices", 100)
        pf = preflight.run(rows, names, input_type="sqlite", table="prices")
        self.assertEqual(pf["dataset_type"], "market_timeseries")
        self.assertEqual(pf["status"], "unsupported")


class TestSqliteApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        make_db(os.path.join(cls.dir.name, "w.db"))
        pathlib.Path(cls.dir.name, "notes.txt").write_text("x")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def setUp(self):
        self._old = os.environ.get("THEMIS_DB_DIR")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("THEMIS_DB_DIR", None)
        else:
            os.environ["THEMIS_DB_DIR"] = self._old

    def test_disabled_until_a_database_directory_is_configured(self):
        os.environ.pop("THEMIS_DB_DIR", None)
        self.assertEqual(self.client.get("/api/sqlite/tables", params={"db": "w.db"}).status_code, 409)

    def test_lists_tables_columns_and_preflights_a_table(self):
        os.environ["THEMIS_DB_DIR"] = self.dir.name
        t = self.client.get("/api/sqlite/tables", params={"db": "w.db"}).json()
        self.assertEqual({x["table"]: x["n_rows"] for x in t["tables"]}["wallets"], 300)
        c = self.client.get("/api/sqlite/columns", params={"db": "w.db", "table": "wallets"}).json()
        self.assertEqual(c["columns"][0]["name"], "address")
        p = self.client.post("/api/sqlite/preflight", data={"db": "w.db", "table": "wallets"}).json()
        self.assertEqual(p["preflight"]["input"]["type"], "sqlite")
        self.assertEqual(p["preflight"]["dataset_type"], "attribution_claims")
        self.assertTrue(p["preflight"]["can_analyze"])
        self.assertEqual(self.client.get("/api/sqlite/columns", params={"db": "w.db", "table": "zzz"}).status_code, 400)

    def test_paths_outside_the_directory_or_of_other_types_are_refused(self):
        os.environ["THEMIS_DB_DIR"] = self.dir.name
        for db in ("../w.db", "/etc/passwd", "notes.txt", "..%2fw.db"):
            self.assertIn(self.client.get("/api/sqlite/tables", params={"db": db}).status_code, (400, 404), db)

    def test_a_truncated_or_corrupt_database_is_a_clear_error_not_a_crash(self):
        # a valid SQLite header followed by nothing usable, as an interrupted download leaves it
        good = pathlib.Path(self.dir.name, "w.db").read_bytes()
        pathlib.Path(self.dir.name, "partial.db").write_bytes(good[:100] + b"\x00" * 4096)
        os.environ["THEMIS_DB_DIR"] = self.dir.name
        r = self.client.get("/api/sqlite/tables", params={"db": "partial.db"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("not a readable SQLite database", r.json()["detail"])

    def test_a_database_is_not_accepted_as_an_upload(self):
        r = self.client.post("/api/preflight", files={"file": ("w.db", b"SQLite format 3\x00", "application/octet-stream")})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
