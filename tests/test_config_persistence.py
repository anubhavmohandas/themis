"""Part Z - config must not silently drift under an already-created analysis.

THEMIS's config is loaded once per process (`config_io.load()`, an
`lru_cache` keyed by config directory) rather than re-read per request. This
is what actually prevents the failure mode Part Z describes: editing
`themis/config/*.yml` on disk while the backend is running must never change
what an in-memory analysis reports on its next request - a live-drift risk
that would exist if `load()` re-read the files every call. In-memory
workspaces don't survive a restart at all (confirmed separately), so the two guarantees
together mean an analysis's config is pinned for its entire observable
lifetime.
"""
import sys, pathlib, shutil, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis import config_io


class TestConfigCaching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copytree(config_io.PKG_CONFIG, self.tmp, dirs_exist_ok=True)
        self._orig_env = __import__("os").environ.get("THEMIS_CONFIG_DIR")
        __import__("os").environ["THEMIS_CONFIG_DIR"] = self.tmp
        config_io.load.cache_clear()

    def tearDown(self):
        import os
        if self._orig_env is None:
            os.environ.pop("THEMIS_CONFIG_DIR", None)
        else:
            os.environ["THEMIS_CONFIG_DIR"] = self._orig_env
        config_io.load.cache_clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_disk_edit_after_first_load_does_not_change_the_running_process(self):
        original = config_io.load().thresholds.get("kappa_substantial_threshold")
        thresholds_path = pathlib.Path(self.tmp) / "thresholds.yml"
        text = thresholds_path.read_text()
        thresholds_path.write_text(text + "\nkappa_substantial_threshold: 0.99\n")

        still_cached = config_io.load()
        self.assertEqual(still_cached.thresholds.get("kappa_substantial_threshold"), original)
        self.assertNotEqual(original, 0.99)  # sanity: the edit really would have changed it

    def test_cache_clear_is_the_only_way_to_observe_a_disk_edit(self):
        thresholds_path = pathlib.Path(self.tmp) / "thresholds.yml"
        text = thresholds_path.read_text()
        thresholds_path.write_text(text + "\nkappa_substantial_threshold: 0.99\n")

        config_io.load.cache_clear()
        refreshed = config_io.load()
        self.assertEqual(refreshed.thresholds.get("kappa_substantial_threshold"), 0.99)

    def test_repeated_load_calls_return_the_identical_cached_object(self):
        self.assertIs(config_io.load(), config_io.load())


if __name__ == "__main__":
    unittest.main(verbosity=2)
