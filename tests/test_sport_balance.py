"""#124 sport balance (actuals): ISO week and month buckets, share maths, target validation, empty data, routes."""
from datetime import date, timedelta

import pytest

import sport_balance as sb

TODAY = date(2026, 10, 18)   # a Sunday: the last day of ISO week 42


def act(day, sport, hours, tss=None):
    return {"date": day, "sport": sport, "duration_sec": hours * 3600, "tss": tss}


# ── week and month boundaries ─────────────────────────────────────────────────────────────────────
def test_weeks_are_iso_monday_to_sunday_and_the_last_holds_today():
    wk, mo = sb.window(TODAY, 9)
    assert wk[-1] == (date(2026, 10, 12), date(2026, 10, 18))
    assert wk[0][0] == date(2026, 8, 17) and all(s.weekday() == 0 and (e - s).days == 6 for s, e in wk)
    assert [s for s, _ in mo] == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)] and mo[-1][1] == date(2026, 10, 31)
    assert mo[0][1] == date(2026, 8, 31) and sb.window(TODAY, 1)[1] == [(date(2026, 10, 1), date(2026, 10, 31))]


def test_sunday_and_monday_land_in_different_weeks():
    out = sb.balance([act("2026-10-11", "Ride", 1), act("2026-10-12", "Ride", 2)], TODAY, 2)
    assert [(b["key"], b["hours"]["cycling"]) for b in out["weeks"]] == [("2026-W41", 1.0), ("2026-W42", 2.0)]


def test_iso_week_key_crosses_the_year():
    out = sb.balance([act("2027-01-01", "Run", 1)], date(2027, 1, 3), 5)
    assert [b["key"] for b in out["weeks"]][-2:] == ["2026-W52", "2026-W53"]
    assert out["weeks"][-1]["hours"]["running"] == 1.0
    assert [b["key"] for b in out["months"]] == ["2026-12", "2027-01"] and out["months"][-1]["hours"]["running"] == 1.0


def test_month_buckets_use_calendar_months_and_ignore_the_future_and_the_past():
    acts = [act("2026-09-30", "Ride", 1), act("2026-10-01", "Ride", 2), act("2026-10-19", "Ride", 9), act("2025-01-01", "Ride", 9)]
    out = sb.balance(acts, TODAY, 9)
    assert {b["key"]: b["hours"]["cycling"] for b in out["months"]} == {"2026-08": 0.0, "2026-09": 1.0, "2026-10": 2.0}
    assert sum(b["hours"]["cycling"] for b in out["weeks"]) == 3.0


def test_window_start_covers_both_the_first_week_and_the_first_month():
    assert sb.window_start(TODAY, 12) == date(2026, 7, 27)      # the week starts before August 1
    assert sb.window_start(TODAY, 1) == date(2026, 10, 1)       # the month starts before the Monday


# ── share maths ───────────────────────────────────────────────────────────────────────────────────
def test_hours_load_and_shares_by_sport():
    acts = [act("2026-10-13", "Ride", 3, 150), act("2026-10-14", "VirtualRide", 1, 50),
            act("2026-10-15", "Run", 1, 60), act("2026-10-16", "Swim", 1, 40), act("2026-10-17", "Yoga", 1)]
    w = sb.balance(acts, TODAY, 1)["weeks"][0]
    assert w["hours"] == {"cycling": 4.0, "running": 1.0, "swimming": 1.0, "other": 1.0}
    assert w["load"] == {"cycling": 200.0, "running": 60.0, "swimming": 40.0, "other": 0.0}
    assert w["total_hours"] == 7.0 and w["hours_share"] == {"cycling": 57.1, "running": 14.3, "swimming": 14.3, "other": 14.3}
    assert w["load_share"] == {"cycling": 66.7, "running": 20.0, "swimming": 13.3, "other": 0.0}
    assert w["gap_pp"] is None


def test_gap_is_actual_share_minus_target_in_percentage_points():
    targets = {"cycling": 50.0, "running": 30.0, "swimming": 20.0, "other": 0.0}
    acts = [act("2026-10-13", "Ride", 3), act("2026-10-14", "Run", 1)]
    w = sb.balance(acts, TODAY, 1, targets)["weeks"][0]
    assert w["gap_pp"] == {"cycling": 25.0, "running": -5.0, "swimming": -20.0, "other": 0.0}


def test_bad_rows_count_as_zero_not_as_errors():
    acts = [{"date": "bad", "sport": "Ride", "duration_sec": 3600}, {"date": "2026-10-13", "sport": None, "duration_sec": None, "tss": "x"},
            {"date": "2026-10-13T08:00:00", "sport": "Ride", "duration_sec": -5, "tss": -3}, {"date": "2026-10-14", "sport": "Ride", "duration_sec": True, "tss": True}]
    w = sb.balance(acts, TODAY, 1)["weeks"][0]
    assert w["total_hours"] == 0.0 and w["total_load"] == 0.0


# ── empty data and one sport ──────────────────────────────────────────────────────────────────────
def test_no_history_gives_zero_buckets_with_no_shares_and_no_gap():
    t = {"cycling": 100.0, "running": 0.0, "swimming": 0.0, "other": 0.0}
    out = sb.balance([], TODAY, 12, t)
    assert len(out["weeks"]) == 12 and not out["has_history"] and out["single_sport"] is None and out["sports_present"] == []
    assert all(b["total_hours"] == 0 and b["gap_pp"] is None and set(b["hours_share"].values()) == {None} for b in out["weeks"] + out["months"])


def test_a_cycling_only_rider_is_a_single_sport():
    out = sb.balance([act("2026-10-13", "Ride", 2, 90)], TODAY, 12)
    assert out["single_sport"] == "cycling" and out["weeks"][-1]["hours_share"]["cycling"] == 100.0
    assert sb.balance([act("2026-10-13", "Ride", 2), act("2026-10-13", "Run", 1)], TODAY, 12)["single_sport"] is None


# ── targets ───────────────────────────────────────────────────────────────────────────────────────
def test_no_file_means_no_targets_and_no_limiter(tmp_path):
    assert sb.read_targets(tmp_path / sb.FILE_NAME) == {"targets": None, "limiter": None}


def test_targets_round_trip_and_a_missing_sport_counts_as_zero(tmp_path):
    p = tmp_path / sb.FILE_NAME
    got = sb.save_targets(p, {"cycling": 60, "running": 40}, "running")
    assert got == {"targets": {"cycling": 60.0, "running": 40.0, "swimming": 0.0, "other": 0.0}, "limiter": "running"}
    assert sb.read_targets(p) == got
    assert sb.save_targets(p, {}, None) == {"targets": None, "limiter": None}
    assert sb.save_targets(p, None, "swimming") == {"targets": None, "limiter": "swimming"}


@pytest.mark.parametrize("targets", [
    {"cycling": 60, "running": 30},                       # 90
    {"cycling": 60, "running": 50},                       # 110
    {"cycling": 120, "running": -20},                     # out of range
    {"cycling": "100"}, {"cycling": True}, {"cycling": float("nan")},
    {"cycling": 50, "triathlon": 50}, [("cycling", 100)],
])
def test_bad_targets_are_refused_and_nothing_is_written(tmp_path, targets):
    p = tmp_path / sb.FILE_NAME
    with pytest.raises(ValueError):
        sb.save_targets(p, targets, None)
    assert not p.exists()


@pytest.mark.parametrize("limiter", ["other", "triathlon", 3])
def test_a_bad_limiter_is_refused(tmp_path, limiter):
    with pytest.raises(ValueError):
        sb.save_targets(tmp_path / sb.FILE_NAME, None, limiter)


def test_a_corrupt_file_reads_as_empty(tmp_path):
    p = tmp_path / sb.FILE_NAME
    p.write_text("{nope")
    assert sb.read_targets(p) == {"targets": None, "limiter": None}


# ── routes ────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _leave_no_trace():
    """The route test saves real targets (which switch on companion-session planning for every later plan
    built in this worker) and inserts activity rows into the shared test profile: undo both."""
    yield
    try:
        import db
        from fastapi.testclient import TestClient
        import app
        TestClient(app.app).put("/api/balance/targets", json={"targets": {}, "limiter": None})
        db.get_db().execute("DELETE FROM activities WHERE id LIKE 'bal%'")
        db.get_db().commit()
    except Exception:  # noqa: BLE001 - cleanup only
        pass


def test_routes_empty_profile_then_targets_and_actuals():
    from fastapi.testclient import TestClient
    import app
    import clock
    import db
    c = TestClient(app.app)
    empty = c.get("/api/balance?weeks=4")
    assert empty.status_code == 200
    body = empty.json()
    assert len(body["weeks"]) == 4 and body["has_targets"] is False and body["has_history"] is False and "first pick" in body["limiter_note"]
    assert c.get("/api/balance?weeks=0").status_code == 422 and c.get("/api/balance?weeks=500").status_code == 422

    d = db.get_db()
    day = (clock.today() - timedelta(days=clock.today().weekday())).isoformat()   # Monday of this week
    for i, (sport, sec) in enumerate((("Ride", 10800), ("Run", 3600))):
        d.execute("INSERT INTO activities (id, date, sport, duration_sec, tss) VALUES (?, ?, ?, ?, ?)", (f"bal{i}", day, sport, sec, 100))
    d.commit()

    assert c.put("/api/balance/targets", json={"targets": {"cycling": 50, "running": 30}, "limiter": None}).status_code == 400
    assert c.put("/api/balance/targets", json={"targets": None}).status_code == 400
    ok = c.put("/api/balance/targets", json={"targets": {"cycling": 50, "running": 30, "swimming": 20}, "limiter": "swimming"})
    assert ok.status_code == 200 and ok.json()["limiter"] == "swimming" and ok.json()["has_targets"] is True

    got = c.get("/api/balance?weeks=4").json()
    wk = got["weeks"][-1]
    assert wk["hours"]["cycling"] == 3.0 and wk["hours_share"]["cycling"] == 75.0
    assert wk["gap_pp"] == {"cycling": 25.0, "running": -5.0, "swimming": -20.0, "other": 0.0}
    assert got["limiter"] == "swimming" and got["sports_present"] == ["cycling", "running"] and got["single_sport"] is None
