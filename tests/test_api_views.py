"""The workbench projections (claims filters, conflict explorer, trust-policy
preview, job runner, on-demand paper tasks) must add NO new classification:
every number they return has to reconcile with what the engine already
reports in the canonical result object."""
import pathlib, sys, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from themis.api import app
from _data import requires_reference_corpus   # skips when the reference corpus is not shipped

_client = TestClient(app, base_url="http://localhost")
_state = {}


def paper_id():
    if "paper" not in _state:
        r = _client.post("/api/analysis/paper")
        assert r.status_code == 200, r.text
        _state["paper"] = r.json()["analysis_id"]
    return _state["paper"]


BTC_CSV = (b"wallet_address,entity_type\n"
           b"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2,ransomware\n"
           b"3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy,exchange\n"
           b"1LLEoSTzRmSL3xC5AWhsn9QjpGFh4Wx72N,ransomware\n")


def upload_id():
    if "upload" not in _state:
        r = _client.post("/api/analysis", files={"file": ("btc.csv", BTC_CSV, "text/csv")},
                         data={"source_id": "btc_test", "use_reference": "true"})
        assert r.status_code == 200, r.text
        _state["upload"] = r.json()["analysis_id"]
    return _state["upload"]


@requires_reference_corpus
class TestConflictsReconcileWithAgreement(unittest.TestCase):
    def test_kind_totals_equal_the_reported_agreement_outcomes(self):
        aid = paper_id()
        outcomes = _client.get(f"/api/analysis/{aid}/summary").json()["result"]["agreement"]["outcomes"]
        expect = {"polarity": outcomes["licit/illicit conflict"]["n"], "entity": outcomes["entity-type conflict"]["n"],
                  "hierarchical": outcomes["hierarchical refinement"]["n"], "incomparable": outcomes["incomparable"]["n"]}
        for kind, n in expect.items():
            body = _client.get(f"/api/analysis/{aid}/conflicts", params=dict(kind=kind, limit=1)).json()
            self.assertEqual(body["total"], n, kind)
        counts = body["counts"]
        self.assertEqual(counts["exact"], outcomes["exact"]["n"])

    def test_all_is_the_four_non_exact_kinds(self):
        aid = paper_id()
        body = _client.get(f"/api/analysis/{aid}/conflicts", params=dict(limit=1)).json()
        self.assertEqual(body["total"], sum(v for k, v in body["counts"].items() if k != "exact"))

    def test_items_carry_both_claims_and_their_provenance(self):
        aid = paper_id()
        item = _client.get(f"/api/analysis/{aid}/conflicts", params=dict(kind="polarity", limit=1)).json()["items"][0]
        self.assertGreaterEqual(len({c["source"] for c in item["claims"]}), 2)
        self.assertIn(item["relationship"], ("distinct_roots", "shared_root", "unresolved"))
        for c in item["claims"]:
            self.assertIn(c["provenance"], ("resolved", "inherited", "unresolved"))

    def test_source_pair_and_relationship_filters_narrow_the_list(self):
        aid = paper_id()
        base = _client.get(f"/api/analysis/{aid}/conflicts", params=dict(kind="polarity", limit=1)).json()["total"]
        pair = _client.get(f"/api/analysis/{aid}/conflicts",
                           params=dict(kind="polarity", source_a="ellipticpp", source_b="rodwald_mixers", limit=200)).json()
        self.assertLess(pair["total"], base)
        for it in pair["items"]:
            self.assertTrue({"ellipticpp", "rodwald_mixers"} <= {c["source"] for c in it["claims"]})

    def test_bad_filters_are_rejected(self):
        aid = paper_id()
        self.assertEqual(_client.get(f"/api/analysis/{aid}/conflicts", params=dict(kind="nope")).status_code, 400)
        self.assertEqual(_client.get(f"/api/analysis/{aid}/conflicts", params=dict(relationship="nope")).status_code, 400)


@requires_reference_corpus
class TestClaimsFilters(unittest.TestCase):
    def test_comparable_split_is_exhaustive(self):
        aid = paper_id()
        yes = _client.get(f"/api/analysis/{aid}/claims", params=dict(comparable="yes", limit=1)).json()["total"]
        no = _client.get(f"/api/analysis/{aid}/claims", params=dict(comparable="no", limit=1)).json()["total"]
        everything = _client.get(f"/api/analysis/{aid}/claims", params=dict(limit=1)).json()["total"]
        self.assertEqual(yes + no, everything)
        single = _client.get(f"/api/analysis/{aid}/claims", params=dict(outcome="single-source", limit=1)).json()["total"]
        self.assertEqual(single, no)

    def test_outcome_filter_rows_are_all_that_outcome(self):
        aid = paper_id()
        rows = _client.get(f"/api/analysis/{aid}/claims", params={"outcome": "licit/illicit conflict", "limit": 50}).json()["claims"]
        self.assertTrue(rows)
        self.assertTrue(all(r["outcome"] == "licit/illicit conflict" for r in rows))

    def test_provenance_filter_and_search(self):
        aid = paper_id()
        rows = _client.get(f"/api/analysis/{aid}/claims", params=dict(provenance="inherited", limit=20)).json()["claims"]
        self.assertTrue(rows and all(r["provenance"] == "inherited" for r in rows))
        rows = _client.get(f"/api/analysis/{aid}/claims", params=dict(q="RANSOMWHERE", limit=5)).json()["claims"]
        self.assertTrue(rows and all("ransomwhere" in (r["source"] + r["raw_label"] + r["address"]).lower() for r in rows))

    def test_unknown_filter_values_are_rejected(self):
        aid = paper_id()
        self.assertEqual(_client.get(f"/api/analysis/{aid}/claims", params=dict(outcome="bogus")).status_code, 400)
        self.assertEqual(_client.get(f"/api/analysis/{aid}/claims", params=dict(provenance="bogus")).status_code, 400)
        self.assertEqual(_client.get(f"/api/analysis/{aid}/claims", params=dict(comparable="maybe")).status_code, 400)


@requires_reference_corpus
class TestTrustCoverage(unittest.TestCase):
    def test_paper_mode_is_refused(self):
        self.assertEqual(_client.get(f"/api/analysis/{paper_id()}/trust-coverage").status_code, 409)

    def test_no_rules_retains_everything_and_steps_are_monotone(self):
        aid = upload_id()
        none = _client.get(f"/api/analysis/{aid}/trust-coverage").json()
        self.assertEqual(none["eligible"]["claims"], none["universe"]["claims"])
        both = _client.get(f"/api/analysis/{aid}/trust-coverage",
                           params=dict(rules="exclude_conflicts,resolved_provenance_only")).json()
        counts = [s["claims"] for s in both["steps"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(both["eligible"]["claims"], counts[-1])
        self.assertLessEqual(both["eligible"]["claims"], both["universe"]["claims"])

    def test_unknown_rule_is_rejected(self):
        self.assertEqual(_client.get(f"/api/analysis/{upload_id()}/trust-coverage", params=dict(rules="bogus")).status_code, 400)


@requires_reference_corpus
class TestJobsReportRealStages(unittest.TestCase):
    def _wait(self, job_id):
        for _ in range(200):
            j = _client.get(f"/api/jobs/{job_id}").json()
            if j["status"] != "running":
                return j
            time.sleep(0.1)
        self.fail("job did not finish")

    def test_upload_job_completes_and_every_stage_ran(self):
        r = _client.post("/api/jobs/analysis", files={"file": ("btc.csv", BTC_CSV, "text/csv")},
                         data={"source_id": "btc_job", "use_reference": "true"})
        j = self._wait(r.json()["job_id"])
        self.assertEqual(j["status"], "complete")
        self.assertTrue(j["analysis_id"])
        self.assertTrue(all(s["status"] == "complete" for s in j["stages"]), j["stages"])

    def test_stopped_upload_is_reported_as_stopped_not_failed(self):
        r = _client.post("/api/jobs/analysis", files={"file": ("iris.csv", b"name,age\nAlice,30\nBob,25\n", "text/csv")},
                         data={"source_id": "iris", "use_reference": "false"})
        j = self._wait(r.json()["job_id"])
        self.assertEqual(j["status"], "stopped")
        self.assertTrue(j["preflight"]["stopped"])

    def test_unknown_job_is_404(self):
        self.assertEqual(_client.get("/api/jobs/nope").status_code, 404)


@requires_reference_corpus
class TestPaperTasks(unittest.TestCase):
    def test_tasks_start_not_run_and_bootstrap_fills_uncertainty(self):
        r = _client.post("/api/analysis/paper")
        aid = r.json()["analysis_id"]
        t = _client.get(f"/api/analysis/{aid}/tasks").json()
        self.assertEqual(t["tasks"]["audit"]["state"], "complete")
        self.assertEqual(t["tasks"]["bootstrap"]["state"], "not_run")
        done = _client.post(f"/api/analysis/{aid}/run/bootstrap").json()
        self.assertEqual(done["tasks"]["bootstrap"]["state"], "complete")
        self.assertIn("exact", done["uncertainty"]["stats"])
        self.assertEqual(_client.post(f"/api/analysis/{aid}/run/nope").status_code, 404)

    def test_tasks_refused_for_uploads(self):
        self.assertEqual(_client.get(f"/api/analysis/{upload_id()}/tasks").status_code, 409)


@requires_reference_corpus
class TestNewExports(unittest.TestCase):
    def test_conflicts_csv_has_one_row_per_claim(self):
        aid = paper_id()
        r = _client.get(f"/api/analysis/{aid}/export/conflicts.csv")
        self.assertEqual(r.status_code, 200)
        lines = r.text.strip().splitlines()
        self.assertTrue(lines[0].startswith("address,kind,outcome"))
        self.assertGreater(len(lines), 1)

    def test_provenance_relationships_json(self):
        r = _client.get(f"/api/analysis/{paper_id()}/export/provenance_relationships.json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("field_decodes", r.json())


@requires_reference_corpus
class TestPresentation(unittest.TestCase):
    def test_summary_omits_the_claim_list_and_flags_root_resolution(self):
        body = _client.get(f"/api/analysis/{upload_id()}/summary").json()
        self.assertNotIn("claims", body["result"])
        roots = _client.get(f"/api/analysis/{paper_id()}/summary").json()["result"]["independence"]["root_concentration"]
        self.assertTrue(all(isinstance(r["resolved"], bool) for r in roots))
        elliptic = next(r for r in roots if r["root"] == "elliptic_undisclosed")
        self.assertFalse(elliptic["resolved"])

    def test_complement_shares_come_from_engine_counts(self):
        r = _client.get(f"/api/analysis/{paper_id()}/summary").json()["result"]
        # a paper reproduction's complements live in result["overview"], each inside ONE address universe
        # (the old shares mixed the manifest's raw-key total with the sample's multi-dataset count)
        m = r["overview"]["metrics"]
        self.assertNotIn("single_source_share", r["shares"])
        un = m["unresolved_provenance"]
        self.assertEqual(un["resolved"] + un["numerator"], un["denominator"])
        self.assertAlmostEqual(un["resolved_share"] + un["share"], 1.0)
        if m["single_source"]["quality"] != "unavailable":
            self.assertEqual(m["single_source"]["numerator"] + m["multi_dataset"]["numerator"], m["multi_dataset"]["denominator"])
        u = _client.get(f"/api/analysis/{upload_id()}/summary").json()["result"]
        prov = u["target_audit"]["profile"]["provenance"]
        n = u["target_audit"]["n_target_addresses"]
        self.assertAlmostEqual(u["shares"]["resolved_addr_share"], prov["resolved"] / n)
        self.assertAlmostEqual(u["shares"]["resolved_addr_share"] + u["shares"]["unresolved_addr_share"], 1.0)

    def test_graph_marks_roots_pointed_at_by_several_datasets(self):
        g = _client.get(f"/api/analysis/{paper_id()}/provenance").json()["graph"]
        roots = {n["id"]: n for n in g["nodes"] if n["type"] in ("root", "root_unresolved")}
        montreal = roots["root:montreal_paquet_clouston_2019"]
        self.assertTrue(montreal["shared"])
        self.assertIn("schnoering", montreal["datasets"])
        self.assertIn("tagpack", montreal["datasets"])
        self.assertFalse(roots["root:watchyourback_manual"]["shared"])
        flagged = [e for e in g["edges"] if e.get("shared_root")]
        self.assertTrue(flagged)
        self.assertTrue(all(roots[e["target"]]["shared"] for e in flagged))

    def test_stored_result_and_export_keep_the_claims(self):
        aid = upload_id()
        exported = _client.get(f"/api/analysis/{aid}/export/analysis_summary.json").json()
        self.assertIn("claims", exported["result"])

    def test_claims_page_reports_distinct_addresses(self):
        body = _client.get(f"/api/analysis/{paper_id()}/claims", params=dict(comparable="yes", limit=1)).json()
        self.assertLess(body["n_addresses"], body["total"])
        self.assertEqual(body["n_addresses"], 15400)

    def test_taxonomy_lists_categories_with_polarity(self):
        cats = _client.get("/api/taxonomy").json()
        self.assertIn("ransomware", cats)
        self.assertIn(cats["ransomware"]["polarity"], ("illicit", "licit", "unknown"))

    def test_address_claims_carry_a_provenance_status(self):
        aid = paper_id()
        addr = _client.get(f"/api/analysis/{aid}/conflicts", params=dict(kind="polarity", limit=1)).json()["items"][0]["address"]
        res = _client.get(f"/api/analysis/{aid}/address/{addr}").json()
        self.assertTrue(all(c["provenance"] in ("resolved", "inherited", "unresolved") for c in res["claims"]))
        up = _client.get(f"/api/analysis/{upload_id()}/address/1LLEoSTzRmSL3xC5AWhsn9QjpGFh4Wx72N").json()
        for c in up.get("target_claims", []) + up.get("reference_claims", []):
            self.assertIn(c["provenance"], ("resolved", "inherited", "unresolved"))

    def test_provenance_graph_edges_carry_measured_evidence(self):
        body = _client.get(f"/api/analysis/{paper_id()}/provenance").json()
        with_ev = [e for e in body["graph"]["edges"] if e.get("evidence")]
        self.assertTrue(with_ev)
        decode = [e for e in with_ev if "decode" in e["evidence"]]
        self.assertTrue(all(e["source"] == "dataset:rodwald_ransom" for e in decode))
        self.assertTrue(any(n.get("owner") == "ransomwhere" for n in body["graph"]["nodes"]))


if __name__ == "__main__":
    unittest.main()


class TestMissingReferenceCorpus(unittest.TestCase):
    """A release does not ship the reference corpus. The API must say so plainly
    instead of failing or silently analysing without it."""

    def setUp(self):
        import themis.api as api
        self.api, self._orig = api, api._reference_corpus
        def gone():
            raise FileNotFoundError("No reference corpus found at /nowhere.")
        api._reference_corpus = gone

    def tearDown(self):
        self.api._reference_corpus = self._orig

    def test_paper_reproduction_is_refused_with_the_reason(self):
        r = _client.post("/api/analysis/paper")
        self.assertEqual(r.status_code, 409)
        self.assertIn("No reference corpus", r.json()["detail"])

    def test_paper_job_fails_with_the_reason_not_a_stack(self):
        job = _client.post("/api/jobs/paper").json()
        for _ in range(100):
            j = _client.get(f"/api/jobs/{job['job_id']}").json()
            if j["status"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(j["status"], "failed")
        self.assertIn("No reference corpus", j["error"])

    def test_upload_still_runs_and_states_that_no_comparison_was_made(self):
        r = _client.post("/api/analysis", files={"file": ("btc.csv", BTC_CSV, "text/csv")},
                         data={"source_id": "btc_test", "use_reference": "true"})
        self.assertEqual(r.status_code, 200, r.text)
        aid = r.json()["analysis_id"]
        res = _client.get(f"/api/analysis/{aid}/summary").json()["result"]
        self.assertTrue(any("No cross-source comparison was run" in x for x in res["limitations"]))

