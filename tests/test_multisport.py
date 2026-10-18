"""Per-sport and combined load, sport mapping and per-sport thresholds (#109)."""
import math
from datetime import date, timedelta

import pytest

import multisport as ms

TODAY = date(2026, 6, 30)


def act(days_ago, sport, tss):
    return {"date": (TODAY - timedelta(days=days_ago)).isoformat(), "sport": sport, "tss": tss}


def test_intervals_types_map_to_a_sport_and_unknowns_are_other():
    assert [ms.sport_of(t) for t in ("Ride", "VirtualRide", "GravelRide", "Run", "TrailRun", "Swim", "OpenWaterSwim", "WeightTraining", None, "")] == [
        "cycling", "cycling", "cycling", "running", "running", "swimming", "swimming", "other", "other", "other"]


def test_a_single_day_of_load_gives_the_exponential_weighted_value():
    r = ms.load_by_sport([act(0, "Run", 100)], TODAY)
    assert r["sports"]["running"]["ctl"] == pytest.approx(100 * (1 - math.exp(-1 / 42)), abs=0.05)
    assert r["sports"]["running"]["atl"] == pytest.approx(100 * (1 - math.exp(-1 / 7)), abs=0.05)
    assert r["sports"]["running"]["tsb"] == 0.0  # nothing before yesterday
    assert "cycling" not in r["sports"]


def test_steady_daily_load_converges_to_that_load_and_combined_is_the_sum():
    rides = [act(i, "Ride", 60) for i in range(180)]
    runs = [act(i, "Run", 30) for i in range(180)]
    r = ms.load_by_sport(rides + runs, TODAY)
    assert r["sports"]["cycling"]["ctl"] == pytest.approx(60, abs=1.5)
    assert r["sports"]["running"]["atl"] == pytest.approx(30, abs=0.1)
    assert r["combined"]["ctl"] == pytest.approx(r["sports"]["cycling"]["ctl"] + r["sports"]["running"]["ctl"], abs=0.2)
    assert r["settled"] is True and r["days_of_history"] == 180


def test_rest_after_load_makes_form_positive_and_short_history_is_flagged():
    r = ms.load_by_sport([act(i, "Ride", 100) for i in range(10, 30)], TODAY)
    assert r["combined"]["tsb"] > 0 and r["combined"]["week_load"] == 0
    assert r["settled"] is False


def test_rows_without_usable_load_or_date_are_ignored():
    r = ms.load_by_sport([act(1, "Ride", None), act(1, "Ride", 0), {"date": "bad", "sport": "Ride", "tss": 50}, act(400, "Ride", 80)], TODAY)
    assert r["sports"] == {} and r["combined"]["ctl"] == 0 and r["days_of_history"] == 0


def test_thresholds_keep_dated_history_and_reject_bad_values(tmp_path):
    p = tmp_path / "t.json"
    assert ms.read_thresholds(p)["swim_css"]["current"] is None
    ms.set_threshold(p, "swim_css", 95, date(2026, 5, 1))
    ms.set_threshold(p, "swim_css", 92, date(2026, 6, 1))
    ms.set_threshold(p, "swim_css", 93, date(2026, 6, 1))  # same day replaces
    t = ms.read_thresholds(p)["swim_css"]
    assert t["current"] == 93 and [e["value"] for e in t["history"]] == [95, 93]
    for kind, value in (("swim_css", 5), ("run_threshold_pace", "fast"), ("run_threshold_hr", True), ("nope", 1)):
        with pytest.raises(ValueError):
            ms.set_threshold(p, kind, value, TODAY)


def test_a_corrupt_thresholds_file_reads_as_empty(tmp_path):
    p = tmp_path / "t.json"
    p.write_text("{not json")
    assert ms.read_thresholds(p)["run_threshold_hr"]["current"] is None


def test_endpoints_return_load_and_store_a_threshold():
    from fastapi.testclient import TestClient
    import app
    c = TestClient(app.app)
    load = c.get("/api/sports/load")
    assert load.status_code == 200 and set(load.json()["combined"]) == {"ctl", "atl", "tsb", "week_load"}
    assert c.post("/api/sports/thresholds", json={"kind": "swim_css", "value": 1}).status_code == 400
    ok = c.post("/api/sports/thresholds", json={"kind": "swim_css", "value": 95})
    assert ok.status_code == 200 and ok.json()["thresholds"]["swim_css"]["current"] == 95
    assert c.get("/api/sports/thresholds").json()["thresholds"]["swim_css"]["history"][0]["value"] == 95
