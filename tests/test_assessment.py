"""The closing verdict (themis/assessment.py): each verdict is reachable, follows the cut-offs in
config/assessment.yml rather than a literal, and never promotes absent evidence to trust."""
import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from themis import assessment as A, target_audit
from test_config_driven_parameters import config_with, setkey


def result(n_addr=100, n_rej=0, contradictions=0, comparable=80, agree=79, conflict=1, unresolved=0, same=0, stale_share=0.0):
    """The slice of an ingest result that assess() reads."""
    outcomes = {k: dict(n=0) for k in ("exact", "hierarchical refinement", "entity-type conflict",
                                        "licit/illicit conflict", "incomparable")}
    outcomes["exact"]["n"], outcomes["licit/illicit conflict"]["n"] = agree, conflict
    cmp_ = {f"a{i}": (target_audit.SAME_PROVENANCE if i < same else target_audit.DISTINCT_PROVENANCE) for i in range(comparable)}
    return dict(
        stopped=False, validation=dict(n_input=n_addr, n_rejected=n_rej), claims=[dict(canon="exchange")] * n_addr,
        internal_consistency={"internal contradiction": dict(n=contradictions)},
        analysis_states=dict(staleness=dict(state="computed")),
        target_audit=dict(n_target_addresses=n_addr, n_target_claims=n_addr, address_comparability=cmp_, profile=dict(
            reference_comparability=dict(available=True, comparable=comparable, comparable_share=comparable / n_addr,
                                         no_reference_match_share=1 - comparable / n_addr),
            agreement=dict(available=True, outcomes=outcomes),
            provenance=dict(available=True, unresolved=unresolved),
            currency=dict(available=True, n_claims=n_addr, stale=int(stale_share * n_addr), stale_share=stale_share))))


class TestVerdicts(unittest.TestCase):
    def verdict(self, **kw):
        return A.assess(result(**kw))["verdict_id"]

    def test_clean_evidence_is_supported(self):
        self.assertEqual(self.verdict(conflict=0, agree=80), A.SUPPORTED)

    def test_a_limit_the_reader_must_carry_is_a_caveat(self):
        self.assertEqual(self.verdict(conflict=0, agree=80, unresolved=60), A.WITH_CAVEATS)
        self.assertEqual(self.verdict(conflict=0, agree=80, same=60), A.WITH_CAVEATS)      # inherited, not independent
        self.assertEqual(self.verdict(conflict=0, agree=80, stale_share=0.9), A.WITH_CAVEATS)

    def test_measured_problems_are_concerns(self):
        self.assertEqual(self.verdict(conflict=20, agree=60), A.CONCERNS)           # 25% of judged pairs conflict
        self.assertEqual(self.verdict(contradictions=5, conflict=0, agree=80), A.CONCERNS)
        self.assertEqual(self.verdict(n_rej=30, conflict=0, agree=80), A.CONCERNS)

    def test_no_external_evidence_is_never_support(self):
        self.assertEqual(self.verdict(comparable=5, agree=5, conflict=0), A.NOT_ESTABLISHED)
        # ...but a proven internal problem still outranks a lack of evidence
        self.assertEqual(self.verdict(comparable=5, agree=5, conflict=0, contradictions=5), A.CONCERNS)

    def test_a_stopped_dataset_cannot_be_assessed_and_says_why(self):
        a = A.assess(dict(stopped=True, message="Unsupported dataset.\n\nMore text."))
        self.assertEqual(a["verdict_id"], A.CANNOT_ASSESS)
        self.assertIn("Unsupported dataset.", a["statement"])
        self.assertNotIn("More text", a["statement"])

    def test_the_statement_carries_the_verdict_and_its_measured_reasons(self):
        s = A.assess(result(conflict=20, agree=60))["statement"]
        self.assertTrue(s.startswith("According to the THEMIS report, the assessment of this dataset is EVIDENCE CONCERNS, because:"))
        self.assertIn("20 (25.0%) conflict", s)


class TestLabelsComeFromConfig(unittest.TestCase):
    IDS = (A.SUPPORTED, A.WITH_CAVEATS, A.NOT_ESTABLISHED, A.CONCERNS, A.CANNOT_ASSESS)

    def test_every_outcome_has_a_distinct_label_and_none_claims_trust(self):
        labels = A.config_io.load().assessment["labels"]
        self.assertEqual(set(labels), set(self.IDS))
        self.assertEqual(len(set(labels.values())), len(self.IDS))
        self.assertFalse([v for v in labels.values() if "TRUST" in v.upper()])

    def test_the_reader_sees_the_configured_label_everywhere(self):
        r = result(conflict=20, agree=60)
        with config_with("assessment.yml", setkey("labels", "concerns", value="RENAMED IN CONFIG")):
            a = A.assess(r)
        self.assertEqual((a["verdict_id"], a["verdict"]), (A.CONCERNS, "RENAMED IN CONFIG"))
        self.assertIn(f'{a["lead"]} RENAMED IN CONFIG, because:', a["statement"])


class TestCutoffsComeFromConfig(unittest.TestCase):
    def test_the_conflict_cutoff_is_read_from_assessment_yml(self):
        r = result(conflict=20, agree=60)
        self.assertEqual(A.assess(r)["verdict_id"], A.CONCERNS)
        with config_with("assessment.yml", setkey("reference_conflict_share", "fail", value=0.5)):
            self.assertEqual(A.assess(r)["verdict_id"], A.WITH_CAVEATS)

    def test_the_evidence_floor_is_read_from_assessment_yml(self):
        r = result(comparable=5, agree=5, conflict=0)
        self.assertEqual(A.assess(r)["verdict_id"], A.NOT_ESTABLISHED)
        with config_with("assessment.yml", setkey("min_comparable_addresses", value=5)):
            self.assertNotEqual(A.assess(r)["verdict_id"], A.NOT_ESTABLISHED)


if __name__ == "__main__":
    unittest.main()
