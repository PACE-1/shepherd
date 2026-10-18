"""#10 — the typed response contracts do not drift silently."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tests" / "api_contract.json"


def _current() -> dict:
    out = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "dump_openapi.py")],
                         capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_contract_matches_the_checked_in_snapshot():
    assert _current() == json.loads(SNAPSHOT.read_text()), (
        "A typed response contract changed. If that is intended, regenerate with "
        "`python tools/dump_openapi.py > tests/api_contract.json` and "
        "`tools/gen-api-types.sh`, and review both diffs.")


def test_every_documented_route_still_exists_with_its_method():
    snap = json.loads(SNAPSHOT.read_text())
    import os, tempfile
    os.environ.setdefault("SHEPHERD_HOME", tempfile.mkdtemp(prefix="domestique-contract-"))
    import app as app_module
    def flat(routes, prefix=""):
        # FastAPI >= 0.139 keeps an included router (src/routes_*.py) as one wrapper entry.
        for r in routes:
            inner = getattr(r, "original_router", None)
            if inner is not None:
                yield from flat(inner.routes, prefix + (getattr(inner, "prefix", "") or ""))
            else:
                yield prefix + r.path, getattr(r, "methods", None) or ()

    live = {(path, m.lower()) for path, methods in flat(app_module.app.routes) for m in methods}
    for path, ops in snap["paths"].items():
        for method in ops:
            assert (path, method) in live, f"{method.upper()} {path} is documented but not served"
