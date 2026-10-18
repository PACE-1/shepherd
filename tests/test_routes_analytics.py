"""Endpoints for #114 (weight trend, power model) and #116 (ride comparison); responses match their models."""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import api_models
import db
import routes_analytics

# A date no other test writes rows for, so the shared sandbox does not leak in.
TODAY = date(2031, 3, 15)


@pytest.fixture
def client(freeze_clock):
    freeze_clock(TODAY)
    import app
    with TestClient(app.app) as c:
        yield c


def d(n):
    return (TODAY - timedelta(days=n)).isoformat()


def test_weight_trend_merges_typed_and_synced_weight_and_gives_w_per_kg(client):
    db.log_metric(d(20), "weight", 72.0, source="manual")
    db.log_metric(d(20), "ftp", 288.0, source="settings")
    conn = db.get_db()
    conn.execute("INSERT OR REPLACE INTO wellness (date, raw_json) VALUES (?, ?)", (d(10), json.dumps({"id": d(10), "weight": 71.0})))
    conn.execute("INSERT OR REPLACE INTO wellness (date, raw_json) VALUES (?, ?)", (d(9), json.dumps({"id": d(9), "weight": 0})))
    conn.commit()
    r = client.get("/api/analytics/weight-trend?days=30")
    assert r.status_code == 200
    body = api_models.WeightTrend.model_validate(r.json())
    pts = [(p.date, p.weight_kg, p.source) for p in body.points]
    assert pts == [(d(20), 72.0, "manual"), (d(10), 71.0, "intervals.icu")]  # the 0 kg synced day is no reading
    assert body.tau_days == 7 and "7 days" in body.method
    assert body.points[-1].trend_kg == pytest.approx(72 - (1 - 2.718281828 ** (-10 / 7)), abs=0.01)
    assert body.wkg[0].w_per_kg == 4.0 and body.latest_w_per_kg == round(288 / body.points[-1].trend_kg, 2)
    assert client.get("/api/analytics/weight-trend?days=1").status_code == 422


def test_power_model_reports_a_fit_with_an_interval_or_refuses(client, monkeypatch):
    import power_curve
    curve = {"n_rides": 3, "pmax_w": 950, "rider_curve": [
        {"duration_s": t, "watts": round(260 + 21000 / t)} for t in (5, 180, 300, 600, 1200, 3600)]}
    monkeypatch.setattr(power_curve, "aggregate_power_curve", lambda window_days=90: curve)
    monkeypatch.setattr(power_curve, "_load_cached_rides", lambda: [])
    monkeypatch.setattr(power_curve, "_profile_ftp_weight", lambda profile_id=None: (255, 65.0))
    r = client.get("/api/analytics/power-model?window_days=90")
    assert r.status_code == 200
    m = api_models.PowerModel.model_validate(r.json())
    assert m.fit.status == "ok" and m.fit.cp_w == pytest.approx(260, abs=1) and m.fit.n_points == 4
    assert m.fit.cp_ci95_w[0] <= m.fit.cp_w <= m.fit.cp_ci95_w[1]
    assert m.cp_w_per_kg == round(m.fit.cp_w / 65, 2) and m.pmax_w == 950 and len(m.history) == 12
    assert "Monod" in m.method and m.caveat
    curve["rider_curve"] = curve["rider_curve"][:2]
    m = api_models.PowerModel.model_validate(client.get("/api/analytics/power-model").json())
    assert m.fit.status == "insufficient" and m.fit.cp_w is None and m.cp_w_per_kg is None


def _rec(rid, watts, n):
    return {"ride_id": rid, "name": rid, "started_at": "2031-03-01T08:00:00", "ftp_at_ride": 250,
            "duration_s": n, "np_w": watts, "tss": 50, "avg_hr": 140, "distance_km": 30,
            "samples": {"t_s": list(range(n)), "power_w": [watts] * n, "hr_bpm": [140] * n}}


def test_compare_two_rides_and_two_efforts(client, monkeypatch):
    rides = {"icu_a": _rec("icu_a", 200, 2400), "icu_b": _rec("icu_b", 230, 2400),
             "icu_empty": {**_rec("icu_empty", 0, 10), "samples": {"t_s": [], "power_w": [], "hr_bpm": []}}}
    monkeypatch.setattr(routes_analytics, "_load_ride", lambda rid: rides.get(rid))
    r = client.get("/api/analytics/compare?a=icu_a&b=icu_b")
    assert r.status_code == 200
    c = api_models.RideCompare.model_validate(r.json())
    assert c.delta.np_w == 30 and c.a.summary.distance_km == 30
    assert {e.duration_s: e.delta_w for e in c.best_efforts}[1200] == 30
    seg = api_models.RideCompare.model_validate(
        client.get("/api/analytics/compare?a=icu_a&b=icu_b&a_start=0&a_end=600&b_start=600&b_end=1200").json())
    assert seg.a.summary.duration_s == 600 and seg.b.start_s == 600 and seg.b.summary.if_pct == 92.0
    assert client.get("/api/analytics/compare?a=icu_a&b=nope").status_code == 404
    assert client.get("/api/analytics/compare?a=icu_a&b=icu_b&a_start=600&a_end=300").status_code == 400
    assert client.get("/api/analytics/compare?a=icu_a&b=icu_empty").status_code == 422


def test_compare_loads_rides_through_the_ride_detail_endpoint(client):
    assert routes_analytics._load_ride("fit_does_not_exist") is None
