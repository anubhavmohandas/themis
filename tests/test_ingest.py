"""STEP 37 - the new-dataset pipeline (STEP 23): crypto detection, schema
inference, input validation, and the "unknown provenance stays unknown"
guarantee for a source THEMIS has never configured.
"""
import sys, pathlib, unittest, tempfile, csv, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.ingest import detect, schema, validate, claims as claim_mod, pipeline
from themis import config_io, provenance, taxonomy


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

# Ethereum-shaped addresses - no registered adapter validates these (THEMIS
# V1 is Bitcoin-only), but they are still opaque, address-named, fixed-shape
# tokens, unlike ordinary tabular data.
UNSUPPORTED_CHAIN_ROWS = [
    {"address": "0x28C6c06298d514Db089934071355E5743bf21d60", "label": "Binance"},
    {"address": "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d", "label": "Kraken"},
    {"address": "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549", "label": "Bitfinex"},
]
UNSUPPORTED_CHAIN_FIELDS = ["address", "label"]

SHORT_ACCOUNT_ID_ROWS = [{"account_id": "ACC-0001-USER", "plan": "premium"},
                         {"account_id": "ACC-0002-USER", "plan": "free"},
                         {"account_id": "ACC-0003-USER", "plan": "premium"}]
SHORT_ACCOUNT_ID_FIELDS = ["account_id", "plan"]

# Crypto-but-not-attribution shape (Part H): a price/market row naming a
# recognized asset, no address column anywhere.
CRYPTO_OHLC_ROWS = [
    {"Date": "2024-01-01", "Symbol": "BTC-USD", "Open": "42000", "Close": "43000"},
    {"Date": "2024-01-02", "Symbol": "BTC-USD", "Open": "43000", "Close": "44000"},
    {"Date": "2024-01-03", "Symbol": "BTC-USD", "Open": "44000", "Close": "41000"},
]
CRYPTO_OHLC_FIELDS = ["Date", "Symbol", "Open", "Close"]

# Identically-shaped, but the asset itself isn't a known chain - must not be
# swept into "crypto data detected" just because the column is named Symbol.
STOCK_OHLC_ROWS = [
    {"Date": "2024-01-01", "Symbol": "AAPL", "Open": "180", "Close": "182"},
    {"Date": "2024-01-02", "Symbol": "AAPL", "Open": "182", "Close": "179"},
    {"Date": "2024-01-03", "Symbol": "AAPL", "Open": "179", "Close": "185"},
]
STOCK_OHLC_FIELDS = ["Date", "Symbol", "Open", "Close"]

# Real shape of external_data/non_crypto/btc_ohlc_real.csv: a bare price
# series with no column stating what asset it even is. No content signal
# exists here for THEMIS to find - correctly stays "not crypto", not a bug.
BARE_PRICE_ROWS = [{"Date": "2010-07-18", "Price": "0.09"},
                   {"Date": "2010-07-19", "Price": "0.08"},
                   {"Date": "2010-07-20", "Price": "0.07"}]
BARE_PRICE_FIELDS = ["Date", "Price"]


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

    def test_unsupported_chain_address_shape_is_flagged_not_treated_as_non_crypto(self):
        # crypto data on a chain THEMIS has no adapter for must not collapse
        # into the same NONE-confidence bucket as genuinely non-crypto data.
        d = detect.detect(UNSUPPORTED_CHAIN_ROWS, UNSUPPORTED_CHAIN_FIELDS)
        self.assertEqual(d["confidence"], detect.NONE)
        self.assertIsNone(d["blockchain"])
        self.assertEqual(d["unsupported_chain_field"], "address")

    def test_short_account_ids_are_not_mistaken_for_an_unsupported_chain(self):
        d = detect.detect(SHORT_ACCOUNT_ID_ROWS, SHORT_ACCOUNT_ID_FIELDS)
        self.assertEqual(d["confidence"], detect.NONE)
        self.assertIsNone(d["unsupported_chain_field"])

    def test_medium_confidence_band_is_read_from_min_identifier_valid_rate_not_hardcoded(self):
        # preflight.yml documents detect.py's MEDIUM band as the exact same
        # number as min_identifier_valid_rate; raising it must actually
        # change confidence_of's output, not just the pre-flight gate's.
        original = config_io.load().preflight["min_identifier_valid_rate"]
        config_io.load().preflight["min_identifier_valid_rate"] = 0.7
        try:
            # CRYPTO_ROWS' sample rate (2/3 = 0.667) cleared the old 0.3 floor
            # for MEDIUM; it must now fall below the raised 0.7 floor into LOW.
            self.assertEqual(detect.confidence_of(2 / 3), detect.LOW)
            d = detect.detect(CRYPTO_ROWS, CRYPTO_FIELDS)
            self.assertEqual(d["confidence"], detect.LOW)
        finally:
            config_io.load().preflight["min_identifier_valid_rate"] = original

    def test_non_crypto_dataset_has_no_unsupported_chain_field(self):
        d = detect.detect(NON_CRYPTO_ROWS, NON_CRYPTO_FIELDS)
        self.assertIsNone(d["unsupported_chain_field"])

    def test_crypto_symbol_column_is_recognized_as_crypto_non_attribution(self):
        d = detect.detect(CRYPTO_OHLC_ROWS, CRYPTO_OHLC_FIELDS)
        self.assertEqual(d["confidence"], detect.NONE)
        self.assertIsNone(d["unsupported_chain_field"])
        self.assertEqual(d["crypto_asset_field"], "Symbol")

    def test_stock_symbol_is_not_mistaken_for_a_crypto_asset(self):
        d = detect.detect(STOCK_OHLC_ROWS, STOCK_OHLC_FIELDS)
        self.assertIsNone(d["crypto_asset_field"])

    def test_bare_price_series_with_no_asset_identity_has_no_crypto_signal(self):
        d = detect.detect(BARE_PRICE_ROWS, BARE_PRICE_FIELDS)
        self.assertIsNone(d["crypto_asset_field"])

    def test_non_crypto_dataset_has_no_crypto_asset_field(self):
        d = detect.detect(NON_CRYPTO_ROWS, NON_CRYPTO_FIELDS)
        self.assertIsNone(d["crypto_asset_field"])


class TestSchemaMapping(unittest.TestCase):
    def test_infers_all_roles(self):
        m = schema.infer_mapping(CRYPTO_ROWS, CRYPTO_FIELDS)["mapping"]
        self.assertEqual(m["address"], "wallet_address")
        self.assertEqual(m["label"], "entity_type")
        self.assertEqual(m["source"], "notes_url")
        # `last_seen` dates an observation, not the attribution: it must never become the
        # revision date that staleness is computed from
        self.assertIsNone(m["timestamp"])

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
        v = validate.validate_rows(rows, dict(address="a", label="b"), "bitcoin")
        self.assertEqual(v["n_valid"], 0)
        self.assertEqual(v["rejected"][0]["reason"], "empty address")

    def _dup_rows(self, sources):
        return [dict(wallet_address=CRYPTO_ROWS[0]["wallet_address"], entity_type="exchange", src=s, seen=str(i))
                for i, s in enumerate(sources)]           # `seen` differs, so these are duplicate CLAIMS, not duplicate rows

    def test_same_claim_from_the_same_declared_source_is_one_claim(self):
        m = dict(address="wallet_address", label="entity_type", source="src")
        v = validate.validate_rows(self._dup_rows(["A", "A", "A"]), m, "bitcoin")
        self.assertEqual((v["n_valid"], v["rejected_by_reason"]), (1, {"duplicate claim": 2}))

    def test_same_claim_from_different_declared_sources_is_kept_per_source(self):
        m = dict(address="wallet_address", label="entity_type", source="src")
        v = validate.validate_rows(self._dup_rows(["A", "B", "A", "C", " B "]), m, "bitcoin")
        self.assertEqual([r["src"] for r in v["valid_rows"]], ["A", "B", "C"])   # first of each; whitespace is not a new source
        self.assertEqual(v["rejected_by_reason"], {"duplicate claim": 2})

    def test_without_a_mapped_source_column_the_key_is_still_address_and_label(self):
        m = dict(address="wallet_address", label="entity_type")
        v = validate.validate_rows(self._dup_rows(["A", "B"]), m, "bitcoin")
        self.assertEqual((v["n_valid"], v["rejected_by_reason"]), (1, {"duplicate claim": 1}))

    def test_address_validation_without_a_chain_is_refused_not_skipped(self):
        # the old behaviour accepted every non-empty string as an address when no chain was known
        with self.assertRaises(ValueError):
            validate.validate_rows([{"a": "1000", "b": "x"}], dict(address="a", label="b"), None)

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

    def test_dedicated_category_column_drives_canon_when_label_is_a_name(self):
        # a real shape (OFAC SDN export): "label" role lands on a free-text
        # entity name (never canonicalizable), while a separate, correctly
        # schema-inferred "category" column holds the actual classification.
        row = {"address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
              "entity_name": "MESRI Behzad", "category": "sanctioned"}
        c = claim_mod.build_claim(
            row, dict(address="address", label="entity_name", category="category"), "test_src")
        self.assertEqual(c["raw_label"], "MESRI Behzad")
        self.assertEqual(c["canon"], "sanctioned")
        self.assertEqual(c["polarity"], "illicit")
        self.assertEqual(c["subcat"], "sanctioned")   # still preserved raw, unchanged

    def test_label_still_wins_when_category_does_not_canonicalize(self):
        row = {"address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
              "entity_type": "ransomware-wallet", "category": "tier-2-internal-code"}
        c = claim_mod.build_claim(
            row, dict(address="address", label="entity_type", category="category"), "test_src")
        self.assertEqual(c["canon"], "ransomware")


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

    def test_utf8_bom_does_not_leak_into_the_address_column_name(self):
        # Excel commonly exports UTF-8 CSVs with a leading BOM; unstripped,
        # it becomes part of the *first column's name* ("﻿address"),
        # breaking exact-name matching (a --map override, a mapping echoed
        # back to the caller) even though detection still works by luck.
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\xef\xbb\xbfaddress,label\n"
                    b"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2,ransomware\n")
        try:
            rows, fieldnames = pipeline.load_csv(path)
            self.assertEqual(fieldnames, ["address", "label"])
            self.assertEqual(rows[0]["address"], "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")
        finally:
            os.remove(path)

    def test_unsupported_chain_file_gets_a_distinct_message_from_non_crypto(self):
        path = _write_csv(UNSUPPORTED_CHAIN_ROWS, UNSUPPORTED_CHAIN_FIELDS)
        try:
            r = pipeline.ingest(path, "test_eth")
            self.assertTrue(r["stopped"])
            self.assertIn("not currently supported", r["message"])
            self.assertNotIn("does not appear to contain cryptocurrency", r["message"])
        finally:
            os.remove(path)

    def test_crypto_asset_data_gets_a_distinct_message_from_non_crypto_and_unsupported_chain(self):
        path = _write_csv(CRYPTO_OHLC_ROWS, CRYPTO_OHLC_FIELDS)
        try:
            r = pipeline.ingest(path, "test_ohlc")
            self.assertTrue(r["stopped"])
            self.assertIn("no usable attribution-label structure", r["message"])
            self.assertNotIn("does not appear to contain cryptocurrency", r["message"])
            self.assertNotIn("not currently supported", r["message"])
        finally:
            os.remove(path)

    def test_hostile_label_content_does_not_crash_ingestion_and_survives_verbatim(self):
        # Part J: formula/DDE-injection strings, HTML/JS, SQL-looking text,
        # path traversal, JSON, very long fields, Unicode/emoji/RTL - none
        # of this is THEMIS's to sanitize at ingestion (STEP 23 requires
        # raw evidence preserved verbatim; escaping is an export/render-time
        # concern, already covered separately: CSV formula-injection guard
        # in api.py, React's automatic JSX escaping in the frontend). This
        # only checks ingestion itself never crashes and never mutates the
        # raw value.
        addr = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"
        hostile_labels = [
            "=SUM(A1:A10)", "+CMD|'/C calc'!A0", "-2+3+cmd|' /C calc'!A0", "@SUM(1+1)",
            "<script>alert(1)</script>", "<img src=x onerror=alert(1)>",
            "'; DROP TABLE users; --", "../../../../etc/passwd",
            '{"nested": [1, 2, {"a": "b"}]}', "A" * 10000,
            "比特币交易所 🚀💰", "‮gnp.exe", "line1\nline2\r\nline3", "",
        ]
        rows = [{"address": addr, "label": lbl} for lbl in hostile_labels]
        path = _write_csv(rows, ["address", "label"])
        try:
            r = pipeline.ingest(path, "test_hostile")
            self.assertFalse(r["stopped"])
            got = {c["raw_label"] for c in r["claims"]}
            expected_nonempty = {lbl for lbl in hostile_labels if lbl.strip()}
            self.assertEqual(got, expected_nonempty)
            for c in r["claims"]:
                self.assertEqual(c["canon"], "unknown")  # none are real taxonomy terms
        finally:
            os.remove(path)

    def test_bare_price_series_still_gets_the_generic_not_crypto_message(self):
        # No symbol/ticker column at all (the real external_data shape) - no
        # content signal exists, so THEMIS must not guess it's crypto.
        path = _write_csv(BARE_PRICE_ROWS, BARE_PRICE_FIELDS)
        try:
            r = pipeline.ingest(path, "test_bare_price")
            self.assertTrue(r["stopped"])
            self.assertIn("does not appear to contain cryptocurrency", r["message"])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
