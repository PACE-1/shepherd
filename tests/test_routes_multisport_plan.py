"""Companion-session routes and the completion hook (ADDENDUM 5): GET /api/plan/companions,
POST /api/plan/companions/{id}/dismiss, and app._reconcile_current_week's companion step."""
import copy
import json
from datetime import date, timedelta

import pytest

import api_models
import clock
import db

TODAY = date(2026, 9, 16)                       # a Wednesday
MON = TODAY - timedelta(days=2)


def _comp(day, sport="running", minutes=40, status="pending"):
    return {"id": f"{sport}-{day}", "day": day, "day_name": "", "sport": sport, "session_type": "run_easy",
            "duration_min": minutes, "tss_estimate": 0.0, "description": "Easy run", "status": status,
            "hard": False, "template_id": "placeholder-run-easy", "dismissed_at": "",
            "workout": {"name": "Easy run", "steps": []}}


def _ride(day, minutes=60):
    return {"day": day, "day_name": "", "session_type": "z2", "duration_min": minutes, "tss_estimate": 40.0,
            "description": "", "zwo_file": "", "status": "pending"}


def _plan():
    d = lambda k: (MON + timedelta(days=k)).isoformat()
    return {"goal": {"type": "ftp", "hours_per_week": 10},
            "weeks": [
                {"week_num": 0, "start": d(-7), "end": d(-1), "phase": "base", "tss_target": 300, "is_stepback": False,
                 "sessions": [_ride(d(-6))], "companions": [_comp(d(-5), status="missed"), _comp(d(-4), status="done")]},
                {"week_num": 1, "start": d(0), "end": d(6), "phase": "base", "tss_target": 300, "is_stepback": False,
                 "sessions": [_ride(d(1)), _ride(d(3))],
                 "companions": [_comp(d(1)), _comp(d(2), "swimming"), _comp(d(4))]},
                {"week_num": 2, "start": d(7), "end": d(13), "phase": "base", "tss_target": 300, "is_stepback": False,
                 "sessions": [_ride(d(8))], "companions": [_comp(d(9))]},
                {"week_num": 3, "start": d(14), "end": d(20), "phase": "base", "tss_target": 300, "is_stepback": False,
                 "sessions": [_ride(d(15))], "companions": [_comp(d(16))]}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_multisport_plan as r
    monkeypatch.setattr(r, "_plan_dir", lambda: tmp_path)
    clock.freeze(TODAY)
    (tmp_path / "current_plan.json").write_text(json.dumps(_plan()))
    yield TestClient(app.app), tmp_path
    clock.unfreeze()


def test_get_returns_this_and_next_week_and_today(client):
    c, _d = client
    r = c.get("/api/plan/companions")
    assert r.status_code == 200
    body = api_models.PlanCompanions.model_validate(r.json())
    assert [w.week_num for w in body.weeks] == [1, 2]
    assert [x.id for x in body.today] == [f"swimming-{TODAY.isoformat()}"]
    assert "not validated" in body.note.lower() and body.has_plan


def test_get_from_another_week_and_ended_weeks_hide_missed(client):
    c, _d = client
    weeks = c.get("/api/plan/companions", params={"start": (MON - timedelta(days=3)).isoformat()}).json()["weeks"]
    assert [w["week_num"] for w in weeks] == [0, 1]
    assert [x["status"] for x in weeks[0]["companions"]] == ["done"]
    assert c.get("/api/plan/companions", params={"start": "nope"}).status_code == 400


def test_get_without_a_plan(client):
    c, d = client
    (d / "current_plan.json").unlink()
    body = c.get("/api/plan/companions").json()
    assert body["has_plan"] is False and body["weeks"] == [] and body["today"] == []


def test_dismiss_persists_and_unknown_is_404(client):
    c, d = client
    cid = f"running-{(MON + timedelta(days=4)).isoformat()}"
    r = c.post(f"/api/plan/companions/{cid}/dismiss")
    assert r.status_code == 200
    assert api_models.CompanionDismissed.model_validate(r.json()).companion.status == "dismissed"
    stored = json.loads((d / "current_plan.json").read_text())
    got = [x for w in stored["weeks"] for x in w.get("companions", []) if x["id"] == cid][0]
    assert got["status"] == "dismissed" and got["dismissed_at"]
    assert stored["weeks"][1]["sessions"] == _plan()["weeks"][1]["sessions"]
    assert c.post("/api/plan/companions/nope/dismiss").status_code == 404


def test_reconcile_hook_marks_companions_and_leaves_cycling_matching_alone(client, monkeypatch):
    import app
    run = {"id": "act-run", "date": (MON + timedelta(days=1)).isoformat(), "sport": "Run",
           "duration_sec": 45 * 60, "tss": 30}
    monkeypatch.setattr(db, "query_activities", lambda days=14: [dict(run)])
    with_c, without = _plan(), _plan()
    for w in without["weeks"]:
        w.pop("companions")
    app._reconcile_current_week(with_c, TODAY)
    app._reconcile_current_week(without, TODAY)
    assert [w["sessions"] for w in with_c["weeks"]] == [w["sessions"] for w in without["weeks"]]
    st = {x["id"]: x["status"] for x in with_c["weeks"][1]["companions"]}
    assert st[f"running-{(MON + timedelta(days=1)).isoformat()}"] == "done"
    assert st[f"swimming-{TODAY.isoformat()}"] == "pending"


def test_reconcile_hook_never_raises(monkeypatch):
    import routes_multisport_plan as r

    def boom(days=14):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "query_activities", boom)
    wk = copy.deepcopy(_plan()["weeks"][1])
    assert r.reconcile_plan_week(wk, TODAY) == 0
    assert r.reconcile_plan_week({"sessions": []}, TODAY) == 0
