"""Nutrition tracker connection, the nutrition_daily table, and the Fueling card (#112).

The tracker is SparkyFitness (nutrition_sparkyfitness.py). Everything here reads the table, never the
tracker, except the sync. The handlers are plain ``def``: FastAPI runs them in its worker thread pool,
so the tracker's HTTP calls (up to 10 s each) never block the event loop.

Sync is on demand (Settings and the Fueling screen). There is no background sync: the after-sync hook
(db.post_sync_callback) is assigned in app.py, which this feature does not edit; calling ``sync_now``
from app._after_background_sync would add it.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException

import api_models
import clock
import config
import db
import fueling
import nutrition_sparkyfitness as sparky

router = APIRouter()
_log = logging.getLogger("shepherd.nutrition")
SYNC_DAYS = 30

_TABLE = """CREATE TABLE IF NOT EXISTS nutrition_daily (
    date      TEXT NOT NULL,
    source    TEXT NOT NULL,
    kcal      REAL,
    carbs_g   REAL,
    protein_g REAL,
    fat_g     REAL,
    water_ml  REAL,
    synced_at TEXT,
    PRIMARY KEY (date, source)
)"""
_COLS = ("date", "source", "kcal", "carbs_g", "protein_g", "fat_g", "water_ml", "synced_at")


def _conn():
    """The active profile's database, with the table created on first use (idempotent)."""
    c = db.get_db()
    c.execute(_TABLE)
    return c


def store(source: str, start: str, end: str, records: list[dict], synced_at: str) -> int:
    """Replaces ``source``'s rows for [start, end] with ``records``, so a day emptied in the tracker
    is emptied here too."""
    c = _conn()
    with c:
        c.execute("DELETE FROM nutrition_daily WHERE source = ? AND date BETWEEN ? AND ?", (source, start, end))
        c.executemany(
            "INSERT INTO nutrition_daily (date, source, kcal, carbs_g, protein_g, fat_g, water_ml, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(r["date"], source, r.get("kcal"), r.get("carbs_g"), r.get("protein_g"), r.get("fat_g"),
              r.get("water_ml"), synced_at) for r in records])
    return len(records)


def read_day(day: str) -> dict | None:
    """The logged totals for one day. With one tracker there is one row; ordered by source so a
    second tracker would not make the answer change from call to call."""
    row = _conn().execute(f"SELECT {', '.join(_COLS)} FROM nutrition_daily WHERE date = ? ORDER BY source LIMIT 1",
                          (day,)).fetchone()
    return dict(row) if row else None


def _last_synced(source: str) -> str | None:
    row = _conn().execute("SELECT MAX(synced_at) FROM nutrition_daily WHERE source = ?", (source,)).fetchone()
    return row[0] if row else None


def _profile_dir():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir


def _cfg() -> dict:
    return sparky.load(_profile_dir())


def _public(cfg: dict) -> dict:
    return {**sparky.public(cfg), "last_synced_at": _last_synced(sparky.SOURCE) if cfg else None}


def sync_now(days: int = SYNC_DAYS) -> dict:
    """Fetch the last ``days`` days from the tracker into nutrition_daily. Raises NutritionError."""
    end = clock.today()
    start = end - timedelta(days=days - 1)
    records = sparky.fetch_daily_totals(_cfg(), start, end)
    synced_at = clock.now().isoformat(timespec="seconds")
    n = store(sparky.SOURCE, start.isoformat(), end.isoformat(), records, synced_at)
    _log.info("EVENT=nutrition_sync source=%s days=%d with_data=%d", sparky.SOURCE, days, n)
    return {"start": start.isoformat(), "end": end.isoformat(), "days_with_data": n, "synced_at": synced_at}


@router.get("/api/nutrition/connection", responses={200: {"model": api_models.NutritionConnection}})
def nutrition_connection():
    """The SparkyFitness connection. The API key is never returned, only whether one is saved."""
    return _public(_cfg())


@router.post("/api/nutrition/connection", responses={200: {"model": api_models.NutritionConnection}})
def nutrition_connection_save(body: dict):
    """Saves the address and key. An empty key keeps the saved one, for the same address only."""
    key = body.get("api_key")
    try:
        cfg = sparky.save(_profile_dir(), str(body.get("base_url") or ""),
                          key if isinstance(key, str) and key.strip() else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _public(cfg)


@router.delete("/api/nutrition/connection", responses={200: {"model": api_models.NutritionConnection}})
def nutrition_connection_delete():
    """Forgets the address and key. Synced days stay in the table."""
    sparky.clear(_profile_dir())
    return _public({})


@router.post("/api/nutrition/test", responses={200: {"model": api_models.NutritionTest}})
def nutrition_test():
    try:
        sparky.check_connection(_cfg())
    except sparky.NutritionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "message": "Connected: SparkyFitness accepted the key."}


@router.post("/api/nutrition/sync", responses={200: {"model": api_models.NutritionSync}})
def nutrition_sync(body: dict | None = None):
    days = (body or {}).get("days", SYNC_DAYS)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= sparky.MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"days must be an integer from 1 to {sparky.MAX_RANGE_DAYS}")
    try:
        return sync_now(days)
    except sparky.NutritionError as e:
        raise HTTPException(status_code=502, detail=str(e))


def _today_session(today: str) -> dict | None:
    """Today's planned session as the Today card reads it (app's one week view)."""
    import app as _app      # lazily: app imports this module
    week = _app._stored_week_view(_app._read_stored_plan(), 0).as_weekly_plan()
    s = next((s for s in week["sessions"] if s.get("day") == today and s.get("on_record")), None)
    if not s or (s.get("session_type") or "rest") == "rest" or not s.get("duration_min"):
        return None
    return {"session_type": s.get("session_type") or "", "duration_min": int(s.get("duration_min") or 0)}


@router.get("/api/fueling", responses={200: {"model": api_models.Fueling}})
def fueling_today():
    """Today's carbohydrate guidance from the planned session and the rider's weight, against what the
    tracker has logged so far (as of the last sync)."""
    today = clock.today().isoformat()
    session = _today_session(today)
    minutes = session["duration_min"] if session else 0
    try:
        weight = float(config.ATHLETE_WEIGHT_KG or 0) or None
    except (TypeError, ValueError):
        weight = None
    work_kj = sum(float(a.get("kilojoules") or 0) for a in db.query_activities(days=1)
                  if str(a.get("date") or "")[:10] == today)
    return {
        "date": today,
        "weight_kg": weight,
        "session": session,
        "during": fueling.during_session(minutes) if session else None,
        "day": fueling.daily_carbs(weight, minutes, session["session_type"] if session else "rest") if weight else None,
        "logged": read_day(today),
        "connected": bool(_cfg()),
        "ride_kcal_approx": fueling.ride_kcal(work_kj) if work_kj > 0 else None,
        "hourly_method": fueling.HOURLY_METHOD,
        "daily_method": fueling.DAILY_METHOD,
        "energy_method": fueling.ENERGY_METHOD,
        "note": fueling.NOT_MEDICAL_ADVICE,
    }
