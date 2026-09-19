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
