"""Colibri environment setup: device detection, repo manifest, fetching."""
from .devices import detect, recommend, Device
from .fetch import load_manifest, repos_for_features, fetch, fetch_repo

__all__ = ["detect", "recommend", "Device", "load_manifest", "repos_for_features", "fetch", "fetch_repo"]