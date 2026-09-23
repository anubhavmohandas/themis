"""Every scientific parameter is read from config/*.yml, not a literal in code.

Each test changes ONE config value in a scratch copy of the config tree and
asserts the behaviour follows it - the only way to tell a real config read
from a literal that happens to equal the config's current value. A test that
passes with the value at its default proves nothing, so each asserts both.
"""
import contextlib, io, os, pathlib, shutil, sqlite3, sys, tempfile, unittest
import yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from themis import config_io, target_audit
from themis.ingest import detect, preflight, relational as rel
from test_preflight import btc_address
from test_relational import make_relational_db
from _data import requires_reference_corpus


@contextlib.contextmanager
def config_with(filename: str, edit):
    """The active config, with `edit(parsed_yaml)` applied to one file of a scratch copy."""
    tmp = tempfile.mkdtemp()
    old = os.environ.get("THEMIS_CONFIG_DIR")
    try:
        shutil.copytree(config_io.PKG_CONFIG, tmp, dirs_exist_ok=True)
        path = pathlib.Path(tmp) / filename
        data = yaml.safe_load(path.read_text())
        edit(data)
        path.write_text(yaml.safe_dump(data))
        os.environ["THEMIS_CONFIG_DIR"] = tmp
        config_io.load.cache_clear()
        yield
    finally:
        os.environ.pop("THEMIS_CONFIG_DIR") if old is None else os.environ.update(THEMIS_CONFIG_DIR=old)
        config_io.load.cache_clear()
        shutil.rmtree(tmp, ignore_errors=True)


def setkey(*keys, value):
    def edit(d):
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = value
    return edit


class TestPreflightParameters(unittest.TestCase):
    ROWS = [dict(a=btc_address(i), n=str(i * 7 + 3)) for i in range(20)]

    def _note(self):
        r = preflight.run(self.ROWS, ["a", "n"], overrides={"n": "attribution_label"})   # numbers are a 0% fit for a label
        return next(c for c in r["columns"] if c["column"] == "n")["notes"]

    def test_a_poor_fit_note_uses_review_confidence_not_a_literal(self):
        self.assertTrue(any("look unlike" in n for n in self._note()))          # default 0.5: 0% fit is below it
        with config_with("preflight.yml", setkey("review_confidence", value=0.0)):
            self.assertEqual(self._note(), [])                                  # nothing is below 0.0

    def test_a_counter_needs_min_sequence_sample_values(self):
        self.assertFalse(preflight._Profile("c", ["0", "1"]).sequential)
        self.assertTrue(preflight._Profile("c", ["0", "1", "2"]).sequential)
        with config_with("preflight.yml", setkey("min_sequence_sample", value=2)):
            self.assertTrue(preflight._Profile("c", ["0", "1"]).sequential)
        with config_with("preflight.yml", setkey("min_sequence_sample", value=5)):
            self.assertFalse(preflight._Profile("c", ["0", "1", "2"]).sequential)

    def test_unsupported_chain_needs_min_sample_values(self):
        two, three = ["A" * 30, "B" * 30], ["A" * 30, "B" * 30, "C" * 30]
        self.assertFalse(detect._looks_like_unrecognized_address(two))
        self.assertTrue(detect._looks_like_unrecognized_address(three))
        with config_with("preflight.yml", setkey("detect", "unsupported_chain_shape", "min_sample", value=2)):
            self.assertTrue(detect._looks_like_unrecognized_address(two))
        with config_with("preflight.yml", setkey("detect", "unsupported_chain_shape", "min_sample", value=4)):
            self.assertFalse(detect._looks_like_unrecognized_address(three))


class TestRelationalParameters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.dir.name, "rel.db")
        make_relational_db(cls.db)
        con = sqlite3.connect(cls.db)          # an unindexed foreign key on a table of 30 rows
        con.execute("CREATE TABLE tags (tag TEXT, note TEXT)")
        con.executemany("INSERT INTO tags VALUES (?,?)", [(f"t{i}", "x") for i in range(30)])
        con.execute("CREATE TABLE lut (k INTEGER PRIMARY KEY, payload TEXT)")     # small, keyed, no claim columns
        con.executemany("INSERT INTO lut VALUES (?,?)", [(i, "p") for i in range(5)])
        con.execute("CREATE TABLE plain_wallets (address TEXT, tag TEXT)")
        con.executemany("INSERT INTO plain_wallets VALUES (?,?)", [(btc_address(i), f"t{i % 30}") for i in range(30)])
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def role(self, table):
        return next(c for c in rel.candidate_roles(self.db) if c["table"] == table)

    def test_lookup_table_rank_comes_from_config(self):
        self.assertEqual(self.role("lut")["role"], "lookup_or_provenance")
        self.assertEqual(self.role("lut")["confidence"], 0.5)
        with config_with("preflight.yml", setkey("sqlite", "lookup_role_confidence", value=0.31)):
            self.assertEqual(self.role("lut")["confidence"], 0.31)

    def test_inferred_relationship_rank_comes_from_config(self):
        def inferred():
            return [r for r in rel.infer_relationships(self.db) if r["kind"] == "inferred"]
        base = inferred()
        self.assertTrue(base, "the fixture should propose at least one undeclared relationship")
        self.assertEqual({r["confidence"] for r in base}, {0.6})
        with config_with("preflight.yml", setkey("sqlite", "inferred_relationship_confidence", value=0.77)):
            self.assertEqual({r["confidence"] for r in inferred()}, {0.77})

    def test_a_declared_foreign_key_is_never_ranked_by_those_settings(self):
        with config_with("preflight.yml", setkey("sqlite", "inferred_relationship_confidence", value=0.1)):
            declared = [r for r in rel.infer_relationships(self.db) if r["kind"] == "declared"]
        self.assertTrue(declared)
        self.assertEqual({r["confidence"] for r in declared}, {1.0})

    def test_unindexed_join_warning_threshold_comes_from_config(self):
        spec = dict(driving_table="plain_wallets", joins=[dict(table="tags", local_key="tag", foreign_key="tag")])
        self.assertEqual(rel.validate_join_spec(self.db, spec)["warnings"], [])            # 30 rows < 1000
        with config_with("preflight.yml", setkey("sqlite", "unindexed_join_warn_rows", value=10)):
            self.assertEqual(len(rel.validate_join_spec(self.db, spec)["warnings"]), 1)    # 30 rows > 10

    def test_dependency_candidate_minimum_length_comes_from_config(self):
        pair = ["AB", "AB (via CD)"]                      # "AB" is 2 characters
        self.assertEqual(rel.dependency_candidates(pair), [])
        with config_with("preflight.yml", setkey("sqlite", "dependency_min_descriptor_length", value=2)):
            self.assertEqual([(d["citing"], d["cited"]) for d in rel.dependency_candidates(pair)],
                             [("AB (via CD)", "AB")])
        with config_with("preflight.yml", setkey("sqlite", "dependency_min_descriptor_length", value=20)):
            self.assertEqual(rel.dependency_candidates(["DemoCorpus-13", "DemoCorpus-13 (labels via DemoExplorer)"]), [])


class TestTargetAuditParameter(unittest.TestCase):
    CLAIMS = [dict(prov_family="see the abc paper", source_url="", notes="")]
    SOURCES = {"zz": dict(display_name="abc")}          # a 3-character name; the id "zz" is 2

    def test_a_short_source_name_matches_only_at_the_configured_length(self):
        self.assertEqual(target_audit._naming_residue(self.CLAIMS, self.SOURCES), {})              # 3 < 4
        with config_with("preflight.yml", setkey("target_audit", "min_source_name_length", value=3)):
            self.assertEqual(target_audit._naming_residue(self.CLAIMS, self.SOURCES), {"zz": 1})


@requires_reference_corpus
class TestConsoleDecodeLimit(unittest.TestCase):
    """thresholds.yml's decode_report_limit was documented but never read; the console printed 12."""

    def _groups_printed(self):
        from themis import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["audit"])
        return sum(1 for ln in buf.getvalue().splitlines() if ln.startswith("    group "))

    def test_limit_comes_from_config(self):
        default = self._groups_printed()
        with config_with("thresholds.yml", setkey("decode_report_limit", value=1)):
            limited = self._groups_printed()
        self.assertGreater(default, limited)
        self.assertGreaterEqual(limited, 1)


if __name__ == "__main__":
    unittest.main()
