"""Serializable action plans and opt-in execution (stdlib bootstrap only)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import (ROOTS, action_environment, resolve_config, resolved_manifest,
                     write_config)
from .devices import detect, recommend
from .fetch import repos_for_features, validate_checkout, fetch_repo, update_installed


class InstallError(RuntimeError):
    pass


# Prebuilt OpenVINO IR embedding model for the accelerator sidecar. Downloading
# this instead of exporting it keeps optimum-intel, and therefore torch/nncf, out
# of the interpreter that the Colibri engine also uses.
EMBED_IR_REPO = "OpenVINO/bge-base-en-v1.5-int8-ov"


def selected_features(manifest, features=None, all_features=False):
    if all_features and features:
        raise ValueError("Choose either --all or --features, not both")
    result = list(manifest["features"]) if all_features else list(dict.fromkeys(
        f.strip() for f in (features or "").split(",") if f.strip()))
    if not result:
        raise ValueError("Select --features a,b or --all; no implicit full installation")
    repos_for_features(manifest, result)
    return result


def build_plan(manifest, features, *, root=None, config=None, overrides=None,
               build=False, native_target="fennec", update=False, device=None,
               environ=None, home=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", native_target):
        raise ValueError("Native target must be a simple Makefile target, not options or shell text")
    values, path = resolve_config(manifest, root=root, config=config, overrides=overrides,
                                  environ=environ, home=home)
    dev = device or detect(values["models_root"])
    rec = recommend(dev)
    values, path = resolve_config(manifest, root=root, config=config, overrides=overrides,
                                  environ=environ, home=home, recommendation=rec)
    repos = repos_for_features(resolved_manifest(manifest, values), features)
    locations = {r["concept"]: r["local"] for r in repos}
    actions, missing, warnings = [], [], [rec["note"]]
    explicit = set(k for k, v in (overrides or {}).items() if v is not None)
    if root:
        explicit.update(ROOTS)
    if root or "suite_root" in explicit:
        explicit.add("web_root")
    if root or "engine_root" in explicit:
        explicit.add("python")
    def add(label, argv, cwd=None, requires=()):
        actions.append({"label": label, "argv": [str(a) for a in argv], "cwd": cwd,
                        "requires": [str(p) for p in requires]})
    if not shutil.which("git"):
        missing.append("Git: install Git and add it to PATH before fetching")
    if sys.version_info < (3, 10):
        missing.append("Python: use Python 3.10+ with pip")
    packages = []
    visited = set()
    def dependencies(feature):
        if feature in visited:
            return
        visited.add(feature)
        spec = manifest["features"][feature]
        for child in spec.get("features", []):
            dependencies(child)
        packages.extend(spec.get("pip", []))
    for feature in features:
        dependencies(feature)
    packages = list(dict.fromkeys(packages))
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.<>=!~\[\],-]*", p) for p in packages):
        raise ValueError("Invalid dependency specification")
    python = values["python"]
    windows = dev.os == "Windows"
    needs_python = bool({"core", "cli"} & locations.keys() or packages)
    if needs_python:
        if not shutil.which(python) and not Path(python).is_file():
            missing.append(f"Python: install Python 3.10+ on PATH or set FENNEC_PYTHON (configured: {python})")
        add("verify pip", [python, "-m", "pip", "--version"])
        for concept in ("core", "cli"):
            if concept in locations:
                project = locations[concept]
                add(f"install editable {concept}", [python, "-m", "pip", "install", "--editable", project],
                    requires=[f"{project}/pyproject.toml"])
        if packages:
            add("install selected optional dependencies", [python, "-m", "pip", "install", *packages])
        if "npu" in features:
            # The desktop/IDE sidecar imports openvino from this same interpreter and
            # looks for IR under models_root/embed, so provision both in place.
            embed_dir = f"{values['models_root']}/embed/{EMBED_IR_REPO.split('/')[1]}"
            add("fetch the sidecar embedding model (prebuilt OpenVINO IR)",
                [python, "-c",
                 "import sys; from huggingface_hub import snapshot_download; "
                 "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])",
                 EMBED_IR_REPO, embed_dir],
                requires=[python])
            warnings.append("The NPU/iGPU sidecar runs the device probe and the batched code index only; token generation stays on the Colibri engine.")
            warnings.append("The sidecar uses prebuilt OpenVINO IR, so optimum-intel (and the torch/nncf tree behind it) is never installed here.")
    if "desktop" in locations:
        project = locations["desktop"]
        for tool in ("node", "npm"):
            if not shutil.which(tool):
                missing.append(f"Node: install Node.js LTS and npm ({tool} is missing)")
        add("install desktop dependencies", ["npm", "ci"], project,
            [f"{project}/package.json", f"{project}/package-lock.json"])
        warnings.append("Desktop dependencies only; distributable Electron packaging is not run. Launch with npm start in the desktop checkout.")
    native = f"{values['engine_root']}/c/coli" + (".exe" if windows else "")
    launcher = f"{values['engine_root']}/c/coli"
    model = values.get("model")
    model_status = "existing path; format/size not validated" if model and Path(model).exists() else "missing"
    if "engine" in locations:
        if not Path(launcher).is_file():
            missing.append(f"Engine launcher missing: {launcher}. Use a complete engine checkout.")
        if build:
            for tool, choices in (("make", ("make",)), ("C compiler", ("cc", "gcc", "clang"))):
                if not any(shutil.which(choice) for choice in choices):
                    missing.append(f"Native toolchain: install {tool} (on Windows use a compatible MSYS2/MinGW toolchain)")
            if model and Path(model).is_dir():
                add("build engine for the selected model", [python, launcher, "build", "--model", model],
                    requires=[f"{values['engine_root']}/c/Makefile"])
                add("verify engine for the selected model", [python, launcher, "info", "--model", model],
                    requires=[f"{model}/config.json"])
            else:
                add("build selected native target", ["make", "-C", f"{values['engine_root']}/c", native_target],
                    requires=[f"{values['engine_root']}/c/Makefile"])
                warnings.append(f"No model selected, so make builds the {native_target!r} target. With a model, the launcher picks its engine family automatically.")
        else:
            warnings.append("Engine binaries are not built or verified by this plan; run install with --build (needs a compatible toolchain).")
    if "jetbrains" in locations:
        warnings.append("JetBrains plugin is fetched only; build/package it separately using its README and JDK/Gradle requirements.")
    if "finetune" in locations:
        warnings.append("Training dependencies are selected; datasets, model weights and training runs are never downloaded/started implicitly.")
    if model_status == "missing":
        warnings.append("Inference is NOT ready: no existing model selected. Pass --model /path/to/existing/model. No model download is automatic (35B models can be enormous).")
    if values["backend"] != "cpu":
        warnings.append(f"Configured backend {values['backend']!r} requires an independently verified engine build; hardware detection does not prove decoding support.")
    run = []
    if "engine" in locations and model:
        run.append({"label": "engine (after native build and model validation)",
                    "argv": [python, launcher, "serve", "--auto-tier", "--model", model,
                             "--ctx", str(values["ctx"]), "--policy", values["policy"],
                             "--host", "127.0.0.1", "--port", "8184"]})
    if "core" in locations:
        base = Path(shutil.which(python) or python).parent
        scripts = base if base.name.lower() in ("scripts", "bin") else base / ("Scripts" if windows else "bin")
        entry = str(scripts / ("fennec-agent.exe" if windows else "fennec-agent"))
        run.append({"label": "shared agent (reads shared config)", "argv": [entry]})
    if "desktop" in locations:
        run.append({"label": "desktop", "argv": ["npm", "start"], "cwd": locations["desktop"]})
    if "mobile" in features or dev.client_only or dev.termux:
        warnings.append("Mobile = shared core + coding-agent PWA, on the same device (Termux) or reached from another device over trusted HTTPS with FENNEC_APP_TOKEN. The engine starts on demand; there is no automatic public exposure.")
    if dev.client_only:
        actions = []
        missing.append("Android/iOS is PWA client mode only: execute this installation plan on a Windows/macOS/Linux host")
        run = []
    return {"features": list(features), "device": dev.to_dict(), "recommendation": rec,
            "config_path": str(path), "config": values, "explicit_keys": sorted(explicit),
            "repos": repos, "actions": actions, "build": build, "update": update,
            "native_target": native_target, "engine_launcher": launcher if "engine" in locations else None,
            "model_status": model_status, "missing": missing, "warnings": warnings,
            "run": run, "credits": manifest.get("credits", []),
            "config_write": bool(needs_python or build) and not dev.client_only,
            "cache_environment": {k: v for k, v in action_environment(values, {}).items()
                                  if k in ("HF_HOME", "PIP_CACHE_DIR", "npm_config_cache")}}


def print_plan(plan, machine=False):
    if machine:
        print(json.dumps(plan, indent=2))
        return
    print("Plan only; no downloads, installs, builds, config writes or servers started.")
    print("Features: " + ", ".join(plan["features"]))
    print(f"Device: {plan['device']['os']} {plan['device']['arch']}; detected hardware={plan['device']['tier']}")
    print(f"Runtime: backend={plan['config']['backend']} ctx={plan['config']['ctx']} policy={plan['config']['policy']}")
    for repo in plan["repos"]:
        print(f"  checkout {repo['repo']} [{repo.get('branch', 'main')}] -> {repo['local']}")
    for action in plan["actions"]:
        print(f"  {action['label']}: {json.dumps(action['argv'])}" + (f" (cwd={action['cwd']})" if action["cwd"] else ""))
    print(f"Config after successful relevant install only: {plan['config_path']}")
    for message in plan["missing"] + plan["warnings"]:
        print("  NOTE: " + message)
    for credit in plan["credits"]:
        print(f"Credit: {credit['name']} — {credit['upstream']} ({credit['role']})")


def _run_action(action, env):
    argv = list(action["argv"])
    if argv[0] == "npm" and os.name == "nt":
        # Avoid cmd.exe / shell=True, which would reinterpret paths/metacharacters.
        npm = shutil.which("npm")
        node = shutil.which("node")
        if not npm or not node:
            raise InstallError("Node.js/npm are missing")
        npm_cli = Path(npm).parent / "node_modules/npm/bin/npm-cli.js"
        if not npm_cli.is_file():
            raise InstallError(f"Cannot safely locate npm-cli.js beside {npm}; use a standard Node.js installation")
        argv = [node, str(npm_cli), *argv[1:]]
    try:
        result = subprocess.run(argv, cwd=action.get("cwd"), env=env, shell=False)
    except OSError as exc:
        raise InstallError(f"{action['label']} could not start: {exc}") from exc
    if result.returncode:
        raise InstallError(f"{action['label']} failed (exit {result.returncode}); configuration was not written")


def execute_plan(plan, *, install=False, emit=print):
    """Caller explicitly opts into acquisition or installation. Never launches servers."""
    if install and plan["missing"]:
        raise InstallError("Preflight failed: " + "; ".join(plan["missing"]))
    if install and "model" in plan["explicit_keys"] and plan["model_status"] == "missing":
        raise InstallError("--model must point to an existing local file or directory")
    for repo in plan["repos"]:
        validate_checkout(repo, update=plan["update"])
    for repo in plan["repos"]:
        emit(fetch_repo(repo, update=plan["update"]))
    if not install:
        emit("Fetch-only complete. No dependencies installed, engine built, runtime config written or servers started.")
        for message in plan["missing"] + plan["warnings"]:
            emit("Still required / note: " + message)
        return
    # Verify required source files before creating a venv or installing packages.
    for action in plan["actions"]:
        for required in action["requires"]:
            if not Path(required).is_file():
                raise InstallError(f"Missing {required}; cannot {action['label']}. Configuration was not written.")
    env = action_environment(plan["config"])
    env["FENNEC_CONFIG"] = plan["config_path"]
    for action in plan["actions"]:
        emit("Running: " + action["label"])
        _run_action(action, env)
    if plan["build"] and plan["engine_launcher"] and not Path(plan["engine_launcher"]).is_file():
        raise InstallError("Engine launcher is missing after the build; verify the checkout. Configuration was not written.")
    if plan["config_write"]:
        write_config(plan["config_path"], plan["config"], plan["explicit_keys"], environ=env)
        emit("Runtime configuration saved atomically: " + plan["config_path"])
    emit(f"Selected actions completed ({len(plan['actions'])}); no server was started. Inference readiness is not verified.")
    for message in plan["warnings"]:
        emit("Still required / note: " + message)
    for command in plan["run"]:
        emit("Run separately — " + command["label"] + ": " + json.dumps(command["argv"]) +
             (" (cwd=" + command["cwd"] + ")" if command.get("cwd") else ""))


def add_plan_options(parser):
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--features", help="comma-separated feature names")
    selection.add_argument("--all", action="store_true", help="every feature, including installer and training")
    parser.add_argument("--root", help="clean layout: ROOT/{engine,suite,models,cache}")
    parser.add_argument("--config", help="shared config path; default FENNEC_CONFIG or ~/.fennec/config.json")
    for key in ROOTS + ("python", "model", "engine_url", "web_root", "workspace", "backend", "policy"):
        parser.add_argument("--" + key.replace("_", "-"))
    parser.add_argument("--ctx", type=int)
    parser.add_argument("--build", action="store_true", help="include/execute the selected native target with install")
    parser.add_argument("--native-target", default="fennec", help="engine c/Makefile target when no model is selected (default fennec)")
    parser.add_argument("--update", action="store_true", help="fast-forward clean matching tracked branches only")
    parser.add_argument("--json", action="store_true", help="machine-readable plan (plan mode only)")


def plan_from_args(manifest, args, features=None):
    from .config import KEYS
    overrides = {key: getattr(args, key, None) for key in KEYS}
    return build_plan(manifest, features or selected_features(manifest, args.features, args.all),
                      root=args.root, config=args.config, overrides=overrides,
                      build=args.build, native_target=args.native_target, update=args.update)
