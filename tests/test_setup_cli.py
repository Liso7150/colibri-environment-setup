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


if __name__ == "__main__":
    unittest.main()
