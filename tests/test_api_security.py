"""API security for THEMIS's local-use threat model (themis/config/api.yml):

  * CORS names the frontend's origins, never "*"; a state-changing request from
    any other browser origin is refused outright, not just left unreadable
  * every uploaded-file route enforces one config-driven size limit WHILE READING
    (Content-Length may be absent, low or high, and a .gz may expand)
  * a client never sees an internal exception: no path, SQL or library text -
    the server log keeps the diagnostic
  * the claims table pages deterministically and never past its cap
"""
import gzip, io, logging, os, pathlib, sys, tempfile, unittest, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
import themis.api as api
from themis import config_io, workspace
from test_preflight import btc_address, to_csv

client = TestClient(api.app)
quiet = TestClient(api.app, raise_server_exceptions=False)   # what a browser sees on a 500

ALLOWED = "http://localhost:5173"
BTC_CSV = (b"wallet_address,entity_type\n"
           b"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2,ransomware\n"
           b"3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy,exchange\n"
           b"1LLEoSTzRmSL3xC5AWhsn9QjpGFh4Wx72N,ransomware\n")


def n_analyses() -> int:
    return len(client.get("/api/analysis").json())


def upload(path: str, data: bytes, name="btc.csv", **kw):
    return client.post(path, files={"file": (name, data, "application/octet-stream")},
                       data={"use_reference": "false"}, **kw)


class TestCors(unittest.TestCase):
    def test_config_names_local_frontend_origins_and_never_a_wildcard(self):
        origins = config_io.load().api["cors"]["allowed_origins"]
        self.assertTrue(origins)
        self.assertNotIn("*", origins)
        for o in origins:
            self.assertRegex(o, r"^http://(localhost|127\.0\.0\.1):\d+$")

    def test_allowed_origin_gets_cors_permission(self):
        r = client.get("/api/health", headers={"Origin": ALLOWED})
        self.assertEqual(r.headers.get("access-control-allow-origin"), ALLOWED)

    def test_unknown_origin_gets_no_cors_permission(self):
        for evil in ("https://evil.example", "http://localhost:9999", "null", "http://localhost:5173.evil.example"):
            r = client.get("/api/health", headers={"Origin": evil})
            self.assertEqual(r.status_code, 200)           # a read is still served to a non-browser client...
            self.assertNotIn("access-control-allow-origin", r.headers, evil)   # ...but a browser may not read it

    def test_no_origin_header_is_ordinary_local_api_use(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("access-control-allow-origin", r.headers)
        self.assertEqual(upload("/api/preflight", BTC_CSV).status_code, 200)

    def test_preflight_request_is_answered_only_for_an_allowed_origin(self):
        ask = {"Access-Control-Request-Method": "POST"}
        ok = client.options("/api/analysis", headers={"Origin": ALLOWED, **ask})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers["access-control-allow-origin"], ALLOWED)
        bad = client.options("/api/analysis", headers={"Origin": "https://evil.example", **ask})
        self.assertNotIn("access-control-allow-origin", bad.headers)
        self.assertGreaterEqual(bad.status_code, 400)

    def test_a_blind_cross_origin_upload_is_refused_and_creates_nothing(self):
        before = n_analyses()
        for path in ("/api/analysis", "/api/jobs/analysis", "/api/preflight"):
            r = upload(path, BTC_CSV, headers={"Origin": "https://evil.example"})
            self.assertEqual(r.status_code, 403, path)
        self.assertEqual(n_analyses(), before)

    def test_an_allowed_origin_may_write(self):
        self.assertEqual(upload("/api/preflight", BTC_CSV, headers={"Origin": ALLOWED}).status_code, 200)


class _SmallLimit(unittest.TestCase):
    """Runs the real guard against a tiny limit (a test cannot upload 256 MiB)."""
    LIMIT, OVERHEAD = 400, 3000

    def setUp(self):
        self._saved = (api._MAX_UPLOAD, api._MAX_BODY)
        api._MAX_UPLOAD, api._MAX_BODY = self.LIMIT, self.LIMIT + self.OVERHEAD

    def tearDown(self):
        api._MAX_UPLOAD, api._MAX_BODY = self._saved

    def padded(self, size: int) -> bytes:
        """A valid CSV of exactly `size` bytes (trailing blank lines are ignored by the parser)."""
        assert size >= len(BTC_CSV)
        return BTC_CSV + b"\n" * (size - len(BTC_CSV))


ROUTES = ("/api/preflight", "/api/analysis", "/api/jobs/analysis")


class TestUploadLimit(_SmallLimit):
    def assertRejectedCleanly(self, r, path):
        self.assertEqual(r.status_code, 413, f"{path}: {r.text[:200]}")
        self.assertNotIn("Traceback", r.text)
        self.assertIn("limit", r.json()["detail"])

    def test_config_limit_is_positive_and_bounds_the_body(self):
        cfg = config_io.load().api["upload"]
        self.assertGreater(cfg["max_bytes"], 0)
        self.assertGreater(cfg["multipart_overhead_bytes"], 0)

    def test_small_valid_file_is_accepted_on_every_route(self):
        for path in ROUTES:
            self.assertEqual(upload(path, BTC_CSV).status_code, 200, path)

    def test_zero_byte_file_is_a_clean_answer_not_a_crash(self):
        for path in ROUTES:
            r = quiet.post(path, files={"file": ("empty.csv", b"", "text/csv")}, data={"use_reference": "false"})
            self.assertLess(r.status_code, 500, path)
            self.assertNotIn("Traceback", r.text)

    def test_exactly_at_the_limit_is_accepted(self):
        for path in ROUTES:
            self.assertEqual(upload(path, self.padded(self.LIMIT)).status_code, 200, path)

    def test_one_byte_over_the_limit_is_refused_and_creates_nothing(self):
        jobs_before, analyses_before = len(api._jobs), n_analyses()
        for path in ROUTES:
            self.assertRejectedCleanly(upload(path, self.padded(self.LIMIT + 1)), path)
        self.assertEqual(n_analyses(), analyses_before)
        self.assertEqual(len(api._jobs), jobs_before)

    def test_far_over_the_limit_is_refused_while_reading(self):
        """Larger than limit + multipart allowance: the wire guard fires, before the file is parsed."""
        for path in ROUTES:
            self.assertRejectedCleanly(upload(path, b"x" * (self.LIMIT + self.OVERHEAD + 500)), path)

    def _raw(self, path, body: bytes, headers: dict):
        boundary = "b" + uuid.uuid4().hex
        pre = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
               "Content-Type: text/csv\r\n\r\n").encode()
        post = f"\r\n--{boundary}--\r\n".encode()
        h = {"content-type": f"multipart/form-data; boundary={boundary}", **headers}
        return pre + body + post, h

    def test_missing_content_length_is_still_bounded(self):
        for path in ROUTES:
            payload, h = self._raw(path, self.padded(self.LIMIT + 1), {})
            chunks = (payload[i:i + 100] for i in range(0, len(payload), 100))   # chunked: no Content-Length
            r = client.post(path, content=chunks, headers=h)
            self.assertRejectedCleanly(r, path)

    def test_missing_content_length_and_a_body_far_past_the_limit(self):
        """Only the wire guard can catch this one: the file is never small enough to parse."""
        for path in ROUTES:
            payload, h = self._raw(path, b"z" * (self.LIMIT + self.OVERHEAD + 500), {})
            chunks = (payload[i:i + 100] for i in range(0, len(payload), 100))
            self.assertRejectedCleanly(client.post(path, content=chunks, headers=h), path)

    def test_an_endless_body_is_cut_off_after_the_limit_not_consumed(self):
        """No Content-Length and a body that never ends: the server must stop READING at the
        limit (bounded memory/disk), not merely refuse once it has swallowed everything."""
        import asyncio
        chunk, seen, sent = b"x" * 1000, [0], []
        head = (b'--zzz\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
                b"Content-Type: text/csv\r\n\r\n")          # a valid start, then file bytes forever

        async def receive():
            body = head + chunk if not seen[0] else chunk
            seen[0] += len(body)
            if seen[0] > 100 * (self.LIMIT + self.OVERHEAD):          # a runaway reader would end up here
                return dict(type="http.disconnect")
            return dict(type="http.request", body=body, more_body=True)

        async def send(m):
            sent.append(m)
        scope = dict(type="http", method="POST", path="/api/analysis", raw_path=b"/api/analysis", query_string=b"",
                     headers=[(b"content-type", b"multipart/form-data; boundary=zzz")], http_version="1.1",
                     scheme="http", server=("t", 80), client=("c", 1), root_path="")
        asyncio.run(api.app(scope, receive, send))
        self.assertEqual(sent[0]["status"], 413)
        self.assertLessEqual(seen[0], api._MAX_BODY + 2 * len(chunk))

    def test_missing_content_length_but_within_limit_is_accepted(self):
        payload, h = self._raw("/api/preflight", BTC_CSV, {})
        r = client.post("/api/preflight", content=(payload[i:i + 100] for i in range(0, len(payload), 100)), headers=h)
        self.assertEqual(r.status_code, 200, r.text[:200])

    def test_false_low_content_length_cannot_smuggle_a_big_body(self):
        for path in ROUTES:
            payload, h = self._raw(path, b"y" * (self.LIMIT + self.OVERHEAD + 500), {"content-length": "10"})
            self.assertRejectedCleanly(client.post(path, content=payload, headers=h), path)

    def test_false_high_content_length_is_refused_up_front(self):
        for path in ROUTES:
            payload, h = self._raw(path, BTC_CSV, {"content-length": str(10 ** 12)})
            self.assertRejectedCleanly(client.post(path, content=payload, headers=h), path)

    def test_a_non_numeric_content_length_does_not_crash_the_guard(self):
        payload, h = self._raw("/api/preflight", BTC_CSV, {"content-length": "abc"})
        r = quiet.post("/api/preflight", content=payload, headers=h)
        self.assertLess(r.status_code, 500)

    def test_malformed_oversized_content_is_refused_not_parsed(self):
        for path in ROUTES:
            for ctype in ("multipart/form-data; boundary=zzz", "multipart/form-data", "application/json", "text/plain"):
                r = client.post(path, content=os.urandom(self.LIMIT + self.OVERHEAD + 1000),
                                headers={"content-type": ctype})
                self.assertRejectedCleanly(r, f"{path} [{ctype}]")

    def test_a_gzip_that_expands_past_the_limit_is_refused(self):
        api._MAX_UPLOAD, api._MAX_BODY = 50_000, 50_000 + self.OVERHEAD    # the archive fits; its content does not
        bomb = gzip.compress(b"a,b\n" + b"0" * 5_000_000)          # ~5 KB on the wire, 5 MB expanded
        self.assertLess(len(bomb), api._MAX_UPLOAD)
        for path in ROUTES:
            r = upload(path, bomb, name="bomb.csv.gz")
            self.assertEqual(r.status_code, 413, path)
            self.assertIn("decompresses", r.json()["detail"])

    def test_a_small_valid_gzip_is_accepted(self):
        small = gzip.compress(BTC_CSV)
        self.assertEqual(upload("/api/preflight", small, name="ok.csv.gz").status_code, 200)

    def test_a_file_that_is_not_a_gzip_is_a_client_error_not_a_500(self):
        for path in ROUTES:
            r = quiet.post(path, files={"file": ("fake.csv.gz", b"this is not gzip data", "text/csv")},
                           data={"use_reference": "false"})
            self.assertEqual(r.status_code, 400 if path != "/api/jobs/analysis" else 200, path)
            self.assertNotIn("Traceback", r.text)


class TestErrorDisclosure(unittest.TestCase):
    SECRET = "/Users/analyst/private/wallets.db: SELECT secret_col FROM t WHERE token='hunter2'"

    def _boom(self, *a, **k):
        raise RuntimeError(self.SECRET)

    def setUp(self):
        self._orig = api._ingest_pipeline.ingest
        api._ingest_pipeline.ingest = self._boom

    def tearDown(self):
        api._ingest_pipeline.ingest = self._orig

    def test_unexpected_failure_returns_the_generic_message_and_logs_the_cause(self):
        with self.assertLogs("themis.api", level="ERROR") as cap:
            r = quiet.post("/api/analysis", files={"file": ("a.csv", BTC_CSV, "text/csv")},
                           data={"use_reference": "false"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {"detail": api.GENERIC_ERROR})
        for leak in ("hunter2", "/Users", "SELECT", "RuntimeError", "Traceback"):
            self.assertNotIn(leak, r.text)
        logged = "\n".join(cap.output)
        self.assertIn("hunter2", logged)            # the server keeps the real diagnostic ...
        self.assertIn("RuntimeError", logged)       # ... including the exception type and traceback
        self.assertIn("Traceback", logged)

    def test_a_failed_background_job_reports_the_generic_message(self):
        with self.assertLogs("themis.api", level="ERROR") as cap:
            job = client.post("/api/jobs/analysis", files={"file": ("a.csv", BTC_CSV, "text/csv")},
                              data={"use_reference": "false"}).json()
            import time
            for _ in range(200):
                j = client.get(f"/api/jobs/{job['job_id']}").json()
                if j["status"] != "running":
                    break
                time.sleep(0.02)
        self.assertEqual(j["status"], "failed")
        self.assertEqual(j["error"], api.GENERIC_ERROR)
        self.assertNotIn("hunter2", str(j))
        self.assertIn("hunter2", "\n".join(cap.output))

    def test_a_failing_paper_task_reports_the_generic_message(self):
        ws = workspace.AnalysisWorkspace(analysis_id="paper-x", mode=workspace.MODE_PAPER, dataset_name="p",
                                         created_at="", analysis_as_of_date="2020-01-01", reference_corpus=object(),
                                         result={})
        api._store.put(ws)
        orig = api.analysis.drift
        api.analysis.drift = self._boom
        try:
            with self.assertLogs("themis.api", level="ERROR") as cap:
                r = quiet.post("/api/analysis/paper-x/run/drift")
            self.assertEqual(r.status_code, 500)
            self.assertEqual(r.json(), {"detail": api.GENERIC_ERROR})
            self.assertIn("hunter2", "\n".join(cap.output))
            state = client.get("/api/analysis/paper-x/tasks").json()["tasks"]["drift"]
            self.assertEqual(state["error"], api.GENERIC_ERROR)
        finally:
            api.analysis.drift = orig

    def test_a_caller_written_message_is_still_shown(self):
        api._ingest_pipeline.ingest = self._orig
        r = client.post("/api/analysis", files={"file": ("a.csv", BTC_CSV, "text/csv")},
                        data={"use_reference": "false", "mapping": '{"address": "no_such_column"}'})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no_such_column", r.json()["detail"])

    def test_missing_reference_corpus_does_not_reveal_the_server_path(self):
        orig = api._reference_corpus
        def gone():
            raise FileNotFoundError("No reference corpus found at /Users/analyst/themis/demo_data.")
        api._reference_corpus = gone
        try:
            r = client.post("/api/analysis/paper")
            self.assertEqual(r.status_code, 409)
            self.assertNotIn("/Users", r.text)
            self.assertIn("No reference corpus", r.json()["detail"])
        finally:
            api._reference_corpus = orig

    def test_an_unreadable_sqlite_file_does_not_echo_the_library_message(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "junk.db").write_bytes(os.urandom(4096))
            old = os.environ.get("THEMIS_DB_DIR")
            os.environ["THEMIS_DB_DIR"] = d
            try:
                r = client.get("/api/sqlite/tables", params=dict(db="junk.db"))
            finally:
                os.environ.pop("THEMIS_DB_DIR") if old is None else os.environ.update(THEMIS_DB_DIR=old)
        self.assertEqual(r.status_code, 422)
        self.assertNotIn("file is not a database", r.text)
        self.assertNotIn(d, r.text)


class TestClaimsPaging(unittest.TestCase):
    N = 260

    @classmethod
    def setUpClass(cls):
        rows = [dict(wallet_address=btc_address(i), entity_type=("ransomware", "exchange", "mixer")[i % 3])
                for i in range(cls.N)]
        rows += [dict(wallet_address=btc_address(0), entity_type="exchange")]   # a second claim at address 0
        r = client.post("/api/analysis", files={"file": ("p.csv", to_csv(rows, ["wallet_address", "entity_type"]),
                                                          "text/csv")},
                        data={"source_id": "paging_test", "use_reference": "false"})
        assert r.status_code == 200, r.text
        cls.aid = r.json()["analysis_id"]

    def page(self, **params):
        r = client.get(f"/api/analysis/{self.aid}/claims", params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def walk(self, limit, **filters):
        out, offset = [], 0
        while True:
            b = self.page(limit=limit, offset=offset, **filters)
            out += [(c["address"], c["source"], c["raw_label"]) for c in b["claims"]]
            offset += limit
            if offset >= b["total"]:
                return out, b["total"]

    def test_pages_partition_the_result_with_no_duplicate_and_no_gap(self):
        whole, total = self.walk(limit=500)
        self.assertEqual(total, self.N + 1)
        for size in (1, 7, 100, 259, 260, 261):
            paged, _ = self.walk(limit=size)
            self.assertEqual(paged, whole, f"limit={size}")

    def test_order_is_deterministic_across_calls(self):
        self.assertEqual(self.page(limit=50, offset=20)["claims"], self.page(limit=50, offset=20)["claims"])

    def test_a_huge_limit_is_capped_by_config(self):
        cap = config_io.load().api["paging"]["claims_max_page"]
        b = self.page(limit=10 ** 9)
        self.assertEqual(b["limit"], cap)
        self.assertLessEqual(b["n_returned"], cap)
        self.assertEqual(b["n_returned"], min(cap, self.N + 1))

    def test_offset_at_and_past_the_end_is_an_empty_page(self):
        for off in (self.N + 1, self.N + 2, 10 ** 12):
            b = self.page(offset=off)
            self.assertEqual((b["claims"], b["n_returned"], b["total"]), ([], 0, self.N + 1))

    def test_last_boundary_record_is_present(self):
        whole, _ = self.walk(limit=500)
        last = self.page(limit=1, offset=self.N)["claims"]
        self.assertEqual([(c["address"], c["source"], c["raw_label"]) for c in last], whole[-1:])

    def test_invalid_offsets_and_limits_are_clean(self):
        b = self.page(offset=-5, limit=0)
        self.assertEqual((b["offset"], b["limit"]), (0, 1))
        b = self.page(limit=-3)
        self.assertEqual(b["limit"], 1)
        for bad in (dict(offset="abc"), dict(limit="1e3"), dict(limit="")):
            r = client.get(f"/api/analysis/{self.aid}/claims", params=bad)
            self.assertEqual(r.status_code, 422, bad)
            self.assertNotIn("Traceback", r.text)

    def test_filters_compose(self):
        both = self.page(source="paging_test", canon="ransomware", limit=500)
        only_canon = self.page(canon="ransomware", limit=500)
        self.assertEqual(both["total"], only_canon["total"])
        self.assertTrue(all(c["canon"] == "ransomware" and c["source"] == "paging_test" for c in both["claims"]))
        self.assertEqual(self.page(source="paging_test", canon="ransomware", provenance="unresolved",
                                   limit=500)["total"], both["total"])
        self.assertEqual(self.page(source="no_such_source")["total"], 0)
        self.assertEqual(self.page(canon="ransomware", source="no_such_source")["total"], 0)
        # a narrower filter can never return more than a wider one
        self.assertLessEqual(both["total"], self.page(source="paging_test")["total"])

    def test_evidence_tier_and_currency_filters(self):
        every = self.page(limit=500)["total"]
        tiers = {c["evidence_tier"] for c in self.page(limit=500)["claims"]}
        got = sum(self.page(evidence_tier=t, limit=500)["total"] for t in tiers)
        self.assertEqual(got, every)                       # the tiers partition the claims
        # no revision date in this CSV: every claim is currency-unknown, none stale, none "current"
        self.assertEqual(self.page(currency="currency-unknown")["total"], every)
        self.assertEqual(self.page(currency="stale")["total"], 0)
        self.assertEqual(self.page(currency="current")["total"], 0)

    def test_an_unknown_outcome_filter_is_a_400(self):
        r = client.get(f"/api/analysis/{self.aid}/claims", params=dict(outcome="nonsense"))
        self.assertEqual(r.status_code, 400)


class TestPaperRunIdIsNeverAPath(unittest.TestCase):
    def test_dot_names_are_not_run_ids(self):
        from themis.paper import reproduce
        for bad in (".", "..", "...", ".hidden", "a/b", "..\\x", "", None):
            self.assertIsNone(reproduce.run_dir_of(bad), bad)

    def test_the_artifact_route_refuses_a_traversal_run_id(self):
        r = client.get("/api/paper/experiments/anything/artifact/x.json", params=dict(run_id=".."))
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
