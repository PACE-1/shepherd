"""#10 — the typed response contracts do not drift silently."""
import json
import os
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


_LIVE_ROUTES = (
    "import json, sys; sys.path.insert(0, 'src'); import app; "
    "print(json.dumps([[p, m] for p, ops in app.app.openapi()['paths'].items() for m in ops]))"
)


def test_every_documented_route_still_exists_with_its_method(tmp_path):
    snap = json.loads(SNAPSHOT.read_text())
    # Subprocess with its own SHEPHERD_HOME: importing `app` in-process leaks profile/env
    # state into later tests (#164).
    # openapi(), not app.routes: routers added by include_router (src/routes_*.py) are lazy
    # _IncludedRouter entries in FastAPI >= 0.139 and carry no path/methods of their own.
    out = subprocess.run([sys.executable, "-I", "-c", _LIVE_ROUTES], capture_output=True, text=True,
                         timeout=120, cwd=str(ROOT), env={**os.environ, "SHEPHERD_HOME": str(tmp_path)})
    assert out.returncode == 0, out.stderr[-800:]
    live = {tuple(r) for r in json.loads(out.stdout.splitlines()[-1])}
    for path, ops in snap["paths"].items():
        for method in ops:
            assert (path, method) in live, f"{method.upper()} {path} is documented but not served"
