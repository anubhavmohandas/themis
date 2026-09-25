"""The row guard (config/api.yml upload.max_rows): THEMIS holds a dataset in memory, so an upload with
more LOGICAL rows than the configured limit is refused outright: a stable client error, no partial
analysis, no scientific result, and a service that stays healthy.

  * the limit counts CSV records as the parser yields them, never physical lines
  * exactly `max_rows` rows is accepted, one more is refused
  * a refused file is not read to the end and creates no workspace and no job result
"""
import gzip, pathlib, sys, tempfile, time, unittest, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
import themis.api as api
from themis import config_io
from themis.errors import InputError, RowLimitError
from themis.ingest import pipeline
from test_preflight import btc_address

client = TestClient(api.app, base_url="http://localhost")
LIMIT = 5
ROUTES = ("/api/preflight", "/api/analysis", "/api/jobs/analysis")


def csv_bytes(n: int, label=lambda i: "exchange") -> bytes:
    return ("wallet_address,category\n" + "".join(f"{btc_address(i)},{label(i)}\n" for i in range(n))).encode()


def load(data: bytes, max_rows, suffix=".csv"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return pipeline.load_csv(path, max_rows)
    finally:
        os.remove(path)


class TestConfig(unittest.TestCase):
    def test_the_default_is_a_positive_integer_read_from_config(self):
        n = config_io.load().api["upload"]["max_rows"]
        self.assertIsInstance(n, int)
        self.assertGreater(n, 0)
        self.assertEqual(api._MAX_ROWS, n)

    def test_the_default_is_conservative_for_an_in_memory_service(self):
        # ~2.5 KB of RAM per row was measured at scale: the default must stay within a few GB
        self.assertLessEqual(config_io.load().api["upload"]["max_rows"], 2_000_000)


class TestLoadCsvBoundary(unittest.TestCase):
    def test_exactly_the_limit_is_accepted_and_one_more_is_refused(self):
        rows, _ = load(csv_bytes(LIMIT), LIMIT)
        self.assertEqual(len(rows), LIMIT)
        with self.assertRaises(RowLimitError):
            load(csv_bytes(LIMIT + 1), LIMIT)

    def test_the_refusal_is_an_input_error_with_a_message_for_the_client(self):
        with self.assertRaises(InputError) as cm:
            load(csv_bytes(LIMIT + 1), LIMIT)
        self.assertIn(f"{LIMIT:,} rows", str(cm.exception))
        self.assertIn("Nothing was analysed", str(cm.exception))

    def test_no_limit_means_no_guard(self):
        self.assertEqual(len(load(csv_bytes(50), None)[0]), 50)

    def test_a_quoted_newline_is_one_logical_row_not_two(self):
        # LIMIT logical rows, every one spanning three physical lines: a line count would refuse it
        data = csv_bytes(LIMIT, label=lambda i: '"exchange\nwith\nnewlines"')
        self.assertGreater(data.count(b"\n"), LIMIT * 3)
        rows, _ = load(data, LIMIT)
        self.assertEqual(len(rows), LIMIT)
        with self.assertRaises(RowLimitError):
            load(csv_bytes(LIMIT + 1, label=lambda i: '"exchange\nwith\nnewlines"'), LIMIT)

    def test_blank_lines_are_not_rows(self):
        rows, _ = load(csv_bytes(LIMIT) + b"\n" * 50, LIMIT)
        self.assertEqual(len(rows), LIMIT)

    def test_a_gzipped_file_is_counted_the_same_way(self):
        self.assertEqual(len(load(gzip.compress(csv_bytes(LIMIT)), LIMIT, ".csv.gz")[0]), LIMIT)
        with self.assertRaises(RowLimitError):
            load(gzip.compress(csv_bytes(LIMIT + 1)), LIMIT, ".csv.gz")

    def test_the_read_stops_at_the_first_row_over_the_limit(self):
        # a refused file is not parsed to the end: rows are never accumulated past the limit
        seen = []
        real = pipeline.csv.DictReader

        class Counting(real):
            def __next__(self):
                row = super().__next__()
                seen.append(row)
                return row
        pipeline.csv.DictReader = Counting
        try:
            with self.assertRaises(RowLimitError):
                load(csv_bytes(1000), LIMIT)
        finally:
            pipeline.csv.DictReader = real
        self.assertEqual(len(seen), LIMIT + 1)


class TestApiRowGuard(unittest.TestCase):
    def setUp(self):
        self._saved, api._MAX_ROWS = api._MAX_ROWS, LIMIT

    def tearDown(self):
        api._MAX_ROWS = self._saved

    def post(self, path, data):
        return client.post(path, files={"file": ("a.csv", data, "text/csv")}, data={"use_reference": "false"})

    def n_analyses(self):
        return len(client.get("/api/analysis").json())

    def wait(self, job_id):
        for _ in range(500):
            j = client.get(f"/api/jobs/{job_id}").json()
            if j["status"] != "running":
                return j
            time.sleep(0.02)
        self.fail("job did not finish")

    def test_exactly_the_limit_is_analysed(self):
        for path in ROUTES:
            self.assertEqual(self.post(path, csv_bytes(LIMIT)).status_code, 200, path)

    def test_over_the_limit_is_refused_with_a_stable_error_and_no_result(self):
        before = self.n_analyses()
        for path in ("/api/preflight", "/api/analysis"):
            r = self.post(path, csv_bytes(LIMIT + 1))
            self.assertEqual(r.status_code, 413, path)
            self.assertEqual(r.json()["detail"].startswith(f"The file has more than {LIMIT:,} rows"), True, path)
            self.assertNotIn("Traceback", r.text)
            self.assertNotIn("claims", r.json())
            self.assertNotIn("preflight", r.json())
        self.assertEqual(self.n_analyses(), before)

    def test_a_background_job_over_the_limit_fails_cleanly_without_a_result(self):
        job = self.post("/api/jobs/analysis", csv_bytes(LIMIT + 1)).json()
        j = self.wait(job["job_id"])
        self.assertEqual(j["status"], "failed")
        self.assertIn("rows", j["error"])
        self.assertIsNone(j["analysis_id"])
        self.assertIsNone(j["preflight"])

    def test_the_service_stays_healthy_and_serves_the_next_file(self):
        self.post("/api/analysis", csv_bytes(LIMIT + 1))
        self.assertEqual(client.get("/api/health").json()["status"], "ok")
        self.assertEqual(self.post("/api/analysis", csv_bytes(LIMIT)).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
