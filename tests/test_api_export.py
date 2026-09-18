"""CSV export must neutralize spreadsheet formula/DDE injection: raw_label
and other exported fields come straight from an attacker-controllable
upload (STEP 23 preserves raw evidence verbatim internally), so a label
like "=cmd|' /C calc'!A0" must not reach a downloaded CSV as a live formula.
"""
import asyncio, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
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
    b"0x28C6c06298d514Db089934071355E5743bf21d60,Binance\n"
    b"0xDFd5293D8e347dFe59E90eFd55b2956a1343963d,Kraken\n"
    b"0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549,Bitfinex\n"
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
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
