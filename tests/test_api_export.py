"""CSV export must neutralize spreadsheet formula/DDE injection: raw_label
and other exported fields come straight from an attacker-controllable
upload (STEP 23 preserves raw evidence verbatim internally), so a label
like "=cmd|' /C calc'!A0" must not reach a downloaded CSV as a live formula.
"""
import asyncio, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _data import requires_reference_corpus
from themis.api import _csv_safe_cell, _csv_response, app
from fastapi.testclient import TestClient


class TestCsvExportInjectionGuard(unittest.TestCase):
    def test_formula_leading_cells_are_neutralized(self):
        for dangerous in ("=SUM(A1:A10)", "+CMD|'/C calc'!A0", "-2+3", "@SUM(1)", "\tcmd"):
            self.assertTrue(_csv_safe_cell(dangerous).startswith("'"))

    def test_ordinary_cells_are_untouched(self):
        for benign in ("ransomware", "exchange", "14BWrn1evbyvBGGxFzUCVQ61ntNtRjRdm7", "", None):
            self.assertEqual(_csv_safe_cell(benign), "" if benign is None else benign)

    def test_csv_response_body_has_no_live_formula(self):
        rows = [["addr1", "=SUM(A1:A10)", "ransomware"]]
        resp = _csv_response(rows, ["address", "raw_label", "canon"], "out.csv")

        async def _drain():
            return "".join([chunk async for chunk in resp.body_iterator])

        body = asyncio.run(_drain())
        self.assertNotIn("\n=SUM", body)
        self.assertIn("'=SUM(A1:A10)", body)


NON_CRYPTO_CSV = b"name,age,city\nAlice,30,Springfield\nBob,25,Shelbyville\n"
UNSUPPORTED_CHAIN_CSV = (
    b"address,label\n"
    b"TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t,Binance\n"
    b"TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj,Kraken\n"
    b"TNPeeaaFB7K9cmo4uQpcU32zGK8G1NYqeL,Bitfinex\n"
)
BTC_CSV = (
    b"wallet_address,entity_type\n"
    b"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2,ransomware\n"
    b"3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy,exchange\n"
)


class TestUploadStoppedIngestDoesNotCrash(unittest.TestCase):
    """POST /api/analysis on a rejected upload must return the pipeline's
    'stopped' pre-flight result, not a 500: `_ingest_pipeline.ingest()`
    returns an early dict with no schema_mapping/claims keys for anything
    it stops on (non-crypto data, an unsupported chain), and the endpoint
    must not assume every result has them.
    """
    def setUp(self):
        self.client = TestClient(app, base_url="http://localhost")

    def _upload(self, content: bytes, filename: str, source_id: str):
        return self.client.post(
            "/api/analysis",
            files={"file": (filename, content, "text/csv")},
            data={"source_id": source_id, "use_reference": "false"},
        )

    def test_non_crypto_upload_returns_stopped_not_500(self):
        r = self._upload(NON_CRYPTO_CSV, "iris.csv", "iris_test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["preflight"]["stopped"])
        self.assertIn("does not appear to contain cryptocurrency", body["preflight"]["message"])

    def test_unsupported_chain_upload_returns_stopped_not_500(self):
        r = self._upload(UNSUPPORTED_CHAIN_CSV, "eth.csv", "eth_test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["preflight"]["stopped"])
        self.assertIn("not currently supported", body["preflight"]["message"])

    def test_valid_bitcoin_upload_still_succeeds(self):
        r = self._upload(BTC_CSV, "btc.csv", "btc_test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["preflight"]["stopped"])
        self.assertEqual(body["meta"]["n_claims"], 2)


class TestUploadInputValidation(unittest.TestCase):
    """API hardening: malformed request input must return a clean 4xx, never
    an unhandled exception that reaches the client as a 500 or crashes the
    worker."""
    def setUp(self):
        self.client = TestClient(app, base_url="http://localhost")

    def _upload(self, content: bytes = BTC_CSV, **form):
        data = {"source_id": "t", "use_reference": "false", **form}
        return self.client.post("/api/analysis",
                                files={"file": ("x.csv", content, "text/csv")}, data=data)

    def test_malformed_mapping_json_is_a_clean_400(self):
        r = self._upload(mapping="{not valid json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid mapping", r.json()["detail"])

    def test_mapping_that_is_not_a_json_object_is_a_clean_400(self):
        r = self._upload(mapping="[1, 2, 3]")
        self.assertEqual(r.status_code, 400)

    def test_non_utf8_upload_does_not_crash(self):
        r = self._upload(content=b"\x00\x01\x02\xff\xfe not utf8 \x80\x81")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["preflight"]["stopped"])

    def test_zero_byte_upload_does_not_crash(self):
        r = self._upload(content=b"")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["preflight"]["stopped"])

    @requires_reference_corpus
    def test_unknown_export_name_is_a_clean_404(self):
        r = self.client.post("/api/analysis/paper")
        aid = r.json()["analysis_id"]
        r = self.client.get(f"/api/analysis/{aid}/export/nonexistent.json")
        self.assertEqual(r.status_code, 404)

    def test_unknown_analysis_id_is_a_clean_404_everywhere(self):
        for path in ("", "/summary", "/address/1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
                     "/export/normalized_claims.csv"):
            r = self.client.get(f"/api/analysis/does-not-exist{path}")
            self.assertEqual(r.status_code, 404, path)

    @requires_reference_corpus
    def test_claims_endpoint_paginates_and_never_returns_the_whole_corpus(self):
        r = self.client.post("/api/analysis/paper")
        aid = r.json()["analysis_id"]

        page = self.client.get(f"/api/analysis/{aid}/claims", params={"offset": 0, "limit": 5})
        self.assertEqual(page.status_code, 200)
        body = page.json()
        self.assertEqual(body["n_returned"], 5)
        self.assertEqual(len(body["claims"]), 5)
        self.assertGreater(body["total"], 5)   # the real corpus, not a stub

        # a client asking for an enormous limit is still capped, not honored
        huge = self.client.get(f"/api/analysis/{aid}/claims", params={"limit": 10_000_000})
        self.assertLessEqual(huge.json()["n_returned"], 500)

    @requires_reference_corpus
    def test_claims_endpoint_ordering_is_stable_across_requests(self):
        r = self.client.post("/api/analysis/paper")
        aid = r.json()["analysis_id"]
        first = self.client.get(f"/api/analysis/{aid}/claims", params={"offset": 0, "limit": 10}).json()
        second = self.client.get(f"/api/analysis/{aid}/claims", params={"offset": 0, "limit": 10}).json()
        self.assertEqual(first["claims"], second["claims"])
        # a later page's first row is not a page-1 row (no gap/overlap at the boundary)
        next_page = self.client.get(f"/api/analysis/{aid}/claims", params={"offset": 10, "limit": 10}).json()
        self.assertNotIn(next_page["claims"][0]["address"], {c["address"] for c in first["claims"]})

    @requires_reference_corpus
    def test_claims_endpoint_filters_by_source_and_evidence_tier(self):
        r = self.client.post("/api/analysis/paper")
        aid = r.json()["analysis_id"]

        by_source = self.client.get(f"/api/analysis/{aid}/claims",
                                    params={"source": "watchyourback", "limit": 500}).json()
        self.assertEqual(by_source["total"], 309)   # manifest.json's declared count for this source
        self.assertTrue(all(c["source"] == "watchyourback" for c in by_source["claims"]))

        by_tier = self.client.get(f"/api/analysis/{aid}/claims",
                                  params={"evidence_tier": "verified", "limit": 5}).json()
        self.assertTrue(all(c["evidence_tier"] == "verified" for c in by_tier["claims"]))

        combined = self.client.get(f"/api/analysis/{aid}/claims",
                                   params={"source": "watchyourback", "canon": "does-not-exist"}).json()
        self.assertEqual(combined["total"], 0)

    def test_hostile_filenames_do_not_crash_and_never_reach_a_csv_cell(self):
        # Part J/G: the uploaded filename is never used to build a
        # filesystem path (tempfile.mkstemp ignores it entirely) and is
        # only ever echoed back as JSON metadata (dataset_name), never
        # written into normalized_claims.csv's fields - so it can't reach
        # the CSV-injection guard's blind spot even if hostile.
        hostile = ["../../../../etc/passwd.csv", "a" * 500 + ".csv", "=cmd|calc.csv",
                  "..\\..\\windows.csv", "<script>alert(1)</script>.csv"]
        for fn in hostile:
            r = self.client.post("/api/analysis", files={"file": (fn, BTC_CSV, "text/csv")},
                                 data={"source_id": "t", "use_reference": "false"})
            self.assertEqual(r.status_code, 200, fn)
            aid = r.json()["analysis_id"]
            self.assertEqual(r.json()["meta"]["dataset_name"], fn)
            export = self.client.get(f"/api/analysis/{aid}/export/normalized_claims.csv")
            self.assertEqual(export.status_code, 200)
            self.assertNotIn(fn, export.text)


class TestNoReferenceCorpus(unittest.TestCase):
    """A release ships no reference corpus (the derived observation table is
    not redistributed). Nothing may crash: paper mode says how to get the
    corpus, and an upload that asks for a comparison is analysed without one
    and says so."""

    def setUp(self):
        import os
        from themis import api
        self._os, self._api = os, api
        self._old = os.environ.get("THEMIS_DATA_DIR")
        os.environ["THEMIS_DATA_DIR"] = "/nonexistent-themis-data-dir"
        api._reference_cache.clear()
        self.client = TestClient(app, base_url="http://localhost")

    def tearDown(self):
        if self._old is None:
            self._os.environ.pop("THEMIS_DATA_DIR", None)
        else:
            self._os.environ["THEMIS_DATA_DIR"] = self._old
        self._api._reference_cache.clear()

    def test_paper_mode_is_a_409_naming_the_fix(self):
        r = self.client.post("/api/analysis/paper")
        self.assertEqual(r.status_code, 409)
        self.assertIn("build_corpus.py", r.json()["detail"])

    def test_upload_requesting_a_reference_degrades_to_no_comparison(self):
        r = self.client.post("/api/analysis", files={"file": ("x.csv", BTC_CSV, "text/csv")},
                             data={"source_id": "t", "use_reference": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any("No cross-source comparison" in w for w in r.json()["meta"]["warnings"]))
        self.assertFalse(r.json()["preflight"]["stopped"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
