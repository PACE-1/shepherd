"""Weather forecast for planned outdoor sessions (#117): parsing, rating, rounding, privacy, no-net, endpoints.

The HTTP layer is always faked (``weather._http_get``): no test touches the network.
"""
import json
import re
from pathlib import Path

import pytest

import weather

FIX = Path(__file__).parent / "fixtures"
FORECAST = json.loads((FIX / "open_meteo_forecast.json").read_text(encoding="utf-8"))
GEOCODING = json.loads((FIX / "open_meteo_geocoding.json").read_text(encoding="utf-8"))
BERLIN = {"name": "Berlin", "region": "Berlin", "country": "Germany", "latitude": 52.52437, "longitude": 13.41053}


@pytest.fixture(autouse=True)
def _fresh_cache():
    weather.clear_cache()
    yield
    weather.clear_cache()


# ── parsing ─────────────────────────────────────────────────────────────────────────────────────────
def test_parse_forecast_zips_the_hourly_columns():
    hours = weather.parse_forecast(FORECAST)
    assert len(hours) == 72
    h = hours[14]   # 2026-10-19 14:00
    assert h == {"time": "2026-10-19T14:00", "temp_c": 14, "feels_c": 12, "rain_pct": 5, "rain_mm": 0.0,
                 "wind_kmh": 12.0, "gust_kmh": 24.0, "code": 2}


def test_parse_forecast_rejects_a_reply_without_hourly():
    with pytest.raises(weather.WeatherUnavailable):
        weather.parse_forecast({"error": True, "reason": "bad"})


def test_parse_forecast_tolerates_null_and_short_columns():
    hours = weather.parse_forecast({"hourly": {"time": ["2026-10-19T08:00"], "wind_gusts_10m": [None]}})
    assert hours[0]["gust_kmh"] is None and hours[0]["code"] is None
    assert weather.rate_day(hours)["rating"] == "good"


def test_parse_places_drops_entries_without_coordinates_and_rounds():
    places = weather.parse_places(GEOCODING)
    assert [p["country"] for p in places] == ["Germany", "United States"]
    assert places[0] == {"name": "Berlin", "region": "Berlin", "country": "Germany", "latitude": 52.52, "longitude": 13.41}


@pytest.mark.parametrize("code,text", [(0, "Clear sky"), (3, "Overcast"), (45, "Fog"), (63, "Rain"),
                                       (95, "Thunderstorm"), (99, "Thunderstorm with heavy hail"), (7, "Unknown"),
                                       (None, "Unknown")])
def test_wmo_codes_map_to_text(code, text):
    assert weather.weather_text(code) == text


# ── rating ──────────────────────────────────────────────────────────────────────────────────────────
def test_daily_rates_the_fixture_days_and_ignores_night_hours():
    days = {d["date"]: d for d in weather.daily(weather.parse_forecast(FORECAST))}
    assert set(days) == {"2026-10-19", "2026-10-20", "2026-10-21"}
    calm = days["2026-10-19"]
    # The 90 km/h gust is at 03:00, outside the riding hours.
    assert calm["rating"] == "good" and calm["reasons"] == [] and calm["gust_max_kmh"] == 24
    assert calm["summary"] == "Partly cloudy" and (calm["temp_min_c"], calm["temp_max_c"]) == (8, 14)
    storm = days["2026-10-20"]
    assert storm["rating"] == "poor" and storm["suggest_indoor"] is True
    assert "gusts 58 km/h" in storm["reasons"] and "thunderstorms forecast" in storm["reasons"]
    assert any(r.startswith("rain 80% likely, 6.3 mm") for r in storm["reasons"])
    assert storm["summary"] == "Thunderstorm"
    meh = days["2026-10-21"]
    assert meh["rating"] == "marginal" and meh["suggest_indoor"] is False
    assert "gusts 42 km/h" in meh["reasons"]


def _hour(**kw):
    base = {"time": "2026-10-19T10:00", "temp_c": 12, "feels_c": 12, "rain_pct": 0, "rain_mm": 0.0,
            "wind_kmh": 10, "gust_kmh": 15, "code": 1}
    return {**base, **kw}


@pytest.mark.parametrize("hour,rating", [
    ({}, "good"),
    ({"gust_kmh": weather.GUST_MARGINAL_KMH - 1}, "good"),
    ({"gust_kmh": weather.GUST_MARGINAL_KMH}, "marginal"),
    ({"gust_kmh": weather.GUST_POOR_KMH}, "poor"),
    ({"rain_pct": weather.RAIN_PROB_MARGINAL_PCT}, "marginal"),
    ({"rain_pct": 90, "rain_mm": 0.2}, "marginal"),          # likely but hardly any: not poor
    ({"rain_pct": 90, "rain_mm": 1.5}, "poor"),
    ({"rain_mm": weather.RAIN_MM_POOR}, "poor"),
    ({"feels_c": weather.FEELS_COLD_MARGINAL_C}, "marginal"),
    ({"feels_c": weather.FEELS_COLD_POOR_C}, "poor"),
    ({"feels_c": weather.FEELS_HOT_MARGINAL_C}, "marginal"),
    ({"feels_c": weather.FEELS_HOT_POOR_C}, "poor"),
    ({"code": 95}, "poor"),
    ({"code": 73}, "poor"),
    ({"code": 66}, "poor"),
    ({"code": 45}, "marginal"),
])
def test_rating_thresholds(hour, rating):
    assert weather.rate_day([_hour(**hour)])["rating"] == rating


def test_reasons_are_in_words_with_numbers():
    r = weather.rate_day([_hour(gust_kmh=55.4), _hour(feels_c=-3.2)])
    assert r["reasons"] == ["gusts 55 km/h", "feels like -3 °C"]


def test_thresholds_are_labelled_as_heuristics():
    src = (Path(weather.__file__)).read_text(encoding="utf-8")
    assert "heuristic defaults, not from a published standard" in src


# ── privacy: rounding, what is sent, logs ───────────────────────────────────────────────────────────
def test_coordinates_are_rounded_to_two_decimals_everywhere():
    assert weather.round_coord(52.52437) == 52.52 and weather.round_coord(-71.18508) == -71.19
    assert weather.clean_place(BERLIN)["latitude"] == 52.52


@pytest.mark.parametrize("bad", [{}, {"name": "x"}, {"name": "x", "latitude": 91, "longitude": 0},
                                 {"name": "x", "latitude": 0, "longitude": 181}, {"name": " ", "latitude": 1, "longitude": 1},
                                 {"name": "x", "latitude": "a", "longitude": 1}])
def test_clean_place_rejects_unusable_input(bad):
    with pytest.raises(ValueError):
        weather.clean_place(bad)


def test_forecast_request_carries_only_rounded_coordinates(monkeypatch):
    sent = []
    monkeypatch.setattr(weather, "_http_get", lambda url, params: sent.append((url, params)) or FORECAST)
    weather.get_hours(52.52437, 13.41053)
    (url, params), = sent
    assert url == weather.FORECAST_URL
    assert (params["latitude"], params["longitude"]) == (52.52, 13.41)
    assert not re.search(r"52\.524|13\.410", json.dumps(params))
    assert set(params) == {"latitude", "longitude", "hourly", "forecast_days", "timezone"}


def test_search_request_carries_only_the_typed_text(monkeypatch):
    sent = []
    monkeypatch.setattr(weather, "_http_get", lambda url, params: sent.append((url, params)) or GEOCODING)
    weather.search_places("Berlin")
    (url, params), = sent
    assert url == weather.GEOCODE_URL and params["name"] == "Berlin" and params["count"] == 5
    assert weather.search_places("a") == []     # too short: no call
    assert len(sent) == 1


def test_a_failure_logs_no_location_or_search_text(monkeypatch):
    lines = []

    class Spy:
        def __getattr__(self, _):
            return lambda msg, *a, **k: lines.append(str(msg))
    monkeypatch.setattr(weather, "log", Spy())

    def boom(url, params):
        raise weather.WeatherUnavailable("ConnectError")
    monkeypatch.setattr(weather, "_http_get", boom)
    with pytest.raises(weather.WeatherUnavailable):
        weather.get_hours(52.52437, 13.41053)
    assert lines and all(not re.search(r"52\.5|13\.4|Berlin", ln) for ln in lines)


def test_real_transport_does_not_log_url_or_params(monkeypatch):
    """The exception text of an HTTP library can hold the URL (with the coordinates): only the class name survives."""
    import httpx
    monkeypatch.delenv("SHEPHERD_NO_NET", raising=False)

    def boom(url, **k):
        raise httpx.ConnectError(f"cannot reach {url}?latitude=52.52&longitude=13.41")
    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(weather.WeatherUnavailable) as e:
        weather._http_get(weather.FORECAST_URL, {"latitude": 52.52})
    assert "52.52" not in str(e.value) and str(e.value) == "ConnectError"


def test_no_other_module_reads_the_location():
    """The coach, reports and exports never see it: only weather.py and routes_weather.py touch the file."""
    src = Path(weather.__file__).parent
    users = {p.name for p in src.rglob("*.py") if "weather_location" in p.read_text(encoding="utf-8", errors="ignore")
             or "LOCATION_FILE" in p.read_text(encoding="utf-8", errors="ignore")}
    assert users <= {"weather.py", "routes_weather.py"}


# ── SHEPHERD_NO_NET ─────────────────────────────────────────────────────────────────────────────────
def test_no_net_switches_off_every_outgoing_call(monkeypatch):
    import httpx
    monkeypatch.setenv("SHEPHERD_NO_NET", "1")

    def must_not_be_called(*a, **k):
        raise AssertionError("an outgoing call was made")
    monkeypatch.setattr(httpx, "get", must_not_be_called)
    with pytest.raises(weather.WeatherUnavailable):
        weather.search_places("Berlin")
    with pytest.raises(weather.WeatherUnavailable):
        weather.get_hours(52.5, 13.4)


# ── cache ───────────────────────────────────────────────────────────────────────────────────────────
def test_forecast_is_cached_per_rounded_location_for_an_hour(monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "_http_get", lambda url, params: calls.append(1) or FORECAST)
    weather.get_hours(52.52437, 13.41053, now=1000)
    weather.get_hours(52.5201, 13.4099, now=1000 + 3599)    # same rounded location, inside the hour
    assert len(calls) == 1
    weather.get_hours(52.52437, 13.41053, now=1000 + 3600)
    assert len(calls) == 2
    weather.get_hours(48.86, 2.35, now=1000 + 3600)         # another location
    assert len(calls) == 3


def test_a_failed_fetch_is_not_retried_straight_away(monkeypatch):
    calls = []

    def fail(url, params):
        calls.append(1)
        raise weather.WeatherUnavailable("x")
    monkeypatch.setattr(weather, "_http_get", fail)
    for t in (0, 10, 299):
        with pytest.raises(weather.WeatherUnavailable):
            weather.get_hours(1.0, 2.0, now=t)
    assert len(calls) == 1
    with pytest.raises(weather.WeatherUnavailable):
        weather.get_hours(1.0, 2.0, now=300)
    assert len(calls) == 2


# ── location file ───────────────────────────────────────────────────────────────────────────────────
def test_location_file_roundtrip_and_clear(tmp_path):
    p = tmp_path / "p" / weather.LOCATION_FILE
    assert weather.read_location(p) is None
    weather.write_location(p, BERLIN)
    assert json.loads(p.read_text())["latitude"] == 52.52        # stored rounded, never the precise value
    assert "52.524" not in p.read_text()
    assert weather.read_location(p)["name"] == "Berlin"
    weather.clear_location(p)
    weather.clear_location(p)       # idempotent
    assert weather.read_location(p) is None


def test_a_corrupt_location_file_reads_as_no_location(tmp_path):
    p = tmp_path / weather.LOCATION_FILE
    p.write_text("{not json")
    assert weather.read_location(p) is None


# ── endpoints ───────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app
    import routes_weather
    monkeypatch.setattr(routes_weather, "_path", lambda: tmp_path / weather.LOCATION_FILE)
    return TestClient(app.app)


def test_location_endpoints(client, tmp_path):
    r = client.get("/api/weather/location").json()
    assert r["has_location"] is False and r["place"] is None
    assert client.put("/api/weather/location", json={"name": "x"}).status_code == 400
    r = client.put("/api/weather/location", json=BERLIN).json()
    assert r["has_location"] and r["place"]["latitude"] == 52.52
    assert client.get("/api/weather/location").json()["place"]["name"] == "Berlin"
    assert client.delete("/api/weather/location").json()["has_location"] is False
    assert not (tmp_path / weather.LOCATION_FILE).exists()


def test_forecast_with_no_location_is_off_not_an_error(client, monkeypatch):
    monkeypatch.setattr(weather, "_http_get", lambda *a: pytest.fail("called without a location"))
    r = client.get("/api/weather/forecast")
    assert r.status_code == 200 and r.json()["status"] == "no_location" and r.json()["days"] == []
    assert r.json()["attribution"] == {"text": "Weather data by Open-Meteo.com", "url": "https://open-meteo.com/"}


def test_forecast_endpoint_returns_rated_days(client, monkeypatch):
    monkeypatch.setattr(weather, "_http_get", lambda url, params: FORECAST)
    client.put("/api/weather/location", json=BERLIN)
    r = client.get("/api/weather/forecast").json()
    assert r["status"] == "ok" and [d["rating"] for d in r["days"]] == ["good", "poor", "marginal"]


def test_forecast_endpoint_degrades_when_the_fetch_fails(client, monkeypatch):
    def fail(url, params):
        raise weather.WeatherUnavailable("ConnectError")
    monkeypatch.setattr(weather, "_http_get", fail)
    client.put("/api/weather/location", json=BERLIN)
    r = client.get("/api/weather/forecast")
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["message"] == "Forecast unavailable"


def test_search_endpoint_lists_places_and_degrades(client, monkeypatch):
    real = weather._http_get
    monkeypatch.setattr(weather, "_http_get", lambda url, params: GEOCODING)
    r = client.get("/api/weather/search", params={"q": "Berlin"}).json()
    assert r["available"] and [p["country"] for p in r["results"]] == ["Germany", "United States"]
    monkeypatch.setattr(weather, "_http_get", real)
    monkeypatch.setenv("SHEPHERD_NO_NET", "1")
    r = client.get("/api/weather/search", params={"q": "Berlin"})
    assert r.status_code == 200 and r.json()["available"] is False and "unavailable" in r.json()["message"]
    assert client.get("/api/weather/location").json()["network_enabled"] is False
