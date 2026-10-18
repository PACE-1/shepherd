"""Workout builder routes (#110): preview, save into the rider's folder, and
send to the intervals.icu calendar. Hermetic: stubbed HOME + the ICU seam
(``icu_calendar_push._http``) mocked, like tests/test_calendar_push_workout.py."""
from __future__ import annotations

import copy
import json
import os
import sys
import types
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import db as db_module  # noqa: E402
import app as app_module  # noqa: E402
import training_planner as tp  # noqa: E402
import icu_calendar_push as icp  # noqa: E402
from profile_manager import ProfileManager  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_ENV_KEYS = ("ICU_ATHLETE_ID", "ICU_API_KEY", "ICU_ACCESS_TOKEN")
D1 = (date.today() + timedelta(days=1)).isoformat()


def P(lo, hi=None):
    return {"kind": "power", "lo": lo, "hi": lo if hi is None else hi}


W = {
    "name": "Over unders",
    "description": "",
    "steps": [
        {"kind": "warmup", "duration_s": 600, "target": P(50, 70), "cadence_note": ""},
        {"kind": "repeat", "count": 3,
         "on": {"duration_s": 480, "target": P(95, 105), "cadence_note": "90 rpm"},
         "off": {"duration_s": 240, "target": P(50), "cadence_note": ""}},
        {"kind": "cooldown", "duration_s": 300, "target": P(40, 55), "cadence_note": ""},
    ],
}


@pytest.fixture()
def stub(tmp_path):
    patcher = mock.patch("pathlib.Path.home", return_value=tmp_path)
    patcher.start()
    old = dict(inst=ProfileManager._instance, db=db_module.DB_PATH, data=app_module.DATA_DIR,
               wd=app_module.WORKOUT_DIR, extra=app_module.EXTRA_WORKOUT_DIR, gpx=app_module.GPX_DIR,
               tpextra=tp.EXTRA_WORKOUT_DIR, plan=tp.PLAN_DIR, tpwd=tp.WORKOUT_DIR,
               env={k: os.environ.get(k) for k in _ENV_KEYS})
    for attr in _ENV_KEYS:
        try:
            delattr(config, attr)
        except AttributeError:
            pass
    ProfileManager._instance = None
    app_module.DATA_DIR = tmp_path / ".shepherd"
    app_module.EXTRA_WORKOUT_DIR = None
    pm = ProfileManager.get()
    pid = pm.create_profile("Builder")
    pm.switch(pid)
    db_module._sync_stop.clear()
    ns = types.SimpleNamespace(pm=pm, client=TestClient(app_module.app), home=tmp_path)
    try:
        yield ns
    finally:
        patcher.stop()
        t = app_module._icu_push_timer
        if t is not None:
            t.cancel()
        app_module._icu_push_timer = None
        tp.post_write_callback = None
        ProfileManager._instance = old["inst"]
        app_module.DATA_DIR = old["data"]
        app_module.WORKOUT_DIR = old["wd"]
        app_module.EXTRA_WORKOUT_DIR = old["extra"]
        app_module.GPX_DIR = old["gpx"]
        tp.EXTRA_WORKOUT_DIR = old["tpextra"]
        tp.PLAN_DIR = old["plan"]
        tp.WORKOUT_DIR = old["tpwd"]
        db_module.set_db_path(old["db"])
        db_module._sync_stop.clear()
        app_module.clear_cache()
        for k, v in old["env"].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for attr in _ENV_KEYS:
            try:
                delattr(config, attr)
            except AttributeError:
                pass


class FakeICU:
    def __init__(self, fail=None):
        self.calls, self.fail = [], dict(fail or {})

    def __call__(self, method, path, payload=None, timeout=30.0):
        self.calls.append((method, path, payload))
        return self.fail.get(method, (200, b"[]"))


@pytest.fixture()
def fake(monkeypatch):
    f = FakeICU()
    monkeypatch.setattr(icp, "_http", f)
    return f


def post(stub, path, **body):
    return stub.client.post(f"/api/builder/{path}", json=body)


# ── preview ──────────────────────────────────────────────────────────────────

def test_preview_reports_duration_if_tss_and_profile(stub):
    r = post(stub, "preview", workout=W).json()
    assert r["ok"] is True and r["errors"] == []
    assert r["duration_s"] == 600 + 3 * 720 + 300
    assert 0.4 < r["intensity_factor"] < 1.0
    # same formula as the Library: TSS = hours * IF^2 * 100
    assert r["tss"] == pytest.approx(r["duration_s"] / 3600 * r["intensity_factor"] ** 2 * 100, rel=0.01)
    assert r["profile"][0] == {"x": 0.0, "y": 50.0}


def test_preview_returns_errors_not_an_http_error(stub):
    bad = copy.deepcopy(W)
    bad["steps"][0]["duration_s"] = 0
    res = post(stub, "preview", workout=bad)
    assert res.status_code == 200
    j = res.json()
    assert j["ok"] is False and j["errors"][0]["path"] == "steps[0].duration_s"


def test_preview_with_no_body_workout_is_a_problem_not_a_crash(stub):
    assert post(stub, "preview").json()["ok"] is False


# ── save ─────────────────────────────────────────────────────────────────────

def test_save_writes_zwo_into_profile_folder_and_library_lists_it(stub):
    r = post(stub, "save", workout=W)
    assert r.status_code == 200
    j = r.json()
    assert j["file"] == "builder_over-unders.zwo" and j["created"] is True
    folder = Path(stub.pm.active_dir) / "workouts"
    assert (folder / j["file"]).is_file() and (folder / "builder_over-unders.builder.json").is_file()
    rows = stub.client.get("/api/workouts?limit=3000").json()
    mine = [w for w in rows if w["File"] == j["file"]]
    assert len(mine) == 1 and mine[0]["Name"] == "Over unders"


def test_save_twice_makes_two_files_and_edit_overwrites_in_place(stub):
    a = post(stub, "save", workout=W).json()["file"]
    b = post(stub, "save", workout=W).json()["file"]
    assert a != b
    w2 = copy.deepcopy(W)
    w2["name"] = "Over unders v2"
    c = post(stub, "save", workout=w2, file=a).json()
    assert c["file"] == a and c["created"] is False
    loaded = stub.client.get("/api/builder/workout", params={"file": a}).json()
    assert loaded["workout"]["name"] == "Over unders v2"


def test_invalid_save_is_422_and_writes_nothing(stub):
    bad = copy.deepcopy(W)
    bad["steps"][1]["count"] = 0
    r = post(stub, "save", workout=bad)
    assert r.status_code == 422 and r.json()["errors"]
    assert not (Path(stub.pm.active_dir) / "workouts").exists()


def test_cannot_edit_or_load_a_library_file_or_traverse(stub):
    for f in ("steady.zwo", "../x.zwo", "../../etc/passwd", "sweet_spot_10x1min-1min_90pct_33min.zwo"):
        assert post(stub, "save", workout=W, file=f).status_code == 409
        assert stub.client.get("/api/builder/workout", params={"file": f}).status_code == 404


def test_save_into_an_unwritable_folder_reports_an_error(stub, monkeypatch):
    import routes_builder
    monkeypatch.setattr(routes_builder, "write_text_atomic", mock.Mock(side_effect=PermissionError("denied")))
    r = post(stub, "save", workout=W)
    assert r.status_code == 500 and "denied" in r.json()["error"]


def test_saved_workout_builds_a_fit_like_any_library_workout(stub):
    f = post(stub, "save", workout=W).json()["file"]
    fit = app_module.build_fit_workout_bytes("threshold", 55, "Over unders", f)
    assert fit and len(fit) > 50


# ── send ─────────────────────────────────────────────────────────────────────

def test_send_pushes_the_saved_file_to_the_calendar(stub, fake):
    stub.pm.save_env("i123", "KEY123")
    r = post(stub, "send", workout=W, date=D1).json()
    assert r["push"]["ok"] is True and r["push"]["event_date"] == D1
    method, path, payload = next(c for c in fake.calls if c[0] == "POST")
    assert path.startswith("athlete/i123/events/bulk")
    ev = payload[0]
    assert ev["filename"] == r["file"] and ev["name"] == "Over unders" and ev["start_date_local"] == f"{D1}T00:00:00"
    assert ev["external_id"].startswith(icp._MANUAL_ID_ROOT)


@pytest.mark.parametrize("setup,expect", [
    ("no_connection", "error"),             # nothing connected
    ("oauth_unstamped", "needs_reconnect"),  # token without CALENDAR:WRITE
    ("past_date", "error"),
    ("network", "error"),
    ("http500", "error"),
])
def test_push_failures_keep_the_saved_workout_and_say_why(stub, fake, setup, expect):
    date_ = D1
    if setup == "oauth_unstamped":
        stub.pm.save_icu_token("TOK", "i123")
    elif setup != "no_connection":
        stub.pm.save_env("i123", "KEY123")
    if setup == "past_date":
        date_ = (date.today() - timedelta(days=2)).isoformat()
    if setup == "network":
        fake.fail["POST"] = (0, b"unreachable")
    if setup == "http500":
        fake.fail["POST"] = (500, b"boom")
    res = post(stub, "send", workout=W, date=date_)
    assert res.status_code == 200
    j = res.json()
    assert j["ok"] is True and j["push"].get(expect)
    assert j["push"].get("ok") is not True
    assert (Path(stub.pm.active_dir) / "workouts" / j["file"]).is_file()      # never lost


def test_push_that_raises_still_returns_the_saved_file(stub, monkeypatch):
    monkeypatch.setattr(app_module, "api_calendar_push_workout", mock.Mock(side_effect=RuntimeError("x")))
    j = post(stub, "send", workout=W, date=D1).json()
    assert j["ok"] is True and j["push"]["error"] == "internal:RuntimeError"
    assert (Path(stub.pm.active_dir) / "workouts" / j["file"]).is_file()


def test_send_with_an_invalid_workout_saves_and_pushes_nothing(stub, fake):
    stub.pm.save_env("i123", "KEY123")
    bad = copy.deepcopy(W)
    bad["name"] = ""
    assert post(stub, "send", workout=bad, date=D1).status_code == 422
    assert not fake.calls
