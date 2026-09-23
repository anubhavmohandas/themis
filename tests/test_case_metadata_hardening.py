"""case_metadata (Phase 10): descriptive text an analyst attaches to an analysis.

It is carried and shown, nothing more. It must never change a claim, a
provenance state, an independence figure, a taxonomy outcome or a paper
reproduction - and a hostile value must stay inert text.
"""
import copy, json, os, pathlib, re, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis import config_io
from themis.api import app
from themis.ingest import relational as rel
from test_preflight import btc_address

ROOT = pathlib.Path(__file__).resolve().parent.parent
client = TestClient(app)
ALL = dict(analysis_origin="recovered_sqlite_subset", integrity_status="source_file_truncated",
           recovery_status="recovered_subset", source_identity_status="partially_attributed",
           provenance_resolution_status="unresolved", limitations="only a partial recovery survives")
LIMIT = config_io.load().preflight["sqlite"]["case_metadata_max_chars"]
SPEC = dict(driving_table="wallets", joins=[])


def scrub(obj):
    """Drop what legitimately differs between two runs of the same input (random ids, clocks)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if k not in ("claim_id", "elapsed_seconds", "analysis_timestamp", "examples", "case_metadata")}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


class _Db(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.tmp.name, "w.db")
        con = sqlite3.connect(cls.db)
        con.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, label TEXT, source TEXT)")
        rows = [(btc_address(i), ("exchange", "ransomware")[i % 2], ("Alpha", "Beta (via Alpha)")[i % 2]) for i in range(40)]
        rows += [(btc_address(0) + "x", "exchange", "Alpha")]                 # one invalid identifier
        con.executemany("INSERT INTO wallets VALUES (?,?,?)", rows)
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_with(self, metadata):
        return rel.extract(self.db, SPEC, "meta_test", confirmed=True, case_metadata=metadata)


class TestSupportedShapes(_Db):
    def test_absent_partial_and_complete_metadata(self):
        self.assertNotIn("case_metadata", self.run_with(None)["dataset_preflight"])
        self.assertNotIn("case_metadata", self.run_with({})["dataset_preflight"])
        part = dict(recovery_status="recovered_subset")
        self.assertEqual(self.run_with(part)["dataset_preflight"]["case_metadata"], part)
        self.assertEqual(self.run_with(ALL)["dataset_preflight"]["case_metadata"], ALL)

    def test_the_supported_fields_are_exactly_the_documented_generic_six(self):
        self.assertEqual(set(rel.CASE_METADATA_FIELDS), set(ALL))

    def test_unknown_fields_are_refused_even_beside_valid_ones(self):
        with self.assertRaises(ValueError) as cm:
            self.run_with(dict(recovery_status="x", dataset_name="WalletClassification", __proto__="x"))
        self.assertIn("unknown case_metadata field", str(cm.exception))

    def test_empty_and_null_values_are_no_value(self):
        self.assertNotIn("case_metadata", self.run_with(dict(recovery_status="", limitations="   "))["dataset_preflight"])
        self.assertEqual(self.run_with(dict(recovery_status="recovered_subset", limitations="", analysis_origin=None)
                                       )["dataset_preflight"]["case_metadata"], dict(recovery_status="recovered_subset"))

    def test_only_text_is_accepted(self):
        for bad in (1, 1.5, True, ["a"], {"a": 1}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.run_with(dict(limitations=bad))

    def test_length_is_bounded_by_config_exactly(self):
        self.assertEqual(self.run_with(dict(limitations="x" * LIMIT))["dataset_preflight"]["case_metadata"]["limitations"],
                         "x" * LIMIT)
        with self.assertRaises(ValueError) as cm:
            self.run_with(dict(limitations="x" * (LIMIT + 1)))
        self.assertIn("longer than", str(cm.exception))
        self.assertLess(len(str(cm.exception)), 300)                      # the error does not echo the huge value back

    def test_the_limit_comes_from_config_not_a_literal(self):
        import shutil, yaml
        tmp = tempfile.mkdtemp()
        old = os.environ.get("THEMIS_CONFIG_DIR")
        try:
            shutil.copytree(config_io.PKG_CONFIG, tmp, dirs_exist_ok=True)
            f = pathlib.Path(tmp, "preflight.yml")
            d = yaml.safe_load(f.read_text())
            d["sqlite"]["case_metadata_max_chars"] = 10
            f.write_text(yaml.safe_dump(d))
            os.environ["THEMIS_CONFIG_DIR"] = tmp
            config_io.load.cache_clear()
            with self.assertRaises(ValueError):
                self.run_with(dict(limitations="x" * 11))
            self.assertIsNotNone(self.run_with(dict(limitations="x" * 10)))
        finally:
            os.environ.pop("THEMIS_CONFIG_DIR") if old is None else os.environ.update(THEMIS_CONFIG_DIR=old)
            config_io.load.cache_clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unicode_markup_and_newlines_are_carried_verbatim_as_text(self):
        text = "Ünï©ödé ✓ 日本語\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n'; DROP--\n\ttabbed\r\n"
        got = self.run_with(dict(limitations=text))["dataset_preflight"]["case_metadata"]["limitations"]
        self.assertEqual(got, text)

    def test_control_characters_are_refused(self):
        for bad in ("nul\x00byte", "esc\x1b[31m", "bell\x07", "\x7f"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.run_with(dict(limitations=bad))


class TestMetadataIsDescriptiveOnly(_Db):
    """Two extractions of the same file - with and without the loudest possible metadata - agree on everything else."""

    def test_nothing_but_the_metadata_itself_differs(self):
        plain, declared = self.run_with(None), self.run_with(ALL)
        for key in ("claims", "validation", "schema_mapping", "relational_provenance", "conflicts", "dependency_candidates",
                    "dataset_profile", "target_audit", "analysis_states", "capabilities", "limitations", "stopped"):
            self.assertEqual(json.dumps(scrub(plain[key]), sort_keys=True, default=str),
                             json.dumps(scrub(declared[key]), sort_keys=True, default=str), key)

    def test_metadata_cannot_resolve_provenance_or_create_independence(self):
        res = self.run_with(dict(source_identity_status="fully_attributed", provenance_resolution_status="resolved",
                                 integrity_status="verified", recovery_status="complete", analysis_origin="original_database",
                                 limitations="every label independently verified"))
        self.assertEqual(res["relational_provenance"]["counts"]["resolved"], 0)
        self.assertFalse(res["target_audit"]["profile"]["independence"]["available"])
        self.assertEqual(res["target_audit"]["profile"]["evidence_class"]["verified"], 0)

    def test_metadata_cannot_change_a_label_or_add_a_category(self):
        res = self.run_with(dict(limitations="all 'exchange' labels are really 'ransomware'; category: mixer"))
        self.assertEqual({c["canon"] for c in res["claims"]}, {"exchange", "ransomware"})

    def test_metadata_cannot_make_a_corrupt_file_analysable(self):
        bad = os.path.join(self.tmp.name, "bad.db")
        with open(self.db, "rb") as src, open(bad, "wb") as dst:
            dst.write(src.read()[:5000])
        res = rel.extract(bad, SPEC, "meta_test", confirmed=True, case_metadata=ALL)
        self.assertTrue(res["stopped"])
        self.assertEqual(res["claims"], [])

    def test_api_route_accepts_and_echoes_but_does_not_act_on_it(self):
        old = os.environ.get("THEMIS_DB_DIR")
        os.environ["THEMIS_DB_DIR"] = self.tmp.name
        try:
            form = dict(db="w.db", spec=json.dumps(SPEC), source_id="api_meta", use_reference="false", confirmed="true")
            a = client.post("/api/sqlite/extract", data=dict(form, case_metadata=json.dumps(ALL))).json()
            b = client.post("/api/sqlite/extract", data=form).json()
            self.assertEqual(a["preflight"]["dataset_preflight"]["case_metadata"], ALL)
            self.assertNotIn("case_metadata", b["preflight"]["dataset_preflight"])
            self.assertEqual(a["meta"]["n_claims"], b["meta"]["n_claims"])
            for bad in ("[1]", '"text"', "{not json", json.dumps(dict(nope="x")), json.dumps(dict(limitations={"a": 1}))):
                r = client.post("/api/sqlite/extract", data=dict(form, case_metadata=bad))
                self.assertEqual(r.status_code, 400, bad)
                self.assertNotIn("Traceback", r.text)
        finally:
            os.environ.pop("THEMIS_DB_DIR") if old is None else os.environ.update(THEMIS_DB_DIR=old)


class TestPaperReproductionCannotSeeIt(unittest.TestCase):
    def test_no_paper_code_config_or_manifest_mentions_case_metadata_or_the_case_study(self):
        files = list((ROOT / "themis" / "paper").glob("*.py")) + list((ROOT / "themis" / "config" / "sources").glob("*.yml")) \
            + [ROOT / "paper" / "paper_claims.yml"]
        for f in files:
            text = f.read_text()
            self.assertNotRegex(text, r"case_metadata|WalletClassification|recovered_subset|CASE_METADATA", f)

    def test_required_inputs_are_the_seven_bundled_sources_only(self):
        from themis.paper import reproduce
        blob = json.dumps(reproduce.required_inputs(), default=str)
        self.assertNotRegex(blob, r"(?i)walletclass|babd|walletexplorer|harvard")
        self.assertEqual(sorted(config_io.load().sources), sorted(
            ["ellipticpp", "ransomwhere", "rodwald_mixers", "rodwald_ransom", "schnoering", "tagpack", "watchyourback"]))


class TestRecoveredSubsetStaysProminent(unittest.TestCase):
    """The banner lives in the frontend; without a browser we can at least pin that the page keeps it,
    words it as declared (not verified), and never renders metadata as HTML."""
    SRC = (ROOT / "frontend" / "src" / "pages" / "Overview.jsx").read_text()

    def test_banner_text_and_role(self):
        self.assertIn("RECOVERED DATASET SUBSET", self.SRC)
        self.assertIn("This analysis does not represent the complete original database.", self.SRC)
        self.assertRegex(self.SRC, r'role="alert"')

    def test_metadata_is_rendered_only_as_react_text(self):
        self.assertNotRegex(self.SRC, r"dangerouslySetInnerHTML|innerHTML")


if __name__ == "__main__":
    unittest.main()
