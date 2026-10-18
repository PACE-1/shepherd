"""Weather forecast for planned outdoor sessions (#117): Open-Meteo client, parsing and a plain-words rating.

Privacy (owner decisions, ADDENDUM 2): the rider's location lives only in their profile folder. Only the
latitude and longitude rounded to 2 decimals (about 1 km) ever leave the machine, and the text typed into the
place search is sent to the Open-Meteo geocoder. Nothing here logs a coordinate, a place name or a search text;
a failure logs the exception class only. ``SHEPHERD_NO_NET=1`` switches every outgoing call off. The coach and
error reports never read this module's data.

Data: Open-Meteo.com (https://open-meteo.com), CC BY 4.0, free for non-commercial use. The credit
"Weather data by Open-Meteo.com" (linked) must be visible wherever the forecast is shown.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from atomic_io import write_text_atomic
from obs import log

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ATTRIBUTION = {"text": "Weather data by Open-Meteo.com", "url": "https://open-meteo.com/"}

COORD_DECIMALS = 2          # ~1 km: the most precise a location ever leaves the machine
FORECAST_DAYS = 7           # matches the plan view (Open-Meteo allows 16)
CACHE_SECONDS = 3600        # >= 1 h per rounded location keeps usage far below Open-Meteo's limits
FAILURE_BACKOFF_SECONDS = 300   # after a failed fetch, do not retry for this long
TIMEOUT_SECONDS = 5
HOURLY = ("temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation",
          "wind_speed_10m", "wind_gusts_10m", "weather_code")
LOCATION_FILE = "weather_location.json"

# ── Rating thresholds ───────────────────────────────────────────────────────────────────────────────
# heuristic defaults, not from a published standard. They are rules of thumb for "would I rather ride
# indoors", meant to be tuned; a rider can still ride whatever the rating says.
RIDE_HOURS = range(6, 21)       # a session has no time of day in the plan: judge 06:00 to 20:59 local
GUST_MARGINAL_KMH = 40
GUST_POOR_KMH = 55
RAIN_PROB_MARGINAL_PCT = 40
RAIN_PROB_POOR_PCT = 70
RAIN_MM_MARGINAL = 1.0          # total over the riding hours
RAIN_MM_POOR = 5.0
FEELS_COLD_MARGINAL_C = 3
FEELS_COLD_POOR_C = -2
FEELS_HOT_MARGINAL_C = 30
FEELS_HOT_POOR_C = 35

# WMO weather interpretation codes (WMO code table 4677 subset used by Open-Meteo).
WMO_TEXT = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Light freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Violent rain showers", 85: "Light snow showers",
    86: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}
THUNDER_CODES = {95, 96, 99}
ICY_CODES = {56, 57, 66, 67, 71, 73, 75, 77, 85, 86}   # snow and freezing rain: poor for riding
FOG_CODES = {45, 48}


class WeatherUnavailable(Exception):
    """The forecast or place search could not be fetched (no network, switched off, bad reply)."""


def weather_text(code: Any) -> str:
    try:
        return WMO_TEXT.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def round_coord(x: float) -> float:
    return round(float(x), COORD_DECIMALS)


def net_disabled() -> bool:
    return os.environ.get("SHEPHERD_NO_NET") == "1"


# ── HTTP (the only function that touches the network; tests replace it) ─────────────────────────────
def _http_get(url: str, params: dict) -> dict:
    if net_disabled():
        raise WeatherUnavailable("network disabled")
    import httpx
    import tls_trust
    try:
        r = httpx.get(url, params=params, timeout=TIMEOUT_SECONDS, verify=tls_trust.make_context(),
                      headers={"User-Agent": "Shepherd"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # never log the URL or params: they hold the location
        raise WeatherUnavailable(type(e).__name__) from None
    if not isinstance(data, dict):
        raise WeatherUnavailable("unexpected reply")
    return data


# ── Location (per profile, atomic JSON file) ────────────────────────────────────────────────────────
def clean_place(p: dict) -> dict:
    """A validated place with coordinates rounded to ``COORD_DECIMALS``. ValueError when unusable."""
    try:
        lat, lon = round_coord(p["latitude"]), round_coord(p["longitude"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("latitude and longitude are required") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude or longitude out of range")
    name = str(p.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("a place name is required")
    return {"name": name, "region": str(p.get("region") or "").strip()[:80],
            "country": str(p.get("country") or "").strip()[:80], "latitude": lat, "longitude": lon}


def read_location(path: Path) -> Optional[dict]:
    try:
        return clean_place(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def write_location(path: Path, place: dict) -> dict:
    place = clean_place(place)
    write_text_atomic(path, json.dumps(place), mode=0o600)
    return place


def clear_location(path: Path) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


# ── Place search ────────────────────────────────────────────────────────────────────────────────────
def parse_places(data: dict) -> list[dict]:
    out = []
    for r in data.get("results") or []:
        try:
            out.append(clean_place({"name": r.get("name"), "region": r.get("admin1"),
                                    "country": r.get("country"), "latitude": r.get("latitude"),
                                    "longitude": r.get("longitude")}))
        except ValueError:
            continue
    return out


def search_places(query: str) -> list[dict]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    return parse_places(_http_get(GEOCODE_URL, {"name": q[:100], "count": 5, "language": "en", "format": "json"}))


# ── Forecast ────────────────────────────────────────────────────────────────────────────────────────
def parse_forecast(data: dict) -> list[dict]:
    """Open-Meteo's column arrays under ``hourly`` as one dict per hour (local time, from ``timezone=auto``)."""
    h = data.get("hourly")
    if not isinstance(h, dict) or not isinstance(h.get("time"), list):
        raise WeatherUnavailable("unexpected reply")
    out = []
    for i, t in enumerate(h["time"]):
        def col(name):
            v = h.get(name)
            return v[i] if isinstance(v, list) and i < len(v) else None
        out.append({"time": str(t), "temp_c": col("temperature_2m"), "feels_c": col("apparent_temperature"),
                    "rain_pct": col("precipitation_probability"), "rain_mm": col("precipitation"),
                    "wind_kmh": col("wind_speed_10m"), "gust_kmh": col("wind_gusts_10m"),
                    "code": col("weather_code")})
    return out


_cache: dict[tuple[float, float], tuple[float, Any]] = {}   # rounded location -> (when, hours | WeatherUnavailable)
_lock = threading.Lock()


def get_hours(lat: float, lon: float, now: Optional[float] = None) -> list[dict]:
    """The hourly forecast for the rounded location, cached ``CACHE_SECONDS`` (a failure for ``FAILURE_BACKOFF_SECONDS``)."""
    key = (round_coord(lat), round_coord(lon))
    now = time.time() if now is None else now
    with _lock:
        hit = _cache.get(key)
    if hit:
        ttl = FAILURE_BACKOFF_SECONDS if isinstance(hit[1], WeatherUnavailable) else CACHE_SECONDS
        if now - hit[0] < ttl:
            if isinstance(hit[1], WeatherUnavailable):
                raise hit[1]
            return hit[1]
    try:
        hours = parse_forecast(_http_get(FORECAST_URL, {
            "latitude": key[0], "longitude": key[1], "hourly": ",".join(HOURLY),
            "forecast_days": FORECAST_DAYS, "timezone": "auto"}))
        result: Any = hours
    except WeatherUnavailable as e:
        result = e
        log.info(f"weather: forecast unavailable ({e})")
    with _lock:
        _cache[key] = (now, result)
    if isinstance(result, WeatherUnavailable):
        raise result
    return result


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# ── Rating ──────────────────────────────────────────────────────────────────────────────────────────
def _nums(hours: list[dict], key: str) -> list[float]:
    return [h[key] for h in hours if isinstance(h.get(key), (int, float))]


def rate_day(hours: list[dict]) -> dict:
    """Summary and rating of one day's riding hours: ``rating`` good/marginal/poor and the reasons in words."""
    gust = max(_nums(hours, "gust_kmh"), default=None)
    prob = max(_nums(hours, "rain_pct"), default=None)
    mm = sum(_nums(hours, "rain_mm"))
    feels = _nums(hours, "feels_c")
    coldest, hottest = (min(feels), max(feels)) if feels else (None, None)
    codes = [int(c) for c in _nums(hours, "code")]
    level, reasons = 0, []

    def flag(lvl: int, text: str):
        nonlocal level
        level = max(level, lvl)
        reasons.append(text)

    if any(c in THUNDER_CODES for c in codes):
        flag(2, "thunderstorms forecast")
    if any(c in ICY_CODES for c in codes):
        flag(2, "snow or freezing rain forecast")
    if any(c in FOG_CODES for c in codes):
        flag(1, "fog forecast")
    if gust is not None and gust >= GUST_POOR_KMH:
        flag(2, f"gusts {round(gust)} km/h")
    elif gust is not None and gust >= GUST_MARGINAL_KMH:
        flag(1, f"gusts {round(gust)} km/h")
    wet = f"rain {round(prob or 0)}% likely, {mm:.1f} mm"
    if mm >= RAIN_MM_POOR or ((prob or 0) >= RAIN_PROB_POOR_PCT and mm >= RAIN_MM_MARGINAL):
        flag(2, wet)
    elif mm >= RAIN_MM_MARGINAL or (prob or 0) >= RAIN_PROB_MARGINAL_PCT:
        flag(1, wet)
    if coldest is not None and coldest <= FEELS_COLD_POOR_C:
        flag(2, f"feels like {round(coldest)} °C")
    elif coldest is not None and coldest <= FEELS_COLD_MARGINAL_C:
        flag(1, f"feels like {round(coldest)} °C")
    if hottest is not None and hottest >= FEELS_HOT_POOR_C:
        flag(2, f"feels like {round(hottest)} °C")
    elif hottest is not None and hottest >= FEELS_HOT_MARGINAL_C:
        flag(1, f"feels like {round(hottest)} °C")

    temps = _nums(hours, "temp_c")
    worst = max(codes, key=lambda c: (c in THUNDER_CODES, c in ICY_CODES, c), default=None)
    return {
        "rating": ("good", "marginal", "poor")[level],
        "reasons": reasons,
        "suggest_indoor": level == 2,
        "summary": weather_text(worst) if worst is not None else "",
        "temp_min_c": round(min(temps)) if temps else None,
        "temp_max_c": round(max(temps)) if temps else None,
        "feels_min_c": round(coldest) if coldest is not None else None,
        "feels_max_c": round(hottest) if hottest is not None else None,
        "rain_pct_max": round(prob) if prob is not None else None,
        "rain_mm": round(mm, 1),
        "gust_max_kmh": round(gust) if gust is not None else None,
        "wind_max_kmh": round(max(_nums(hours, "wind_kmh"), default=0)) if _nums(hours, "wind_kmh") else None,
    }


def daily(hours: list[dict]) -> list[dict]:
    """One rated entry per day, from the hourly rows (riding hours only)."""
    days: dict[str, list[dict]] = {}
    for h in hours:
        d, _, t = h["time"].partition("T")
        try:
            hr = int(t[:2])
        except ValueError:
            continue
        if hr in RIDE_HOURS:
            days.setdefault(d, []).append(h)
    return [{"date": d, **rate_day(hs)} for d, hs in sorted(days.items())]
