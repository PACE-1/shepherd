"""Brick routes (#123): the rider's transition-time target and the per-brick note on the run off the bike."""
import json
from datetime import date

import pytest

import api_models
import clock

TODAY = date(2026, 9, 16)                       # a Wednesday


def _comp(day, brick=True, **kw):
    w = {"name": "Brick run", "steps": []}
    if brick:
        w["brick_of"] = f"cycling-{day}"
    return {"id": f"running-{day}", "day": day, "day_name": "", "sport": "running",
            "session_type": "brick_run" if brick else "run_easy", "duration_min": 20, "tss_estimate": 0.0,
            "description": "Brick", "status": "pending", "hard": False, "template_id": "placeholder-run-brick",
            "dismissed_at": "", "workout": w, **kw}


def _plan():
    return {"goal": {"type": "ftp"}, "weeks": [
        {"week_num": 1, "start": "2026-09-14", "end": "2026-09-20", "phase": "base", "tss_target": 300,
         "is_stepback": False, "sessions": [],
         "companions": [_comp("2026-09-15"), _comp("2026-09-16", brick=False), _comp("2026-09-19")]}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_multisport_plan as r
    monkeypatch.setattr(r, "_plan_dir", lambda: tmp_path)
    monkeypatch.setattr(r, "_transition_path", lambda: tmp_path / r.TRANSITION_FILE)
    clock.freeze(TODAY)
    (tmp_path / "current_plan.json").write_text(json.dumps(_plan()))
    yield TestClient(app.app), tmp_path
    clock.unfreeze()


def test_the_transition_target_has_no_default_and_is_stored(client):
    c, d = client
    assert c.get("/api/plan/companions").json()["transition_target_s"] is None
    r = c.put("/api/plan/bricks/transition", json={"transition_target_s": 150})
    assert r.status_code == 200 and api_models.BrickTransition(**r.json()).transition_target_s == 150
    assert json.loads((d / "brick_transition.json").read_text()) == {"transition_target_s": 150}
    assert c.get("/api/plan/companions").json()["transition_target_s"] == 150
    assert c.put("/api/plan/bricks/transition", json={"transition_target_s": None}).json()["transition_target_s"] is None
    assert c.get("/api/plan/companions").json()["transition_target_s"] is None


@pytest.mark.parametrize("bad", [0, -5, 3601, 2.5, "2:30", True])
def test_a_bad_transition_target_is_refused(client, bad):
    c, d = client
    assert c.put("/api/plan/bricks/transition", json={"transition_target_s": bad}).status_code == 400
    assert not (d / "brick_transition.json").exists()


def test_the_brick_note_is_stored_with_the_companion_and_editable(client):
    c, d = client
    comps = c.get("/api/plan/companions", params={"start": "2026-09-14"}).json()["weeks"][0]["companions"]
    assert comps[0]["brick_of"] == "cycling-2026-09-15" and "brick_of" not in comps[1]
    r = c.post("/api/plan/companions/running-2026-09-15/brick-note", json={"note": "  Heavy legs, then fine. "})
    assert r.status_code == 200
    out = api_models.CompanionDismissed(**r.json()).companion
    assert out.brick_note == "Heavy legs, then fine." and out.brick_of == "cycling-2026-09-15"
    stored = json.loads((d / "current_plan.json").read_text())["weeks"][0]["companions"][0]
    assert stored["workout"]["brick_note"] == "Heavy legs, then fine."
    c.post("/api/plan/companions/running-2026-09-15/brick-note", json={"note": ""})
    stored = json.loads((d / "current_plan.json").read_text())["weeks"][0]["companions"][0]
    assert "brick_note" not in stored["workout"]


@pytest.mark.parametrize("cid,body,code", [
    ("running-2026-09-16", {"note": "x"}, 400),         # not a brick
    ("running-2026-09-19", {"note": "x"}, 400),         # its day has not come
    ("running-2026-09-15", {"note": "x" * 501}, 400),
    ("running-2026-09-15", {"note": 5}, 400),
    ("nope", {"note": "x"}, 404),
])
def test_bad_brick_notes_are_refused(client, cid, body, code):
    c, d = client
    before = (d / "current_plan.json").read_text()
    assert c.post(f"/api/plan/companions/{cid}/brick-note", json=body).status_code == code
    assert (d / "current_plan.json").read_text() == before
