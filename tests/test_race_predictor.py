"""Race predictor (#121): Riegel 1981 and the critical-speed hyperbolic model.

Reference values are worked by hand from the published formulas cited in src/race_predictor.py.
"""
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import clock
import db
import race_predictor as rp


# ── Riegel: T2 = T1 * (D2 / D1) ** 1.06 ──────────────────────────────────────
def test_riegel_reference_values():
    # 20:00 5K -> 10K: 2 ** 1.06 = 2 * e^(0.06 ln 2) = 2 * 1.042466 = 2.084932; 1200 * 2.084932 = 2501.9 s (41:42)
    assert rp.riegel(1200, 5000, 10000) == pytest.approx(2501.9, abs=0.1)
    # 20:00 5K -> marathon: (42195 / 5000) ** 1.06 = 8.439 ** 1.06 = e^(1.06 * 2.132864) = 9.591100; x 1200 = 11509.3 s (3:11:49)
    assert rp.riegel(1200, 5000, 42195) == pytest.approx(11509.3, abs=0.1)
    # 50:00 10K -> half: 2.10975 ** 1.06 = e^(1.06 * 0.746570) = 2.206403; x 3000 = 6619.2 s (1:50:19)
    assert rp.riegel(3000, 10000, 21097.5) == pytest.approx(6619.2, abs=0.1)
    # the same distance gives the same time; exponent 1 gives even pace
    assert rp.riegel(1500, 5000, 5000) == 1500 and rp.riegel(1500, 5000, 10000, exponent=1.0) == 3000
    with pytest.raises(ValueError):
        rp.riegel(0, 5000, 10000)


# ── CS hyperbolic: T = (D - D') / CS ─────────────────────────────────────────
def test_cs_time_reference_values():
    assert rp.cs_time(5000, 4.0, 240) == 1190.0       # (5000 - 240) / 4 = 19:50
    assert rp.cs_time(10000, 4.0, 240) == 2440.0      # (10000 - 240) / 4 = 40:40
    assert rp.cs_time(10000, 5.5, 250) == pytest.approx(1772.7, abs=0.1)  # 9750 / 5.5
    assert rp.cs_time(200, 4.0, 240) is None           # all inside D': no prediction
    with pytest.raises(ValueError):
        rp.cs_time(5000, 0, 240)


def test_cs_predicts_only_5k_and_10k_inside_two_to_thirty_minutes():
    rows = {r["race"]: r for r in rp.cs_predictions(4.0, 240)}
    assert rows["5k"]["status"] == "ok" and rows["5k"]["time_s"] == 1190.0 and rows["5k"]["pace_s_per_km"] == 238.0
    assert rows["10k"]["status"] == "out_of_range" and rows["10k"]["time_s"] is None   # 40:40 > 30 min
    assert rows["half"]["status"] == rows["marathon"]["status"] == "not_supported"
    assert all(r["range_text"] is None for r in rows.values())   # no citable error band for CS
    fast = {r["race"]: r for r in rp.cs_predictions(5.5, 250)}
    assert fast["10k"]["status"] == "ok" and fast["10k"]["time_s"] == pytest.approx(1772.7, abs=0.1)


# ── input choice and the long-run heuristic ──────────────────────────────────
RUNS = [
    {"id": "a", "distance_m": 5000, "time_s": 1500},    # Riegel 10K equivalent 3127 s
    {"id": "b", "distance_m": 10000, "time_s": 2900},   # 2900 s: the best
    {"id": "c", "distance_m": 2000, "time_s": 400},     # would be 2204 s, but under 3 km
]


def test_best_effort_is_the_fastest_riegel_equivalent_of_at_least_3_km():
    assert rp.best_effort(RUNS)["id"] == "b"
    assert rp.best_effort([RUNS[2]]) is None and rp.best_effort([]) is None


def test_long_races_need_a_long_run_of_half_the_distance():
    out = {r["race"]: r for r in rp.predict(RUNS, None)["predictions"]}
    assert out["10k"]["time_s"] == 2900.0 and out["5k"]["time_s"] == pytest.approx(1390.9, abs=0.1)  # 2900 * 0.5 ** 1.06
    # longest 10 km < 10.55 km (half of a half marathon): no time, a plain message instead
    assert out["half"]["status"] == out["marathon"]["status"] == "not_enough_long_run"
    assert out["half"]["time_s"] is None and "Not enough long-run history" in out["half"]["notes"][0]
    out = {r["race"]: r for r in rp.predict(RUNS + [{"id": "d", "distance_m": 12000, "time_s": 4200}], None)["predictions"]}
    assert out["half"]["status"] == "ok" and out["half"]["time_s"] == pytest.approx(6398.6, abs=0.1)  # 2900 * 2.10975 ** 1.06
    assert rp.ENDURANCE_CAVEAT in out["half"]["notes"] and out["half"]["range_text"] is None
    assert out["marathon"]["status"] == "not_enough_long_run"
    out = {r["race"]: r for r in rp.predict(RUNS + [{"id": "e", "distance_m": 22000, "time_s": 8000}], None)["predictions"]}
    m = out["marathon"]
    assert m["status"] == "ok" and m["time_s"] == pytest.approx(13340.6, abs=0.1)        # 2900 * 4.2195 ** 1.06
    assert "at least 10 minutes" in m["range_text"] and rp.ENDURANCE_CAVEAT in m["notes"]
    assert not any("230 minute" in n for n in m["notes"])                                # 3:42:21 is inside Riegel's range
    # 22 km in 2:30 -> marathon 9000 * (42195 / 22000) ** 1.06 = 17949 s (4:59:09): beyond 230 min, flagged
    slow = {r["race"]: r for r in rp.predict([{"id": "s", "distance_m": 22000, "time_s": 9000}], None)["predictions"]}
    assert any("230 minute" in n for n in slow["marathon"]["notes"])


def test_predict_says_what_is_missing():
    out = rp.predict([], None)
    assert out["predictions"] == [] and len(out["missing"]) == 2 and out["best_run"] is None
    assert "Vickers and Vertosick" in out["riegel_confidence"] and "Heuristic" in out["long_run_rule"]


# ── endpoint ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    import app
    import routes_run
    monkeypatch.setattr(routes_run, "_thresholds_path", lambda: tmp_path / "sport_thresholds.json")
    yield TestClient(app.app)
    con = db.get_db()
    con.execute("DELETE FROM activities WHERE id LIKE 'rp-%'")
    con.commit()


def _seed(rows):
    con = db.get_db()
    for aid, days_ago, sport, dur, km in rows:
        d = (clock.today() - timedelta(days=days_ago)).isoformat()
        con.execute("INSERT OR REPLACE INTO activities (id, date, name, sport, duration_sec, distance_km, raw_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)", (aid, d, aid, sport, dur, km, json.dumps({})))
    con.commit()


def test_endpoint_uses_recent_runs_and_the_saved_critical_speed(client):
    r = client.get("/api/run/predict").json()
    assert r["window_days"] == 56 and r["critical_speed"] is None and r["best_run"] is None and len(r["missing"]) == 2
    _seed([("rp-1", 3, "Run", 2900, 10.0),       # the best effort
           ("rp-2", 10, "Run", 4200, 12.0),
           ("rp-3", 70, "Run", 2000, 10.0),      # faster, but older than eight weeks
           ("rp-4", 5, "Ride", 1800, 30.0),
           ("rp-5", 6, "Walk", 3600, 25.0)])     # a long walk is not long-run history
    r = client.get("/api/run/predict").json()
    assert r["best_run"]["id"] == "rp-1" and r["best_run"]["pace_s_per_km"] == 290.0 and r["longest_run_m"] == 12000.0
    by = {(p["model"], p["race"]): p for p in r["predictions"]}
    assert by[("riegel", "half")]["status"] == "ok" and by[("riegel", "marathon")]["status"] == "not_enough_long_run"
    assert not any(m == "critical_speed" for m, _ in by)
    client.post("/api/run/critical-speed", json={"trials": [{"distance_m": 1200, "time_s": 240}, {"distance_m": 3600, "time_s": 840}], "save": True})
    r = client.get("/api/run/predict").json()
    assert r["critical_speed"] == {"cs_m_per_s": 4.0, "d_prime_m": 240.0, "date": clock.today().isoformat()}
    by = {(p["model"], p["race"]): p for p in r["predictions"]}
    assert by[("critical_speed", "5k")]["time_s"] == 1190.0 and by[("critical_speed", "10k")]["status"] == "out_of_range"
    assert r["missing"] == []


def test_a_corrupt_saved_test_is_ignored(client):
    import routes_run
    routes_run._cs_path().write_text('{"cs_m_per_s": "fast", "d_prime_m": 240}')
    assert client.get("/api/run/predict").json()["critical_speed"] is None


# ── target gap: the inverse of each formula ──────────────────────────────────
def test_target_gap_inverts_riegel_and_cs():
    best = {"distance_m": 5000, "time_s": 1200}
    g = rp.target_gap("10k", 2501.9 * 0.95, best, {"cs_m_per_s": 4.0, "d_prime_m": 240})
    assert g["riegel"]["faster_pct"] == pytest.approx(5.0, abs=0.1)
    assert g["riegel"]["needed_time_s"] == pytest.approx(1200 * 0.95, abs=0.2)
    # 5K in 19:00 (1140 s) with D' 240 m: CS = 4760 / 1140 = 4.1754 m/s, 4.4 % above 4.0
    g = rp.target_gap("5k", 1140, best, {"cs_m_per_s": 4.0, "d_prime_m": 240})
    assert g["critical_speed"] == {"needed_cs_m_per_s": 4.175, "current_cs_m_per_s": 4.0, "higher_pct": 4.4}
    # CS gives nothing for the marathon or outside 2 to 30 minutes; no inputs give nothing
    assert rp.target_gap("marathon", 12000, best, {"cs_m_per_s": 4.0, "d_prime_m": 240})["critical_speed"] is None
    assert rp.target_gap("10k", 3000, best, {"cs_m_per_s": 4.0, "d_prime_m": 240})["critical_speed"] is None
    assert rp.target_gap("5k", 1200, None, None)["riegel"] is None
    with pytest.raises(ValueError):
        rp.target_gap("1mile", 400, best, None)


def test_predict_endpoint_target(client):
    assert client.get("/api/run/predict").json()["target"] is None
    r = client.get("/api/run/predict", params={"target_race": "5k", "target_time_s": 1200})
    assert r.status_code == 200 and r.json()["target"]["race"] == "5k"
    assert client.get("/api/run/predict", params={"target_race": "1mile", "target_time_s": 400}).status_code == 422
    assert client.get("/api/run/predict", params={"target_race": "5k"}).status_code == 422
