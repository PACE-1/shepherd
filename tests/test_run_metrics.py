"""Running zones, critical speed, grade-adjusted pace, rTSS/hrTSS and stride (#118, #119).

Reference values are worked by hand from the published formulas cited in src/run_metrics.py.
"""
import json
import math
import statistics

import pytest
from fastapi.testclient import TestClient

import clock
import db
import run_metrics as rm


# ── critical speed (linear distance-time model) ──────────────────────────────
def test_two_trials_give_cs_as_the_slope_and_d_prime_as_the_intercept():
    r = rm.critical_speed([(1200, 240), (3600, 840)])
    # CS = (3600 - 1200) / (840 - 240) = 4.0 m/s; D' = 1200 - 4.0 * 240 = 240 m
    assert r["cs_m_per_s"] == 4.0 and r["d_prime_m"] == 240.0 and r["cs_pace_s_per_km"] == 250.0
    assert r["r2"] is None and r["n_trials"] == 2 and r["warnings"] == []
    assert "no error estimate" in r["confidence"]


def test_three_trials_on_the_model_line_recover_it_exactly():
    r = rm.critical_speed([(200 + 4.5 * t, t) for t in (180, 420, 720)])
    assert r["cs_m_per_s"] == 4.5 and r["d_prime_m"] == 200.0 and r["r2"] == 1.0


def test_three_noisy_trials_match_an_independent_least_squares_fit():
    trials = [(1000, 180), (2100, 420), (3430, 720)]
    fit = statistics.linear_regression([t for _, t in trials], [d for d, _ in trials])
    r = rm.critical_speed(trials)
    assert r["cs_m_per_s"] == pytest.approx(fit.slope, abs=1e-3)
    assert r["d_prime_m"] == pytest.approx(fit.intercept, abs=0.1)
    assert 0.99 < r["r2"] < 1.0


def test_trials_that_cannot_fit_the_model_are_refused():
    for bad in ([(1200, 240)], [(1200, 240), (2400, 240)], [(3600, 240), (1200, 840)],
                [(1000, 250), (2000, 500)], [(0, 240), (3600, 840)], [("1", 240), (3600, 840)],
                [(1, 2), (3, 4), (5, 6), (7, 8)]):
        with pytest.raises(ValueError):
            rm.critical_speed(bad)


def test_a_trial_outside_two_to_fifteen_minutes_is_flagged():
    assert len(rm.critical_speed([(450, 60), (3600, 840)])["warnings"]) == 1


# ── Friel zones ──────────────────────────────────────────────────────────────
def test_friel_pace_zones_scale_threshold_pace():
    z = {x["zone"]: x for x in rm.pace_zones(300)}
    assert [x["zone"] for x in rm.pace_zones(300)] == ["1", "2", "3", "4", "5a", "5b", "5c"]
    assert (z["1"]["slow_s_per_km"], z["1"]["fast_s_per_km"]) == (None, 387.0)  # slower than 129 %
    assert (z["2"]["slow_s_per_km"], z["2"]["fast_s_per_km"]) == (387.0, 342.0)  # 114-129 %
    assert (z["4"]["slow_s_per_km"], z["4"]["fast_s_per_km"]) == (315.0, 297.0)  # 99-105 %
    assert (z["5c"]["slow_s_per_km"], z["5c"]["fast_s_per_km"]) == (270.0, None)  # faster than 90 %


def test_friel_run_hr_zones_scale_lthr():
    z = {x["zone"]: (x["low_bpm"], x["high_bpm"]) for x in rm.hr_zones(160)}
    assert z == {"1": (None, 136), "2": (136, 142), "3": (144, 150), "4": (152, 158),
                 "5a": (160, 163), "5b": (165, 170), "5c": (170, None)}


# ── Minetti et al. 2002 grade-adjusted pace ──────────────────────────────────
def test_minetti_cost_matches_the_published_polynomial():
    assert rm.minetti_cost(0) == pytest.approx(3.6)
    assert rm.minetti_cost(0.10) == pytest.approx(5.968214, abs=1e-6)
    assert rm.minetti_cost(-0.10) == pytest.approx(2.151706, abs=1e-6)
    assert rm.minetti_cost(0.45) == pytest.approx(19.426015, abs=1e-6)
    # cheapest slope is a moderate downhill, about -18 % to -20 % in the paper
    best = min(range(-450, 451), key=lambda g: rm.minetti_cost(g / 1000)) / 1000
    assert -0.20 <= best <= -0.17
    with pytest.raises(ValueError):
        rm.minetti_cost(0.5)


def test_grade_adjusted_pace_is_faster_uphill_and_slower_on_the_cheap_downhill():
    assert rm.grade_adjusted_pace(300, 0) == pytest.approx(300)
    assert rm.grade_adjusted_pace(300, 0.10) == pytest.approx(300 * 3.6 / 5.968214, abs=1e-3)  # 180.96 s/km
    assert rm.grade_adjusted_pace(300, -0.10) == pytest.approx(300 * 3.6 / 2.151706, abs=1e-3)  # 501.93 s/km


# ── load ─────────────────────────────────────────────────────────────────────
def test_rtss_is_100_for_an_hour_at_threshold_and_scales_with_if_squared():
    assert rm.rtss(3600, 4.0, 4.0) == 100.0
    assert rm.rtss(1800, 3.2, 4.0) == 32.0  # 0.5 h x 0.8^2 x 100
    assert rm.rtss(0, 3.2, 4.0) is None


def test_banister_trimp_reference_values():
    # 60 min, HR reserve fraction 0.5: men 60 x 0.5 x 0.64 e^0.96, women 60 x 0.5 x 0.86 e^0.835
    assert rm.banister_trimp(60, 120, 50, 190, "M") == pytest.approx(60 * 0.5 * 0.64 * math.exp(0.96))
    assert rm.banister_trimp(60, 120, 50, 190, "M") == pytest.approx(50.14, abs=0.01)
    assert rm.banister_trimp(60, 120, 50, 190, "F") == pytest.approx(59.46, abs=0.01)
    assert rm.banister_trimp(60, 120, 50, 190, "O") is None
    assert rm.banister_trimp(60, 40, 50, 190, "M") is None


def test_hrtss_scores_an_hour_at_lthr_as_100():
    assert rm.hrtss(3600, 165, 165, 50, 190, "M") == 100.0
    assert rm.hrtss(1800, 165, 165, 50, 190, "F") == 50.0
    assert rm.hrtss(3600, 140, 165, 50, 190, "M") < 100
    assert rm.hrtss(3600, 165, 165, 50, 190, None) is None


def test_cadence_and_stride():
    assert rm.steps_per_minute(170) == (170.0, False)
    assert rm.steps_per_minute(85) == (170.0, True)  # per-foot FIT cadence
    assert rm.steps_per_minute(30) is None and rm.steps_per_minute(None) is None
    assert rm.step_and_stride(4.0, 180) == (1.33, 2.67)


# ── endpoints ────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _own_thresholds_file(tmp_path, monkeypatch):
    """The profile dir outlives a test; give each one its own thresholds file."""
    import app
    import routes_run
    p = tmp_path / "sport_thresholds.json"
    monkeypatch.setattr(routes_run, "_thresholds_path", lambda: p)
    monkeypatch.setattr(app, "_sport_thresholds_path", lambda: p)


def _client():
    import app
    return TestClient(app.app)


def test_zones_endpoint_is_empty_until_a_threshold_is_set():
    c = _client()
    r = c.get("/api/run/zones").json()
    assert r["pace_zones"] == [] and r["hr_zones"] == [] and "Friel" in r["method"]
    c.post("/api/sports/thresholds", json={"kind": "run_threshold_pace", "value": 300})
    c.post("/api/sports/thresholds", json={"kind": "run_threshold_hr", "value": 160})
    r = c.get("/api/run/zones").json()
    assert r["pace_zones"][1]["fast_s_per_km"] == 342.0 and r["hr_zones"][3]["low_bpm"] == 152
    assert r["pace_history"][0]["value"] == 300


def test_critical_speed_endpoint_computes_and_saves_as_threshold_pace():
    c = _client()
    body = {"trials": [{"distance_m": 1200, "time_s": 240}, {"distance_m": 3600, "time_s": 840}]}
    r = c.post("/api/run/critical-speed", json=body)
    assert r.status_code == 200 and r.json()["cs_pace_s_per_km"] == 250.0 and r.json()["saved"] is False
    assert c.get("/api/sports/thresholds").json()["thresholds"]["run_threshold_pace"]["current"] is None
    r = c.post("/api/run/critical-speed", json={**body, "save": True})
    assert r.json()["saved"] is True
    hist = c.get("/api/sports/thresholds").json()["thresholds"]["run_threshold_pace"]["history"]
    assert hist[-1]["value"] == 250.0 and hist[-1]["source"] == "critical_speed"
    assert c.post("/api/run/critical-speed", json={"trials": [{"distance_m": 1200, "time_s": 240}]}).status_code == 400
    assert c.post("/api/run/critical-speed", json={"trials": "x"}).status_code == 400


def test_gap_endpoint():
    c = _client()
    r = c.get("/api/run/gap", params={"pace_s_per_km": 300, "grade_pct": 10}).json()
    assert r["gap_s_per_km"] == 181.0 and r["cost_j_per_kg_m"] == 5.97 and r["flat_cost_j_per_kg_m"] == 3.6
    assert c.get("/api/run/gap", params={"pace_s_per_km": 300, "grade_pct": 60}).status_code == 400


@pytest.fixture
def _seeded_rows():
    yield
    con = db.get_db()
    con.execute("DELETE FROM activities WHERE id IN ('r1', 'r2', 'r3')")
    con.execute("DELETE FROM wellness WHERE date = ?", (clock.today().isoformat(),))
    con.commit()


def test_activities_endpoint_scores_runs_and_skips_rides_and_walks(monkeypatch, _seeded_rows):
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    monkeypatch.setitem(pm._athlete, "max_hr", 190)
    monkeypatch.setitem(pm._athlete, "sex", "M")
    today = clock.today().isoformat()
    con = db.get_db()
    con.execute("INSERT OR REPLACE INTO wellness (date, rhr) VALUES (?, 50)", (today,))
    rows = [("r1", "Run", 3600, 14.4, 165, 95, {"average_cadence": 85}),   # 4.0 m/s, per-foot cadence
            ("r2", "Ride", 3600, 30, 140, 60, {}),
            ("r3", "Walk", 3600, 5, 100, 20, {})]
    for aid, sport, dur, km, hr, tss, raw in rows:
        con.execute("INSERT OR REPLACE INTO activities (id, date, name, sport, duration_sec, tss, avg_hr, distance_km, raw_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (aid, today, aid, sport, dur, tss, hr, km, json.dumps(raw)))
    con.commit()
    c = _client()
    r = c.get("/api/run/activities").json()
    assert [x["id"] for x in r["runs"]] == ["r1"]
    run = r["runs"][0]
    assert run["rtss"] is None and run["hrtss"] is None and len(r["missing"]) == 2
    c.post("/api/sports/thresholds", json={"kind": "run_threshold_pace", "value": 250})  # 4.0 m/s
    c.post("/api/sports/thresholds", json={"kind": "run_threshold_hr", "value": 165})
    r = c.get("/api/run/activities").json()
    run = r["runs"][0]
    assert r["missing"] == [] and r["rest_hr"] == 50 and r["max_hr"] == 190
    assert run["pace_s_per_km"] == 250.0 and run["intensity"] == 1.0 and run["rtss"] == 100.0
    assert run["hrtss"] == 100.0 and run["icu_load"] == 95
    assert run["cadence_spm"] == 170.0 and run["cadence_doubled"] is True
    assert run["step_length_m"] == 1.41 and run["stride_length_m"] == 2.82
