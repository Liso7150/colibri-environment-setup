import json
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from colibri_setup.config import KEYS, read_config, resolve_config, validate_config, write_config  # noqa: E402

SYSTEM = platform.system()


def slash(path):
    return str(path).replace("\\", "/")

SHARED_CASES = [
    ({}, True),
    ({"engine_root": "/opt/colibri", "ctx": 4096}, True),
    ({"model": ""}, True),
    ({"backend": "vulkan"}, True),
    ({"policy": "experimental-fast"}, True),
    ({"ctx": 0}, True),
    ({"ctx": 1048576}, True),
    ({"engine_url": "http://127.0.0.1:8184/"}, True),
    ({"engine_url": "http://127.0.0.1:8184"}, True),
    ({"api_key": "x"}, False),
    ({"token": "x"}, False),
    ({"coli_api_key": "x"}, False),
    ({"backend": "cuda"}, False),
    ({"backend": "npu"}, False),
    ({"backend": ""}, False),
    ({"policy": "speed"}, False),
    ({"policy": "auto"}, False),
    ({"ctx": -1}, False),
    ({"ctx": 1048577}, False),
    ({"ctx": True}, False),
    ({"ctx": "4096"}, False),
    ({"engine_root": ""}, False),
    ({"python": ""}, False),
    ({"python": 3}, False),
    ({"engine_url": "http://127.0.0.1:8184/api"}, False),
    ({"engine_url": "http://user:pw@127.0.0.1:8184"}, False),
    ({"engine_url": "http://127.0.0.1:8184?q=1"}, False),
    ({"engine_url": "ftp://127.0.0.1:8184"}, False),
    ({"engine_url": "http://127.0.0.1:0"}, False),
    ({"engine_url": "http://192.168.1.5:8184"}, False),
]

REMOTE = {"engine_url": "http://192.168.1.5:8184"}


def _locate_core():
    candidates = []
    if os.environ.get("COLIBRI_CORE_DIR"):
        candidates.append(Path(os.environ["COLIBRI_CORE_DIR"]))
    try:
        manifest = json.loads((ROOT / "repos.json").read_text(encoding="utf-8"))
        candidates.append(Path(manifest["suite_root"]) / "colibri-core")
    except (OSError, ValueError, KeyError):
        pass
    candidates.append(ROOT.parent / "colibri-core")
    for candidate in candidates:
        if (candidate / "colibri_core" / "config.py").is_file():
            return candidate
    return None


def _core_accepts(core, data, environ):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        try:
            core.load_config(path, environ=environ, home=Path(directory))
            return True
        except core.ConfigError:
            return False


class ValidateConfigTests(unittest.TestCase):
    def test_shared_cases(self):
        for data, accepted in SHARED_CASES:
            with self.subTest(data=data):
                if accepted:
                    validate_config(data, environ={})
                else:
                    with self.assertRaises(ValueError):
                        validate_config(data, environ={})

    def test_remote_engine_requires_environment_key(self):
        with self.assertRaises(ValueError):
            validate_config(REMOTE, environ={})
        validate_config(REMOTE, environ={"COLI_API_KEY": "k"})

    def test_unknown_keys_refused_although_runtime_ignores_them(self):
        # Stricter than the runtime loader: an unknown key in a config the
        # installer writes could smuggle a secret past the secret-name filter.
        with self.assertRaises(ValueError):
            validate_config({"engine_root": "/opt/colibri", "api-key": "x"})


@unittest.skipUnless(_locate_core(), "colibri-core checkout not available")
class CoreParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(_locate_core()))
        import colibri_core.config as core
        cls.core = core

    def test_validator_parity(self):
        for data, accepted in SHARED_CASES:
            with self.subTest(data=data):
                self.assertEqual(_core_accepts(self.core, data, {}), accepted)
                try:
                    validate_config(data, environ={})
                    hub_accepts = True
                except ValueError:
                    hub_accepts = False
                self.assertEqual(hub_accepts, accepted)

    def test_hub_written_config_loads_in_the_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            values, path = resolve_config({}, root=slash(home / "root"),
                                          config=home / "config.json", environ={},
                                          system=SYSTEM, home=home,
                                          exists=lambda path: False)
            write_config(path, values, environ={})
            config = self.core.load_config(path, environ={}, home=home)
        self.assertEqual(slash(config.engine_root), values["engine_root"])
        self.assertEqual(slash(config.workspace), values["workspace"])
        self.assertEqual(slash(config.cache_root), values["cache_root"])
        self.assertEqual(config.backend, values["backend"])
        self.assertEqual(config.ctx, values["ctx"])
        self.assertEqual(config.policy, values["policy"])
        self.assertEqual(config.engine_url, values["engine_url"])


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = {}

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, **kwargs):
        kwargs.setdefault("manifest", {})
        kwargs.setdefault("config", self.home / "config.json")
        kwargs.setdefault("environ", self.env)
        kwargs.setdefault("system", SYSTEM)
        kwargs.setdefault("home", self.home)
        kwargs.setdefault("exists", lambda path: False)
        return resolve_config(**kwargs)[0]

    def test_portable_roots_and_workspace_follow_suite(self):
        values = self.resolve()
        self.assertEqual(values["workspace"], values["suite_root"])
        self.assertEqual(values["workspace"], slash(self.home / "Colibri-Suite"))
        self.assertEqual(values["web_root"], slash(self.home / "Colibri-Suite/colibri-coding-agent/web"))
        self.assertEqual(values["engine_url"], "http://127.0.0.1:8184")

    def test_explicit_suite_root_moves_workspace(self):
        values = self.resolve(overrides={"suite_root": slash(self.home / "Suite")})
        self.assertEqual(values["workspace"], slash(self.home / "Suite"))

    def test_environment_workspace_and_config_path(self):
        self.env["COLIBRI_WORKSPACE"] = slash(self.home / "ws")
        values = self.resolve()
        self.assertEqual(values["workspace"], slash(self.home / "ws"))

    def test_root_layout(self):
        values, path = resolve_config({}, root=slash(self.home / "root"), config=self.home / "config.json",
                                      environ={}, system=SYSTEM, home=self.home,
                                      exists=lambda path: False)
        self.assertEqual(values["engine_root"], slash(self.home / "root/engine"))
        self.assertEqual(values["workspace"], slash(self.home / "root/suite"))
        self.assertEqual(values["models_root"], slash(self.home / "root/models"))
        self.assertEqual(path, self.home / "config.json")
        self.assertFalse((self.home / "config.json").exists())

    def test_relative_model_resolves_under_models_root(self):
        values = self.resolve(overrides={"model": "qwen36-35b"})
        self.assertEqual(values["model"], f"{values['models_root']}/qwen36-35b")

    def test_empty_overrides_rejected(self):
        for key in ("engine_root", "python", "engine_url"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self.resolve(overrides={key: ""})

    def test_saved_config_must_validate(self):
        path = self.home / "config.json"
        path.write_text(json.dumps({"api_key": "leak"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_config(path)

    def test_write_config_retains_user_choices(self):
        path = self.home / "config.json"
        path.write_text(json.dumps({"ctx": 1024, "policy": "quality"}), encoding="utf-8")
        write_config(path, {"ctx": 2048, "policy": "balanced", "engine_root": "/opt/e"},
                     explicit_keys=["engine_root"], environ={})
        merged = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(merged, {"ctx": 1024, "policy": "quality", "engine_root": "/opt/e"})


class KeysTests(unittest.TestCase):
    def test_shared_key_set(self):
        self.assertEqual(KEYS, {"engine_root", "suite_root", "models_root", "cache_root",
                                "python", "model", "engine_url", "web_root", "workspace",
                                "backend", "ctx", "policy"})


if __name__ == "__main__":
    unittest.main()
