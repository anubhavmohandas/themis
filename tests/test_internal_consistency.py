"""WITHIN-DATASET / INTERNAL LABEL CONTRADICTION: does the same normalized subject (chain, address)
carry mutually incompatible labels inside ONE source's own claims? This is deliberately a different
question from `taxonomy.classify_address` / `classify_target_address` (cross-SOURCE agreement, which
requires >= 2 distinct sources by design and is blind to a single source repeating or contradicting
itself). Every fixture here is synthetic and names no real dataset; the categories used
(`exchange`, `ransomware`, `illicit_unspec`, `mixer`) are generic taxonomy entries already exercised
by the existing relational-conflict tests, not vocabulary invented for any one file.
"""
import os, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from themis import taxonomy
from themis.ingest import relational
from test_preflight import btc_address, to_csv, write_tmp
from themis.ingest import pipeline

BASE = dict(source="upload", lastmod="", heuristic="", subcat="")


def claim(i, canon, address=None, blockchain="bitcoin", raw=None, source="upload", claim_id=None):
    return dict(BASE, claim_id=claim_id if claim_id is not None else i, address=address or btc_address(1),
                blockchain=blockchain, canon=canon, raw_label=raw if raw is not None else canon, source=source)


class TestInternalConsistencyTaxonomy(unittest.TestCase):
    """Direct unit tests of `taxonomy.internal_consistency`, one per required scenario."""

    def _n(self, claims):
        return {k: v["n"] for k, v in taxonomy.internal_consistency(claims).items()}

    def test_same_subject_same_label_is_a_repeated_observation(self):
        a = btc_address(1)
        claims = [claim(1, "exchange", a, raw="exchange"), claim(2, "exchange", a, raw="exchange")]
        counts = self._n(claims)
        self.assertEqual(counts["repeated observation"], 1)
        self.assertEqual(counts["repeated same label"], 0)
        self.assertEqual(counts["compatible multi-label claim"], 0)
        self.assertEqual(counts["internal contradiction"], 0)

    def test_same_subject_repeated_time_windows_is_repeated_same_label_not_a_contradiction(self):
        # two observations of the same address+label, at different times (a different raw
        # spelling stands in for "the file said this again on another day" - THEMIS's own
        # claims never carry the day/time dimension, see BitcoinHeistData §9)
        a = btc_address(2)
        claims = [claim(1, "exchange", a, raw="exchange"), claim(2, "exchange", a, raw="Exchange (seen again)")]
        counts = self._n(claims)
        self.assertEqual(counts["repeated observation"], 0)
        self.assertEqual(counts["repeated same label"], 1)
        self.assertEqual(counts["internal contradiction"], 0)

    def test_same_subject_compatible_labels_is_a_compatible_multi_label_claim(self):
        # a generic placeholder plus a specific descendant on the same branch refines, it does
        # not contradict - the same rule classify_address applies cross-source
        a = btc_address(3)
        claims = [claim(1, "illicit_unspec", a), claim(2, "ransomware", a)]
        counts = self._n(claims)
        self.assertEqual(counts["compatible multi-label claim"], 1)
        self.assertEqual(counts["internal contradiction"], 0)
        self.assertEqual(counts["repeated same label"], 0)

    def test_same_subject_incompatible_labels_is_an_internal_contradiction(self):
        a = btc_address(4)
        claims = [claim(1, "exchange", a), claim(2, "ransomware", a)]
        counts = self._n(claims)
        self.assertEqual(counts["internal contradiction"], 1)
        self.assertEqual(counts["compatible multi-label claim"], 0)

    def test_same_address_string_on_different_chains_is_two_subjects_not_a_contradiction(self):
        # the same literal address text, one claim on bitcoin, one on a different chain: two
        # distinct (chain, address) subjects, so this must never surface as a contradiction
        addr_text = btc_address(5)
        claims = [claim(1, "exchange", addr_text, blockchain="bitcoin"),
                  claim(2, "ransomware", addr_text, blockchain="litecoin")]
        counts = self._n(claims)
        self.assertEqual(sum(counts.values()), 0)

    def test_a_single_observation_is_not_repetition_or_contradiction(self):
        counts = self._n([claim(1, "exchange", btc_address(6))])
        self.assertEqual(sum(counts.values()), 0)

    def test_unmapped_labels_contribute_no_interpretable_opinion(self):
        # both claims are canon "unknown" (an unmapped vocabulary): they cannot be judged compatible
        # or incompatible, so none of the four interpretable buckets may claim the subject ...
        a = btc_address(7)
        claims = [claim(1, "unknown", a, raw="code-A"), claim(2, "unknown", a, raw="code-B")]
        counts = self._n(claims)
        for k in ("repeated observation", "repeated same label", "compatible multi-label claim",
                  "internal contradiction"):
            self.assertEqual(counts[k], 0, k)

    def test_unmapped_distinct_labels_on_one_subject_are_accounted_for_not_silently_dropped(self):
        # ... but the subject DID carry two different labels. A measured zero must not hide it:
        # it lands in the explicit "uninterpretable multi-label" bucket
        a = btc_address(7)
        claims = [claim(1, "unknown", a, raw="code-A"), claim(2, "unknown", a, raw="code-B")]
        self.assertEqual(self._n(claims)["uninterpretable multi-label"], 1)

    def test_an_unmapped_label_beside_a_mapped_one_is_not_a_repeated_same_label(self):
        # "code-A" is not known to be the same category as "exchange"; counting it as a repeat of
        # the mapped label would overstate agreement
        a = btc_address(13)
        counts = self._n([claim(1, "exchange", a, raw="exchange"), claim(2, "unknown", a, raw="code-A")])
        self.assertEqual(counts["repeated same label"], 0)
        self.assertEqual(counts["uninterpretable multi-label"], 1)

    def test_a_repeated_unmapped_label_is_a_repeated_observation(self):
        # byte-identical claims need no interpretation to be recognised as the same thing said twice
        a = btc_address(14)
        counts = self._n([claim(1, "unknown", a, raw="code-A"), claim(2, "unknown", a, raw="code-A")])
        self.assertEqual(counts["repeated observation"], 1)
        self.assertEqual(counts["uninterpretable multi-label"], 0)

    def test_three_compatible_labels_on_one_branch_are_still_compatible(self):
        a = btc_address(8)
        claims = [claim(1, "illicit_unspec", a), claim(2, "ransomware", a), claim(3, "ransomware", a, raw="again")]
        counts = self._n(claims)
        self.assertEqual(counts["compatible multi-label claim"], 1)
        self.assertEqual(counts["internal contradiction"], 0)


class TestRelationalConflictsIsChainAware(unittest.TestCase):
    """`relational.conflicts` used to group by the bare address string; the same address on two
    chains would have been misreported as one subject contradicting itself. Fixed by grouping on
    `provenance.subject_key` (chain + address), the same key every other cross-address analysis
    in THEMIS uses."""

    def test_same_address_different_chains_is_not_reported_as_a_conflict(self):
        addr_text = btc_address(9)
        claims = [claim(1, "exchange", addr_text, blockchain="bitcoin"),
                  claim(2, "ransomware", addr_text, blockchain="litecoin")]
        report = relational.conflicts(claims)
        self.assertEqual(report["conflicting_addresses"], [])
        self.assertEqual(report["n_addresses_checked"], 0)

    def test_a_real_within_chain_conflict_is_still_reported(self):
        a = btc_address(10)
        claims = [claim(1, "exchange", a), claim(2, "ransomware", a)]
        report = relational.conflicts(claims)
        self.assertEqual(len(report["conflicting_addresses"]), 1)
        self.assertEqual(report["conflicting_addresses"][0]["outcome"], "licit/illicit conflict")
        self.assertEqual(report["internal_consistency"]["internal contradiction"]["n"], 1)


class TestPipelineExposesRealInternalConsistency(unittest.TestCase):
    """The plain CSV/API upload path (what an external dataset like BitcoinHeist or MBAL goes
    through) declared `capabilities.internal_consistency: True` unconditionally with nothing
    behind it. It now runs the same generic check and reports its result."""

    def _ingest(self, rows, fields):
        path = write_tmp(to_csv(rows, fields))
        try:
            return pipeline.ingest(path, "synthetic_upload", reference=None)
        finally:
            os.remove(path)

    def test_a_clean_file_reports_zero_contradictions(self):
        rows = [dict(address=btc_address(i), label="exchange") for i in range(5)]
        res = self._ingest(rows, ["address", "label"])
        self.assertIn("internal_consistency", res)
        self.assertEqual(res["internal_consistency"]["internal contradiction"]["n"], 0)
        self.assertTrue(res["capabilities"]["internal_consistency"])

    def test_a_file_with_two_labels_on_one_address_is_flagged(self):
        a = btc_address(11)
        rows = [dict(address=a, label="exchange"), dict(address=a, label="ransomware"),
                dict(address=btc_address(12), label="exchange")]
        res = self._ingest(rows, ["address", "label"])
        self.assertEqual(res["internal_consistency"]["internal contradiction"]["n"], 1)

    def test_a_file_with_only_unmapped_labels_does_not_report_a_bare_zero_for_a_multi_label_subject(self):
        a = btc_address(15)
        rows = [dict(address=a, label="code-A"), dict(address=a, label="code-B"),
                dict(address=btc_address(16), label="code-A")]
        res = self._ingest(rows, ["address", "label"])
        ic = res["internal_consistency"]
        self.assertEqual(ic["internal contradiction"]["n"], 0)
        self.assertEqual(ic["uninterpretable multi-label"]["n"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
