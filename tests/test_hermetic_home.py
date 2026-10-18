"""3.4.3 — hermetic-fs gate: the suite must NEVER write the user's real home.

Owner incident (2026-07-16): a release-gate run replaced the owner's live
~/.shepherd/profiles/<name>/plans/current_plan.json with a fixture plan
(goal.event_name == "v134-test", from test_v134_generate_plan_no_yellow's
TestClient POST to /api/plan/generate). Every app data path resolves through
Path.home()/.shepherd at import time, and profile_manager rebinds
training_planner.PLAN_DIR to the ACTIVE PROFILE's plan dir — so any
unsandboxed test that generates/updates a plan stomped the real store.

conftest.py now swaps HOME to a per-process sandbox BEFORE any project
import (keeping the real path in SHEPHERD_REAL_HOME for read-only
validations). These tests pin that contract.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import app as app_module
import training_planner as tp


def test_home_is_sandboxed():
    real = os.environ.get("SHEPHERD_REAL_HOME")
    assert real, "conftest must record the real home in SHEPHERD_REAL_HOME"
    assert str(Path.home()) != real, "HOME must be swapped to a sandbox"
    assert "domestique-test-home-" in str(Path.home()), (
        f"HOME does not look like the conftest sandbox: {Path.home()}")


def test_app_data_paths_resolve_inside_sandbox():
    real = os.environ.get("SHEPHERD_REAL_HOME") or ""
    sandbox = str(Path.home())
    # The two import-time roots every plan write funnels through.
    plan_dir = str(app_module._plan_dir())
    assert plan_dir.startswith(sandbox), (
        f"app._plan_dir() escapes the sandbox: {plan_dir}")
    assert not plan_dir.startswith(str(Path(real) / ".shepherd")), (
        f"app._plan_dir() points at the REAL home: {plan_dir}")
    tp_dir = str(tp.PLAN_DIR)
    assert tp_dir.startswith(sandbox), (
        f"training_planner.PLAN_DIR escapes the sandbox: {tp_dir}")


def test_generate_endpoint_writes_only_the_sandbox():
    """Behavioral pin on the exact leak path: POST /api/plan/generate via
    TestClient and assert the plan landed in the SANDBOX plan dir (the write
    path itself proves no real-home write — _plan_dir() is sandboxed and is
    the only path the endpoint writes)."""
    from fastapi.testclient import TestClient

    sandbox = str(Path.home())
    with TestClient(app_module.app) as client:
        r = client.post("/api/plan/generate", json={
            "goal_type": "event",
            "event_name": "hermetic-fs-test",
            "event_km": 120, "event_climb": 800,
            "event_type": "gran fondo",
            "hours_per_week": 8, "plan_weeks": 8,
            "rest_days": [0], "available_days": [1, 2, 3, 4, 5, 6],
        })
        assert r.status_code == 200, r.text
    written = app_module._plan_dir() / "current_plan.json"
    assert str(written).startswith(sandbox)
    assert written.exists(), "generate must persist the plan in the sandbox"
    goal = (json.loads(written.read_text()).get("goal") or {})
    assert goal.get("event_name") == "hermetic-fs-test"


@pytest.mark.skipif(
    not os.environ.get("SHEPHERD_REAL_HOME"), reason="no real home recorded")
def test_real_home_helper_points_outside_sandbox():
    real = Path(os.environ["SHEPHERD_REAL_HOME"])
    assert str(Path.home()) != str(real)
    # Never a sandbox artifact: the recorded real home must not be a tmp dir
    # minted by this gate.
    assert "domestique-test-home-" not in str(real)


@pytest.mark.parametrize("mode", ["collect", "run", "workers"])
def test_inherited_data_root_and_credentials_cannot_escape_sandbox(tmp_path, mode):
    """Exercise the real bootstrap in a fresh interpreter, before collection."""
    external = tmp_path / "external-data"
    external.mkdir()
    (external / "sentinel").write_text("untouched")
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "conftest.py").symlink_to(Path(__file__).with_name("conftest.py"))
    (suite / "_sandbox.py").symlink_to(Path(__file__).with_name("_sandbox.py"))
    report = tmp_path / "report.json"
    (suite / "test_probe.py").write_text('''
import json, os
from pathlib import Path
import app, db, config, training_planner
from user_home import shepherd_home

root = shepherd_home()
assert root.is_relative_to(Path.home())
assert os.environ["SHEPHERD_NO_NET"] == "1"
assert not config.ICU_API_KEY
assert not config.ICU_ACCESS_TOKEN
assert not config.ICU_OAUTH_CLIENT_SECRET
assert db._USER_DATA == root
assert app.DATA_DIR == root
assert training_planner.PLAN_DIR.is_relative_to(root)
(root / "collection-probe").write_text("sandbox only")
worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
Path(os.environ["SANDBOX_REPORT"] + "." + worker).write_text(json.dumps({"root": str(root)}))

def test_startup_and_write():
    from fastapi.testclient import TestClient
    with TestClient(app.app) as client:
        assert client.get("/healthz").status_code == 200   # not "/": it redirects into the web UI, which the gate job has not built
    (app._plan_dir() / "probe.json").write_text("{}")
''')
    env = os.environ.copy()
    env.update(SHEPHERD_HOME=str(external), ICU_API_KEY="external-key",
               ICU_ACCESS_TOKEN="external-token", ICU_OAUTH_CLIENT_SECRET="external-secret",
               SANDBOX_REPORT=str(report), PYTEST_ADDOPTS="")
    env.pop("SHEPHERD_NO_NET", None)
    # Block real transports even before pytest's network fixtures run.
    runner = '''
import socket, sys, pytest
def blocked(*args, **kwargs):
    raise AssertionError("unexpected network during sandbox bootstrap")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
sys.exit(pytest.main(sys.argv[1:]))
'''
    args = [sys.executable, "-c", runner, str(suite), "-q", "-p", "no:cacheprovider"]
    if mode == "collect":
        args.append("--collect-only")
    elif mode == "workers":
        args.extend(["-n", "2", "--dist", "each"])
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(external.iterdir()) == [external / "sentinel"]
    assert (external / "sentinel").read_text() == "untouched"
    reports = list(tmp_path.glob("report.json.*"))
    roots = {Path(json.loads(p.read_text())["root"]) for p in reports}
    assert len(roots) == (2 if mode == "workers" else 1)
    assert all(not root.exists() for root in roots), "child sandboxes must be cleaned up"
