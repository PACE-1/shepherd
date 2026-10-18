"""SparkyFitness adapter, the nutrition_daily table and the /api/nutrition + /api/fueling endpoints (#112).

The HTTP layer is faked. The fixtures follow the response shapes read from the SparkyFitness source at
commit 5364674f (docs/NUTRITION.md): reportService.getMiniNutritionTrends and
HydrationNutritionRange.api.zod.ts. Nothing here talks to a real server.
"""
import json
import logging
import os
import stat
from datetime import date
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
import nutrition_sparkyfitness as sparky
import routes_nutrition

KEY = "k" * 64          # SparkyFitness keys are 64+ characters
CFG = {"base_url": "http://192.168.1.20:3004", "api_key": KEY}

# GET /api/reports/mini-nutrition-trends: only days with entries; numbers already parsed by the server.
FOOD = [
    {"date": "2026-10-16", "calories": 2450.5, "protein": 120.2, "carbs": 310.04, "fat": 80.4,
     "saturated_fat": 20.1, "polyunsaturated_fat": 0, "monounsaturated_fat": 0, "trans_fat": 0,
     "cholesterol": 200, "sodium": 2100, "potassium": 0, "dietary_fiber": 30, "sugars": 90,
     "vitamin_a": 0, "vitamin_c": 0, "calcium": 0, "iron": 0, "caffeine_mg": 95, "alcohol_g": 0},
    {"date": "2026-10-18", "calories": 900, "protein": 40, "carbs": 120, "fat": 25,
     "caffeine_mg": 0, "alcohol_g": 0, "My custom": 3},
]
# GET /api/v2/reports/hydration-nutrition-range: one zero-padded row per day.
WATER = {"days": [
    {"date": "2026-10-16", "water_ml": 2500, "caffeine_mg": 95, "alcohol_g": 0},
    {"date": "2026-10-17", "water_ml": 750, "caffeine_mg": 0, "alcohol_g": 0},
    {"date": "2026-10-18", "water_ml": 0, "caffeine_mg": 0, "alcohol_g": 0},
]}


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def _server(food=FOOD, water=WATER, water_status=200):
    def get(url, **kw):
        if url.endswith("/api/reports/mini-nutrition-trends"):
            return _Resp(200, food)
        if url.endswith("/api/v2/reports/hydration-nutrition-range"):
            return _Resp(water_status, water if water_status == 200 else {"error": "Not found"})
        return _Resp(404, {"error": "Not found"})
    return mock.patch.object(sparky.httpx, "get", side_effect=get)


@pytest.fixture(autouse=True)
def _net(monkeypatch):
    monkeypatch.delenv("SHEPHERD_NO_NET", raising=False)


# ── Settings ──────────────────────────────────────────────────────────────────

def test_save_is_private_and_public_never_has_the_key(tmp_path):
    cfg = sparky.save(tmp_path, " http://localhost:3004/ ", KEY)
    assert cfg == {"base_url": "http://localhost:3004", "api_key": KEY}
    assert stat.S_IMODE(os.stat(tmp_path / sparky.FILE_NAME).st_mode) == 0o600
    pub = sparky.public(sparky.load(tmp_path))
    assert pub == {"configured": True, "base_url": "http://localhost:3004", "has_key": True}
    assert KEY not in json.dumps(pub)


def test_blank_key_is_kept_only_for_the_same_address(tmp_path):
    sparky.save(tmp_path, "http://10.0.0.5:3004", KEY)
    assert sparky.save(tmp_path, "http://10.0.0.5:3004", None)["api_key"] == KEY
    with pytest.raises(ValueError, match="again"):
        sparky.save(tmp_path, "https://evil.example", None)
    assert sparky.load(tmp_path)["base_url"] == "http://10.0.0.5:3004"


@pytest.mark.parametrize("url", ["", "ftp://x", "file:///etc/passwd", "javascript:alert(1)", "http://",
                                 "http://u:p@host", "http://host?x=1", "http://host#a", "http://ho st",
                                 "http://host:99999"])
def test_bad_addresses_are_refused(tmp_path, url):
    with pytest.raises(ValueError):
        sparky.save(tmp_path, url, KEY)
    assert sparky.load(tmp_path) == {}


@pytest.mark.parametrize("url", ["http://localhost:3004", "http://192.168.1.20:3004", "https://fit.home.lan",
                                 "http://[::1]:3004", "https://example.org/sparky"])
def test_self_hosted_addresses_are_allowed(url):
    assert sparky.check_base_url(url) == url


@pytest.mark.parametrize("key", ["", "  ", "a b", "a\nb"])
def test_bad_keys_are_refused(tmp_path, key):
    with pytest.raises(ValueError):
        sparky.save(tmp_path, "http://localhost:3004", key if key.strip() else None)


# ── HTTP ──────────────────────────────────────────────────────────────────────

def test_fetch_normalises_the_verified_shapes():
    with _server() as g:
        out = sparky.fetch_daily_totals(CFG, date(2026, 10, 16), date(2026, 10, 18))
    assert out == [
        {"date": "2026-10-16", "kcal": 2450.5, "carbs_g": 310.0, "protein_g": 120.2, "fat_g": 80.4, "water_ml": 2500.0},
        {"date": "2026-10-17", "kcal": None, "carbs_g": None, "protein_g": None, "fat_g": None, "water_ml": 750.0},
        {"date": "2026-10-18", "kcal": 900.0, "carbs_g": 120.0, "protein_g": 40.0, "fat_g": 25.0, "water_ml": 0.0},
    ]
    food_call, water_call = g.call_args_list
    assert food_call.args[0] == "http://192.168.1.20:3004/api/reports/mini-nutrition-trends"
    assert food_call.kwargs["params"] == {"startDate": "2026-10-16", "endDate": "2026-10-18"}
    assert water_call.args[0] == "http://192.168.1.20:3004/api/v2/reports/hydration-nutrition-range"
    assert water_call.kwargs["params"] == {"start": "2026-10-16", "end": "2026-10-18"}
    for c in g.call_args_list:
        assert c.kwargs["headers"]["x-api-key"] == KEY
        assert c.kwargs["follow_redirects"] is False and c.kwargs["timeout"] == sparky.TIMEOUT_S


def test_an_older_server_without_the_water_route_still_gives_food():
    with _server(water_status=404):
        out = sparky.fetch_daily_totals(CFG, date(2026, 10, 16), date(2026, 10, 18))
    assert [r["date"] for r in out] == ["2026-10-16", "2026-10-18"]
    assert all(r["water_ml"] is None for r in out)


def test_rows_outside_the_range_or_malformed_are_ignored():
    food = [{"date": "2026-10-01", "calories": 1}, {"date": "bad"}, "x", {"date": "2026-10-16", "calories": "nan", "carbs": -5}]
    with _server(food=food, water={"days": []}):
        out = sparky.fetch_daily_totals(CFG, date(2026, 10, 16), date(2026, 10, 18))
    assert out == [{"date": "2026-10-16", "kcal": None, "carbs_g": None, "protein_g": None, "fat_g": None, "water_ml": None}]


@pytest.mark.parametrize("resp,fragment", [
    (_Resp(401, {"error": "Authentication required."}), "rejected the API key"),
    (_Resp(403, {"error": "API key is disabled."}), "disabled"),
    (_Resp(429, {"error": "Rate limit exceeded."}), "rate limit"),
    (_Resp(302), "redirect"),
    (_Resp(500, {"error": "boom"}), "returned 500"),
    (_Resp(200, None), "not SparkyFitness data"),
    (_Resp(200, {"not": "a list"}), "not SparkyFitness data"),
])
def test_server_failures_become_readable_errors(resp, fragment):
    with mock.patch.object(sparky.httpx, "get", return_value=resp):
        with pytest.raises(sparky.NutritionError, match=fragment) as e:
            sparky.check_connection(CFG)
    assert KEY not in str(e.value)


def test_unreachable_server_error_has_no_key_and_no_request():
    err = httpx.ConnectError("down", request=httpx.Request("GET", "http://x", headers={"x-api-key": KEY}))
    with mock.patch.object(sparky.httpx, "get", side_effect=err):
        with pytest.raises(sparky.NutritionError, match="Could not reach .*: ConnectError") as e:
            sparky.check_connection(CFG)
    assert KEY not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_no_connection_no_network_and_bad_ranges(monkeypatch):
    with pytest.raises(sparky.NutritionError, match="not connected"):
        sparky.check_connection({})
    monkeypatch.setenv("SHEPHERD_NO_NET", "1")
    with mock.patch.object(sparky.httpx, "get") as g, pytest.raises(sparky.NutritionError, match="turned off"):
        sparky.check_connection(CFG)
    g.assert_not_called()
    with pytest.raises(ValueError):
        sparky.fetch_daily_totals(CFG, date(2026, 10, 18), date(2026, 10, 16))
    with pytest.raises(ValueError):
        sparky.fetch_daily_totals(CFG, date(2025, 1, 1), date(2026, 10, 16))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@pytest.fixture
def c(freeze_clock):
    freeze_clock(date(2026, 10, 18))
    with TestClient(app_module.app) as client:
        client.delete("/api/nutrition/connection")
        routes_nutrition._conn().execute("DELETE FROM nutrition_daily")
        routes_nutrition._conn().commit()
        yield client
        client.delete("/api/nutrition/connection")


def test_connection_round_trip_never_echoes_the_key(c, caplog):
    caplog.set_level(logging.DEBUG)
    assert c.get("/api/nutrition/connection").json() == {"configured": False, "base_url": "", "has_key": False, "last_synced_at": None}
    r = c.post("/api/nutrition/connection", json={"base_url": "http://192.168.1.20:3004", "api_key": KEY})
    assert r.status_code == 200 and r.json()["has_key"] is True and KEY not in r.text
    assert KEY not in c.get("/api/nutrition/connection").text
    assert c.post("/api/nutrition/connection", json={"base_url": "ftp://x", "api_key": KEY}).status_code == 400
    with _server():
        assert c.post("/api/nutrition/test").json()["ok"] is True
        assert c.post("/api/nutrition/sync", json={}).status_code == 200
    with mock.patch.object(sparky.httpx, "get", return_value=_Resp(401, {"error": "Authentication required."})):
        bad = c.post("/api/nutrition/test")
    assert bad.status_code == 502 and KEY not in bad.text
    assert KEY not in caplog.text
    assert c.delete("/api/nutrition/connection").json()["configured"] is False


def test_sync_stores_rows_and_replaces_the_synced_range(c):
    c.post("/api/nutrition/connection", json={"base_url": "http://localhost:3004", "api_key": KEY})
    with _server():
        r = c.post("/api/nutrition/sync", json={"days": 3})
    assert r.status_code == 200
    assert r.json()["start"] == "2026-10-16" and r.json()["end"] == "2026-10-18" and r.json()["days_with_data"] == 3
    today = routes_nutrition.read_day("2026-10-18")
    assert today["source"] == "sparkyfitness" and today["carbs_g"] == 120.0 and today["kcal"] == 900.0
    assert c.get("/api/nutrition/connection").json()["last_synced_at"] == r.json()["synced_at"]
    # The rider deleted the 16th's entries in SparkyFitness: the next sync empties it here too.
    with _server(food=FOOD[1:], water={"days": []}):
        c.post("/api/nutrition/sync", json={"days": 3})
    assert routes_nutrition.read_day("2026-10-16") is None
    assert c.post("/api/nutrition/sync", json={"days": 0}).status_code == 400
    assert c.post("/api/nutrition/sync", json={"days": True}).status_code == 400


def test_sync_without_a_connection_is_a_readable_502(c):
    r = c.post("/api/nutrition/sync", json={})
    assert r.status_code == 502 and "not connected" in r.json()["detail"]


def test_table_creation_is_idempotent(c):
    routes_nutrition._conn()
    routes_nutrition._conn()
    cols = [r[1] for r in routes_nutrition._conn().execute("PRAGMA table_info(nutrition_daily)")]
    assert cols == ["date", "source", "kcal", "carbs_g", "protein_g", "fat_g", "water_ml", "synced_at"]


def _plan(session_type, minutes):
    return {"weeks": [{"start": "2026-10-12", "end": "2026-10-18", "phase": "base", "sessions": [
        {"day": "2026-10-18", "session_type": session_type, "duration_min": minutes, "tss_estimate": 150}]}]}


def test_fueling_for_a_long_ride_against_logged_intake(c, monkeypatch):
    monkeypatch.setattr(app_module, "_read_stored_plan", lambda: _plan("long_z2", 180))
    monkeypatch.setattr(routes_nutrition, "config", SimpleNamespace(ATHLETE_WEIGHT_KG=70))
    routes_nutrition.store("sparkyfitness", "2026-10-18", "2026-10-18",
                           [{"date": "2026-10-18", "kcal": 900, "carbs_g": 120, "protein_g": 40, "fat_g": 25, "water_ml": 500}],
                           "2026-10-18T09:00:00")
    f = c.get("/api/fueling").json()
    assert f["session"] == {"session_type": "long_z2", "duration_min": 180}
    assert (f["during"]["band"], f["during"]["low_g_per_h"], f["during"]["high_g_per_h"]) == ("high", 60, 90)
    assert (f["during"]["low_g"], f["during"]["high_g"]) == (180, 270)
    assert f["day"] == {"load": "high", "low_g_per_kg": 6, "high_g_per_kg": 10, "low_g": 420, "high_g": 700}
    assert f["logged"]["carbs_g"] == 120 and f["logged"]["synced_at"] == "2026-10-18T09:00:00"
    assert "Not medical advice" in f["note"] and "Jeukendrup" in f["hourly_method"] and "ACSM" in f["daily_method"]


def test_fueling_on_a_rest_day_has_no_session_and_a_light_day(c, monkeypatch):
    monkeypatch.setattr(app_module, "_read_stored_plan", lambda: _plan("rest", 0))
    monkeypatch.setattr(routes_nutrition, "config", SimpleNamespace(ATHLETE_WEIGHT_KG=70))
    f = c.get("/api/fueling").json()
    assert f["session"] is None and f["during"] is None and f["logged"] is None and f["connected"] is False
    assert f["day"]["load"] == "light" and (f["day"]["low_g"], f["day"]["high_g"]) == (210, 350)


def test_fueling_without_a_plan_or_weight(c, monkeypatch):
    monkeypatch.setattr(app_module, "_read_stored_plan", lambda: None)
    monkeypatch.setattr(routes_nutrition, "config", SimpleNamespace(ATHLETE_WEIGHT_KG=None))
    f = c.get("/api/fueling").json()
    assert f["session"] is None and f["day"] is None and f["weight_kg"] is None


def test_backups_that_exclude_secrets_leave_the_key_out():
    import backup
    assert sparky.FILE_NAME in backup._SECRET_NAMES
