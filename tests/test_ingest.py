"""STEP 37 - the new-dataset pipeline (STEP 23): crypto detection, schema
inference, input validation, and the "unknown provenance stays unknown"
guarantee for a source THEMIS has never configured.
"""
import sys, pathlib, unittest, tempfile, csv, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.ingest import detect, schema, validate, claims as claim_mod, pipeline
from themis import provenance, taxonomy


def _write_csv(rows, fieldnames):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path


CRYPTO_ROWS = [
    {"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "entity_type": "ransomware",
     "notes_url": "https://example.org/1", "last_seen": "2025-01-01"},
    {"wallet_address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "entity_type": "exchange",
     "notes_url": "https://example.org/2", "last_seen": "2020-05-05"},
    {"wallet_address": "not-a-real-address", "entity_type": "scam",
     "notes_url": "https://example.org/3", "last_seen": "2023-01-01"},
]
CRYPTO_FIELDS = ["wallet_address", "entity_type", "notes_url", "last_seen"]

NON_CRYPTO_ROWS = [{"name": "Alice", "age": "30", "city": "Springfield"},
                   {"name": "Bob", "age": "25", "city": "Shelbyville"}]
NON_CRYPTO_FIELDS = ["name", "age", "city"]


class TestDetection(unittest.TestCase):
    def test_crypto_dataset_detected_with_confidence(self):
        # 2 of 3 sample addresses are valid (one is deliberately malformed);
        # that is well above the LOW/NONE floor without being a clean 100%.
        d = detect.detect(CRYPTO_ROWS, CRYPTO_FIELDS)
        self.assertEqual(d["confidence"], detect.MEDIUM)
        self.assertEqual(d["blockchain"], "bitcoin")
        self.assertEqual(d["address_field"], "wallet_address")

    def test_non_crypto_dataset_is_none_confidence(self):
        d = detect.detect(NON_CRYPTO_ROWS, NON_CRYPTO_FIELDS)
        self.assertEqual(d["confidence"], detect.NONE)
        self.assertIsNone(d["blockchain"])

    def test_no_columns_no_rows_does_not_crash(self):
        d = detect.detect([], [])
        self.assertEqual(d["confidence"], detect.NONE)


class TestSchemaMapping(unittest.TestCase):
    def test_infers_all_roles(self):
        m = schema.infer_mapping(CRYPTO_ROWS, CRYPTO_FIELDS)["mapping"]
        self.assertEqual(m["address"], "wallet_address")
        self.assertEqual(m["label"], "entity_type")
        self.assertEqual(m["source"], "notes_url")
        self.assertEqual(m["timestamp"], "last_seen")

    def test_missing_optional_columns_report_none_not_a_guess(self):
        rows = [{"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"}]
        m = schema.infer_mapping(rows, ["wallet_address"])["mapping"]
        self.assertIsNone(m["label"])
        self.assertIsNone(m["timestamp"])


class TestValidation(unittest.TestCase):
    def test_invalid_and_valid_rows_both_reported(self):
        mapping = dict(address="wallet_address", label="entity_type",
                      source="notes_url", timestamp="last_seen", category=None, confidence=None)
        v = validate.validate_rows(CRYPTO_ROWS, mapping, "bitcoin")
        self.assertEqual(v["n_input"], 3)
        self.assertEqual(v["n_valid"], 2)
        self.assertEqual(v["n_rejected"], 1)
        self.assertEqual(v["rejected"][0]["reason"], "invalid address")

    def test_empty_address_column_rejects_every_row(self):
        rows = [{"a": "", "b": "x"}]
        v = validate.validate_rows(rows, dict(address="a", label="b"), None)
        self.assertEqual(v["n_valid"], 0)
        self.assertEqual(v["rejected"][0]["reason"], "empty address")

    def test_duplicate_rows_are_flagged_not_silently_dropped(self):
        rows = [CRYPTO_ROWS[0], dict(CRYPTO_ROWS[0])]
        mapping = dict(address="wallet_address", label="entity_type")
        v = validate.validate_rows(rows, mapping, "bitcoin")
        self.assertEqual(v["n_valid"], 1)
        self.assertEqual(v["rejected"][0]["reason"], "duplicate row")


class TestClaimNormalization(unittest.TestCase):
    def test_raw_label_preserved_alongside_canonical(self):
        row = {"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "entity_type": "ransomware-wallet"}
        c = claim_mod.build_claim(row, dict(address="wallet_address", label="entity_type"), "test_src")
        self.assertEqual(c["raw_label"], "ransomware-wallet")
        self.assertEqual(c["canon"], "ransomware")   # via the taxonomy alias, not a guess
        self.assertEqual(c["polarity"], "illicit")

    def test_unmapped_label_alias_stays_unknown_not_invented(self):
        row = {"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "entity_type": "totally-novel-thing"}
        c = claim_mod.build_claim(row, dict(address="wallet_address", label="entity_type"), "test_src")
        self.assertEqual(c["canon"], "unknown")


class TestUnknownEvidenceTier(unittest.TestCase):
    """Loop 2 STEP 9/28 - an upload with no declared methodology must land
    on TIER_UNKNOWN, never be silently upgraded to TIER_DERIVED."""

    def test_freshly_ingested_claim_defaults_to_unknown_tier(self):
        row = {"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "entity_type": "ransomware"}
        c = claim_mod.build_claim(row, dict(address="wallet_address", label="entity_type"), "test_src")
        self.assertEqual(c["heuristic"], "unknown")
        self.assertEqual(taxonomy.tier_of(c), taxonomy.TIER_UNKNOWN)

    def test_confidence_field_survives_ingestion_uninterpreted(self):
        row = {"wallet_address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "entity_type": "ransomware",
              "score": "high"}
        mapping = dict(address="wallet_address", label="entity_type", confidence="score")
        c = claim_mod.build_claim(row, mapping, "test_src")
        self.assertEqual(c["confidence_raw"], "high")
        self.assertIsNone(c["confidence_normalized"])   # never guessed


class TestUnknownProvenanceStaysUnknown(unittest.TestCase):
    """STEP 4/33 - a source with no declared provenance rule must resolve
    UNRESOLVED, never be assumed identified or independent."""

    def test_unconfigured_source_resolves_unresolved(self):
        claim = {"source": "a_source_themis_has_never_seen", "address": "x"}
        r = provenance.resolve(claim)
        self.assertFalse(r["resolved"])
        self.assertFalse(r["native"])
        self.assertFalse(r["verified"])
        self.assertTrue(provenance.is_unresolved(r["root"]))

    def test_two_unconfigured_claims_are_not_silently_the_same_root(self):
        """Two different unrecognized sources must not collapse onto one
        root just because THEMIS doesn't know either of them - that would
        manufacture false circularity."""
        r1 = provenance.resolve({"source": "mystery_source_one", "address": "x"})
        r2 = provenance.resolve({"source": "mystery_source_two", "address": "x"})
        self.assertNotEqual(r1["root"], r2["root"])


class TestPipeline(unittest.TestCase):
    def test_non_crypto_file_stops_forensic_analysis(self):
        path = _write_csv(NON_CRYPTO_ROWS, NON_CRYPTO_FIELDS)
        try:
            r = pipeline.ingest(path, "test_people")
            self.assertTrue(r["stopped"])
            self.assertIn("does not appear to contain cryptocurrency", r["message"])
            self.assertEqual(r["basic_quality"]["rows"], 2)
        finally:
            os.remove(path)

    def test_crypto_file_produces_claims_and_reports_rejections(self):
        path = _write_csv(CRYPTO_ROWS, CRYPTO_FIELDS)
        try:
            r = pipeline.ingest(path, "test_upload", reference=None)
            self.assertFalse(r["stopped"])
            self.assertEqual(len(r["claims"]), 2)   # the malformed address is rejected
            self.assertEqual(r["validation"]["n_rejected"], 1)
            self.assertIn("Cross-source comparison unavailable: no reference corpus was supplied.",
                          r["limitations"])
        finally:
            os.remove(path)

    def test_missing_address_column_is_none_confidence_not_a_crash(self):
        path = _write_csv(NON_CRYPTO_ROWS, NON_CRYPTO_FIELDS)
        try:
            r = pipeline.ingest(path, "test_missing_cols")
            self.assertTrue(r["stopped"])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
