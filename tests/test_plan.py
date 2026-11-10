import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from colibri_setup.devices import Device  # noqa: E402
from colibri_setup.fetch import load_manifest, repos_for_features  # noqa: E402
from colibri_setup.provision import (build_plan, print_plan, selected_features)  # noqa: E402

CONCEPTS = ("engine", "core", "cli", "desktop", "coding-agent", "jetbrains", "installer", "finetune")


def manifest():
    return {
        "repos": [{"concept": concept, "repo": f"Liso7150/colibri-{concept}", "branch": "main"}
                  for concept in CONCEPTS],
        "features": {
            "inference": {"requires": ["engine", "core", "cli"]},
            "desktop": {"requires": ["engine", "core", "desktop", "coding-agent"]},
            "coding-agent": {"requires": ["engine", "core", "coding-agent"]},
            "jetbrains": {"requires": ["engine", "core", "jetbrains"]},
            "npu": {"requires": ["core"], "pip": ["openvino"]},
            "fine-tune": {"requires": ["engine", "finetune"], "pip": ["airllm", "torch"]},
            "mobile": {"requires": ["core", "coding-agent"]},
            "installer": {"requires": ["installer"]},
        },
        "credits": [],
    }


def device(**overrides):
    fields = dict(os="Windows" if sys.platform.startswith("win") else "Linux", os_version="test",
                  arch="x86_64", cpu_cores=8, ram_gb=32.0, gpu=[], npu=False, cuda=False,
                  vulkan=False, metal=False, client_only=False, disk_free_gb=100.0,
                  disk_path=".", python="3.12", tier="cpu")
    fields.update(overrides)
    return Device(**fields)


def slash(path):
    return str(path).replace("\\", "/")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.config = self.home / "config.json"
        self.overrides = {"engine_root": str(self.home / "engine"),
                          "suite_root": str(self.home / "suite"),
                          "models_root": str(self.home / "models"),
                          "cache_root": str(self.home / "cache")}

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, features=("inference",), dev=None, **kwargs):
        return build_plan(manifest(), list(features), overrides=self.overrides,
                          config=str(self.config), environ={}, home=self.home,
                          device=dev or device(), **kwargs)

    def test_planning_never_writes_config_or_fetches(self):
        plan = self.plan()
        self.assertFalse(self.config.exists())
        self.assertEqual(plan["config"]["workspace"], plan["config"]["suite_root"])
        labels = [action["label"] for action in plan["actions"]]
        self.assertIn("install editable core", labels)
        self.assertIn("install editable cli", labels)
        self.assertTrue(plan["config_write"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_plan(plan)
        self.assertIn("Plan only", out.getvalue())
        engine = next(repo for repo in plan["repos"] if repo["concept"] == "engine")
        self.assertEqual(engine["local"], slash(self.home / "engine"))

    def test_machine_readable_plan(self):
        plan = self.plan()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_plan(plan, machine=True)
        self.assertIn('"config_path"', out.getvalue())

    def test_client_only_has_no_actions(self):
        plan = self.plan(features=("mobile",), dev=device(os="Android", client_only=True, tier="client"))
        self.assertEqual(plan["actions"], [])
        self.assertFalse(plan["config_write"])
        self.assertTrue(any("PWA client mode" in message for message in plan["missing"]))

    def test_engine_uses_the_launcher_with_the_selected_model(self):
        model = self.home / "model"
        model.mkdir()
        (model / "config.json").write_text("{}", encoding="utf-8")
        overrides = dict(self.overrides, model=str(model))
        plan = build_plan(manifest(), ["inference"], overrides=overrides, build=True,
                          config=str(self.config), environ={}, home=self.home, device=device())
        launcher = slash(self.home / "engine/c/coli")
        labels = [action["label"] for action in plan["actions"]]
        self.assertIn("build engine for the selected model", labels)
        self.assertIn("verify engine for the selected model", labels)
        build = next(action for action in plan["actions"]
                     if action["label"] == "build engine for the selected model")
        self.assertEqual(build["argv"][1:], [launcher, "build", "--model", slash(model)])
        serve = plan["run"][0]["argv"]
        self.assertEqual(serve[1:3], [launcher, "serve"])
        self.assertIn("--auto-tier", serve)
        self.assertEqual(serve[serve.index("--host") + 1], "127.0.0.1")
        self.assertEqual(plan["engine_launcher"], launcher)

    def test_build_without_a_model_uses_a_real_make_target(self):
        plan = self.plan(build=True)
        action = next(action for action in plan["actions"] if "native target" in action["label"])
        self.assertEqual(action["argv"][-1], "colibri")
        self.assertNotIn(".exe", " ".join(action["argv"]))

    def test_unknown_feature_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(features=("does-not-exist",))

    def test_selection_requires_explicit_choice(self):
        with self.assertRaises(ValueError):
            selected_features(manifest(), None)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()

    def test_feature_closure(self):
        concepts = {repo["concept"] for repo in self.manifest["repos"]}
        for name, spec in self.manifest["features"].items():
            with self.subTest(feature=name):
                self.assertLessEqual(set(spec["requires"]), concepts)
                self.assertLessEqual(set(spec.get("features", [])), set(self.manifest["features"]))

    def test_all_includes_installer_training_and_mobile(self):
        selected = selected_features(self.manifest, None, all_features=True)
        for name in ("installer", "fine-tune", "mobile", "desktop"):
            self.assertIn(name, selected)

    def test_every_feature_resolves_repos(self):
        for name in self.manifest["features"]:
            with self.subTest(feature=name):
                self.assertTrue(repos_for_features(self.manifest, [name]))

    def test_cycle_and_unknown_feature_detected(self):
        cyclic = manifest()
        cyclic["features"]["a"] = {"requires": [], "features": ["b"]}
        cyclic["features"]["b"] = {"requires": [], "features": ["a"]}
        with self.assertRaises(ValueError):
            repos_for_features(cyclic, ["a"])
        with self.assertRaises(ValueError):
            repos_for_features(cyclic, ["missing"])

    def test_upstream_credits_present(self):
        credits = self.manifest.get("credits", [])
        upstreams = " ".join(entry["upstream"] for entry in credits)
        self.assertIn("JustVugg/colibri", upstreams)
        self.assertIn("lyogavin/airllm", upstreams)


if __name__ == "__main__":
    unittest.main()
