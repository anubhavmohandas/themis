"""Generic regressions for what an unseen multi-chain attribution file exposed. Every fixture here
is synthetic and names no real dataset: each test pins a rule that must hold for ANY file.

  * EVM identifiers are validated strictly (no repair), EIP-55 is a separate question
  * a chain name resolves through a generic normaliser, never guessed
  * what a column is profiled on does not depend on the order of the rows
  * a chosen mapping is still judged on the column's values
  * the chain may be stated per row; the same string on two chains is two subjects
  * a label cell is split only when the column itself shows it is a token list
  * an evidence-class column is not a source, an entity is not evidence, rows/addresses/claims differ
  * a file that looks like attribution data is not called "not attribution data"
"""
import csv, hashlib, io, json, os, pathlib, random, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from themis import chains, config_io, corpus as corpus_mod, provenance, target_audit
from themis.chains.evm import keccak256
from themis.ingest import detect, gating, pipeline, preflight, validate
from test_preflight import btc_address, to_csv, write_tmp


def evm(i: int) -> str:
    return "0x" + hashlib.sha256(f"evm-{i}".encode()).hexdigest()[:40]


def run(rows, fields, **kw):
    return preflight.run(rows, fields, total_rows=len(rows), **kw)


def ingest(rows, fields, **kw):
    path = write_tmp(to_csv(rows, fields))
    try:
        return pipeline.ingest(path, "synthetic_upload", reference=None, **kw)
    finally:
        os.remove(path)


class TestEvmIdentifiers(unittest.TestCase):
    eth = chains.get("ethereum")

    def test_keccak_matches_the_published_vectors(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_lowercase_is_valid_and_has_no_checksum_to_fail(self):
        a = "0xde709f2102306220921060314715629080e2fb77"
        self.assertTrue(self.eth.validate_address(a))
        self.assertEqual(self.eth.checksum_state(a), "not_encoded")      # absent, NOT failed

    def test_mixed_case_is_checked_against_eip55(self):
        good = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"               # EIP-55 test vector
        self.assertEqual(self.eth.checksum_state(good), "valid")
        bad = "0x5AAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
        self.assertEqual(self.eth.checksum_state(bad), "invalid")
        self.assertFalse(self.eth.validate_address(bad))

    def test_nothing_is_repaired_or_tolerated(self):
        ok = evm(1)
        for bad in (ok + "\n", ok + " ", "\u200b" + ok, ok + "\u200b", ok[:-1], ok + "0", ok.replace("0x", "0X", 1),
                    ok + "') and 1=1--", "3976", "protocol:name", ""):
            with self.subTest(bad=bad[:30]):
                self.assertFalse(self.eth.validate_address(bad))

    def test_the_same_string_is_valid_on_every_evm_chain_so_the_chain_must_be_stated(self):
        evm_ids = [cid for cid in chains.all_adapters() if cid != "bitcoin"]
        self.assertGreaterEqual(len(evm_ids), 4)
        self.assertTrue(all(chains.get(c).validate_address(evm(2)) for c in evm_ids))
        rows = [{"address": evm(i), "category": "exchange"} for i in range(40)]
        pf = run(rows, ["address", "category"])
        self.assertEqual(pf["chain"]["status"], "ambiguous")             # never defaulted to one of them
        self.assertIn("chain_required", {b["code"] for b in pf["blockers"]})


class TestChainNames(unittest.TestCase):
    def test_names_resolve_generically(self):
        for name, want in [("ethereum", "ethereum"), ("Ethereum_Mainnet", "ethereum"), ("Polygon-Mainnet", "polygon"),
                           ("bnb_chain_mainnet", "bnb_smart_chain"), ("BTC", "bitcoin"), ("bitcoin mainnet", "bitcoin"),
                           ("avalanche_c_chain", "avalanche_c")]:
            self.assertEqual(chains.resolve_chain(name), want, name)

    def test_unknown_and_testnet_names_never_resolve(self):
        for name in ("solana", "ethereum_testnet", "goerli", "", "mainnet"):
            self.assertIsNone(chains.resolve_chain(name), name)


def _mixed_rows(n_btc, n_evm, chain_btc="bitcoin", chain_evm="ethereum"):
    rows = [{"chain": chain_btc, "address": btc_address(i).lower(), "category": "exchange"} for i in range(n_btc)]
    rows += [{"chain": chain_evm, "address": evm(i), "category": "mixer"} for i in range(n_evm)]
    return rows


class TestSamplingIsOrderIndependent(unittest.TestCase):
    """What a column is profiled on must not be whichever rows the file happens to start with."""
    fields = ["chain", "address", "category"]

    def signature(self, rows):
        pf = run(rows, self.fields)
        return (pf["dataset_type"], pf["chain"]["status"], pf["subject"]["column"],
                tuple(sorted((c["column"], c["semantic_type"]) for c in pf["columns"])))

    def test_sorted_shuffled_and_reversed_orders_agree(self):
        rows = _mixed_rows(3000, 3000)                       # a long run of one chain, then the other
        shuffled = rows[:]
        random.Random(7).shuffle(shuffled)
        sigs = {self.signature(rows), self.signature(shuffled), self.signature(rows[::-1])}
        self.assertEqual(len(sigs), 1, sigs)

    def test_a_head_of_unusable_identifiers_does_not_hide_the_rest(self):
        # the first 2,000 rows are lowercase (checksum-broken) Bitcoin; 4,000 valid EVM rows follow
        pf = run(_mixed_rows(2000, 4000), self.fields)
        self.assertEqual(pf["dataset_type"], "attribution_claims")
        self.assertEqual(pf["dataset_state"], "supported_attribution_data")

    def test_the_sample_is_deterministic(self):
        rows = _mixed_rows(500, 500)
        a = run(rows, self.fields)["chain"]["per_row"]
        b = run(rows, self.fields)["chain"]["per_row"]
        self.assertEqual(a, b)

    def test_a_row_counter_is_still_recognised_from_a_random_sample(self):
        rows = [{"id": str(i), "label": "exchange"} for i in range(5000)]
        pf = run(rows, ["id", "label"])
        self.assertTrue(any("row index" in n for c in pf["columns"] for n in c["notes"]))


class TestMappingsAreJudgedOnValues(unittest.TestCase):
    """A choice picks the column; it never waives what the column contains."""
    fields = ["chain", "address", "category", "when", "grade"]

    def rows(self):
        return [{"chain": "ethereum" if i % 2 else "bitcoin", "address": evm(i) if i % 2 else btc_address(i),
                 "category": "exchange", "when": f"2024-01-{1 + i % 28:02d}", "grade": "high" if i % 3 else "low"}
                for i in range(200)]

    def status(self, column, sem):
        pf = run(self.rows(), self.fields, overrides={column: sem})
        return next(c for c in pf["columns"] if c["column"] == column)

    def test_an_address_cannot_be_a_timestamp_of_any_kind(self):
        for sem in ("ts_market_candle", "ts_dataset_created", "ts_attribution_last_updated", "ts_unclassified"):
            with self.subTest(sem=sem):
                self.assertEqual(self.status("address", sem)["status"], "invalid")

    def test_a_chain_name_cannot_be_a_confidence(self):
        self.assertEqual(self.status("chain", "attribution_confidence")["status"], "invalid")

    def test_a_category_cannot_be_a_timestamp(self):
        self.assertEqual(self.status("category", "ts_dataset_created")["status"], "invalid")

    def test_an_identifier_column_cannot_be_a_label_or_a_chain(self):
        for sem in ("attribution_label", "attribution_category", "attribution_actor", "chain"):
            with self.subTest(sem=sem):
                self.assertEqual(self.status("address", sem)["status"], "invalid")

    def test_a_timestamp_and_a_grade_are_accepted_where_the_values_fit(self):
        self.assertEqual(self.status("when", "ts_attribution_last_updated")["status"], "ok")
        self.assertEqual(self.status("grade", "attribution_confidence")["status"], "ok")

    def test_an_inferred_mapping_is_never_labelled_as_the_users(self):
        pf = run(self.rows(), self.fields)
        self.assertNotIn("user", {c["origin"] for c in pf["columns"]})
        pf = run(self.rows(), self.fields, overrides={"grade": "attribution_confidence"})
        self.assertEqual({c["column"] for c in pf["columns"] if c["origin"] == "user"}, {"grade"})


class TestChainPerRow(unittest.TestCase):
    fields = ["chain", "address", "category"]

    def test_each_row_is_validated_under_its_own_chain(self):
        rows = [{"chain": "bitcoin_mainnet", "address": btc_address(i), "category": "exchange"} for i in range(30)]
        rows += [{"chain": "ethereum_mainnet", "address": evm(i), "category": "mixer"} for i in range(30)]
        rows += [{"chain": "bitcoin_mainnet", "address": evm(99), "category": "exchange"}]      # EVM string on Bitcoin
        r = ingest(rows, self.fields)
        self.assertFalse(r["stopped"])
        self.assertEqual(r["dataset_preflight"]["chain"]["status"], "per_row")
        v = r["validation"]
        self.assertEqual(v["per_chain_checked"], {"bitcoin": 31, "ethereum": 30})
        self.assertEqual(v["per_chain_invalid"], {"bitcoin": 1, "ethereum": 0})
        self.assertEqual({c["blockchain"] for c in r["claims"]}, {"bitcoin", "ethereum"})

    def test_an_unsupported_chain_name_rejects_the_row_and_is_never_assigned_a_chain(self):
        rows = _mixed_rows(0, 40)
        rows += [{"chain": "solana", "address": evm(500 + i), "category": "mixer"} for i in range(3)]
        r = ingest(rows, self.fields)
        self.assertEqual(r["validation"]["rejected_by_reason"], {"unresolved chain": 3})
        self.assertEqual(len(r["claims"]), 40)

    def test_the_same_string_on_four_chains_is_four_subjects_and_four_claims(self):
        a = evm(7)
        rows = [{"chain": c, "address": a, "category": lab} for c, lab in
                [("ethereum", "exchange"), ("polygon", "scam"), ("bnb_smart_chain", "wallet"), ("avalanche_c", "sanctioned")]]
        rows += [{"chain": "ethereum", "address": evm(1000 + i), "category": "exchange"} for i in range(30)]
        r = ingest(rows, self.fields)
        mine = [c for c in r["claims"] if c["address"] == a]
        self.assertEqual(len(mine), 4)
        self.assertEqual(len({provenance.subject_key(c) for c in mine}), 4)
        self.assertEqual(r["validation"]["rejected_by_reason"], {})       # not "duplicate" of one another

    def test_the_same_claim_twice_on_one_chain_is_still_one_claim_and_case_is_not_identity(self):
        rows = [{"chain": "ethereum", "address": evm(1), "category": "exchange"},
                {"chain": "ethereum", "address": evm(1).upper().replace("0X", "0x"), "category": "exchange"}]
        rows += [{"chain": "ethereum", "address": evm(i), "category": "mixer"} for i in range(2, 30)]
        r = ingest(rows, self.fields)
        self.assertEqual(r["validation"]["rejected_by_reason"], {"duplicate claim": 1})

    def test_a_reference_source_on_another_chain_never_matches_by_string(self):
        s = "ransomwhere"                                                 # a bundled source that declares chain: bitcoin
        ref = corpus_mod.Corpus([dict(address=evm(7), source=s, raw_label="ransomware", canon="ransomware",
                                      polarity="illicit", prov_family="", lastmod="", heuristic="", subcat="")])
        self.assertEqual(len(ref.for_subject("ethereum", evm(7))), 0)
        self.assertEqual(len(ref.for_subject("bitcoin", evm(7))), 1)
        claim = lambda ch: dict(address=evm(7), blockchain=ch, source="up", canon="exchange", raw_label="exchange",
                                polarity="licit", prov_family="", lastmod="", heuristic="unknown", subcat="")
        eth = target_audit.audit_target_against_reference([claim("ethereum")], ref)
        self.assertEqual(eth["profile"]["reference_comparability"]["comparable"], 0)
        btc = target_audit.audit_target_against_reference([claim("bitcoin")], ref)
        self.assertEqual(btc["profile"]["reference_comparability"]["comparable"], 1)


class TestMultiLabelCells(unittest.TestCase):
    fields = ["chain", "address", "category"]

    def file(self, cells, extra_singles=("exchange", "mixer", "scam")):
        rows = [{"chain": "ethereum", "address": evm(i), "category": c} for i, c in enumerate(cells)]
        n = len(rows)
        for j, s in enumerate(extra_singles):                        # tokens must also occur on their own
            rows += [{"chain": "ethereum", "address": evm(n + 100 * j + k), "category": s} for k in range(20)]
        return rows

    def test_a_column_of_token_lists_is_split_into_one_claim_per_token(self):
        rows = self.file(["exchange,mixer"] * 30 + ["exchange,mixer,scam"] * 10)
        r = ingest(rows, self.fields)
        self.assertEqual(r["dataset_preflight"]["label_structure"]["status"], "multi_label")
        two = [c for c in r["claims"] if c["label_cell"] == "exchange,mixer"]
        self.assertEqual(len(two), 60)
        self.assertEqual({c["subcat"] for c in two}, {"exchange", "mixer"})
        three = [c for c in r["claims"] if c["label_cell"] == "exchange,mixer,scam"]
        self.assertEqual(len(three), 30)

    def test_rows_addresses_and_claims_are_counted_separately(self):
        rows = self.file(["exchange,mixer"] * 30)
        r = ingest(rows, self.fields)
        v = r["validation"]
        self.assertEqual((v["n_valid"], v["n_claims"]), (90, 120))
        self.assertEqual(len(r["claims"]), 120)
        self.assertEqual(len({c["address"] for c in r["claims"]}), 90)
        self.assertTrue(any("label claims" in s for s in r["limitations"]))

    def test_the_first_token_is_never_picked_and_nothing_is_dropped(self):
        rows = self.file(["exchange,mixer"] * 30)
        r = ingest(rows, self.fields)
        for addr in {c["address"] for c in r["claims"] if c["label_cell"]}:
            self.assertEqual({c["subcat"] for c in r["claims"] if c["address"] == addr}, {"exchange", "mixer"})

    def test_a_known_and_an_unknown_token_both_become_claims(self):
        rows = self.file(["exchange,mixer"] * 30 + ["exchange,zzz_new"] * 2)
        pf = run(rows, self.fields)
        self.assertEqual(pf["label_structure"]["status"], "multi_label")
        toks = validate.split_label("exchange,zzz_new", pf["label_structure"])
        self.assertEqual(toks, ["exchange", "zzz_new"])

    def test_a_comma_inside_a_literal_is_not_a_separator(self):
        cells = ["Doe, John"] * 30 + ["Roe, Jane"] * 30 + ["acme"] * 20
        pf = run(self.file(cells, extra_singles=("acme",)), self.fields)
        self.assertEqual(pf["label_structure"]["status"], "single_label")
        self.assertEqual(validate.split_label("Doe, John", {"status": "multi_label", "separator": ",", "column": "category"}),
                         ["Doe, John"])                              # whitespace: not a token list, kept whole

    def test_unestablished_combinations_are_not_split_by_default(self):
        cells = [f"a{i},b{i}" for i in range(50)]                    # every token appears once, never alone
        pf = run(self.file(cells), self.fields)
        self.assertEqual(pf["label_structure"]["status"], "single_label")

    def test_hierarchical_looking_labels_are_not_split_and_no_hierarchy_is_invented(self):
        cells = ["exchange/cex"] * 30 + ["exchange:binance"] * 30
        r = ingest(self.file(cells, extra_singles=("exchange",)), self.fields)
        self.assertEqual(r["dataset_preflight"]["label_structure"]["status"], "single_label")
        self.assertIn("exchange/cex", {c["subcat"] for c in r["claims"]})


class TestEvidenceEntityAndSourceAreNotTruth(unittest.TestCase):
    fields = ["chain", "address", "category", "entity", "source"]

    def rows(self, n=300):
        return [{"chain": "ethereum", "address": evm(i), "category": "exchange",
                 "entity": "acme" if i % 3 == 0 else "", "source": ("ground_truth", "heuristic", "external")[i % 3]}
                for i in range(n)]

    def test_a_blank_entity_does_not_reject_a_row_that_has_a_category(self):
        r = ingest(self.rows(), self.fields)
        self.assertEqual(r["validation"]["rejected_by_reason"], {})
        self.assertEqual(len(r["claims"]), 300)

    def test_entity_is_metadata_and_not_the_claimed_label_when_a_category_exists(self):
        pf = run(self.rows(), self.fields)
        by = {c["column"]: c["semantic_type"] for c in pf["columns"]}
        self.assertEqual(by["entity"], "attribution_entity")
        self.assertEqual(by["category"], "attribution_category")
        self.assertIsNone(pf["mapping"]["label"])
        claim = ingest(self.rows(), self.fields)["claims"][0]
        self.assertEqual((claim["raw_label"], claim["entity"]), ("", "acme"))   # kept as metadata, never as the label

    def test_an_entity_alone_is_what_is_claimed(self):
        rows = [{"chain": "ethereum", "address": evm(i), "entity": "acme"} for i in range(60)]
        pf = run(rows, ["chain", "address", "entity"])
        self.assertEqual(pf["mapping"]["label"], "entity")

    def test_a_three_value_source_column_is_a_class_of_evidence_not_provenance(self):
        r = ingest(self.rows(), self.fields)
        st = r["analysis_states"]["provenance"]
        self.assertEqual(st["state"], gating.INSUFFICIENT_DATA)
        self.assertIn("class or method", st["reason"])
        self.assertTrue(any("different values are not independent sources" in w
                            for w in r["dataset_preflight"]["warnings"]))
        self.assertTrue(all(provenance.resolve(c)["resolved"] is False for c in r["claims"]))

    def test_the_class_of_evidence_threshold_is_read_from_config_by_both_code_paths(self):
        # 300 rows over 3 values = 100 rows per value: a class at the configured 10, not at 200
        c = config_io.load().preflight
        original = c["source_class_min_rows_per_value"]
        try:
            for threshold, is_class in ((10, True), (200, False)):
                c["source_class_min_rows_per_value"] = threshold
                r = ingest(self.rows(), self.fields)
                self.assertEqual(r["analysis_states"]["provenance"]["state"] == gating.INSUFFICIENT_DATA, is_class)
                self.assertEqual(any("class or method" in w for w in r["dataset_preflight"]["warnings"]), is_class)
        finally:
            c["source_class_min_rows_per_value"] = original

    def test_the_declared_string_never_becomes_verified_evidence(self):
        from themis import taxonomy
        r = ingest(self.rows(), self.fields)
        self.assertEqual({taxonomy.tier_of(c) for c in r["claims"]}, {taxonomy.TIER_UNKNOWN})

    def test_many_distinct_source_names_are_still_a_declared_source(self):
        rows = self.rows()
        for i, row in enumerate(rows):
            row["source"] = f"https://example.org/list/{i}"
        r = ingest(rows, self.fields)
        self.assertEqual(r["analysis_states"]["provenance"]["state"], gating.COMPUTED)


class TestIdentifierIntegrityIsReportedNotRepaired(unittest.TestCase):
    fields = ["chain", "address", "category"]

    def test_padding_is_trimmed_and_counted_but_invisible_characters_are_rejected(self):
        rows = [{"chain": "ethereum", "address": evm(i), "category": "exchange"} for i in range(60)]
        rows.append({"chain": "ethereum", "address": evm(100) + "\n", "category": "exchange"})
        rows.append({"chain": "ethereum", "address": "\u200b" + evm(101) + "\u200b", "category": "exchange"})
        r = ingest(rows, self.fields)
        v = r["validation"]
        self.assertEqual(v["n_identifiers_trimmed"], 1)
        self.assertEqual(v["rejected_by_reason"], {"invalid address": 1})
        self.assertTrue(any("trimmed" in s for s in r["limitations"]))

    def test_lowercased_case_sensitive_identifiers_are_rejected_not_fixed(self):
        rows = [{"chain": "bitcoin", "address": btc_address(i), "category": "exchange"} for i in range(10)]
        rows += [{"chain": "bitcoin", "address": btc_address(100 + i).lower(), "category": "exchange"} for i in range(60)]
        rows += [{"chain": "ethereum", "address": evm(i), "category": "exchange"} for i in range(100)]
        r = ingest(rows, self.fields)
        lowered = sum(1 for i in range(60) if not chains.get("bitcoin").validate_address(btc_address(100 + i).lower()))
        self.assertGreater(lowered, 50)
        self.assertEqual(r["validation"]["per_chain_invalid"]["bitcoin"], lowered)
        self.assertTrue(any(s.startswith("bitcoin:") and "failed validation" in s for s in r["limitations"]))

    def test_an_absent_checksum_is_reported_as_absent(self):
        r = ingest([{"chain": "ethereum", "address": evm(i), "category": "exchange"} for i in range(40)], self.fields)
        self.assertTrue(any("EIP-55" in s and "none of the" in s for s in r["limitations"]))


class TestHonestStates(unittest.TestCase):
    def test_attribution_shaped_data_with_unresolvable_identifiers_is_not_called_non_attribution(self):
        rows = [{"address": f"acct-{i:05d}-zz", "category": "exchange"} for i in range(80)]
        pf = run(rows, ["address", "category"])
        self.assertEqual(pf["dataset_state"], "attribution_like_schema_unresolved")
        self.assertNotIn("does not appear to contain", pf["message"] or "")
        self.assertIn("could not establish a schema", pf["message"])

    def test_a_plain_table_is_not_attribution_data(self):
        pf = run([{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}], ["name", "age"])
        self.assertEqual(pf["dataset_state"], "not_attribution_data")

    def test_a_supported_file_says_so(self):
        pf = run(_mixed_rows(0, 50), ["chain", "address", "category"])
        self.assertEqual(pf["dataset_state"], "supported_attribution_data")


class TestInvalidUserMappingIsTheMappingsProblem(unittest.TestCase):
    fields = ["chain", "address", "category", "source"]

    def rows(self):
        return [{"chain": "ethereum", "address": evm(i), "category": "exchange", "source": ("a", "b", "c")[i % 3]}
                for i in range(200)]

    def test_a_broken_user_mapping_is_not_a_verdict_that_the_file_is_not_attribution_data(self):
        pf = run(self.rows(), self.fields, overrides={"address": "ts_market_candle", "chain": "attribution_confidence"})
        self.assertEqual(pf["dataset_type"], "mapping_unresolved")
        self.assertEqual(pf["dataset_state"], "schema_unresolved")
        self.assertNotIn("does not appear to contain", pf["message"])
        self.assertIn("user_mapping_invalid", {b["code"] for b in pf["blockers"]})
        self.assertFalse(pf["can_analyze"])

    def test_an_invalid_column_is_never_listed_as_a_date_that_could_date_a_claim(self):
        pf = run(self.rows(), self.fields, overrides={"address": "ts_market_candle"})
        self.assertNotIn("address", pf["timestamp_roles"])
        self.assertFalse(any("address (Market" in (c["detail"] or "") for c in pf["checks"]))

    def test_the_checks_do_not_tick_a_class_of_evidence_as_a_source(self):
        pf = run(self.rows(), self.fields)
        line = next(c for c in pf["checks"] if c["text"].startswith("Declared source"))
        self.assertEqual(line["level"], "warn")
        self.assertIn("not a per-claim source", line["text"])


class TestNoStateLeaksBetweenRequests(unittest.TestCase):
    """An automatic mapping is never a manual one, and one analysis never colours the next."""

    def upload(self, semantics=None, data=None):
        from fastapi.testclient import TestClient
        from themis.api import app
        rows = [{"chain": "ethereum", "address": evm(i), "category": "exchange", "grade": "high"} for i in range(60)]
        form = {} if semantics is None else {"semantics": semantics}
        return TestClient(app, base_url="http://localhost").post(
            "/api/preflight", data=form,
            files={"file": ("a.csv", data or to_csv(rows, ["chain", "address", "category", "grade"]), "text/csv")}).json()

    def test_an_override_in_one_request_is_not_visible_in_the_next(self):
        import json
        first = self.upload(json.dumps({"grade": "attribution_confidence"}))
        self.assertEqual({c["column"] for c in first["preflight"]["columns"] if c["origin"] == "user"}, {"grade"})
        second = self.upload()
        self.assertNotIn("user", {c["origin"] for c in second["preflight"]["columns"]})
        self.assertEqual(second["preflight"]["user_overrides"], {})

    def test_an_invalid_user_mapping_is_reported_invalid_by_the_api(self):
        import json
        r = self.upload(json.dumps({"address": "ts_market_candle", "chain": "attribution_confidence"}))
        by = {c["column"]: c for c in r["preflight"]["columns"]}
        self.assertEqual(by["address"]["status"], "invalid")
        self.assertEqual(by["chain"]["status"], "invalid")
        self.assertFalse(r["preflight"]["can_analyze"])


class TestResponsesStayBoundedAtScale(unittest.TestCase):
    """The per-address maps are server-side state; the screen payload must not grow with the number of addresses."""

    def test_the_summary_carries_no_per_address_map_but_the_inspector_still_reads_it(self):
        from fastapi.testclient import TestClient
        from themis.api import app
        rows = [{"chain": "ethereum", "address": evm(i), "category": "exchange"} for i in range(60)]
        c = TestClient(app, base_url="http://localhost")
        aid = c.post("/api/analysis", data={"source_id": "scale_probe", "use_reference": "false"},
                     files={"file": ("a.csv", to_csv(rows, ["chain", "address", "category"]), "text/csv")}).json()["analysis_id"]
        summ = c.get(f"/api/analysis/{aid}/summary").json()
        for v in (summ["result"]["validation"], summ["result"]["dataset_preflight"]["validation"]):
            for per_row in ("valid_rows", "valid_chains", "valid_labels", "rejected"):    # counts, never one entry per row
                self.assertNotIn(per_row, v)
        ta = summ["result"]["target_audit"]
        self.assertNotIn("address_comparability", ta)
        self.assertNotIn("address_resolution", ta)
        self.assertEqual(ta["n_target_addresses"], 60)
        insp = c.get(f"/api/analysis/{aid}/address/{evm(3)}").json()
        self.assertTrue(insp["found"])
        self.assertEqual(insp["chain"], "ethereum")
        # the claims table pages through one cached order, and the summary export streams
        page = c.get(f"/api/analysis/{aid}/claims", params=dict(limit=10)).json()
        self.assertEqual(page["total"], 60)
        self.assertEqual([r["address"] for r in page["claims"]], sorted(r["address"] for r in page["claims"]))
        # the job-status / extract response is bounded too: it is what the browser downloads when a job finishes
        job = c.post("/api/jobs/analysis", data={"source_id": "scale_probe2", "use_reference": "false"},
                     files={"file": ("a.csv", to_csv(rows, ["chain", "address", "category"]), "text/csv")}).json()["job_id"]
        import time
        for _ in range(100):
            st = c.get(f"/api/jobs/{job}").json()
            if st["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(st["status"], "complete")
        self.assertNotIn("address_comparability", st["preflight"]["target_audit"])
        self.assertNotIn("valid_chains", st["preflight"]["validation"])
        exp = c.get(f"/api/analysis/{aid}/export/analysis_summary.json")
        self.assertEqual(exp.status_code, 200)
        self.assertEqual(len(exp.json()["result"]["claims"]), 60)


class TestAddressInspectorKeepsChainsApart(unittest.TestCase):
    """The same string on several chains is several subjects: the inspector never answers with a merged view."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from themis.api import app
        self.a = evm(7)
        rows = [{"chain": c, "address": self.a, "category": lab} for c, lab in
                [("ethereum", "exchange"), ("polygon", "scam")]]
        rows += [{"chain": "ethereum", "address": evm(1000 + i), "category": "exchange"} for i in range(30)]
        self.c = TestClient(app, base_url="http://localhost")
        self.aid = self.c.post("/api/analysis", data={"source_id": "inspector_probe", "use_reference": "false"},
                               files={"file": ("a.csv", to_csv(rows, ["chain", "address", "category"]), "text/csv")}
                               ).json()["analysis_id"]

    def get(self, addr, chain=None):
        return self.c.get(f"/api/analysis/{self.aid}/address/{addr}", params={"chain": chain} if chain else None).json()

    def test_without_a_chain_an_address_on_two_chains_asks_which(self):
        r = self.get(self.a)
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["chains"], ["ethereum", "polygon"])
        self.assertFalse(r["found"])

    def test_each_chain_gets_only_its_own_claims(self):
        eth, pol = self.get(self.a, "ethereum"), self.get(self.a, "polygon")
        self.assertEqual([c["raw"] for c in eth["target_claims"]], ["exchange"])
        self.assertEqual([c["raw"] for c in pol["target_claims"]], ["scam"])
        self.assertEqual((eth["chain"], pol["chain"]), ("ethereum", "polygon"))

    def test_a_chain_the_address_is_not_on_finds_nothing(self):
        r = self.get(self.a, "bnb_smart_chain")
        self.assertFalse(r["found"])
        self.assertEqual(r["chain"], "bnb_smart_chain")

    def test_an_address_on_one_chain_needs_no_chain(self):
        r = self.get(evm(1003))
        self.assertTrue(r["found"])
        self.assertEqual(r["chain"], "ethereum")


class TestLogicalCsvRecords(unittest.TestCase):
    def test_quoted_newlines_commas_quotes_empties_long_fields_unicode_and_crlf_keep_every_column_aligned(self):
        long = "x" * 100_000
        rows = [["chain", "address", "category", "entity", "source"],
                ["ethereum", evm(1) + "\n", "a,b", "", "s"],                    # embedded newline, quoted comma
                ["ethereum", evm(2), 'say "hi"', "ünï-çødé 交易所", "s"],          # double quote, unicode
                ["ethereum", evm(3), "c", long, ""],                            # long field, empty field
                ["ethereum", evm(4), "d\r\ne", "", "s"]]                        # CRLF inside a quoted field
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\r\n").writerows(rows)
        path = write_tmp(buf.getvalue().encode("utf-8"))
        try:
            got, fields = pipeline.load_csv(path)
        finally:
            os.remove(path)
        self.assertEqual(fields, rows[0])
        self.assertEqual(len(got), 4)                                           # logical records, not physical lines
        self.assertEqual([r["address"] for r in got], [evm(1) + "\n", evm(2), evm(3), evm(4)])
        self.assertEqual(got[0]["category"], "a,b")
        self.assertEqual(got[1]["category"], 'say "hi"')
        self.assertEqual(got[2]["entity"], long)
        self.assertEqual(got[3]["category"], "d\r\ne")
        self.assertTrue(all(len(r) == 5 for r in got))


if __name__ == "__main__":
    unittest.main()
