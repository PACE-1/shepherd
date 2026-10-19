#!/usr/bin/env python3
"""List breaking public-API changes between a base revision and the working tree.

Breaking here means (docs/DEVELOPMENT.md, "Versioning"): a route or response
field gone from tests/api_contract.json, or a SHEPHERD_* variable no longer
mentioned in src/ or the Dockerfile (a rename shows up as a removal).
Usage: check_breaking.py <base-rev>   Exit 1 when anything is removed.
"""
import json
import re
import subprocess
import sys

CONTRACT = "tests/api_contract.json"
VAR = re.compile(r"SHEPHERD_[A-Z0-9_]+")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def routes_and_fields(contract):
    routes = {f"{m.upper()} {p}" for p, ops in contract.get("paths", {}).items() for m in ops}
    fields = {
        f"{name}.{prop}"
        for name, schema in contract.get("components", {}).get("schemas", {}).items()
        for prop in schema.get("properties", {})
    }
    return routes, fields


def env_vars(rev=None):
    if rev:
        out = git("grep", "-hoE", VAR.pattern, rev, "--", "src", "Dockerfile")
    else:
        out = git("grep", "-hoE", VAR.pattern, "--", "src", "Dockerfile")
    return set(VAR.findall(out))


def removed(base_rev):
    base_routes, base_fields = routes_and_fields(json.loads(git("show", f"{base_rev}:{CONTRACT}")))
    with open(CONTRACT) as f:
        routes, fields = routes_and_fields(json.load(f))
    return {
        "route": sorted(base_routes - routes),
        "field": sorted(base_fields - fields),
        "variable": sorted(env_vars(base_rev) - env_vars()),
    }


if __name__ == "__main__":
    found = removed(sys.argv[1])
    for kind, items in found.items():
        for item in items:
            print(f"removed {kind}: {item}")
    sys.exit(1 if any(found.values()) else 0)
