"""Fennec environment setup: device detection, repo manifest, fetching."""
__version__ = "1.7.0"
from .devices import detect, recommend, Device
from .fetch import load_manifest, repos_for_features, fetch, fetch_repo, FetchError
from .config import resolve_config, resolved_manifest

__all__ = ["detect", "recommend", "Device", "load_manifest", "repos_for_features", "fetch", "fetch_repo", "FetchError", "resolve_config", "resolved_manifest"]