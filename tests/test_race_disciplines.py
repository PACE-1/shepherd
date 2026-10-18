"""Triathlon, run and swim races (#125 honest version, #111 follow-on): labels only. The discipline and the
triathlon distance label are stored; no distance-specific plan exists; cycling-only fields never reach the
plan's goal; the race-day plan is cycling-only and says so."""
import json
from datetime import date

import pytest

import clock
import races

TODAY = date(2026, 9, 14)


def _goal(**kw):
    return {"type": "event", "event_date": "2027-03-14", "event_name": "Spring Fondo", "event_km": 120,
            "event_climb": 1500, "event_type": "granfondo", "events": [], **kw}


@pytest.mark.parametrize("distance", races.TRI_DISTANCES)
def test_a_triathlon_takes_each_distance_label(tmp_path, distance):
    r = races.add_race(tmp_path / races.FILE_NAME, None,
                       {"date": "2027-06-01", "discipline": "Triathlon", "distance": distance.upper(),
                        "event_km": 40, "event_climb_m": 300, "event_type": "crit"}, TODAY)
    assert (r["discipline"], r["distance"]) == ("triathlon", distance)
    # cycling-only fields are not stored: the planner would read them as a ride
    assert (r["event_km"], r["event_climb_m"], r["event_type"]) == (0, 0, "granfondo")


@pytest.mark.parametrize("disc", ["running", "swimming"])
def test_run_and_swim_races_are_labels_without_a_distance(tmp_path, disc):
    r = races.add_race(tmp_path / races.FILE_NAME, None,
                       {"date": "2027-06-01", "discipline": disc, "distance": "olympic", "event_km": 10}, TODAY)
    assert (r["discipline"], r["distance"], r["event_km"]) == (disc, None, 0)


def test_cycling_races_are_unchanged_and_old_rows_read_as_cycling(tmp_path):
    p = tmp_path / races.FILE_NAME
    r = races.add_race(p, None, {"date": "2027-06-01", "event_km": 90, "distance": "70.3"}, TODAY)
    assert (r["discipline"], r["distance"], r["event_km"]) == ("cycling", None, 90)
    assert races.from_goal(_goal())[0]["discipline"] == "cycling"
    p.write_text(json.dumps({"races": [{"id": "old", "date": "2027-07-01", "priority": "C", "event_km": 50}]}))
    upd = races.update_race(p, None, "old", {"name": "Old one"})
    assert (upd["discipline"], upd["distance"], upd["event_km"]) == ("cycling", None, 50)


def test_a_triathlon_a_race_names_the_goal_but_leaves_its_ride_fields():
    plan = {"goal": _goal()}
    a = {**races.from_goal(_goal())[0], "discipline": "triathlon", "distance": "70.3", "name": "Half", "event_km": 0}
    assert races.sync_plan_goal(plan, [a]) is True
    g = plan["goal"]
    assert g["event_name"] == "Half" and (g["event_km"], g["event_climb"], g["event_type"]) == (120, 1500, "granfondo")


def test_a_b_triathlon_goes_into_the_plan_like_any_b_race():
    plan = {"goal": _goal()}
    b = races._race(date="2026-11-01", priority="B", discipline="triathlon", distance="sprint", name="Sprint")
    assert races.sync_plan_goal(plan, [b])
    assert plan["goal"]["events"] == [{"date": "2026-11-01", "priority": "B", "name": "Sprint",
                                       "event_type": "granfondo", "event_km": 0, "event_climb_m": 0}]


def test_timeline_without_a_warm_up():
    r = {"date": "2027-03-14", "start_time": "07:00"}
    assert [t["label"] for t in races.timeline(r, 0, 5.0)] == ["Start", "Expected finish"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_races
    monkeypatch.setattr(routes_races, "_plan_dir", lambda: tmp_path)
    monkeypatch.setattr(routes_races, "_races_path", lambda: tmp_path / races.FILE_NAME)
    monkeypatch.setattr(routes_races, "_fitness_inputs", lambda: ({"ftp": 250, "weight_kg": 70.0}, 55.0, 3.0, {}))
    clock.freeze(TODAY)
    yield TestClient(app.app)
    clock.unfreeze()


def test_the_race_day_plan_of_a_triathlon_is_cycling_only_and_says_so(client):
    r = client.post("/api/races", json={"date": "2027-06-01", "priority": "B", "discipline": "triathlon",
                                        "distance": "olympic", "start_time": "07:00", "expected_duration_h": 2.5})
    assert r.status_code == 200
    tri = r.json()["races"][0]
    assert (tri["discipline"], tri["distance"]) == ("triathlon", "olympic")
    day = client.get(f"/api/races/{tri['id']}/race-day").json()
    assert day["power"] == {**day["power"], "available": False, "reason": routes_races_text()}
    assert day["warmup_min"] == 0 and [t["label"] for t in day["timeline"]] == ["Start", "Expected finish"]
    assert client.post("/api/races", json={"date": "2027-06-02", "discipline": "triathlon"}).status_code == 400


def routes_races_text():
    import routes_races
    return routes_races.NOT_CYCLING
