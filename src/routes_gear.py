"""Gear (#115): bikes, shoes and components with distance and hours, service thresholds, "service done".

Logic lives in gear.py. There is no push reminder: due items show on the Gear screen (adding an event to
notifications.py would change its settings model, tests and Settings screen, which this feature does not own).
"""
from datetime import date

from fastapi import APIRouter, HTTPException

import api_models
import clock
import db
import gear

router = APIRouter()

_COLS = ("id, date, name, sport, duration_sec, distance_km, json_extract(raw_json, '$.gear.name')")
_KEYS = ("id", "date", "name", "sport", "duration_sec", "distance_km", "icu_gear")
_FIELDS = ("name", "kind", "parent_id", "retired", "service_every_km", "service_every_hours", "started_on", "icu_name")


def _path():
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    if not pm.active_id:
        raise HTTPException(status_code=409, detail="No profile is active.")
    return pm.active_dir / gear.FILE_NAME


def _rows(sql_tail: str = "") -> list[dict]:
    try:
        cur = db.get_db().execute(f"SELECT {_COLS} FROM activities {sql_tail}")
        return [dict(zip(_KEYS, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001 - no database yet (nothing synced): gear still works, with no rides
        return []


def _overview():
    return gear.overview(gear.read(_path()), _rows(), _rows("ORDER BY date DESC LIMIT 15"))


def _store(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(status_code=404, detail="No such gear")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/gear", responses={200: {"model": api_models.GearOverview}})
def gear_overview():
    """Items with their counters, intervals.icu gear names not yet used, and the latest rides with their gear."""
    return _overview()


@router.post("/api/gear", responses={200: {"model": api_models.GearOverview}})
def gear_add(body: dict):
    _store(lambda: gear.add_item(_path(), **{k: body.get(k) for k in _FIELDS}))
    return _overview()


@router.put("/api/gear/assignment", responses={200: {"model": api_models.GearOverview}})
def gear_assign(body: dict):
    """``gear_id`` an item id, "none" for no gear, or null to go back to the automatic choice."""
    aid = str(body.get("activity_id") or "")
    if not aid:
        raise HTTPException(status_code=400, detail="activity_id is required")
    _store(lambda: gear.assign(_path(), aid, body.get("gear_id")))
    return _overview()


@router.patch("/api/gear/{item_id}", responses={200: {"model": api_models.GearOverview}})
def gear_edit(item_id: str, body: dict):
    _store(lambda: gear.edit_item(_path(), item_id, **{k: body[k] for k in _FIELDS if k in body}))
    return _overview()


@router.delete("/api/gear/{item_id}", responses={200: {"model": api_models.GearOverview}})
def gear_delete(item_id: str):
    _store(lambda: gear.delete_item(_path(), item_id))
    return _overview()


@router.post("/api/gear/{item_id}/service", responses={200: {"model": api_models.GearOverview}})
def gear_service(item_id: str, body: dict | None = None):
    """Service done (``date`` defaults to today): the counter restarts after that day; history is kept."""
    body = body or {}

    def run():
        raw = body.get("date")
        try:
            on = date.fromisoformat(str(raw)) if raw else clock.today()
        except ValueError:
            raise ValueError("date must be a date (YYYY-MM-DD)") from None
        if on > clock.today():
            raise ValueError("The service day can't be in the future.")
        return gear.service_done(_path(), item_id, on, body.get("note") or "")
    _store(run)
    return _overview()
