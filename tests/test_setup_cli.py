import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import setup  # noqa: E402


class SetupCliTests(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = setup.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_features_needs_no_hardware_or_network(self):
        code, out, _ = self.run_main(["features"])
        self.assertEqual(code, 0)
        self.assertIn("inference", out)
        self.assertIn("installer", out)

    def test_version_prints_the_hub_version(self):
        code, out, _ = self.run_main(["version"])
        self.assertEqual(code, 0)
        self.assertIn("fennec-setup 1.8.1", out)

    def test_plan_without_selection_fails_honestly(self):
        code, _, err = self.run_main(["plan"])
        self.assertEqual(code, 1)
        self.assertIn("Select --features", err)

    def test_unknown_feature_fails_honestly(self):
        code, _, err = self.run_main(["plan", "--features", "not-a-feature"])
        self.assertEqual(code, 1)
        self.assertIn("Unknown feature", err)

    def test_dry_run_json_never_writes_config(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.json"
            code, out, _ = self.run_main([
                "plan", "--features", "inference", "--json", "--root", str(home / "root"),
                "--config", str(config), "--model", ""])
            self.assertEqual(code, 0)
            self.assertIn('"config_path"', out)
            self.assertFalse(config.exists())
            self.assertFalse((home / "root").exists())

    def test_update_pulls_every_installed_checkout(self):
        import importlib
        from unittest import mock
        fetch_module = importlib.import_module("fennec_setup.fetch")
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / "suite"
            for name in ("fennec-core", "fennec-desktop"):
                (suite / name / ".git").mkdir(parents=True)
            with mock.patch.object(fetch_module, "fetch_repo", return_value="updated") as update:
                code, out, err = self.run_main([
                    "update", "--suite-root", str(suite), "--config",
                    str(Path(directory) / "config.json")])
        self.assertEqual(code, 0, err)
        self.assertIn("Updated 2 checkout(s)", out)
        self.assertIn("JustVugg/colibri", out)
        self.assertIn("lyogavin/airllm", out)
        self.assertEqual(update.call_count, 2)

    def test_update_without_checkouts_fails_honestly(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, err = self.run_main([
                "update", "--suite-root", str(Path(directory) / "empty"),
                "--engine-root", str(Path(directory) / "no-engine"),
                "--config", str(Path(directory) / "config.json")])
        self.assertEqual(code, 1)
        self.assertIn("No updateable Fennec checkouts", err)


if __name__ == "__main__":
    unittest.main()
