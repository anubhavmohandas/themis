"""examples/ - the synthetic files a reviewer with no third-party data can
upload. Each must behave exactly as examples/README.md says."""
import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from themis.api import app
from themis import provenance

EX = pathlib.Path(__file__).resolve().parent.parent / "examples"


def upload(name, **form):
    return TestClient(app, base_url="http://localhost").post("/api/analysis", files={"file": (name, (EX / name).read_bytes(), "text/csv")},
                                data={"source_id": "example_feed", "use_reference": "false", **form}).json()


class TestExamples(unittest.TestCase):
    def test_attribution_example_is_accepted_and_its_provenance_is_unresolved(self):
        r = upload("example_attribution.csv"); p = r["preflight"]
        self.assertFalse(p["stopped"])
        self.assertEqual((p["detection"]["blockchain"], p["validation"]["n_valid"], p["validation"]["n_rejected"]), ("bitcoin", 12, 0))
        # a source id the registry has no rule for resolves UNRESOLVED - never an independent root
        self.assertTrue(all(not provenance.resolve(c)["resolved"] for c in p["claims"]))
        self.assertTrue(all(c["confidence_normalized"] is None for c in p["claims"]))   # native confidence is never re-scaled
        twice = [c for c in p["claims"] if c["address"].startswith("1PqbmmN7")]
        self.assertEqual({c["raw_label"] for c in twice}, {"mixer", "exchange"})       # the disagreement it advertises

    def test_non_crypto_example_stops(self):
        p = upload("example_non_crypto.csv")["preflight"]
        self.assertTrue(p["stopped"])
        self.assertIsNone(p["detection"]["blockchain"])
        self.assertFalse(p["detection"].get("unsupported_chain_field") or p["detection"].get("crypto_asset_field"))

    def test_unsupported_chain_example_is_not_reported_as_non_crypto(self):
        p = upload("example_unsupported_chain.csv")["preflight"]
        self.assertTrue(p["stopped"])
        self.assertEqual(p["detection"]["unsupported_chain_field"], "address")

    def test_crypto_non_attribution_example_is_distinguished_from_non_crypto(self):
        p = upload("example_crypto_non_attribution.csv")["preflight"]
        self.assertTrue(p["stopped"])
        self.assertEqual(p["detection"]["crypto_asset_field"], "symbol")
        self.assertNotEqual(p["message"], upload("example_non_crypto.csv")["preflight"]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
