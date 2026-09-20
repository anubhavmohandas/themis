"""The executable-paper pipeline: what is generated, that the verifier can catch
drift (mutation), that every surface reads one drift object, that absent or
partial input never yields a PASS, and that an independent oracle - written here
from the paper's own definitions, importing nothing from themis's analysis -
agrees with the production results."""
import copy, csv, gzip, json, os, pathlib, re, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _data import HAVE_REFERENCE, REASON, requires_reference_corpus
from themis.corpus import Corpus, data_dir
from themis.paper import experiments as ex, metrics as pm, verify as pv, reproduce as rp, figures

MANIFEST = pv.load_manifest()
_S = {}


def shared():
    """One bundle / metrics / result set for the whole module: the corpus is large."""
    if not _S:
        corpus = Corpus.demo()
        b = ex.AnalysisBundle(corpus, bootstrap="none")
        _S.update(corpus=corpus, bundle=b, metrics=pm.build(b))
    return _S


def check(m, check_pdf=False):
    return pv.verify(m, MANIFEST, check_pdf=check_pdf)


def status_of(res, cid):
    return next(r for r in res["claims"] if r["id"] == cid)["status"]


# --------------------------------------------------------------------------
class TestManifestIsNotAnalysisInput(unittest.TestCase):
    def test_no_analysis_module_reads_the_paper_manifest(self):
        allowed = {"verify.py", "reproduce.py", "cli.py", "api.py"}
        for f in (ROOT / "themis").rglob("*.py"):
            if f.name in allowed:
                continue
            self.assertFalse("paper_claims" in f.read_text(), f"{f} must not read the paper manifest")

    def test_experiments_and_metrics_do_not_import_the_verifier(self):
        for name in ("experiments.py", "metrics.py", "figures.py"):
            text = (ROOT / "themis" / "paper" / name).read_text()
            self.assertIsNone(re.search(r"import[^\n]*\bverify\b", text), name)
            self.assertFalse("yaml" in text, name)

    def test_manifest_structure(self):
        self.assertTrue(MANIFEST["claims"])
        for cid, c in MANIFEST["claims"].items():
            self.assertIn(c.get("class", "SUPPORTING_STABLE"), pv.CLASSES, cid)
            if "expected" in c or "min" in c:
                self.assertIn(c["comparison"], pv.COMPARISONS, cid)
        for cid in MANIFEST["required"]:
            self.assertIn(cid, MANIFEST["claims"])


@requires_reference_corpus
class TestGeneratedFromTheAnalysis(unittest.TestCase):
    def test_every_manifest_metric_is_produced_by_themis(self):
        m = shared()["metrics"]
        for cid, c in MANIFEST["claims"].items():
            if c.get("machine_checkable") is False or c["class"] == "DIAGNOSTIC":
                continue
            self.assertIn(c.get("metric", cid), m.values, cid)

    def test_pdf_manifest_and_themis_layers(self):
        res = pv.verify(shared()["metrics"], MANIFEST)
        pdf = res["pdf"]
        if pdf["status"] == "NOT_CHECKED":
            self.skipTest(pdf.get("reason"))
        self.assertEqual(pdf["status"], "PASS", res["pdf"])
        self.assertTrue(pdf["same_file_as_manifest"])

    def test_the_bundled_sample_can_never_yield_pass(self):
        s = shared()
        self.assertFalse(s["corpus"].full)
        res = check(s["metrics"])
        self.assertNotEqual(res["status"], "PASS")
        for r in res["claims"]:
            if r["basis"] in ("FROZEN_MANIFEST", "SAMPLE_OBSERVED") and r["status"] not in ("INFORMATIONAL", "NOT_MACHINE_CHECKABLE"):
                self.assertNotEqual(r["status"], "PASS", r["id"])

    def test_live_values_match_the_declared_values_that_do_reproduce(self):
        res = check(shared()["metrics"])
        for cid in ("circularity.rodwald_ransomwhere_shared", "circularity.montreal_ransomwhere", "circularity.montreal_tagpack",
                    "circularity.montreal_rodwald", "coverage.multi_dataset_addresses", "drift.D.coverage_vs_B", "drift.B.observations",
                    "circularity.rodwald.group.RSH"):
            self.assertEqual(status_of(res, cid), "PASS", cid)

    def test_a_real_mismatch_is_reported_as_a_mismatch(self):
        # Table 2 revenue: the bundled table is cent-rounded and differs from the paper's own artifact by a few dollars.
        # The verifier must say so, not hide it behind a tolerance.
        res = check(shared()["metrics"])
        for k in "ABCD":
            self.assertEqual(status_of(res, f"drift.{k}.revenue"), "FAIL", k)
        self.assertEqual(res["status"], "FAIL")


@requires_reference_corpus
class TestVerifierCatchesDrift(unittest.TestCase):
    """Phase 35: change one synthetic analysis result, expect FAIL, restore, expect the original verdict."""

    def mutated(self, key, value):
        m = copy.deepcopy(shared()["metrics"])
        m.values[key] = value
        return m

    def test_rodwald_shared_count_7508_to_7507(self):
        key = "circularity.rodwald_ransom.in.ransomwhere.shared_addresses"
        base = shared()["metrics"]
        self.assertEqual(status_of(check(base), "circularity.rodwald_ransomwhere_shared"), "PASS")
        res = check(self.mutated(key, 7507))
        self.assertEqual(status_of(res, "circularity.rodwald_ransomwhere_shared"), "FAIL")
        self.assertEqual(status_of(res, "circularity.rodwald_ransomwhere_shared@abstract"), "FAIL")
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(status_of(check(base), "circularity.rodwald_ransomwhere_shared"), "PASS")   # restored

    def test_a_drift_condition_result(self):
        res = check(self.mutated("drift.D.observations", 7456))
        self.assertEqual(status_of(res, "drift.D.observations"), "FAIL")
        self.assertEqual(status_of(check(shared()["metrics"]), "drift.D.observations"), "PASS")
        self.assertEqual(status_of(check(self.mutated("drift.D.coverage_vs_B", 0.1401)), "drift.D.coverage_vs_B"), "FAIL")

    def test_source_data_change_moves_the_generated_value(self):
        """Not just a metric: remove one Ransomwhere claim from the SOURCE data and the whole chain (corpus ->
        containment -> PaperMetrics -> verifier) must notice."""
        base = shared()["corpus"]
        drop = next(a for a in base.by_addr if {c["source"] for c in base.by_addr[a]} >= {"rodwald_ransom", "ransomwhere"})
        claims = [dict(c) for c in base.claims if not (c["address"] == drop and c["source"] == "ransomwhere")]
        for c in claims:                      # Corpus re-derives these itself
            c["address"] = c.get("raw_address", c["address"])
        m = pm.build(ex.AnalysisBundle(Corpus(claims, manifest=base.manifest), bootstrap="none"))
        self.assertEqual(m.values["circularity.rodwald_ransom.in.ransomwhere.shared_addresses"], 7507)
        res = check(m)
        self.assertEqual(status_of(res, "circularity.rodwald_ransomwhere_shared"), "FAIL")

    def test_config_change_moves_the_generated_value(self):
        """A parsing/provenance rule change (which letter marks inheritance) changes conclusion drift, and is detected."""
        from themis import analysis, provenance
        base = shared()["corpus"]
        cfg = analysis._cfg
        src = provenance._cfg.sources["rodwald_ransom"]["provenance"]["contains_rules"][0]
        original = src["contains"]
        try:
            src["contains"] = "H"                 # a different reading of the undocumented field
            c = Corpus([dict(x, address=x.get("raw_address", x["address"])) for x in base.claims], manifest=base.manifest)
            m = pm.build(ex.AnalysisBundle(c, bootstrap="none"))
        finally:
            src["contains"] = original
        self.assertNotEqual(m.values["drift.C.observations"], 42237)
        self.assertEqual(status_of(check(m), "drift.C.observations"), "FAIL")


@requires_reference_corpus
class TestOneSourceOfTruthForDrift(unittest.TestCase):
    """TABLE 2 = FIGURE 2 DATA = CLI DRIFT = API DRIFT = PAPER METRICS."""

    def test_all_surfaces_carry_the_same_drift_object(self):
        s = shared()
        table = {r["condition"]: r for r in ex.table2(s["bundle"])["rows"]}
        fig = {r["condition"]: r for r in figures.fig2_rows(s["bundle"])}
        cli = self.cli_drift()["conditions"]
        api = self.api_drift()["conditions"]
        m = s["metrics"].values
        for k in "ABCD":
            want = (table[k]["observations"], table[k]["addresses"], table[k]["revenue_usd"],
                    table[k]["ratio_vs_B"], table[k]["coverage_vs_B"])
            self.assertEqual(want, (fig[k]["claim_observations"], fig[k]["unique_addresses"], fig[k]["revenue_usd"],
                                    fig[k]["ratio_vs_B"], fig[k]["coverage_vs_B"]), f"figure {k}")
            self.assertEqual(want, tuple(cli[k][f] for f in ("observations", "addresses", "usd", "ratio_vs_B", "coverage_vs_B")), f"cli {k}")
            self.assertEqual(want, tuple(api[k][f] for f in ("observations", "addresses", "usd", "ratio_vs_B", "coverage_vs_B")), f"api {k}")
            self.assertEqual(want, tuple(m[f"drift.{k}.{f}"] for f in ("observations", "addresses", "revenue", "ratio_vs_B", "coverage_vs_B")), f"metrics {k}")

    def cli_drift(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "d.json"
            subprocess.run([sys.executable, "-m", "themis.cli", "--json", str(out), "drift"], cwd=ROOT, check=True,
                           capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT)))
            return json.loads(out.read_text())

    def api_drift(self):
        from fastapi.testclient import TestClient
        from themis.api import app
        c = TestClient(app)
        aid = c.post("/api/analysis/paper").json()["analysis_id"]
        return c.get(f"/api/analysis/{aid}/drift").json()


# --------------------------------------------------------------------------
@requires_reference_corpus
class TestRunDirectory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = rp.reproduce(corpus=shared()["corpus"], out_root=pathlib.Path(cls.tmp.name), run_id="test-run",
                               bootstrap="both", with_rq1=False, mirror=True)
        cls.d = pathlib.Path(cls.out["run_dir"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_self_contained_directory(self):
        for f in ("metadata.json", "source_manifest.json", "config_manifest.json", "paper_metrics.json", "verification.json",
                  "table1.csv", "table1.json", "table1.md", "table2.csv", "table2.json", "table2.md", "overlap_matrix.csv",
                  "source_depth.json", "rodwald_containment.csv", "montreal_recurrence.csv", "fig1a_data.csv", "fig1b_data.csv",
                  "fig2_data.csv", "currency.json", "unresolved_provenance.json", "anchors.json", "drift.json",
                  "condition_d_trace.json", "bootstrap_lower.json", "bootstrap_upper.json", "limitations.json",
                  "REPRODUCTION_REPORT.md", "PAPER_CLAIM_MAP.md"):
            self.assertTrue((self.d / f).is_file(), f)
        if figures.HAVE_MPL:
            for f in ("fig1a.png", "fig1b.png", "fig2.png", "fig2.pdf", "fig2.svg", "fig2.metadata.json"):
                self.assertTrue((self.d / f).is_file(), f)
        latest = pathlib.Path(self.tmp.name) / "paper_proof"
        self.assertTrue((latest / "table2.json").is_file())
        self.assertEqual((latest / "LATEST_RUN.txt").read_text().strip(), "test-run")

    def test_metadata_identifies_the_run(self):
        m = json.loads((self.d / "metadata.json").read_text())
        for k in ("software_version", "git", "analysis_date", "corpus_hash", "taxonomy_hash", "source_registry_hash",
                  "threshold_config_hash", "bootstrap", "paper_version"):
            self.assertTrue(m[k], k)
        self.assertEqual(m["analysis_date"], "2026-09-15")       # the declared date, never the wall clock
        self.assertEqual((m["bootstrap"]["seed"], m["bootstrap"]["iterations"]), (42, 2000))
        self.assertEqual(m["scope"], "BUNDLED_SAMPLE")

    def test_figure_data_is_the_table_data(self):
        t2 = json.loads((self.d / "table2.json").read_text())["rows"]
        with open(self.d / "fig2_data.csv") as f:
            fig = list(csv.DictReader(f))
        for a, b in zip(t2, fig):
            self.assertEqual(float(b["revenue_usd"]), a["revenue_usd"])
            self.assertEqual(int(b["claim_observations"]), a["observations"])

    @unittest.skipUnless(figures.HAVE_MPL, "matplotlib not installed")
    def test_figure_sidecar_names_its_computation(self):
        m = json.loads((self.d / "fig2.metadata.json").read_text())
        for k in ("figure", "input_artifact", "analysis_function", "software_version", "git_commit", "config_hash", "generated_at"):
            self.assertIn(k, m)
        self.assertEqual(m["input_artifact"], "fig2_data.json")

    def test_table1_is_generated_not_typed(self):
        t1 = json.loads((self.d / "table1.json").read_text())
        self.assertEqual(len(t1["rows"]), 7)
        self.assertEqual({r["basis"] for r in t1["rows"]}, {"LIVE", "FROZEN_MANIFEST"})     # the sample says which is which
        self.assertEqual(t1["total"]["basis"], "FROZEN_MANIFEST")

    def test_report_states_reproduction_not_truth_and_never_a_false_pass(self):
        rep = (self.d / "REPRODUCTION_REPORT.md").read_text()
        self.assertIn("does not prove that any attribution label is true", rep)
        self.assertNotIn("PAPER ↔ THEMIS: PASS", rep)
        self.assertEqual(self.out["status"], json.loads((self.d / "verification.json").read_text())["status"])

    def test_condition_d_trace_and_anchor_conclusion(self):
        d = json.loads((self.d / "condition_d_trace.json").read_text())
        self.assertEqual(d["retained_addresses"], 7457)
        self.assertEqual(d["addresses_meeting_no_criterion"], 0)
        self.assertIn("not independently re-verified", d["interpretation"])
        a = json.loads((self.d / "anchors.json").read_text())
        self.assertFalse(a["source_accuracy_robustly_estimable"])
        self.assertTrue(a["not_robustly_estimable_because"])
        self.assertEqual(a["label"], "AGREEMENT WITH OPEN ANCHOR SET")

    def test_source_depth_exposes_denominators_and_does_not_call_single_source_unreliable(self):
        s = json.loads((self.d / "source_depth.json").read_text())
        self.assertEqual(s["denominator_addresses"], 1_497_191)
        self.assertEqual(s["interpretation"], "NO PUBLIC CROSS-SOURCE CORROBORATION AVAILABLE")
        self.assertEqual(set(s["by_dataset_count"]), {"1", "2", "3", "4", "5+"})

    def test_overlap_is_labelled_coverage_not_correctness(self):
        o = json.loads((self.d / "overlap_matrix.json").read_text())
        self.assertEqual(o["label"], "COVERAGE")
        self.assertIn("CORRECTNESS", o["not_interpreted_as"])

    def test_rodwald_decode_derives_the_letter_it_was_not_told(self):
        d = ex.rodwald_containment(shared()["bundle"])["decodes"][0]
        self.assertEqual((d["dataset"], d["candidate"]), ("rodwald_ransom", "ransomwhere"))
        self.assertEqual(d["decoded_letters"], ["R"])
        self.assertEqual(d["well_formed_inside_candidate"]["addresses"], 7507)


# --------------------------------------------------------------------------
class TestMissingCorpus(unittest.TestCase):
    """Phase 30: no corpus means BLOCKED with instructions, never a PASS."""

    def setUp(self):
        self.empty = tempfile.TemporaryDirectory()
        self._old = os.environ.get("THEMIS_DATA_DIR")
        os.environ["THEMIS_DATA_DIR"] = self.empty.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("THEMIS_DATA_DIR", None)
        else:
            os.environ["THEMIS_DATA_DIR"] = self._old
        self.empty.cleanup()

    def test_reproduce_is_blocked_and_says_how_to_supply_the_data(self):
        with tempfile.TemporaryDirectory() as out:
            r = rp.reproduce(out_root=pathlib.Path(out), run_id="blocked")
            self.assertEqual(r["status"], "BLOCKED")
            self.assertEqual(r["reason"], "INPUT CORPUS NOT AVAILABLE")
            text = (pathlib.Path(r["run_dir"]) / "REPRODUCTION_REPORT.md").read_text()
            self.assertIn("BLOCKED", text)
            self.assertIn("build_corpus.py", text)
            self.assertNotIn("PASS", text.replace("nothing here is a PASS", ""))
            self.assertFalse((pathlib.Path(r["run_dir"]) / "verification.json").exists())
            self.assertIn(len(r["blocked"]["required"]["sources"]), (7,))

    def test_cli_exits_3_and_never_prints_pass(self):
        p = subprocess.run([sys.executable, "-m", "themis.cli", "reproduce-paper", "--no-rq1"], cwd=ROOT, capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(ROOT), THEMIS_DATA_DIR=self.empty.name, THEMIS_RESULTS_DIR=self.empty.name))
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("PAPER REPRODUCTION DATA REQUIRED", p.stdout)
        self.assertNotIn("PAPER ↔ THEMIS: PASS", p.stdout)

    def test_expected_output_files_alone_do_not_make_a_pass(self):
        # a frozen expected artifact (expected_output/) next to the code is not a reproduction
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(rp.reproduce(out_root=pathlib.Path(out))["status"], "BLOCKED")


# --------------------------------------------------------------------------
@requires_reference_corpus
class TestIndependentOracles(unittest.TestCase):
    """Written from the paper's definitions, using only csv/gzip/yaml: if the whole application were consistently
    wrong, agreement between it and these would still fail."""

    @classmethod
    def setUpClass(cls):
        import yaml
        strip = {}
        for f in (ROOT / "themis/config/sources").glob("*.yml"):
            c = yaml.safe_load(open(f))
            p = (c.get("address_normalization") or {}).get("strip_prefix")
            if p:
                strip[c["id"]] = p
        cls.by_src = {}
        with gzip.open(data_dir() / "observations_sample.csv.gz", "rt", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                a = r["address"]
                p = strip.get(r["source"])
                if p and a.startswith(p):
                    a = a[len(p):]
                cls.by_src.setdefault(r["source"], set()).add(a)

    def test_pairwise_overlap_counts(self):
        om = ex.overlap_matrix(shared()["bundle"])
        for p in om["pairs"]:
            self.assertEqual(p["intersection"], len(self.by_src[p["source_a"]] & self.by_src[p["source_b"]]),
                             (p["source_a"], p["source_b"]))

    def test_multi_dataset_address_count(self):
        seen = {}
        for s, addrs in self.by_src.items():
            for a in addrs:
                seen[a] = seen.get(a, 0) + 1
        self.assertEqual(sum(1 for n in seen.values() if n >= 2), shared()["metrics"].values["coverage.multi_dataset_addresses"])

    def test_trust_condition_arithmetic(self):
        rows = list(csv.DictReader(gzip.open(data_dir() / "revenue.csv.gz", "rt", encoding="utf-8-sig")))
        anchors = {ln.strip() for ln in gzip.open(data_dir() / "verified_anchors.txt.gz", "rt") if ln.strip()}
        rod = {r["address"] for r in rows if r["dataset"] == "rodwald_ransom"}
        rw = {r["address"] for r in rows if r["dataset"] == "ransomwhere"}
        best = {}
        for r in rows:
            best[r["address"]] = max(best.get(r["address"], 0.0), float(r["usd"]))
        inherited = {r["address"] for r in rows if r["dataset"] == "rodwald_ransom" and
                     ("R" in r["src_letters"] or r["family"].lower().startswith(("montreal", "padua", "princeton")))}
        keep_c = {a for a in best if not (a in inherited and a not in rw)}
        keep_d = {a for a in best if a in anchors}
        want = {"A": (len(rows), sum(float(r["usd"]) for r in rows)),
                "B": (len(best), sum(best.values())),
                "C": (len(keep_c), sum(best[a] for a in keep_c)),
                "D": (len(keep_d), sum(best[a] for a in keep_d))}
        got = shared()["bundle"].drift["conditions"]
        for k, (n, usd) in want.items():
            self.assertEqual(got[k]["observations"], n, k)
            self.assertAlmostEqual(got[k]["usd"], usd, delta=0.02, msg=k)
        self.assertEqual(len(rod & rw), shared()["bundle"].drift["shared_addresses"])

    def test_agreement_classification_matches_the_standalone_script(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("iac", ROOT / "scripts" / "independent_agreement_check.py")
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            iac = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(iac)
            n, tally = iac.run("frozen")
        finally:
            os.chdir(cwd)
        got = shared()["bundle"].agreement
        self.assertEqual(n, got["n_multi_source"])
        for k, v in got["outcomes"].items():
            self.assertEqual(tally.get(k, 0), v["n"], k)


if __name__ == "__main__":
    unittest.main()
