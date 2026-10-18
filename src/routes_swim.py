"""Swim CSS test, per-swim load and stroke data (#122), and open-water notes (#126).

The science lives in swim_metrics (each method cited there); this module only reads the
profile's thresholds (multisport, kind ``swim_css`` in s/100 m), activities and notes.
Pool and open-water swims are told apart by intervals.icu's activity type and pool length.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

import api_models
import clock
import db
import multisport
import open_water
import swim_metrics as sm

router = APIRouter()


def _profile_dir():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir


def _thresholds_path():
    return _profile_dir() / "sport_thresholds.json"


def _notes_path():
    return _profile_dir() / open_water.FILE_NAME


def _css() -> dict:
    return multisport.read_thresholds(_thresholds_path())["swim_css"]


@router.get("/api/swim/css", responses={200: {"model": api_models.SwimCss}})
def swim_css():
    """The current CSS pace and its dated history. No zones: see swim_metrics.ZONES_NOTE."""
    t = _css()
    return {"css_s_per_100m": t["current"], "history": t["history"], "zones_note": sm.ZONES_NOTE,
            "method": sm.CSS_METHOD, "confidence": sm.CSS_CONFIDENCE}


@router.post("/api/swim/css-test", responses={200: {"model": api_models.SwimCssTest}})
def swim_css_test(body: dict):
    """CSS from two (or three) all-out swims; with save=true it becomes the swim CSS threshold."""
    trials = body.get("trials")
    if not isinstance(trials, list):
        raise HTTPException(status_code=400, detail="trials must be a list of {distance_m, time_s}")
    try:
        out = sm.css([(t.get("distance_m"), t.get("time_s")) if isinstance(t, dict) else (None, None) for t in trials])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e).replace("run them", "swim them"))
    out["saved"] = False
    if body.get("save") is True:
        try:
            multisport.set_threshold(_thresholds_path(), "swim_css", out["css_s_per_100m"], clock.today(), source="css_test")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        out["saved"] = True
    return out


def _raw(raw_json: str | None) -> dict:
    try:
        raw = json.loads(raw_json or "{}")
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


@router.get("/api/swim/activities", responses={200: {"model": api_models.SwimActivities}})
def swim_activities(days: int = 90):
    """Swims in the last ``days`` with pace per 100 m, sTSS and the stroke fields intervals.icu stores."""
    days = max(1, min(int(days), 3650))
    css = _css()["current"]
    swims = []
    for a in reversed(db.query_activities(days=days)):
        if multisport.sport_of(a.get("sport")) != "swimming":
            continue
        raw = _raw(a.get("raw_json"))
        dur, km = a.get("duration_sec") or 0, a.get("distance_km") or 0
        speed = km * 1000 / dur if dur > 0 and km > 0 else None
        swims.append({
            "id": str(a["id"]), "date": a.get("date"), "name": a.get("name") or "", "type": a.get("sport") or "",
            "water": sm.water(a.get("sport"), raw),
            "duration_s": dur, "distance_m": round(km * 1000) if km else None,
            "pace_s_per_100m": round(100 / speed, 1) if speed else None,
            "avg_hr": a.get("avg_hr"), "icu_load": a.get("tss"),
            "intensity": round(speed * css / 100, 3) if speed and css else None,
            "stss": sm.stss(dur, speed, 100 / css) if speed and css else None,
            **sm.stroke_fields(raw),
        })
    return {
        "css_s_per_100m": css,
        "swims": swims,
        "missing": [] if css else ["Set a swim CSS, or save a CSS test, to get sTSS."],
        "method": sm.STSS_METHOD,
        "confidence": sm.STSS_CONFIDENCE,
        "stroke_note": sm.STROKE_NOTE,
    }


# ── open-water notes (#126) ──────────────────────────────────────────────────
def _store(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(status_code=404, detail="No such note")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/swim/open-water", responses={200: {"model": api_models.OpenWaterNotes}})
def open_water_list():
    return {"notes": open_water.read_notes(_notes_path())}


@router.post("/api/swim/open-water", responses={200: {"model": api_models.OpenWaterNote}})
def open_water_add(body: dict):
    return _store(lambda: open_water.add_note(_notes_path(), body))


@router.put("/api/swim/open-water/{note_id}", responses={200: {"model": api_models.OpenWaterNote}})
def open_water_edit(note_id: str, body: dict):
    return _store(lambda: open_water.update_note(_notes_path(), note_id, body))


@router.delete("/api/swim/open-water/{note_id}", responses={200: {"model": api_models.Ok}})
def open_water_delete(note_id: str):
    _store(lambda: open_water.delete_note(_notes_path(), note_id))
    return {"ok": True}
