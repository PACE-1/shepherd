"""#115 gear: accumulation, service reset, due thresholds, assignment, and the endpoints."""
import json
from datetime import date

import pytest

import clock
import gear

TODAY = date(2026, 10, 18)


def _row(i, d, km, hours, icu=None):
    return {"id": i, "date": d, "name": f"ride {i}", "sport": "Ride", "distance_km": km,
            "duration_sec": int(hours * 3600), "icu_gear": icu}


@pytest.fixture
def path(tmp_path):
    return tmp_path / gear.FILE_NAME


def _status(path, rows, item_id):
    st = gear.read(path)
    return gear.item_status(next(i for i in st["items"] if i["id"] == item_id), rows, st)


def test_distance_and_hours_add_up_from_assigned_rides_since_started_on(path):
    bike = gear.add_item(path, name="Road", kind="bike", started_on="2026-09-01")
    gear.assign(path, "a", bike["id"])
    gear.assign(path, "b", bike["id"])
    gear.assign(path, "old", bike["id"])
    gear.assign(path, "other", gear.NONE)
    rows = [_row("a", "2026-09-02", 40.5, 1.5), _row("b", "2026-10-01", 59.5, 2.5),
            _row("old", "2026-08-31", 100, 3), _row("other", "2026-10-02", 30, 1), _row("unassigned", "2026-10-03", 20, 1)]
    s = _status(path, rows, bike["id"])
    assert (s["km"], s["hours"]) == (100.0, 4.0)
    assert s["state"] == "no_threshold" and s["km_pct"] is None


def test_due_thresholds_are_the_riders_and_either_counter_triggers(path):
    bike = gear.add_item(path, name="Road", kind="bike", service_every_km=1000, service_every_hours=50)
    for i in "abc":
        gear.assign(path, i, bike["id"])

    def at(km, h):
        return _status(path, [_row("a", "2026-10-01", km, 0), _row("b", "2026-10-02", 0, h)], bike["id"])
    assert at(100, 5)["state"] == "ok"
    assert at(899, 0)["state"] == "ok"
    s = at(900, 0)
    assert s["state"] == "due_soon" and s["km_pct"] == 0.9
    assert at(0, 45)["state"] == "due_soon" and at(0, 45)["hours_pct"] == 0.9
    assert at(1000, 0)["state"] == "due"
    assert at(10, 50)["state"] == "due"          # hours alone
    gear.edit_item(path, bike["id"], retired=True)
    assert at(5000, 0)["state"] == "retired"


def test_no_default_thresholds(path):
    item = gear.add_item(path, name="Shoes", kind="shoes")
    assert item["service_every_km"] is None and item["service_every_hours"] is None


def test_service_done_restarts_the_counter_after_that_day_and_keeps_history(path):
    bike = gear.add_item(path, name="Road", kind="bike", service_every_km=500)
    for i in ("a", "b", "c"):
        gear.assign(path, i, bike["id"])
    rows = [_row("a", "2026-10-01", 400, 10), _row("b", "2026-10-10", 120, 3), _row("c", "2026-10-11", 50, 1)]
    assert _status(path, rows, bike["id"])["state"] == "due"
    gear.service_done(path, bike["id"], date(2026, 10, 10), "new chain")
    s = _status(path, rows, bike["id"])
    assert (s["km"], s["hours"]) == (50.0, 1.0)          # the service day itself counts as before it
    assert s["state"] == "ok" and s["last_service"] == "2026-10-10"
    gear.service_done(path, bike["id"], date(2026, 10, 11))
    s = _status(path, rows, bike["id"])
    assert s["km"] == 0 and [x["date"] for x in s["services"]] == ["2026-10-11", "2026-10-10"]
    assert s["services"][1]["note"] == "new chain"


def test_a_component_counts_its_bikes_rides_from_its_own_start_and_service(path):
    bike = gear.add_item(path, name="Road", kind="bike")
    chain = gear.add_item(path, name="Chain", kind="component", parent_id=bike["id"], service_every_km=300,
                          started_on="2026-10-05")
    loose = gear.add_item(path, name="Spare tyre", kind="component")
    gear.assign(path, "a", bike["id"])
    gear.assign(path, "b", bike["id"])
    gear.assign(path, "c", loose["id"])
    rows = [_row("a", "2026-10-01", 200, 5), _row("b", "2026-10-06", 100, 2), _row("c", "2026-10-07", 10, 1)]
    assert _status(path, rows, bike["id"])["km"] == 300.0
    assert _status(path, rows, chain["id"])["km"] == 100.0
    assert _status(path, rows, loose["id"])["km"] == 10.0     # no parent: its own rides


def test_component_parent_rules_and_delete_guard(path):
    shoes = gear.add_item(path, name="Shoes", kind="shoes")
    bike = gear.add_item(path, name="Road", kind="bike")
    with pytest.raises(ValueError):
        gear.add_item(path, name="Chain", kind="component", parent_id=shoes["id"])
    with pytest.raises(ValueError):
        gear.add_item(path, name="Bike2", kind="bike", parent_id=bike["id"])
    gear.add_item(path, name="Chain", kind="component", parent_id=bike["id"])
    with pytest.raises(ValueError):
        gear.delete_item(path, bike["id"])
    for bad in ({"name": ""}, {"kind": "car"}, {"service_every_km": 0}, {"service_every_km": "x"}, {"started_on": "soon"}):
        with pytest.raises(ValueError):
            gear.add_item(path, **{"name": "x", "kind": "bike", **bad})


def test_assignment_manual_beats_auto_and_auto_matches_icu_gear_name(path):
    a = gear.add_item(path, name="Road", kind="bike", icu_name="Canyon Aeroad")
    b = gear.add_item(path, name="Gravel", kind="bike")
    with pytest.raises(ValueError):                     # one item per intervals.icu name
        gear.add_item(path, name="Dup", kind="bike", icu_name="canyon aeroad")
    rows = [_row("r1", "2026-10-01", 50, 2, icu="canyon aeroad"), _row("r2", "2026-10-02", 30, 1, icu="Canyon Aeroad"),
            _row("r3", "2026-10-03", 20, 1, icu="Unknown bike"), _row("r4", "2026-10-04", 10, 1, icu=None)]
    assert _status(path, rows, a["id"])["km"] == 80.0
    assert [s["icu_name"] for s in gear.suggestions(rows, gear.read(path))] == ["Unknown bike"]
    gear.assign(path, "r2", b["id"])                    # manual override
    gear.assign(path, "r1", gear.NONE)                  # explicit no gear
    assert _status(path, rows, a["id"])["km"] == 0.0 and _status(path, rows, b["id"])["km"] == 30.0
    gear.assign(path, "r1", None)                       # back to automatic
    assert _status(path, rows, a["id"])["km"] == 50.0
    with pytest.raises(KeyError):
        gear.assign(path, "r1", "missing")


def test_payload_without_gear_name_maps_nothing():
    by_icu = {"x": "id"}
    assert gear.gear_of({"id": "1", "icu_gear": None}, {}, by_icu) == (None, "none")
    assert gear.gear_of({"id": "1", "icu_gear": 7}, {}, by_icu) == (None, "none")
    assert gear.gear_of({"id": "1", "icu_gear": "  "}, {}, by_icu) == (None, "none")


def test_delete_removes_its_ride_choices_and_a_corrupt_file_is_not_overwritten(path):
    bike = gear.add_item(path, name="Road", kind="bike")
    gear.assign(path, "a", bike["id"])
    gear.delete_item(path, bike["id"])
    assert gear.read(path) == {"items": [], "assignments": {}}
    path.write_text("{not json")
    with pytest.raises(OSError):
        gear.add_item(path, name="Road", kind="bike")
    assert path.read_text() == "{not json"


# ── endpoints ───────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import db
    import routes_gear
    monkeypatch.setattr(routes_gear, "_path", lambda: tmp_path / gear.FILE_NAME)
    db.set_db_path(tmp_path / "t.db")
    db.init_db()
    con = db.get_db()
    for i, (d, km, secs, raw) in enumerate([
            ("2026-10-10", 100.0, 3600, {"gear": {"id": "b1", "name": "Canyon"}}),
            ("2026-10-12", 50.0, 7200, {"gear": {"id": "b1", "name": "Canyon"}}),
            ("2026-10-14", 20.0, 1800, {})]):
        con.execute("INSERT INTO activities (id, date, name, sport, duration_sec, distance_km, raw_json) VALUES (?,?,?,?,?,?,?)",
                    (f"act{i}", d, f"ride {i}", "Ride", secs, km, json.dumps(raw)))
    con.commit()
    clock.freeze(TODAY)
    yield TestClient(app.app)
    clock.unfreeze()


def test_endpoints_create_assign_service_and_delete(client):
    c = client
    assert c.get("/api/gear").json()["suggestions"] == [{"icu_name": "Canyon", "rides": 2}]
    assert c.post("/api/gear", json={"name": "", "kind": "bike"}).status_code == 400
    r = c.post("/api/gear", json={"name": "Road", "kind": "bike", "icu_name": "Canyon", "service_every_km": 140}).json()
    bike = r["items"][0]
    assert bike["km"] == 150.0 and bike["hours"] == 3.0 and bike["state"] == "due" and r["suggestions"] == []
    assert {x["id"]: x["source"] for x in r["recent"]}["act0"] == "auto"
    r = c.put("/api/gear/assignment", json={"activity_id": "act2", "gear_id": bike["id"]}).json()
    assert r["items"][0]["km"] == 170.0
    assert c.put("/api/gear/assignment", json={"activity_id": "act2", "gear_id": "nope"}).status_code == 404
    assert c.put("/api/gear/assignment", json={}).status_code == 400
    assert c.post(f"/api/gear/{bike['id']}/service", json={"date": "2026-10-19"}).status_code == 400
    r = c.post(f"/api/gear/{bike['id']}/service", json={"date": "2026-10-12", "note": "chain"}).json()
    assert r["items"][0]["km"] == 20.0 and r["items"][0]["state"] == "ok"
    r = c.patch(f"/api/gear/{bike['id']}", json={"service_every_km": 20}).json()
    assert r["items"][0]["state"] == "due" and r["items"][0]["name"] == "Road"
    assert c.patch("/api/gear/nope", json={"name": "x"}).status_code == 404
    assert c.delete(f"/api/gear/{bike['id']}").json()["items"] == []
    assert c.delete(f"/api/gear/{bike['id']}").status_code == 404
