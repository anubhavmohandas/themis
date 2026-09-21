"""The mandatory pre-flight: a file is analysed only if it holds a defensible
attribution schema. Regression for the failure this exists to prevent: a BTC
price CSV was accepted and its `Number of trades` column became 71,226 "Bitcoin
addresses" (0, 1000, 10000, ...), each with provenance, staleness, conflicts and
trust figures.
"""
import csv, hashlib, io, json, os, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis import chains, provenance
from themis.api import app
from themis.chains.bitcoin import BitcoinAdapter
from themis.ingest import gating, pipeline, preflight

EX = pathlib.Path(__file__).resolve().parent.parent / "examples"
REAL_BTC = pathlib.Path(os.environ.get("THEMIS_TEST_BTC_CSV", "~/Downloads/btc_15m_data_2018_to_2025.csv")).expanduser()

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def btc_address(i: int) -> str:
    """A syntactically valid P2PKH address for no known key (checksum computed)."""
    payload = b"\x00" + hashlib.sha256(f"themis-test-{i}".encode()).digest()[:20]
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n, out = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def to_csv(rows, fields) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def write_tmp(data: bytes, suffix=".csv") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


#: the exact header of the Binance-style file that caused the failure
OHLCV_FIELDS = ["Open time", "Open", "High", "Low", "Close", "Volume", "Close time", "Quote asset volume",
                "Number of trades", "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"]


def ohlcv_bytes(n=3000) -> bytes:
    rows = []
    for i in range(n):
        rows.append({"Open time": f"2018-01-{1 + i % 28:02d} {i % 24:02d}:00:00.000000 ", "Open": f"{13000 + i}.5",
                     "High": f"{13100 + i}.5", "Low": f"{12900 + i}.5", "Close": f"{13050 + i}.5", "Volume": f"{100 + i}.25",
                     "Close time": f"2018-01-{1 + i % 28:02d} {i % 24:02d}:14:59.999000 ", "Quote asset volume": f"{1e6 + i}",
                     "Number of trades": str(1000 + 7 * i),      # thousands of distinct integers, like the real file
                     "Taker buy base asset volume": "50.1", "Taker buy quote asset volume": "700000.2", "Ignore": "0"})
    return to_csv(rows, OHLCV_FIELDS)


ATTRIB_FIELDS = ["wallet_address", "category", "source_url", "last_updated"]


def attribution_bytes(n=6, **cols) -> bytes:
    rows = [{"wallet_address": btc_address(i), "category": ["exchange", "mixer", "ransomware"][i % 3],
             "source_url": f"https://example.org/{i}", "last_updated": f"2025-0{1 + i % 9}-15"} for i in range(n)]
    return to_csv(rows, ATTRIB_FIELDS)


def run_preflight(data: bytes, **kw):
    path = write_tmp(data)
    try:
        rows, fields = pipeline.load_csv(path)
        return preflight.run(rows, fields, **kw)
    finally:
        os.remove(path)


class TestLegitimateAttributionPasses(unittest.TestCase):
    def test_clean_attribution_csv_passes_and_maps_every_role_with_confidence(self):
        pf = run_preflight(attribution_bytes())
        self.assertEqual((pf["status"], pf["dataset_type"], pf["can_analyze"]), ("ready", "attribution_claims", True))
        cols = {c["column"]: c for c in pf["columns"]}
        self.assertEqual(cols["wallet_address"]["semantic_type"], "subject_address")
        self.assertEqual(cols["category"]["semantic_type"], "attribution_category")
        self.assertEqual(cols["source_url"]["semantic_type"], "attribution_source")
        self.assertEqual(cols["last_updated"]["semantic_type"], "ts_attribution_last_updated")
        for c in cols.values():
            self.assertGreaterEqual(c["confidence"], 0.75)
            self.assertEqual(c["status"], "ok")
        self.assertEqual(pf["chain"]["value"], "bitcoin")
        self.assertEqual(pf["chain"]["source"], "detected")

    def test_shipped_example_still_ingests(self):
        r = pipeline.ingest(str(EX / "example_attribution.csv"), "example_feed", reference=None)
        self.assertFalse(r["stopped"])
        self.assertEqual((len(r["claims"]), r["validation"]["n_rejected"]), (12, 0))
        self.assertEqual(r["dataset_preflight"]["chain"]["value"], "bitcoin")


class TestMarketDataIsRefused(unittest.TestCase):
    def test_ohlcv_csv_is_recognised_as_market_data_and_yields_no_claims(self):
        path = write_tmp(ohlcv_bytes())
        try:
            r = pipeline.ingest(path, "btc_price", reference=None)
        finally:
            os.remove(path)
        self.assertTrue(r["stopped"])
        self.assertEqual(r["claims"], [])
        pf = r["dataset_preflight"]
        self.assertEqual(pf["dataset_type"], "market_timeseries")
        self.assertIn("Unsupported dataset for attribution analysis", r["message"])
        self.assertIn("No defensible cryptocurrency attribution schema was detected.", r["message"])
        sem = {c["column"]: c["semantic_type"] for c in pf["columns"]}
        self.assertEqual(sem["Open time"], "ts_market_candle")
        self.assertEqual(sem["Close time"], "ts_market_candle")
        for c in ("Open", "High", "Low", "Close", "Volume", "Number of trades"):
            self.assertEqual(sem[c], "market_numeric")
        self.assertFalse(any(rq["satisfied"] for rq in pf["required"]))
        self.assertEqual({s["state"] for s in r["analysis_states"].values()}, {gating.UNSUPPORTED_SCHEMA})

    def test_forcing_the_trade_count_column_in_as_the_address_cannot_manufacture_claims(self):
        # the original failure, reproduced through every door a user has: role override, semantic override,
        # a chosen chain, and a confirmation. None of them waives validation.
        path = write_tmp(ohlcv_bytes())
        try:
            for kw in (dict(mapping_override=dict(address="Number of trades", label="Ignore")),
                       dict(semantics={"Number of trades": "subject_address", "Ignore": "attribution_label"}),
                       dict(mapping_override=dict(address="Number of trades", label="Ignore"),
                            chain="bitcoin", confirmed=True)):
                r = pipeline.ingest(path, "btc_price", reference=None, **kw)
                self.assertTrue(r["stopped"], kw)
                self.assertEqual(r["claims"], [], kw)
                codes = {b["code"] for b in r["dataset_preflight"]["blockers"]}
                self.assertIn("subject_invalid", codes, kw)
        finally:
            os.remove(path)

    def test_same_via_the_api_creates_a_stopped_workspace_with_no_claims(self):
        client = TestClient(app)
        r = client.post("/api/analysis", files={"file": ("btc.csv", ohlcv_bytes(), "text/csv")},
                        data={"source_id": "btc_price", "use_reference": "false", "chain": "bitcoin", "confirmed": "true",
                              "semantics": json.dumps({"Number of trades": "subject_address", "Ignore": "attribution_label"})})
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["preflight"]["stopped"])
        self.assertEqual(body["meta"]["n_claims"], 0)

    @unittest.skipUnless(REAL_BTC.is_file(), "the real BTC file is not present (set THEMIS_TEST_BTC_CSV)")
    def test_the_real_btc_file_no_longer_becomes_71226_claims(self):
        r = pipeline.ingest(str(REAL_BTC), "btc_price", mapping_override=dict(address="Number of trades", label="Ignore"),
                            chain="bitcoin", confirmed=True)
        self.assertTrue(r["stopped"])
        self.assertEqual(len(r["claims"]), 0)


class TestIdentifierValidation(unittest.TestCase):
    btc = BitcoinAdapter()

    def test_plain_numeric_ids_are_not_bitcoin_addresses(self):
        for v in ("0", "1000", "100007", "10000", "3", "12345678901234567890123456"):
            self.assertFalse(self.btc.validate_address(v), v)

    def test_malformed_addresses_are_rejected(self):
        for v in ("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3",                 # bad checksum
                  "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdx",          # bad bech32 checksum
                  "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNV",                    # truncated
                  "0x28C6c06298d514Db089934071355E5743bf21d60",          # another chain's shape
                  "not-a-real-address", "", "  "):
            self.assertFalse(self.btc.validate_address(v), v)

    def test_valid_supported_address_families_are_accepted(self):
        for v in ("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",                                   # P2PKH
                  "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",                                   # P2SH
                  "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",                           # bech32 v0
                  "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"):      # bech32m v1 (taproot)
            self.assertTrue(self.btc.validate_address(v), v)

    def test_a_column_of_numbers_named_address_is_not_proposed_as_the_subject(self):
        rows = [{"address": str(1000 + i), "label": "exchange"} for i in range(50)]
        pf = run_preflight(to_csv(rows, ["address", "label"]))
        self.assertNotEqual(pf["status"], "ready")
        col = next(c for c in pf["columns"] if c["column"] == "address")
        self.assertFalse(col["semantic_type"].startswith("subject_"))
        self.assertEqual(col["status"], "invalid")
        self.assertIsNone(pf["subject"])

    def test_a_sequential_row_index_is_never_an_identifier(self):
        rows = [{"id": str(i), "label": "exchange"} for i in range(30)]
        pf = run_preflight(to_csv(rows, ["id", "label"]), overrides={"id": "subject_entity"})
        self.assertEqual(pf["subject"]["kind"], "entity")
        self.assertFalse(pf["subject"]["analyzable"])      # recognised, but this pipeline is address-keyed
        self.assertEqual(pf["status"], "blocked")
        self.assertIn("subject_kind_unsupported", {b["code"] for b in pf["blockers"]})

    def test_malformed_rows_inside_an_otherwise_valid_file_are_rejected_with_counts(self):
        rows = [{"wallet_address": btc_address(i), "category": "exchange"} for i in range(8)]
        rows += [{"wallet_address": "1000", "category": "exchange"}, {"wallet_address": "junk", "category": "mixer"}]
        path = write_tmp(to_csv(rows, ["wallet_address", "category"]))
        try:
            r = pipeline.ingest(path, "mixed_upload", reference=None)
        finally:
            os.remove(path)
        self.assertFalse(r["stopped"])
        self.assertEqual(len(r["claims"]), 8)
        self.assertEqual(r["validation"]["rejected_by_reason"], {"invalid address": 2})

    def test_file_whose_addresses_mostly_fail_after_a_clean_head_is_stopped_on_the_full_check(self):
        # the sample (first rows) looks fine; the rest of the file does not
        rows = [{"wallet_address": btc_address(i), "category": "exchange"} for i in range(500)]
        rows += [{"wallet_address": str(i), "category": "exchange"} for i in range(5000)]
        path = write_tmp(to_csv(rows, ["wallet_address", "category"]))
        try:
            r = pipeline.ingest(path, "front_loaded", reference=None)
        finally:
            os.remove(path)
        self.assertTrue(r["stopped"])
        self.assertEqual(r["claims"], [])
        self.assertIn("subject_invalid_full", {b["code"] for b in r["dataset_preflight"]["blockers"]})


class _OtherChain(BitcoinAdapter):
    id = "bitcoin_lookalike"
    display_name = "Lookalike"
    symbol_aliases = ("lkl",)


class TestChainMustBeExplicit(unittest.TestCase):
    def setUp(self):
        chains.base.register(_OtherChain())

    def tearDown(self):
        chains.base._REGISTRY.pop("bitcoin_lookalike", None)

    def test_identifiers_valid_on_two_chains_are_ambiguous_and_block_analysis(self):
        pf = run_preflight(attribution_bytes())
        self.assertEqual(pf["chain"]["status"], "ambiguous")
        self.assertIsNone(pf["chain"]["value"])
        self.assertFalse(pf["can_analyze"])
        self.assertIn("chain_required", {b["code"] for b in pf["blockers"]})

    def test_ingest_refuses_to_run_until_the_user_chooses_then_records_the_choice(self):
        path = write_tmp(attribution_bytes())
        try:
            blocked = pipeline.ingest(path, "amb", reference=None)
            self.assertTrue(blocked["stopped"])
            self.assertEqual(blocked["claims"], [])
            chosen = pipeline.ingest(path, "amb", reference=None, chain="bitcoin")
        finally:
            os.remove(path)
        self.assertFalse(chosen["stopped"])
        self.assertEqual(chosen["dataset_preflight"]["chain"]["source"], "user")
        self.assertEqual(len(chosen["claims"]), 6)

    def test_a_chosen_chain_the_values_do_not_fit_is_still_blocked(self):
        eth = [{"wallet_address": "0x28C6c06298d514Db089934071355E5743bf21d60", "category": "exchange"}] * 3
        pf = run_preflight(to_csv(eth, ["wallet_address", "category"]), chain="bitcoin", confirmed=True)
        self.assertFalse(pf["can_analyze"])

    def test_unknown_chain_is_a_request_error(self):
        with self.assertRaises(ValueError):
            run_preflight(attribution_bytes(), chain="dogecoin")


class TestTimestampSemantics(unittest.TestCase):
    def rows(self, extra: dict):
        base = [{"wallet_address": btc_address(i), "category": "exchange", **{k: v for k, v in extra.items()}} for i in range(6)]
        return to_csv(base, ["wallet_address", "category", *extra])

    def test_unrelated_date_columns_never_become_the_attribution_date(self):
        for name in ("timestamp", "date", "last_seen", "retrieved_at", "published_at", "tx_time", "snapshot_date", "created_at"):
            pf = run_preflight(self.rows({name: "2025-03-01"}))
            self.assertIsNone(pf["currency_basis"], name)
            self.assertIsNone(pf["mapping"]["timestamp"], name)
            role = {c["column"]: c["semantic_type"] for c in pf["columns"]}[name]
            self.assertNotIn(role, ("ts_attribution_last_updated", "ts_attribution_last_verified"), name)

    def test_market_candle_time_is_not_an_attribution_date(self):
        pf = run_preflight(ohlcv_bytes(30))
        self.assertIsNone(pf["currency_basis"])
        self.assertEqual(pf["timestamp_roles"], {"Open time": "ts_market_candle", "Close time": "ts_market_candle"})

    def test_named_attribution_timestamps_are_used_and_the_rule_is_stated(self):
        pf = run_preflight(self.rows({"last_updated": "2025-03-01"}))
        self.assertEqual(pf["currency_basis"]["column"], "last_updated")
        self.assertEqual(pf["currency_basis"]["role"], "ts_attribution_last_updated")
        self.assertIn("'last_updated'", pf["currency_basis"]["rule"])
        self.assertIn("never stale", pf["currency_basis"]["rule"])

    def test_verification_date_outranks_update_date_per_config(self):
        pf = run_preflight(self.rows({"last_updated": "2025-03-01", "last_verified": "2024-01-01"}))
        self.assertEqual(pf["currency_basis"]["role"], "ts_attribution_last_verified")

    def test_user_may_assert_a_role_but_only_a_date_column_can_hold_it(self):
        ok = run_preflight(self.rows({"stamp": "2025-03-01"}), overrides={"stamp": "ts_attribution_last_updated"})
        self.assertEqual(ok["currency_basis"]["column"], "stamp")
        bad = run_preflight(self.rows({"stamp": "not a date"}), overrides={"stamp": "ts_attribution_last_updated"})
        self.assertIsNone(bad["currency_basis"])
        self.assertEqual({c["column"]: c["status"] for c in bad["columns"]}["stamp"], "invalid")

    def test_staleness_is_not_computed_from_an_unrelated_date_end_to_end(self):
        path = write_tmp(self.rows({"timestamp": "2001-01-01"}))
        try:
            r = pipeline.ingest(path, "old_dates", reference=None)
        finally:
            os.remove(path)
        self.assertFalse(r["stopped"])
        self.assertEqual({c["lastmod"] for c in r["claims"]}, {""})
        self.assertEqual(r["analysis_states"]["staleness"]["state"], gating.NOT_APPLICABLE)
        self.assertFalse(r["reliability_profile"]["currency"]["available"])


class TestGatingStates(unittest.TestCase):
    def test_no_comparable_labels_is_not_applicable_never_zero_conflicts(self):
        path = write_tmp(attribution_bytes())
        try:
            r = pipeline.ingest(path, "solo_feed", reference=None)
        finally:
            os.remove(path)
        st = r["analysis_states"]["conflicts"]
        self.assertEqual(st["state"], gating.NOT_APPLICABLE)
        self.assertEqual(st["reason"], "no comparable attribution labels detected")
        self.assertEqual(r["analysis_states"]["reference_match"]["state"], gating.NOT_APPLICABLE)

    def test_no_declared_source_is_insufficient_data_for_provenance(self):
        rows = [{"wallet_address": btc_address(i), "category": "exchange"} for i in range(6)]
        path = write_tmp(to_csv(rows, ["wallet_address", "category"]))
        try:
            r = pipeline.ingest(path, "nosrc", reference=None)
        finally:
            os.remove(path)
        self.assertEqual(r["analysis_states"]["provenance"]["state"], gating.INSUFFICIENT_DATA)

    def test_conflicts_endpoint_reports_the_state_not_a_zero(self):
        client = TestClient(app)
        aid = client.post("/api/analysis", files={"file": ("a.csv", attribution_bytes(), "text/csv")},
                          data={"source_id": "gate_feed", "use_reference": "false"}).json()["analysis_id"]
        c = client.get(f"/api/analysis/{aid}/conflicts").json()
        self.assertEqual(c["state"], "not_applicable")
        self.assertEqual(c["reason"], "no comparable attribution labels detected")
        # the trust screen skips rules whose prerequisite does not exist rather than "keeping 100%"
        t = client.get(f"/api/analysis/{aid}/trust-coverage?rules=exclude_conflicts,current_only,resolved_provenance_only").json()
        by = {r["id"]: r for r in t["rules"]}
        self.assertEqual(by["exclude_conflicts"]["state"], "not_applicable")
        self.assertIsNone(by["exclude_conflicts"]["claims"])
        self.assertEqual(by["current_only"]["state"], "computed")           # last_updated is mapped
        self.assertEqual(by["resolved_provenance_only"]["state"], "computed")
        self.assertEqual(t["skipped"], ["exclude_conflicts"])

    def test_staleness_rule_is_not_applicable_without_an_attribution_date(self):
        client = TestClient(app)
        rows = [{"wallet_address": btc_address(i), "category": "exchange"} for i in range(6)]
        aid = client.post("/api/analysis", files={"file": ("b.csv", to_csv(rows, ["wallet_address", "category"]), "text/csv")},
                          data={"source_id": "nodate_feed", "use_reference": "false"}).json()["analysis_id"]
        by = {r["id"]: r for r in client.get(f"/api/analysis/{aid}/trust-coverage").json()["rules"]}
        self.assertEqual(by["current_only"]["state"], "not_applicable")


class TestInvalidDatasetsCannotEnterAnalysis(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.aid = self.client.post("/api/analysis", files={"file": ("btc.csv", ohlcv_bytes(200), "text/csv")},
                                    data={"source_id": "btc_price", "use_reference": "false"}).json()["analysis_id"]

    def test_every_analysis_route_refuses_a_stopped_dataset(self):
        for path in ("trust-coverage", "conflicts", "claims", "provenance", "address/1000",
                     "export/normalized_claims.csv", "export/conflicts.csv", "export/provenance_relationships.json"):
            r = self.client.get(f"/api/analysis/{self.aid}/{path}")
            self.assertEqual(r.status_code, 409, path)
            self.assertIn("unsupported_schema", r.json()["detail"], path)

    def test_summary_and_preflight_record_stay_readable(self):
        s = self.client.get(f"/api/analysis/{self.aid}/summary").json()
        self.assertTrue(s["result"]["stopped"])
        self.assertEqual(s["result"]["analysis_states"]["trust"]["state"], "unsupported_schema")
        p = self.client.get(f"/api/analysis/{self.aid}/export/preflight.json").json()
        self.assertEqual(p["dataset_type"], "market_timeseries")
        self.assertEqual(p["n_claims"], 0)
        self.assertTrue(p["stopped"])


class TestPreflightEndpointAndExport(unittest.TestCase):
    def test_preflight_endpoint_returns_a_reviewable_mapping(self):
        client = TestClient(app)
        r = client.post("/api/preflight", files={"file": ("a.csv", attribution_bytes(), "text/csv")}).json()
        p = r["preflight"]
        self.assertTrue(p["can_analyze"])
        self.assertTrue(all({"column", "semantic_type", "confidence", "sample_values", "status"} <= set(c) for c in p["columns"]))
        self.assertIn("subject_address", {f["id"] for f in r["semantic_fields"]})
        self.assertEqual(r["chains"], ["bitcoin"])

    def test_a_mapping_that_names_a_missing_column_is_a_400_not_a_silent_no_op(self):
        client = TestClient(app)
        r = client.post("/api/preflight", files={"file": ("a.csv", attribution_bytes(), "text/csv")},
                        data={"semantics": json.dumps({"no_such_column": "subject_address"})})
        self.assertEqual(r.status_code, 400)

    def test_low_confidence_mapping_needs_confirmation_and_records_it(self):
        # valid addresses in a column with no telling name: proposed for review, never silently accepted
        rows = [{"col_a": btc_address(i), "category": "exchange"} for i in range(6)]
        data = to_csv(rows, ["col_a", "category"])
        pf = run_preflight(data)
        self.assertEqual(pf["status"], "needs_confirmation")
        self.assertIn("needs_confirmation", {b["code"] for b in pf["blockers"]})
        ok = run_preflight(data, confirmed=True)
        self.assertEqual(ok["status"], "ready")
        self.assertTrue(ok["user_confirmed"])

    def test_preflight_json_carries_the_reproducibility_record(self):
        client = TestClient(app)
        data = attribution_bytes()
        aid = client.post("/api/analysis", files={"file": ("wallets.csv", data, "text/csv")},
                          data={"source_id": "repro_feed", "use_reference": "false", "confirmed": "true"}).json()["analysis_id"]
        p = client.get(f"/api/analysis/{aid}/export/preflight.json").json()
        self.assertEqual(p["input"]["filename"], "wallets.csv")
        self.assertEqual(p["input"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(p["input"]["type"], "csv")
        self.assertEqual(p["input"]["original_columns"], ATTRIB_FIELDS)
        self.assertEqual(p["dataset_type"], "attribution_claims")
        self.assertEqual(p["chain"]["value"], "bitcoin")
        self.assertTrue(p["user_confirmed"])
        self.assertIn("confidence", p["columns"][0])
        self.assertEqual(p["validation"]["n_rejected"], 0)
        self.assertIn("rejected_by_reason", p["validation"])
        self.assertTrue(p["schema_version"] and p["parser"] and p["analysis_timestamp"] and p["config_hash"])
        self.assertEqual(p["n_claims"], 6)


class TestProvenanceSeparation(unittest.TestCase):
    def test_uploaded_and_reference_provenance_are_separate_and_the_upload_borrows_nothing(self):
        client = TestClient(app)
        aid = client.post("/api/analysis", files={"file": ("a.csv", attribution_bytes(), "text/csv")},
                          data={"source_id": "my_private_feed", "use_reference": "false"}).json()["analysis_id"]
        d = client.get(f"/api/analysis/{aid}/provenance").json()
        self.assertEqual(d["subject"], "uploaded_dataset")
        up_nodes = {n["label"] for n in d["uploaded_dataset"]["graph"]["nodes"]}
        self.assertEqual({n["id"] for n in d["uploaded_dataset"]["graph"]["nodes"] if n["type"] == "dataset"},
                         {"dataset:my_private_feed"})
        bundled = {n["id"] for n in d["reference_corpus"]["graph"]["nodes"] if n["type"] == "dataset"}
        self.assertGreater(len(bundled), 1)
        self.assertNotIn("dataset:my_private_feed", bundled)
        self.assertTrue(all(provenance.is_unresolved(r["root"]) for r in d["uploaded_dataset"]["roots"]))
        self.assertFalse(any(r["resolved"] for r in d["uploaded_dataset"]["roots"]))
        self.assertEqual(d["reference_corpus"]["label"], "THEMIS Reference Corpus")
        self.assertEqual(d["uploaded_dataset"]["label"], "Uploaded dataset provenance")
        self.assertFalse(bundled & {f"dataset:{s}" for s in up_nodes})

    def test_an_upload_cannot_take_a_bundled_source_id_and_with_it_that_sources_provenance(self):
        path = write_tmp(attribution_bytes())
        try:
            with self.assertRaises(ValueError):
                pipeline.ingest(path, "tagpack", reference=None)
        finally:
            os.remove(path)
        r = TestClient(app).post("/api/analysis", files={"file": ("a.csv", attribution_bytes(), "text/csv")},
                                 data={"source_id": "tagpack", "use_reference": "false"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
