"""Whether the reference corpus is present. A release does not ship it (the
paper's data-availability statement: the derived observation table is not
redistributed), so every test that asserts a number printed in the paper, or
drives the paper-reproduction endpoints, skips - with this reason - when it is
absent, instead of failing. Point THEMIS_DATA_DIR at a corpus built by
scripts/build_corpus.py to run them."""
import unittest
from themis import corpus

HAVE_REFERENCE = (corpus.data_dir() / "manifest.json").is_file() and \
                 (corpus.data_dir() / "observations_sample.csv.gz").is_file()
REASON = "reference corpus not present (not redistributed - see THIRD_PARTY_DATA.md; set THEMIS_DATA_DIR)"
requires_reference_corpus = unittest.skipUnless(HAVE_REFERENCE, REASON)


#: a full local build (scripts/build_corpus.py output) named by THEMIS_OBSERVATIONS, for the tests that
#: assert the full-corpus figures the paper prints; skipped, with this reason, when there is none.
import os
HAVE_FULL_CORPUS = bool(os.environ.get("THEMIS_OBSERVATIONS")) and os.path.isfile(os.environ["THEMIS_OBSERVATIONS"])
requires_full_corpus = unittest.skipUnless(
    HAVE_FULL_CORPUS, "full corpus not present (set THEMIS_OBSERVATIONS to an observations.csv.gz from scripts/build_corpus.py)")
