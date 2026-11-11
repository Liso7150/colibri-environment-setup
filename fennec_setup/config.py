"""Portable shared configuration. Planning never writes configuration."""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOTS = ("engine_root", "suite_root", "models_root", "cache_root")
KEYS = set(ROOTS) | {"python", "model", "engine_url", "web_root", "workspace", "backend", "ctx", "policy"}
ENV = {"engine_root": "FENNEC_HOME", "models_root": "FENNEC_MODELS",
       "cache_root": "FENNEC_CACHE", "python": "FENNEC_PYTHON",
       "model": "FENNEC_MODEL", "engine_url": "FENNEC_ENGINE_URL",
       "workspace": "FENNEC_WORKSPACE"}
# Pre-Fennec Windows paths an old manifest or config may still carry. They are
# recognised so they can be migrated, but never chosen as a default: not every
# machine has a D: drive, and the installer lets the user pick any drive.
LEGACY = dict(zip(ROOTS, ("D:/Colibri", "D:/Fennec-Suite", "D:/fennec-models", "D:/.cache")))
PORTABLE = dict(zip(ROOTS, ("~/Colibri", "~/Fennec-Suite", "~/fennec-models", "~/.cache/fennec")))
# Mirrors fennec-core/fennec_core/config.py (authoritative shared schema).
SECRETS = {"api_key", "app_token", "token", "fennec_api_key", "fennec_app_token", "coli_api_key"}
BACKENDS = ("auto", "vulkan", "metal", "cpu")
POLICIES = ("quality", "balanced", "experimental-fast")


def is_loopback(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def absolute(value, *, system=None, home=None, base=None):
    system = system or platform.system()
    home = str(home or Path.home()).replace("\\", "/")
    value = str(value).replace("\\", "/")
    if value == "~" or value.startswith("~/"):
        value = home + value[1:]
    if re.match(r"^[A-Za-z]:", value):
        if system != "Windows":
            raise ValueError(f"Windows path cannot be used on {system}: {value}")
        if not re.match(r"^[A-Za-z]:/", value):
            raise ValueError(f"Drive-relative path is unsafe: {value}")
        return value.rstrip("/") + ("/" if len(value) == 3 else "")
    path = Path(value)
    if not path.is_absolute():
        path = Path(base or Path.cwd()) / path
    return str(path.resolve()).replace("\\", "/")


def config_path(value=None, *, environ=None, home=None):
    env = os.environ if environ is None else environ
    return Path(absolute(value or env.get("FENNEC_CONFIG") or str(Path(home or Path.home()) / ".fennec/config.json")))


def validate_config(data, *, environ=None):
    if not isinstance(data, dict):
        raise ValueError("Shared config must be a JSON object")
    if any(k.lower() in SECRETS for k in data):
        raise ValueError("Secrets belong in environment variables (FENNEC_API_KEY/COLI_API_KEY), not configuration JSON")
    if set(data) - KEYS:
        raise ValueError("Shared config must contain only supported runtime keys; never store secrets here")
    for key, value in data.items():
        if key == "ctx":
            if type(value) is not int or not 0 <= value <= 1_048_576:
                raise ValueError("ctx must be an integer from 0 (automatic) to 1048576")
        elif not isinstance(value, str) or (not value.strip() and key != "model"):
            raise ValueError(f"{key} must be a nonempty string (omit an unselected model)")
    if data.get("backend", "auto") not in BACKENDS:
        raise ValueError("backend must be auto, vulkan, metal or cpu; NPU is not a decoder")
    if data.get("policy", "quality") not in POLICIES:
        raise ValueError("policy must be quality, balanced or experimental-fast")
    try:
        url = urlsplit(data.get("engine_url", "http://127.0.0.1:8184"))
        valid = (url.scheme in ("http", "https") and url.hostname and url.port != 0
                 and not url.username and not url.password and url.path in ("", "/")
                 and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("engine_url must be an HTTP(S) origin without credentials, port 0, path, query or fragment")
    if environ is not None and not is_loopback(url.hostname):
        if not (environ.get("FENNEC_API_KEY") or environ.get("COLI_API_KEY")):
            raise ValueError("A non-loopback engine requires FENNEC_API_KEY or COLI_API_KEY in the environment")


def read_config(path, *, environ=None):
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_config(data, environ=environ)
    return data


def resolve_config(manifest, *, root=None, config=None, overrides=None, environ=None,
                   system=None, home=None, exists=None, recommendation=None):
    env = os.environ if environ is None else environ
    system = system or platform.system()
    exists = exists or Path.exists
    home = home or Path.home()
    path = config_path(config, environ=env, home=home)
    saved = read_config(path, environ=env)
    explicit = {k: v for k, v in (overrides or {}).items() if v is not None}
    unknown = set(explicit) - KEYS
    if unknown:
        raise ValueError(f"Unsupported overrides: {sorted(unknown)}")
    values = {}
    for key in ROOTS:
        candidate = manifest.get(key)
        if not candidate or candidate == LEGACY[key]:
            candidate = PORTABLE[key]
        values[key] = candidate
    values.update(saved)
    values.update({k: env[e] for k, e in ENV.items() if env.get(e)})
    if root:
        root = absolute(root, system=system, home=home)
        values.update(dict(zip(ROOTS, (f"{root}/engine", f"{root}/suite", f"{root}/models", f"{root}/cache"))))
    values.update(explicit)
    # Reject empty strings and invalid enums before normalizing paths.
    validate_config(values, environ=env)
    for key in ROOTS:
        values[key] = absolute(values[key], system=system, home=home, base=manifest.get("_base"))
    # Derived paths follow changed roots, unless explicitly configured themselves.
    if (root or "suite_root" in explicit) and "web_root" not in explicit:
        values.pop("web_root", None)
    if (root or "engine_root" in explicit) and "python" not in explicit and not env.get("FENNEC_PYTHON"):
        values.pop("python", None)
    # The engine venv used to be the derived default; `python` on PATH is now it.
    retired = f"{values['engine_root']}/.venv/" + ("Scripts/python.exe" if system == "Windows" else "bin/python")
    if str(values.get("python", "")).replace("\\", "/") == retired:
        values.pop("python", None)
    defaults = recommendation or {}
    values.setdefault("python", "python")
    values.setdefault("engine_url", "http://127.0.0.1:8184")
    values.setdefault("web_root", f"{values['suite_root']}/fennec-coding-agent/web")
    values.setdefault("workspace", values["suite_root"])
    values.setdefault("backend", defaults.get("backend", "cpu"))
    values.setdefault("ctx", defaults.get("ctx", 2048))
    values.setdefault("policy", defaults.get("policy", "balanced"))
    for key in ("web_root", "workspace"):
        values[key] = absolute(values[key], system=system, home=home)
    if re.search(r"[~/\\]", values["python"]):
        values["python"] = absolute(values["python"], system=system, home=home)
    if values.get("model"):
        values["model"] = absolute(values["model"], system=system, home=home, base=values["models_root"])
    validate_config(values, environ=env)
    return values, path


def resolved_manifest(manifest, config):
    result = dict(manifest)
    result.update({key: config[key] for key in ROOTS})
    result["repos"] = []
    for repo in manifest["repos"]:
        name = repo["repo"].split("/")[-1]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in (".", ".."):
            raise ValueError(f"Invalid repository name: {name}")
        local = config["engine_root"] if repo["concept"] == "engine" else f"{config['suite_root']}/{name}"
        result["repos"].append(dict(repo, local=local))
    return result


def write_config(path, values, explicit_keys=(), *, environ=None):
    """Atomic write after successful actions; retain pre-existing user choices."""
    validate_config(values, environ=environ)
    path = Path(path)
    merged = read_config(path, environ=environ)
    for key, value in values.items():
        if key not in merged or key in explicit_keys:
            merged[key] = value
    validate_config(merged, environ=environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            name = handle.name
            json.dump(merged, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def action_environment(config, environ=None):
    env = dict(os.environ if environ is None else environ)
    env.update({name: str(config[key]) for key, name in ENV.items() if key in config})
    cache = config["cache_root"]
    env.update(HF_HOME=f"{cache}/huggingface", PIP_CACHE_DIR=f"{cache}/pip",
               npm_config_cache=f"{cache}/npm")
    return env
