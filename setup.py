#!/usr/bin/env python3
"""Plan, fetch and provision only the explicitly selected Fennec features."""
import argparse
import json
import sys

from fennec_setup import __version__, detect, recommend, load_manifest
from fennec_setup.config import KEYS
from fennec_setup.provision import (add_plan_options, plan_from_args, print_plan,
                                     execute_plan, update_installed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"fennec-setup {__version__}")
    parser.add_argument("--manifest", help="alternate trusted repos.json")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("detect", help="read-only hardware probes")
    p.add_argument("--disk")
    sub.add_parser("features", help="list explicit feature dependencies")
    sub.add_parser("version", help="print the hub version")
    p = sub.add_parser("update", help="fast-forward every installed clean checkout")
    p.add_argument("--manifest", default=argparse.SUPPRESS)
    p.add_argument("--root", help="clean layout root")
    p.add_argument("--config", help="shared config path")
    for key in KEYS:
        if key != "ctx":
            p.add_argument("--" + key.replace("_", "-"))
    for name in ("plan", "fetch", "install"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", default=argparse.SUPPRESS)
        add_plan_options(p)
        p.add_argument("--dry-run", action="store_true", help="plan without any mutation or network access")
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            device = detect(args.disk)
            print(json.dumps({"device": device.to_dict(), "recommendation": recommend(device)}, indent=2))
            return 0
        manifest = load_manifest(args.manifest)
        if args.command == "features":
            for name, spec in manifest["features"].items():
                print(f"{name:14s} {spec['description']}\n  requires: {', '.join(spec['requires'])}")
            return 0
        if args.command == "version":
            print(f"fennec-setup {__version__}")
            return 0
        if args.command == "update":
            count = update_installed(manifest, root=args.root, config=args.config,
                                     overrides={key: getattr(args, key, None) for key in KEYS})
            print(f"Updated {count} checkout(s).")
            return 0
        planning = args.command == "plan" or args.dry_run
        if args.json and not planning:
            raise ValueError("--json requires plan or --dry-run")
        if args.command == "fetch" and args.build and not planning:
            raise ValueError("--build requires install, not fetch")
        plan = plan_from_args(manifest, args)
        if planning:
            print_plan(plan, machine=args.json)
        else:
            print_plan(plan)
            execute_plan(plan, install=args.command == "install")
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
