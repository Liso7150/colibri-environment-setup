#!/usr/bin/env python3
"""Colibri environment setup CLI.

Detects your device, lets you pick features/apps, and fetches the needed repos
into the suite layout. Credits the Colibri engine (JustVugg/colibri) and AirLLM
(lyogavin/airllm).

    python setup.py detect
    python setup.py features
    python setup.py plan --features inference,desktop,jetbrains
    python setup.py fetch --features inference,desktop
    python setup.py fetch --all
"""
import argparse
import json
import sys

from colibri_setup import detect, recommend, load_manifest, repos_for_features, fetch


def cmd_detect(args):
    dev = detect(args.disk)
    print(json.dumps({"device": dev.to_dict(), "recommendation": recommend(dev)}, indent=2))


def cmd_features(args):
    m = load_manifest(args.manifest)
    for name, spec in m["features"].items():
        paused = " (paused)" if any(r.get("paused") for r in m["repos"] if r["concept"] in spec["requires"]) else ""
        print(f"  {name:14s} {spec['description']}{paused}")
        print(f"                 requires: {', '.join(spec['requires'])}")


def _selected(args, m):
    if args.all:
        return [f for f in m["features"]]
    feats = [f.strip() for f in (args.features or "").split(",") if f.strip()]
    if not feats:
        sys.exit("error: pass --features a,b,c or --all (see `features`)")
    return feats


def cmd_plan(args):
    m = load_manifest(args.manifest)
    feats = _selected(args, m)
    repos = repos_for_features(m, feats)
    print(f"features: {', '.join(feats)}")
    print("repos to fetch:")
    for r in repos:
        tag = " [required]" if r.get("required") else ""
        print(f"  {r['concept']:14s} {r['repo']:32s} -> {r['local']}{tag}")
    print("\ncredits:")
    for c in m["credits"]:
        print(f"  {c['name']}: {c['upstream']} ({c['role']})")


def cmd_fetch(args):
    m = load_manifest(args.manifest)
    feats = _selected(args, m)
    print(f"fetching for features: {', '.join(feats)}", flush=True)
    for line in fetch(feats, manifest=m, update=args.update):
        print(" ", line, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Colibri environment setup")
    ap.add_argument("--manifest", help="path to repos.json (default: bundled)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect", help="detect device + recommend config")
    p.add_argument("--disk", help="model/cache drive to check free space")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("features", help="list installable features")
    p.set_defaults(fn=cmd_features)

    for name, fn, help_ in (("plan", cmd_plan, "show repos for features"),
                            ("fetch", cmd_fetch, "clone repos for features")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--features", help="comma-separated feature names")
        p.add_argument("--all", action="store_true", help="select every feature")
        if name == "fetch":
            p.add_argument("--update", action="store_true", help="git pull existing repos")
        p.set_defaults(fn=fn)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()