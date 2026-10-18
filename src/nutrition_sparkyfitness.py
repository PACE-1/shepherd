"""SparkyFitness (self-hosted nutrition tracker) adapter (#112).

The rider logs food and water in their own SparkyFitness server; this module reads the daily totals.
Two calls for the rest of the app: ``check_connection`` and ``fetch_daily_totals``, which returns one
normalised record per day: {date, kcal, carbs_g, protein_g, fat_g, water_ml}. Storing them is
routes_nutrition's job (table nutrition_daily, keyed by date and SOURCE).

Verified against the SparkyFitness source, CodeWithCJ/SparkyFitness commit 5364674f (2026-10-16), not
against a running server (docs/NUTRITION.md has the detail):
- Auth: header ``x-api-key: <key>`` (SparkyFitnessServer/middleware/authMiddleware.ts; a Bearer key is
  mapped to the same header by utils/bearerAuthBridge.ts). 401 wrong/expired key, 403 disabled key,
  429 rate limit (100 requests per minute per key by default, auth.ts).
- Food: GET /api/reports/mini-nutrition-trends?startDate=&endDate= (routes/reportRoutes.ts,
  services/reportService.ts getMiniNutritionTrends) -> [{date, calories, protein, carbs, fat, ...}],
  only days with entries; calories in kcal, macros in grams.
- Water: GET /api/v2/reports/hydration-nutrition-range?start=&end= (routes/v2/reportRoutes.ts,
  shared/src/schemas/api/HydrationNutritionRange.api.zod.ts) -> {days: [{date, water_ml, ...}]},
  at most 366 days.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx

import clock
from atomic_io import write_text_atomic
from http_util import _icu_verify

SOURCE = "sparkyfitness"
FILE_NAME = "nutrition_sparkyfitness.json"
TIMEOUT_S = 10
MAX_RANGE_DAYS = 366          # the server's limit on the water route
_FOOD = "/api/reports/mini-nutrition-trends"
_WATER = "/api/v2/reports/hydration-nutrition-range"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KEY = re.compile(r"^[\x21-\x7e]{1,512}$")     # printable ASCII, no spaces or newlines


class NutritionError(Exception):
    """A failure the rider can act on; the message is safe to show and never contains the key."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ── Settings: <profile>/nutrition_sparkyfitness.json, mode 0600 ─────────────────

def _path(profile_dir: Path) -> Path:
    return Path(profile_dir) / FILE_NAME


def load(profile_dir: Path) -> dict:
    """The stored connection, or {} when none is saved."""
    try:
        d = json.loads(_path(profile_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) and d.get("base_url") and d.get("api_key") else {}


def public(cfg: dict) -> dict:
    """What the interface may see: everything except the key."""
    return {"configured": bool(cfg), "base_url": cfg.get("base_url", ""), "has_key": bool(cfg.get("api_key"))}


def check_base_url(url: str) -> str:
    """The address the rider opens SparkyFitness at. http or https, any host (it is self-hosted, so a
    LAN address or localhost is normal), no user:password, query or fragment."""
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Enter the address of your SparkyFitness server")
    if any(c.isspace() for c in url) or len(url) > 300:
        raise ValueError("The address may not contain spaces")
    try:
        parts = urlsplit(url)
        parts.port                       # raises ValueError on a bad port
    except ValueError:
        raise ValueError("That is not a valid address") from None
    if parts.scheme not in ("http", "https"):
        raise ValueError("The address must start with http:// or https://")
    if not parts.hostname:
        raise ValueError("The address needs a host name or IP address")
    if parts.username or parts.password:
        raise ValueError("Leave the user name and password out of the address; use an API key")
    if parts.query or parts.fragment:
        raise ValueError("The address may not contain ? or #")
    return url


def save(profile_dir: Path, base_url: str, api_key: "str | None") -> dict:
    """Validate and store the connection. ``api_key`` None keeps the stored key, for the same address only."""
    base_url = check_base_url(base_url)
    if api_key is None:
        old = load(profile_dir)
        if old and old.get("base_url") != base_url:
            raise ValueError("Enter the API key again. The saved key is only reused for the same address.")
        key = old.get("api_key", "")
    else:
        key = api_key.strip()
    if not key:
        raise ValueError("An API key is required. Create a read-only key in SparkyFitness under Settings, API keys.")
    if not _KEY.match(key):
        raise ValueError("The API key may not contain spaces or line breaks")
    cfg = {"base_url": base_url, "api_key": key}
    write_text_atomic(_path(profile_dir), json.dumps(cfg, indent=2), mode=0o600)
    return cfg


def clear(profile_dir: Path) -> None:
    try:
        _path(profile_dir).unlink()
    except FileNotFoundError:
        pass


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _get(cfg: dict, path: str, params: dict):
    """One GET to the rider's server. Blocking: callers run it in a worker thread. Redirects are not
    followed, so the key goes to the saved address and nowhere else."""
    if not cfg:
        raise NutritionError("SparkyFitness is not connected. Add it in Settings.")
    if os.environ.get("SHEPHERD_NO_NET") == "1":
        raise NutritionError("Network access is turned off (SHEPHERD_NO_NET=1).")
    base = cfg["base_url"]
    try:
        r = httpx.get(base + path, params=params, timeout=TIMEOUT_S, follow_redirects=False,
                      headers={"x-api-key": cfg["api_key"], "Accept": "application/json"},
                      verify=_icu_verify())
    except httpx.HTTPError as e:
        # The class name only: the exception carries the request, and its headers hold the key.
        raise NutritionError(f"Could not reach {base}: {e.__class__.__name__}") from None
    s = r.status_code
    if 300 <= s < 400:
        raise NutritionError("The server answered with a redirect. Enter the exact address SparkyFitness opens at.", s)
    if s == 401:
        raise NutritionError("SparkyFitness rejected the API key (wrong or expired).", s)
    if s == 403:
        raise NutritionError("SparkyFitness refused the request (the API key may be disabled).", s)
    if s == 429:
        raise NutritionError("SparkyFitness rate limit reached. Try again in a minute.", s)
    if s >= 400:
        raise NutritionError(f"SparkyFitness returned {s} for {path}.", s)
    try:
        return r.json()
    except ValueError:
        raise NutritionError("The reply was not SparkyFitness data. Check the address.") from None


def _num(v) -> "float | None":
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 1) if math.isfinite(f) and f >= 0 else None


def _range(start: date, end: date) -> dict:
    if end < start:
        raise ValueError("start must not be after end")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"at most {MAX_RANGE_DAYS} days at a time")
    return {"start": start.isoformat(), "end": end.isoformat()}


# ── The two functions the app uses ────────────────────────────────────────────

def check_connection(cfg: dict) -> None:
    """Raises NutritionError unless the server accepts the key for an authenticated read (today's food)."""
    today = clock.today().isoformat()
    if not isinstance(_get(cfg, _FOOD, {"startDate": today, "endDate": today}), list):
        raise NutritionError("The reply was not SparkyFitness data. Check the address.")


def fetch_daily_totals(cfg: dict, start: date, end: date) -> list[dict]:
    """One record per day in [start, end] with something logged:
    {date, kcal, carbs_g, protein_g, fat_g, water_ml}. water_ml is None when the server has no water route."""
    r = _range(start, end)
    food = _get(cfg, _FOOD, {"startDate": r["start"], "endDate": r["end"]})
    if not isinstance(food, list):
        raise NutritionError("The reply was not SparkyFitness data. Check the address.")
    try:
        water_rows = _get(cfg, _WATER, r)
    except NutritionError as e:
        if e.status != 404:          # an older server without the v2 route: food totals only
            raise
        water_rows = None
    water = {}
    if water_rows is not None:
        if not isinstance(water_rows, dict) or not isinstance(water_rows.get("days"), list):
            raise NutritionError("The water reply was not SparkyFitness data.")
        water = {str(w.get("date")): _num(w.get("water_ml")) for w in water_rows["days"] if isinstance(w, dict)}

    out: dict[str, dict] = {}
    for row in food:
        d = str(row.get("date", "")) if isinstance(row, dict) else ""
        if not _DAY.match(d) or not r["start"] <= d <= r["end"]:
            continue
        out[d] = {"date": d, "kcal": _num(row.get("calories")), "carbs_g": _num(row.get("carbs")),
                  "protein_g": _num(row.get("protein")), "fat_g": _num(row.get("fat")),
                  "water_ml": water.get(d) if water_rows is not None else None}
    for d, ml in water.items():
        if d not in out and ml and _DAY.match(d) and r["start"] <= d <= r["end"]:
            out[d] = {"date": d, "kcal": None, "carbs_g": None, "protein_g": None, "fat_g": None, "water_ml": ml}
    return [out[d] for d in sorted(out)]
