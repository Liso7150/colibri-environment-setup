"""Fetch the Colibri repos into their local paths and wire apps together."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def load_manifest(path=None):
    return json.loads((Path(path) if path else HERE / "repos.json").read_text(encoding="utf-8"))


def repos_for_features(manifest, features):
    needed = {}
    for feat in features:
        spec = manifest["features"].get(feat)
        if not spec:
            raise KeyError(f"unknown feature: {feat}")
        for concept in spec["requires"]:
            needed[concept] = True
    for repo in manifest["repos"]:
        if repo.get("required"):
            needed[repo["concept"]] = True
    return [r for r in manifest["repos"] if r["concept"] in needed]


def _git(args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def fetch_repo(repo, update=False):
    local = Path(repo["local"])
    url = f"https://github.com/{repo['repo']}.git"
    if (local / ".git").exists():
        if update:
            r = _git(["pull", "--ff-only"], cwd=local)
            return f"updated {repo['concept']}: {r.stdout.strip() or r.stderr.strip()}"
        return f"exists  {repo['concept']} ({local})"
    if local.exists() and any(local.iterdir()):
        return f"exists  {repo['concept']} (non-git source at {local}; left as-is)"
    local.parent.mkdir(parents=True, exist_ok=True)
    branch = repo.get("branch")
    args = ["clone", url, str(local)]
    if branch:
        args = ["clone", "--branch", branch, url, str(local)]
    r = _git(args)
    if r.returncode != 0:
        return f"FAILED  {repo['concept']}: {r.stderr.strip()}"
    return f"cloned  {repo['concept']} -> {local}"


def fetch(features, manifest=None, update=False):
    manifest = manifest or load_manifest()
    repos = repos_for_features(manifest, features)
    return [fetch_repo(r, update=update) for r in repos]