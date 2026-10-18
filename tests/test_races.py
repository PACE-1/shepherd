"""#111 races: the A/B/C list, its migration from the plan goal, how it reaches the plan, the race-day plan."""
import json
from datetime import date

import pytest

import clock
import races
import training_planner as tp

TODAY = date(2026, 9, 14)


def _goal(**kw):
    return {"type": "event", "event_date": "2027-03-14", "event_name": "Spring Fondo", "event_km": 120,
            "event_climb": 1500, "event_type": "granfondo",
            "events": [{"date": "2026-11-01", "priority": "B", "name": "Club race", "event_km": 0,
                        "event_climb": 0, "event_type": "crit"}], **kw}


# ── the list ──────────────────────────────────────────────────────────────────────────────────────────
def test_event_types_are_the_planners():
    assert set(races.EVENT_TYPES) == set(tp.EVENT_TYPE_IF)


def test_a_rider_without_a_list_reads_the_plan_goal_and_nothing_is_written(tmp_path):
    p = tmp_path / races.FILE_NAME
    got = races.read_races(p, _goal())
    assert [(r["priority"], r["date"], r["name"]) for r in got] == [
        ("B", "2026-11-01", "Club race"), ("A", "2027-03-14", "Spring Fondo")]
    a = got[1]
    assert (a["event_km"], a["event_climb_m"], a["event_type"], a["discipline"]) == (120, 1500, "granfondo", "cycling")
    assert races.read_races(p, _goal())[1]["id"] == a["id"]           # ids are stable before anything is saved
    assert not p.exists() and races.read_stored(p) is None
    assert all(races.in_plan(r, _goal()) for r in got)


def test_a_non_event_plan_has_no_a_race():
    assert races.from_goal({"type": "ftp", "event_date": "2027-03-14"}) == []
    assert races.from_goal(None) == []


def test_the_first_change_stores_the_migrated_list_with_it(tmp_path):
    p = tmp_path / races.FILE_NAME
    races.add_race(p, _goal(), {"date": "2026-12-06", "priority": "C", "name": "Cross"}, TODAY)
    stored = races.read_stored(p)
    assert [(r["priority"], r["date"]) for r in stored] == [("B", "2026-11-01"), ("C", "2026-12-06"),
                                                             ("A", "2027-03-14")]


def test_edit_and_delete(tmp_path):
    p = tmp_path / races.FILE_NAME
    r = races.add_race(p, _goal(), {"date": "2026-12-06", "priority": "B", "event_km": 80}, TODAY)
    upd = races.update_race(p, _goal(), r["id"], {"priority": "C", "start_time": "09:30", "arrive_time": "08:15"})
    assert (upd["priority"], upd["event_km"], upd["start_time"]) == ("C", 80, "09:30")
    races.delete_race(p, _goal(), r["id"])
    assert r["id"] not in [x["id"] for x in races.read_races(p, _goal())]
    with pytest.raises(KeyError):
        races.delete_race(p, _goal(), r["id"])
    with pytest.raises(KeyError):
        races.update_race(p, _goal(), "nope", {})


@pytest.mark.parametrize("body, msg", [
    ({"date": "2026-12-06", "priority": "D"}, "A, B or C"),
    ({"date": "2026-12-06", "discipline": "running"}, "only cycling"),
    ({"date": "06/12/2026"}, "date"),
    ({"date": "2026-09-01"}, "past"),
    ({"date": "2026-12-06", "event_type": "triathlon"}, "event_type"),
    ({"date": "2026-12-06", "event_km": -5}, "distance"),
    ({"date": "2026-12-06", "start_time": "9am"}, "HH:MM"),
    ({"date": "2026-12-06", "start_time": "09:00", "arrive_time": "09:30"}, "arrival"),
    ({"date": "2026-11-01", "priority": "B"}, "already a B race"),
    ({"date": "2026-12-06", "priority": "A"}, "already an A race"),
])
def test_bad_races_are_refused(tmp_path, body, msg):
    with pytest.raises(ValueError, match=msg):
        races.add_race(tmp_path / "r.json", _goal(), body, TODAY)


def test_the_plans_a_race_keeps_its_date_and_priority(tmp_path):
    p = tmp_path / races.FILE_NAME
    a = races.read_races(p, _goal())[1]
    for change in ({"date": "2027-04-01"}, {"priority": "B"}):
        with pytest.raises(ValueError, match="plan's goal"):
            races.update_race(p, _goal(), a["id"], change)
    with pytest.raises(ValueError, match="plan's goal"):
        races.delete_race(p, _goal(), a["id"])
    assert races.update_race(p, _goal(), a["id"], {"event_km": 140})["event_km"] == 140


def test_an_a_race_without_an_event_plan_is_kept_but_not_in_the_plan(tmp_path):
    p = tmp_path / races.FILE_NAME
    goal = {"type": "continuous"}
    r = races.add_race(p, goal, {"date": "2027-05-01", "priority": "A", "name": "Big one"}, TODAY)
    assert not races.in_plan(r, goal)
    plan = {"goal": dict(goal)}
    assert races.sync_plan_goal(plan, races.read_races(p, goal)) is False   # nothing for the planner to take
    assert "events" not in plan["goal"]


def test_a_corrupt_file_is_never_overwritten(tmp_path):
    p = tmp_path / races.FILE_NAME
    p.write_text("{nope")
    with pytest.raises(OSError):
        races.add_race(p, _goal(), {"date": "2026-12-06"}, TODAY)
    assert p.read_text() == "{nope"


# ── the plan ──────────────────────────────────────────────────────────────────────────────────────────
def test_sync_writes_b_c_races_to_goal_events_and_the_a_details_to_the_goal(tmp_path):
    p = tmp_path / races.FILE_NAME
    plan = {"goal": _goal()}
    races.add_race(p, plan["goal"], {"date": "2026-12-06", "priority": "C", "name": "Cross", "event_km": 40}, TODAY)
    a = races.read_races(p, plan["goal"])[-1]
    races.update_race(p, plan["goal"], a["id"], {"name": "Fondo", "event_km": 150})
    assert races.sync_plan_goal(plan, races.read_races(p, plan["goal"])) is True
    g = plan["goal"]
    assert [(e["priority"], e["date"]) for e in g["events"]] == [("B", "2026-11-01"), ("C", "2026-12-06")]
    assert (g["event_name"], g["event_km"], g["event_date"]) == ("Fondo", 150, "2027-03-14")
    # The planner reads it back: B/C as TargetEvents, never an A entry (it refuses a second A).
    goal = tp.goal_from_dict(g)
    assert [(e.priority, e.event_km) for e in goal.events] == [("B", 0), ("C", 40)]
    assert races.sync_plan_goal(plan, races.read_races(p, plan["goal"])) is False   # idempotent


def test_a_plan_without_races_is_left_alone():
    plan = {"goal": {"type": "continuous"}}
    assert races.sync_plan_goal(plan, []) is False and plan == {"goal": {"type": "continuous"}}


# ── race day ──────────────────────────────────────────────────────────────────────────────────────────
def test_timeline():
    r = {"date": "2027-03-14", "start_time": "08:30", "arrive_time": "07:15"}
    assert races.timeline(r, 15, 4.5) == [
        {"time": "07:15", "label": "Arrive"}, {"time": "08:15", "label": "Warm up (15 min)"},
        {"time": "08:30", "label": "Start"}, {"time": "13:00", "label": "Expected finish"}]
    assert races.timeline({"date": "2027-03-14"}, 15, 4.5) == []


# ── endpoints ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_races
    monkeypatch.setattr(routes_races, "_plan_dir", lambda: tmp_path)
    monkeypatch.setattr(routes_races, "_races_path", lambda: tmp_path / races.FILE_NAME)
    monkeypatch.setattr(routes_races, "_fitness_inputs",
                        lambda: ({"ftp": 250, "weight_kg": 70.0}, 55.0, 3.0, {}))
    clock.freeze(TODAY)
    yield TestClient(app.app), tmp_path
    clock.unfreeze()


def _write_plan(d, goal):
    weeks = [{"week_num": 1, "start": "2027-03-01", "end": "2027-03-07", "phase": "taper", "tss_target": 300,
              "is_stepback": False,
              "sessions": [{"day": "2027-03-02", "session_type": "z2", "duration_min": 60, "tss_estimate": 45}]}]
    (d / "current_plan.json").write_text(json.dumps({"goal": goal, "weeks": weeks}))


def test_get_reads_the_plan_and_writes_nothing(client):
    c, d = client
    _write_plan(d, _goal())
    before = (d / "current_plan.json").read_text()
    r = c.get("/api/races").json()
    assert not r["stored"] and r["has_plan"] and r["plan_a_date"] == "2027-03-14"
    assert [(x["priority"], x["in_plan"], x["taper"]["kind"]) for x in r["races"]] == [("B", True, "short"),
                                                                                    ("A", True, "full")]
    assert r["taper_weeks"] == [{"start": "2027-03-01", "end": "2027-03-07", "tss_target": 300, "planned_tss": 45}]
    assert (d / "current_plan.json").read_text() == before and not (d / races.FILE_NAME).exists()


def test_add_edit_delete_mirror_into_the_plan(client):
    c, d = client
    _write_plan(d, _goal())
    assert c.post("/api/races", json={"date": "2026-12-06", "priority": "Z"}).status_code == 400
    r = c.post("/api/races", json={"date": "2026-12-06", "priority": "C", "name": "Cross"}).json()
    assert r["plan_synced"] and r["stored"]
    events = json.loads((d / "current_plan.json").read_text())["goal"]["events"]
    assert [e["date"] for e in events] == ["2026-11-01", "2026-12-06"]
    cross = next(x for x in r["races"] if x["name"] == "Cross")
    assert cross["taper"]["kind"] == "easy_day" and cross["days_to_go"] == 83
    r = c.put(f"/api/races/{cross['id']}", json={"priority": "B"}).json()
    assert json.loads((d / "current_plan.json").read_text())["goal"]["events"][1]["priority"] == "B"
    r = c.delete(f"/api/races/{cross['id']}").json()
    assert [e["date"] for e in json.loads((d / "current_plan.json").read_text())["goal"]["events"]] == ["2026-11-01"]
    assert c.delete(f"/api/races/{cross['id']}").status_code == 404
    a = next(x for x in r["races"] if x["priority"] == "A")
    assert c.delete(f"/api/races/{a['id']}").status_code == 400


def test_races_without_a_plan_are_stored(client):
    c, d = client
    r = c.post("/api/races", json={"date": "2027-05-01", "priority": "A", "name": "Big one"}).json()
    assert not r["has_plan"] and not r["plan_synced"] and r["races"][0]["taper"]["kind"] == "none"


def test_race_day_plan(client):
    c, d = client
    _write_plan(d, _goal())
    a = next(x for x in c.get("/api/races").json()["races"] if x["priority"] == "A")
    c.put(f"/api/races/{a['id']}", json={"start_time": "08:30", "arrive_time": "07:15"})
    r = c.get(f"/api/races/{a['id']}/race-day").json()
    p = r["power"]
    assert p["available"] and p["ftp"] == 250
    assert p["if_low"] <= p["predicted_if"] <= p["if_high"] and p["np_low"] <= p["predicted_np"] <= p["np_high"]
    hours = p["projected_duration_h"]
    assert p["if_low"] == pytest.approx(min(tp._interp_if_by_duration(hours * 60), tp.EVENT_TYPE_IF["granfondo"]),
                                        abs=0.01)
    assert r["warmup_min"] == 15 and r["fueling"] == "Fueling plan comes from the Nutrition settings."
    assert [t["label"] for t in r["timeline"]] == ["Arrive", "Warm up (15 min)", "Start", "Expected finish"]
    b = next(x for x in c.get("/api/races").json()["races"] if x["priority"] == "B")
    assert c.get(f"/api/races/{b['id']}/race-day").json()["power"]["available"] is False   # no distance
    assert c.get("/api/races/nope/race-day").status_code == 404
