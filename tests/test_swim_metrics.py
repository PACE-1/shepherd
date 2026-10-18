"""Swim CSS, sTSS and stroke fields (#122), open-water notes (#126).

Reference values are worked by hand from the published formulas cited in src/swim_metrics.py.
"""
import json

import pytest
from fastapi.testclient import TestClient

import clock
import db
import open_water as ow
import swim_metrics as sm


# ── CSS (Wakayoshi et al. 1992, 1993) ────────────────────────────────────────
def test_css_from_400_and_200_is_the_slope_of_the_distance_time_line():
    r = sm.css([(400, 360), (200, 170)])  # 6:00 and 2:50
    # CSS = (400 - 200) / (360 - 170) = 1.0526 m/s -> 100 / 1.0526 = 95.0 s per 100 m (1:35)
    assert r["css_m_per_s"] == pytest.approx(200 / 190, abs=1e-3)
    assert r["css_s_per_100m"] == 95.0
    # intercept a = 200 - CS * 170 = 21.05 m
    assert r["anaerobic_distance_m"] == pytest.approx(200 - 200 / 190 * 170, abs=0.1)
    assert r["r2"] is None and r["n_trials"] == 2 and "Wakayoshi" in r["method"]


def test_css_order_of_the_swims_does_not_matter_and_bad_swims_are_refused():
    assert sm.css([(200, 170), (400, 360)])["css_s_per_100m"] == 95.0
    for bad in ([(400, 360)], [(400, 170), (200, 360)], [(400, 360), (200, 360)], [(400, 400), (200, 200)]):
        with pytest.raises(ValueError):
            sm.css(bad)


# ── sTSS (TrainingPeaks, cubic) ──────────────────────────────────────────────
def test_stss_is_100_for_an_hour_at_css_and_scales_with_if_cubed():
    assert sm.stss(3600, 1.0, 1.0) == 100.0
    assert sm.stss(1800, 0.8, 1.0) == 25.6  # 0.5 h x 0.8^3 x 100
    assert sm.stss(3600, 1.1, 1.0) == 133.1  # 1.1^3 x 100
    assert sm.stss(0, 0.8, 1.0) is None and sm.stss(1800, 0.8, 0) is None


def test_water_and_stroke_fields_read_only_what_intervals_icu_stores():
    assert sm.water("OpenWaterSwim", {"pool_length": 25}) == "open_water"
    assert sm.water("Swim", {"pool_length": 25}) == "pool"
    assert sm.water("Swim", {}) == "unknown"
    assert sm.stroke_fields({"pool_length": 25, "lengths": 80, "average_cadence": 28.5}) == \
        {"pool_length_m": 25.0, "lengths": 80, "stroke_rate": 28.5}
    assert sm.stroke_fields({"lengths": True, "average_cadence": 0}) == {"pool_length_m": None, "lengths": None, "stroke_rate": None}


# ── open-water notes store ───────────────────────────────────────────────────
def test_notes_add_edit_list_delete(tmp_path):
    p = tmp_path / ow.FILE_NAME
    assert ow.read_notes(p) == []
    a = ow.add_note(p, {"date": "2026-07-01", "water_temp_c": 17.44, "wetsuit": True, "conditions": " choppy "})
    b = ow.add_note(p, {"date": "2026-07-08", "activity_id": "i123", "sighting": "drifted left at buoy 2"})
    assert a["water_temp_c"] == 17.4
    assert a["conditions"] == "choppy" and a["activity_id"] is None and b["wetsuit"] is None
    assert [n["id"] for n in ow.read_notes(p)] == [b["id"], a["id"]]
    e = ow.update_note(p, a["id"], {"wetsuit": False, "note": "cold hands"})
    assert e["wetsuit"] is False and e["note"] == "cold hands" and e["conditions"] == "choppy"
    ow.delete_note(p, b["id"])
    assert [n["id"] for n in ow.read_notes(p)] == [a["id"]]
    with pytest.raises(KeyError):
        ow.delete_note(p, "nope")
    with pytest.raises(KeyError):
        ow.update_note(p, "nope", {"note": "x"})


def test_notes_refuse_bad_input_and_never_overwrite_an_unreadable_file(tmp_path):
    p = tmp_path / ow.FILE_NAME
    for bad in ({}, {"date": "July"}, {"date": "2026-07-01", "water_temp_c": 55}, {"date": "2026-07-01", "water_temp_c": "17"},
                {"date": "2026-07-01", "wetsuit": "yes"}, {"date": "2026-07-01", "colour": "red"}, {"date": "2026-07-01", "note": 5}):
        with pytest.raises(ValueError):
            ow.add_note(p, bad)
    assert ow.add_note(p, {"date": "2026-07-01", "note": "x" * 5000})["note"] == "x" * 1000
    p.write_text("{not json")
    with pytest.raises(OSError):
        ow.add_note(p, {"date": "2026-07-02"})
    assert p.read_text() == "{not json"


# ── endpoints ────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _own_profile_files(tmp_path, monkeypatch):
    """The profile dir outlives a test; give each one its own thresholds and notes files."""
    import app
    import routes_swim
    monkeypatch.setattr(routes_swim, "_profile_dir", lambda: tmp_path)
    monkeypatch.setattr(app, "_sport_thresholds_path", lambda: tmp_path / "sport_thresholds.json")


def _client():
    import app
    return TestClient(app.app)


def test_css_endpoints_compute_save_and_show_history():
    c = _client()
    r = c.get("/api/swim/css").json()
    assert r["css_s_per_100m"] is None and r["history"] == [] and "not shown" in r["zones_note"]
    body = {"trials": [{"distance_m": 400, "time_s": 360}, {"distance_m": 200, "time_s": 170}]}
    r = c.post("/api/swim/css-test", json=body)
    assert r.status_code == 200 and r.json()["css_s_per_100m"] == 95.0 and r.json()["saved"] is False
    assert c.get("/api/swim/css").json()["css_s_per_100m"] is None
    assert c.post("/api/swim/css-test", json={**body, "save": True}).json()["saved"] is True
    r = c.get("/api/swim/css").json()
    assert r["css_s_per_100m"] == 95.0 and r["history"][-1]["source"] == "css_test"
    assert c.get("/api/sports/thresholds").json()["thresholds"]["swim_css"]["current"] == 95.0
    assert c.post("/api/swim/css-test", json={"trials": [{"distance_m": 400, "time_s": 360}]}).status_code == 400
    assert c.post("/api/swim/css-test", json={"trials": "x"}).status_code == 400


@pytest.fixture
def _seeded_rows():
    yield
    con = db.get_db()
    con.execute("DELETE FROM activities WHERE id IN ('s1', 's2', 's3')")
    con.commit()


def test_activities_endpoint_scores_pool_and_open_water_swims(_seeded_rows):
    today = clock.today().isoformat()
    con = db.get_db()
    rows = [("s1", "Swim", 2000, 2.0, 40, {"pool_length": 25, "lengths": 80, "average_cadence": 30}),  # 1.0 m/s
            ("s2", "OpenWaterSwim", 3600, 3.0, 50, {}),                                              # 0.833 m/s
            ("s3", "Run", 3600, 12, 70, {})]
    for aid, sport, dur, km, tss, raw in rows:
        con.execute("INSERT OR REPLACE INTO activities (id, date, name, sport, duration_sec, tss, distance_km, raw_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (aid, today, aid, sport, dur, tss, km, json.dumps(raw)))
    con.commit()
    c = _client()
    r = c.get("/api/swim/activities").json()
    assert sorted(x["id"] for x in r["swims"]) == ["s1", "s2"] and len(r["missing"]) == 1
    assert all(x["stss"] is None for x in r["swims"]) and "SWOLF" in r["stroke_note"]
    c.post("/api/sports/thresholds", json={"kind": "swim_css", "value": 100})  # 1.0 m/s
    r = c.get("/api/swim/activities").json()
    s = {x["id"]: x for x in r["swims"]}
    assert r["missing"] == []
    assert s["s1"]["water"] == "pool" and s["s1"]["pace_s_per_100m"] == 100.0 and s["s1"]["intensity"] == 1.0
    assert s["s1"]["stss"] == pytest.approx(2000 / 3600 * 100, abs=0.05)  # 55.6
    assert (s["s1"]["pool_length_m"], s["s1"]["lengths"], s["s1"]["stroke_rate"]) == (25.0, 80, 30.0)
    assert s["s2"]["water"] == "open_water" and s["s2"]["pace_s_per_100m"] == 120.0
    assert s["s2"]["stss"] == pytest.approx(100 * (1 / 1.2) ** 3, abs=0.05)  # 57.9
    assert s["s2"]["icu_load"] == 50


def test_open_water_endpoints():
    c = _client()
    assert c.get("/api/swim/open-water").json() == {"notes": []}
    r = c.post("/api/swim/open-water", json={"date": "2026-07-01", "water_temp_c": 16, "wetsuit": True, "course": "Lake loop"})
    assert r.status_code == 200
    nid = r.json()["id"]
    assert c.post("/api/swim/open-water", json={"date": "x"}).status_code == 400
    r = c.put(f"/api/swim/open-water/{nid}", json={"sighting": "sun in my eyes"})
    assert r.status_code == 200 and r.json()["sighting"] == "sun in my eyes" and r.json()["course"] == "Lake loop"
    assert c.put("/api/swim/open-water/nope", json={"note": "x"}).status_code == 404
    assert [n["id"] for n in c.get("/api/swim/open-water").json()["notes"]] == [nid]
    assert c.delete(f"/api/swim/open-water/{nid}").json() == {"ok": True}
    assert c.delete(f"/api/swim/open-water/{nid}").status_code == 404
