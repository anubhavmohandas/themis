"""The Paper Reproduction API: every value the UI shows must come from the
backend manifest and verifier, an absent corpus must block (not pass), and the
evidence for a claim must be reachable from the claim."""
import os, pathlib, sys, tempfile, time, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
import themis.api as api
from _data import requires_reference_corpus

client = TestClient(api.app)


class Isolated(unittest.TestCase):
    """A private results directory, so no test reads or writes the developer's real runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {k: os.environ.get(k) for k in ("THEMIS_RESULTS_DIR", "THEMIS_DATA_DIR")}
        os.environ["THEMIS_RESULTS_DIR"] = self.tmp.name

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()


class TestWithoutARun(Isolated):
    def test_claim_matrix_carries_the_paper_values_from_the_backend_and_no_status(self):
        r = client.get("/api/paper/claims").json()
        self.assertEqual(r["status"], "NOT_RUN")
        row = next(c for c in r["claims"] if c["id"] == "corpus.claims")
        self.assertEqual(row["paper_value"], 1545710)
        self.assertIsNone(row["generated_value"])
        self.assertEqual(row["status"], "NOT_RUN")          # never PASS without a run
        self.assertNotIn("PASS", {c["status"] for c in r["claims"]})

    def test_status_names_the_paper_the_modes_and_the_experiments(self):
        s = client.get("/api/paper/status").json()
        self.assertEqual(s["paper"]["version"], "repaired_final")
        self.assertEqual({m["id"] for m in s["modes"]}, {"live", "frozen", "declared"})
        self.assertIsNone(s["latest_run"])
        self.assertEqual({e["status"] for e in s["experiments"]}, {"NOT_RUN"})
        self.assertIn("rodwald_containment", {e["id"] for e in s["experiments"]})

    def test_unknown_experiment_is_404_and_a_path_is_never_a_run_id(self):
        self.assertEqual(client.get("/api/paper/experiments/nope").status_code, 404)
        self.assertEqual(client.get("/api/paper/experiments/drift/artifact/table2.json").status_code, 404)   # no run yet
        self.assertEqual(client.get("/api/paper/claims", params={"run_id": "../../etc"}).json()["status"], "NOT_RUN")

    def test_experiment_evidence_points_at_real_source_code(self):
        d = client.get("/api/paper/experiments/rodwald_containment").json()
        self.assertEqual(d["function_location"]["file"], "themis/provenance.py")
        self.assertGreater(d["function_location"]["line"], 1)
        self.assertIn("fig1a_data.json", d["artifact_names"])


class TestMissingCorpus(Isolated):
    def setUp(self):
        super().setUp()
        self.empty = tempfile.TemporaryDirectory()
        os.environ["THEMIS_DATA_DIR"] = self.empty.name
        self._cache = dict(api._reference_cache)
        api._reference_cache.clear()

    def tearDown(self):
        api._reference_cache.clear(); api._reference_cache.update(self._cache)
        self.empty.cleanup()
        super().tearDown()

    def test_status_says_data_required_and_lists_the_sources(self):
        c = client.get("/api/paper/status").json()["corpus"]
        self.assertFalse(c["available"])
        self.assertEqual(len(c["required"]["sources"]), 7)
        self.assertIn("build_corpus.py", c["required"]["build_command"])

    def test_reproduction_is_refused_not_faked(self):
        r = client.post("/api/paper/reproduce")
        self.assertEqual(r.status_code, 409)
        self.assertIn("DATA REQUIRED", r.json()["detail"])


@requires_reference_corpus
class TestFullRunThroughTheApi(Isolated):
    def test_run_then_matrix_evidence_and_artifacts(self):
        job_id = client.post("/api/paper/reproduce").json()["job_id"]
        for _ in range(600):
            j = client.get(f"/api/jobs/{job_id}").json()
            if j["status"] != "running":
                break
            time.sleep(0.5)
        self.assertEqual(j["status"], "complete", j.get("error"))
        self.assertEqual([s["status"] for s in j["stages"]], ["complete"] * len(j["stages"]))
        self.assertIn(j["paper_status"], ("FAIL", "BLOCKED", "PASS"))

        st = client.get("/api/paper/status").json()
        self.assertEqual(st["latest_run"]["status"], j["paper_status"])
        self.assertNotEqual(st["latest_run"]["status"], "PASS")          # the bundled sample cannot pass

        m = client.get("/api/paper/claims").json()
        row = next(c for c in m["claims"] if c["id"] == "circularity.rodwald_ransomwhere_shared")
        self.assertEqual((row["paper_value"], row["generated_value"], row["status"], row["basis"]), (7508, 7508, "PASS", "LIVE"))
        frozen = next(c for c in m["claims"] if c["id"] == "corpus.claims")
        self.assertEqual((frozen["status"], frozen["basis"]), ("NOT_REPRODUCED", "FROZEN_MANIFEST"))

        ev = client.get("/api/paper/experiments/rodwald_containment").json()      # click-through from the 7,508 row
        self.assertEqual(ev["status"], "PASS")
        groups = {g["code"]: g for g in ev["artifacts"]["fig1a_data.json"]}
        self.assertEqual(groups["RSH"]["overlap_with_candidate"], 6546)
        self.assertTrue(any(c["id"] == "circularity.rodwald_ransomwhere_shared" for c in ev["claims"]))

        d = client.get("/api/paper/experiments/condition_d").json()
        trace = d["artifacts"]["condition_d_trace.json"]
        self.assertEqual(trace["retained_addresses"], 7457)
        self.assertEqual(d["status"], "PASS")          # the abstract-level D claims (USD 112.4M at 13.8%) reproduce
        self.assertEqual(client.get("/api/paper/experiments/drift").json()["status"], "FAIL")   # Table 2 revenue cells do not

        csv = client.get("/api/paper/experiments/drift/artifact/table2.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertEqual(client.get("/api/paper/experiments/drift/artifact/verification.json").status_code, 404)  # only declared artifacts


if __name__ == "__main__":
    unittest.main()
