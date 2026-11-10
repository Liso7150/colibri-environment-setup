"""Conservative Git checkout acquisition; never reset or adopt unknown sources."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .config import resolve_config, resolved_manifest

HERE = Path(__file__).resolve().parent.parent


class FetchError(RuntimeError):
    pass


def load_manifest(path=None):
    source = Path(path) if path else HERE / "repos.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["_base"] = str(source.resolve().parent)
    return manifest


def repos_for_features(manifest, features):
    needed, visiting, visited = set(), set(), set()
    def visit(name):
        if name in visiting:
            raise ValueError(f"Cyclic feature dependency: {name}")
        if name in visited:
            return
        if name not in manifest["features"]:
            raise ValueError(f"Unknown feature: {name}")
        visiting.add(name)
        spec = manifest["features"][name]
        for dependency in spec.get("features", []):
            visit(dependency)
        needed.update(spec.get("requires", []))
        visiting.remove(name)
        visited.add(name)
    for feature in features:
        visit(feature)
    missing = needed - {r["concept"] for r in manifest["repos"]}
    if missing:
        raise ValueError(f"Missing repository concepts: {sorted(missing)}")
    return [dict(r) for r in manifest["repos"] if r["concept"] in needed]


def normalize_origin(value):
    value = value.strip()
    # Compare equivalent HTTPS and SSH transport forms, not substrings.
    match = re.fullmatch(r"git@([^:]+):(.+)", value)
    if match:
        value = f"ssh://git@{match[1]}/{match[2]}"
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "ssh") or not parsed.hostname or parsed.query or parsed.fragment or parsed.password:
        raise FetchError("Origin must be a credential-free GitHub HTTPS/SSH URL")
    if parsed.username and not (parsed.scheme == "ssh" and parsed.username == "git"):
        raise FetchError("Unexpected origin username")
    if parsed.port not in (None, 22 if parsed.scheme == "ssh" else 443):
        raise FetchError("Unexpected origin port")
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise FetchError("Invalid origin repository path")
    return parsed.hostname.lower() + path


def _git(args, cwd=None):
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                                timeout=600, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError(f"Git could not run: {exc}") from exc
    if result.returncode:
        raise FetchError(f"git {args[0]} failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def repository_url(repo):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo["repo"]):
        raise FetchError("Invalid owner/repository")
    return f"https://github.com/{repo['repo']}.git"


def validate_checkout(repo, update=False):
    local = Path(repo["local"])
    url = repository_url(repo)
    branch = repo.get("branch", "main")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", branch) or ".." in branch or branch.endswith("/"):
        raise FetchError(f"Invalid branch: {branch}")
    if not local.exists():
        return False
    if not local.is_dir():
        raise FetchError(f"Checkout path is not a directory: {local}")
    if not (local / ".git").exists():
        if any(local.iterdir()):
            raise FetchError(f"Unknown non-Git source at {local}; move it or choose another root")
        return False
    origins = _git(["remote", "get-url", "--all", "origin"], cwd=local).splitlines()
    if len(origins) != 1 or normalize_origin(origins[0]) != normalize_origin(url):
        raise FetchError(f"Foreign origin at {local}; expected {url}")
    actual = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=local)
    if actual != branch:
        raise FetchError(f"Wrong branch at {local}: {actual}; expected {branch}. No automatic checkout/reset.")
    if update:
        if _git(["status", "--porcelain", "--untracked-files=normal"], cwd=local):
            raise FetchError(f"Dirty checkout at {local}; commit/stash your work yourself before updating")
        upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=local)
        if upstream != f"origin/{branch}":
            raise FetchError(f"Unknown upstream at {local}: {upstream}")
        counts = _git(["rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=local).split()
        if len(counts) != 2 or not all(n.isdigit() for n in counts) or int(counts[0]):
            raise FetchError(f"Local-only/ahead/diverged commits at {local}; refusing update")
    return True


def fetch_repo(repo, update=False):
    local = Path(repo["local"])
    if validate_checkout(repo, update=update):
        if update:
            output = _git(["pull", "--ff-only", "--no-rebase", "origin", repo.get("branch", "main")], cwd=local)
            return f"updated {repo['concept']}: {output}"
        return f"verified {repo['concept']} ({local}); not updated"
    local.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--branch", repo.get("branch", "main"), "--", repository_url(repo), str(local)])
    return f"cloned {repo['concept']} -> {local}"


def fetch(features, manifest=None, update=False, *, config=None, root=None, overrides=None):
    manifest = manifest or load_manifest()
    values, _ = resolve_config(manifest, config=config, root=root, overrides=overrides)
    repos = repos_for_features(resolved_manifest(manifest, values), features)
    # Validate all existing sources before the first network/mutating action.
    for repo in repos:
        validate_checkout(repo, update=update)
    return [fetch_repo(repo, update=update) for repo in repos]
