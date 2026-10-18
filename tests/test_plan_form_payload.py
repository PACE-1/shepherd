"""The plan form's payload for an event goal with B/C races is accepted (the A race is not repeated in events)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

import app
import training_planner as tp


def _payload(events):
    # What web/src/lib/planForm.ts applyAdvanced builds for an event goal with one C race.
    a = date.today() + timedelta(days=100)
    c = date.today() + timedelta(days=50)
    return {"goal": "event", "hours_per_week": 8, "plan_weeks": 12, "rest_days": [],
            "event_name": "Fondo", "event_date": a.isoformat(), "event_km": 120, "event_type": "granfondo",
            "events": events(a, c)}


def test_form_payload_with_a_race_in_goal_fields_and_c_in_events_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(tp, "PLAN_DIR", tmp_path / "plans", raising=False)
    client = TestClient(app.app)
    r = client.post("/api/plan/generate", json=_payload(
        lambda a, c: [{"date": c.isoformat(), "priority": "C", "name": "Crit"}]))
    assert r.status_code == 200, r.text[:300]


def test_an_a_race_repeated_in_events_is_refused_by_the_server(monkeypatch, tmp_path):
    # The server refusal is intended ("one A event per plan"): the form must not send this.
    monkeypatch.setattr(tp, "PLAN_DIR", tmp_path / "plans", raising=False)
    client = TestClient(app.app)
    r = client.post("/api/plan/generate", json=_payload(lambda a, c: [
        {"date": a.isoformat(), "priority": "A", "name": "Fondo"},
        {"date": c.isoformat(), "priority": "C", "name": "Crit"}]))
    assert r.status_code == 400
    assert "one A event" in r.text
