"""#109 — sport mapping, per-sport thresholds, per-sport and combined load,
and plans that predate the sport field."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import clock
import db
import sports
import training_planner as tp

TODAY = clock.today()


@pytest.fixture()
def conn(tmp_path):
    db.set_db_path(tmp_path / "t.db")
    db.init_db()
    yield db.get_db()
    db.close_all_connections()


def _act(conn, i, days_ago, sport, tss):
    conn.execute("INSERT INTO activities (id, date, sport, tss) VALUES (?,?,?,?)",
                 (str(i), (TODAY - timedelta(days=days_ago)).isoformat(), sport, tss))
    conn.commit()


def test_sport_of_maps_icu_types():
    assert [sports.sport_of(t) for t in
            ("Ride", "GravelRide", "TrailRun", "VirtualRun", "OpenWaterSwim", "WeightTraining", None)] == \
           ["ride", "ride", "run", "run", "swim", "other", "other"]


def test_thresholds_keep_dated_history_and_reject_nonsense(conn):
    sports.set_threshold("run_pace", 270, date(2026, 8, 1))
    sports.set_threshold("run_pace", 262, date(2026, 10, 1))
    sports.set_threshold("swim_css", 95, date(2026, 10, 2))
    assert [h["value"] for h in sports.threshold_history("run_pace")] == [270, 262]
    t = sports.thresholds()
    assert t["run"]["run_pace"] == {"value": 262, "unit": "s/km", "tested_on": "2026-10-01"}
    assert t["swim"]["swim_css"]["value"] == 95 and t["run"]["run_lthr"] is None
    with pytest.raises(ValueError):
        sports.set_threshold("run_pace", 20)
    with pytest.raises(ValueError):
        sports.set_threshold("nope", 1)


def test_existing_cycling_ftp_rows_are_the_ride_threshold(conn):
    db.log_metric("2026-09-01", "ftp", 250, source="settings")
    assert sports.thresholds()["ride"]["ftp"]["value"] == 250


def test_load_is_per_sport_and_combined_is_their_sum(conn):
    for i in range(30):
        _act(conn, f"r{i}", i, "Ride", 60)
        _act(conn, f"u{i}", i, "Run", 30)
    _act(conn, "s", 1, "Swim", 40)
    _act(conn, "none", 2, "Ride", None)          # no load: ignored, not an error
    st = sports.load_state()
    assert st["ride"]["ctl"] > st["run"]["ctl"] > st["swim"]["ctl"] > 0
    assert st["other"]["ctl"] == 0
    assert st["combined"]["ctl"] == pytest.approx(
        sum(st[s]["ctl"] for s in sports.SPORTS), abs=0.2)
    assert st["swim"]["tsb"] == pytest.approx(st["swim"]["ctl"] - st["swim"]["atl"], abs=0.1)


def test_plan_saved_before_sport_existed_loads_as_a_ride():
    old = {"day": "2026-10-20", "session_type": "z2", "duration_min": 60,
           "tss_estimate": 50, "description": "x"}
    s = tp.session_from_dict(old)
    assert s.sport == "ride"
    assert tp.session_to_dict(s)["sport"] == "ride"
    assert tp.session_from_dict({**old, "sport": "run"}).sport == "run"
