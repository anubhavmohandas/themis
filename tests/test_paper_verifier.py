"""The verifier itself can be wrong, so it is tested: it must pass what matches,
fail what differs, and never be always-green. Synthetic metrics and manifests, so
none of this needs the reference corpus."""
import math, pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.paper import verify as pv
from themis.paper.metrics import PaperMetrics, LIVE, FROZEN, SAMPLE_OBSERVED


def metrics(**kv):
    m = PaperMetrics()
    for k, v in kv.items():
        m.put(k.replace("__", "."), v, LIVE)
    return m


def manifest(claims, policy=None, required=None):
    return dict(paper=dict(title="t", file="none.pdf"), claims=claims, required=required or [],
                policy=policy or {}, experiments={})


def claim(expected=None, comparison="exact_integer", cls="HEADLINE_STABLE", **kw):
    d = {"class": cls, "section": "5", "text": "x", "comparison": comparison}
    if expected is not None:
        d["expected"] = expected
    d.update(kw)
    return d


def run(m, claims, **kw):
    return pv.verify(m, manifest(claims, **kw), check_pdf=False)


class TestComparisons(unittest.TestCase):
    def test_matching_value_passes(self):
        r = run(metrics(a__b=7508), {"a.b": claim(7508)})
        self.assertEqual((r["claims"][0]["status"], r["status"]), ("PASS", "PASS"))

    def test_differing_value_fails_and_fails_the_run(self):
        r = run(metrics(a__b=7507), {"a.b": claim(7508)})
        self.assertEqual((r["claims"][0]["status"], r["status"]), ("FAIL", "FAIL"))
        self.assertEqual(r["claims"][0]["delta"], -1.0)

    def test_exact_integer_has_no_hidden_tolerance(self):
        self.assertEqual(run(metrics(a__b=1101304942.45), {"a.b": claim(1101304945)})["status"], "FAIL")
        self.assertEqual(run(metrics(a__b=1101304945.31), {"a.b": claim(1101304945)})["status"], "PASS")   # paper's own rounding
        self.assertEqual(run(metrics(a__b=1.5), {"a.b": claim(2)})["status"], "PASS")                     # half rounds up
        self.assertEqual(run(metrics(a__b=2.5), {"a.b": claim(2)})["status"], "FAIL")

    def test_rounded_percent(self):
        c = claim(0.9897, "rounded_percent", decimals=2)
        self.assertEqual(run(metrics(a__b=0.98968), {"a.b": c})["status"], "PASS")     # 98.968 -> 98.97
        self.assertEqual(run(metrics(a__b=0.98964), {"a.b": c})["status"], "FAIL")     # 98.964 -> 98.96
        self.assertEqual(run(metrics(a__b=0.13809), {"a.b": claim(0.138, "rounded_percent", decimals=1)})["status"], "PASS")

    def test_rounded_percent_rounds_half_up_not_to_even(self):
        c = claim(0.0125, "rounded_percent", decimals=1)                               # 1.25% -> 1.3, not banker's 1.2
        self.assertEqual(run(metrics(a__b=0.0125), {"a.b": c})["status"], "PASS")

    def test_rounded_decimal_with_scale(self):
        c = claim(1.101, "rounded_decimal", decimals=3, scale=1e-9)
        self.assertEqual(run(metrics(a__b=1101304942.45), {"a.b": c})["status"], "PASS")
        self.assertEqual(run(metrics(a__b=1102304942.45), {"a.b": c})["status"], "FAIL")

    def test_range(self):
        c = claim(None, "range", min=0.995, max=1.0)
        self.assertEqual(run(metrics(a__b=0.9948), {"a.b": c})["status"], "FAIL")
        self.assertEqual(run(metrics(a__b=0.9951), {"a.b": c})["status"], "PASS")

    def test_exact_string_and_bool(self):
        self.assertEqual(run(metrics(a__b=False), {"a.b": claim(False, "exact_string")})["status"], "PASS")
        self.assertEqual(run(metrics(a__b=True), {"a.b": claim(False, "exact_string")})["status"], "FAIL")

    def test_a_bool_is_not_an_integer(self):
        self.assertEqual(run(metrics(a__b=True), {"a.b": claim(1)})["status"], "FAIL")


class TestDisplay(unittest.TestCase):
    def test_declared_values_are_not_rescaled_but_generated_ones_are(self):
        row = dict(comparison="approximate_text", decimals=1, scale=1e-6)
        self.assertEqual(pv.show(1.5, row, declared=True), "1.5")
        self.assertEqual(pv.show(1497191, row), "1.5")
        self.assertEqual(pv.show(0.98968, dict(comparison="rounded_percent", decimals=2)), "98.97%")


class TestBadInputsFail(unittest.TestCase):
    def test_missing_metric_fails(self):
        r = run(metrics(other=1), {"a.b": claim(1)})
        self.assertEqual(r["claims"][0]["status"], "FAIL")
        self.assertIn("not produced", r["claims"][0]["detail"])
        self.assertEqual(r["status"], "FAIL")

    def test_nan_and_infinity_fail(self):
        for bad in (math.nan, math.inf):
            self.assertEqual(run(metrics(a__b=bad), {"a.b": claim(1)})["status"], "FAIL", bad)
            self.assertEqual(run(metrics(a__b=bad), {"a.b": claim(0.5, "rounded_percent", decimals=1)})["status"], "FAIL", bad)

    def test_non_numeric_value_for_a_numeric_rule_fails(self):
        self.assertEqual(run(metrics(a__b="7508"), {"a.b": claim(7508)})["status"], "FAIL")

    def test_unknown_rule_or_class_fails_rather_than_passing_silently(self):
        self.assertEqual(run(metrics(a__b=1), {"a.b": claim(1, "close_enough")})["status"], "FAIL")
        self.assertEqual(run(metrics(a__b=1), {"a.b": claim(1, cls="WHATEVER")})["status"], "FAIL")

    def test_a_required_claim_absent_from_the_manifest_fails(self):
        r = run(metrics(a__b=1), {"a.b": claim(1)}, required=["a.b", "corpus.claims"])
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("corpus.claims", r["failing"])


class TestClassPolicy(unittest.TestCase):
    POLICY = {"HEADLINE_STABLE": dict(on_fail="fail", on_not_reproduced="block"),
              "DIAGNOSTIC": dict(on_fail="ignore", on_not_reproduced="ignore")}

    def test_headline_failure_fails_the_run_even_if_everything_else_passes(self):
        r = run(metrics(a=1, b=1, c=9), {"a": claim(1), "b": claim(1), "c": claim(2)}, policy=self.POLICY)
        self.assertEqual(r["status"], "FAIL")

    def test_diagnostic_failure_is_governed_by_the_manifest_policy(self):
        cl = {"a": claim(1), "d": claim(2, cls="DIAGNOSTIC")}
        self.assertEqual(run(metrics(a=1, d=99), cl, policy=self.POLICY)["status"], "PASS")
        strict = dict(self.POLICY, DIAGNOSTIC=dict(on_fail="fail", on_not_reproduced="ignore"))
        self.assertEqual(run(metrics(a=1, d=99), cl, policy=strict)["status"], "FAIL")

    def test_a_claim_with_no_declared_value_is_informational_not_a_pass(self):
        r = run(metrics(a=5), {"a": claim(None, None, cls="DIAGNOSTIC")})
        self.assertEqual(r["claims"][0]["status"], "INFORMATIONAL")

    def test_not_machine_checkable_is_reported_as_such(self):
        r = run(metrics(), {"q": claim(None, None, machine_checkable=False, reason="a licensing statement")})
        self.assertEqual(r["claims"][0]["status"], "NOT_MACHINE_CHECKABLE")


class TestFrozenIsNotReproduced(unittest.TestCase):
    def frozen(self, v, basis):
        m = PaperMetrics()
        m.put("a", v, basis)
        return m

    def test_a_frozen_figure_that_matches_is_not_a_pass(self):
        r = run(self.frozen(1545710, FROZEN), {"a": claim(1545710)})
        self.assertEqual(r["claims"][0]["status"], "NOT_REPRODUCED")
        self.assertTrue(r["claims"][0]["frozen_agrees"])
        self.assertEqual(r["status"], "BLOCKED")           # never PASS

    def test_a_frozen_figure_that_disagrees_fails(self):
        self.assertEqual(run(self.frozen(1545711, FROZEN), {"a": claim(1545710)})["status"], "FAIL")

    def test_a_sampled_value_is_never_compared(self):
        r = run(self.frozen(0.86, SAMPLE_OBSERVED), {"a": claim(0.67, "rounded_percent", decimals=1)})
        self.assertEqual((r["claims"][0]["status"], r["status"]), ("NOT_REPRODUCED", "BLOCKED"))

    def test_a_failure_outranks_blocked(self):
        m = PaperMetrics(); m.put("a", 1, FROZEN); m.put("b", 1, LIVE)
        self.assertEqual(run(m, {"a": claim(1), "b": claim(2)})["status"], "FAIL")


class TestPdfLayer(unittest.TestCase):
    PAGES = ["Elliptic++ [14]        822,937        822,937   Not disclosed   No\n"
             "B - address\n                     54,000     54,000    1,101,304,945    1.00x   100.0%\ndeduplication\n"
             "98.97% of addresses occur in\nonly one dataset"]

    def check(self, claim_, pages=None):
        return pv.check_pdf_claim(claim_, pages or self.PAGES)["status"]

    def test_phrase_is_tied_to_the_manifest_value(self):
        c = claim(0.9897, "rounded_percent", decimals=2, pdf=dict(text="{v} of addresses occur in only one dataset"))
        self.assertEqual(self.check(c), "PASS")
        c["expected"] = 0.9898                       # manifest edited, PDF forgotten
        self.assertEqual(self.check(c), "FAIL")

    def test_pdf_edited_manifest_forgotten_fails_too(self):
        c = claim(0.9897, "rounded_percent", decimals=2, pdf=dict(text="{v} of addresses occur in only one dataset"))
        self.assertEqual(self.check(c, [self.PAGES[0].replace("98.97%", "97.89%")]), "FAIL")

    def test_table_row_and_wrapped_row(self):
        self.assertEqual(self.check(claim(822937, pdf=dict(row="Elliptic++ [14]", col=1))), "PASS")
        self.assertEqual(self.check(claim(1101304945, pdf=dict(row="B - address", col=3))), "PASS")   # figures on the next line
        self.assertEqual(self.check(claim(1101304946, pdf=dict(row="B - address", col=3))), "FAIL")

    def test_a_locator_without_the_value_placeholder_is_refused(self):
        self.assertEqual(self.check(claim(1, pdf=dict(text="only one dataset"))), "FAIL")

    def test_missing_pdf_is_reported_not_checked_never_passed(self):
        m = manifest({"a": claim(1)})
        m["paper"] = dict(file="definitely-not-there.pdf")
        self.assertEqual(pv.verify_pdf(m, "/nonexistent.pdf")["status"], "NOT_CHECKED")

    def test_a_wrong_path_never_falls_back_to_a_different_paper(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            other = pathlib.Path(d) / "other.pdf"; other.write_bytes(b"%PDF-1.4 not the paper asked for")
            os.environ["THEMIS_PAPER_PDF"] = str(other)          # a fallback that DOES exist
            try:
                r = pv.verify_pdf(manifest({"a": claim(1)}), "/nonexistent.pdf")
            finally:
                del os.environ["THEMIS_PAPER_PDF"]
        self.assertEqual(r["status"], "NOT_CHECKED")
        self.assertIn("does not exist", r["reason"])


if __name__ == "__main__":
    unittest.main()
