"""Injury and illness episodes, the return ramp they put in the plan, and the ramp-rate warning (#113).

Episodes are stored per profile (injury.py); every change is mirrored into the plan's time off
(``unavailable_periods``), and the client then rebuilds the plan with /api/plan/regenerate, as the Plan's
"Time off" form does.
"""
import json
from datetime import date

from fastapi import APIRouter, HTTPException

import api_models
import clock
import db
import injury
import training_planner as tp
from paths import _plan_dir

router = APIRouter()


def _episodes_path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / injury.FILE_NAME


def _plan_path():
    return _plan_dir() / "current_plan.json"


def _read_plan() -> dict | None:
    try:
        plan = json.loads(_plan_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return plan if isinstance(plan, dict) else None


def _sync_plan(today: date) -> bool:
    """Mirrors the episodes into the plan's time off. True when the plan changed."""
    def run():
        plan = _read_plan()
        if plan is None or not injury.sync_plan_periods(plan, injury.read_episodes(_episodes_path()), today):
            return False
        tp.atomic_write_plan(_plan_path(), plan)
        return True
    return tp.run_under_plan_lock(run)


def _short_break(eps: list[dict], today: date) -> dict | None:
    """The latest finished illness when it was too short for a return ramp (see injury.SHORT_ILLNESS_DAYS)."""
    done = [e for e in eps if e.get("end") and e["end"] < today.isoformat()]
    if not done:
        return None
    last = max(done, key=lambda e: e["end"])
    days = (date.fromisoformat(last["end"]) - date.fromisoformat(last["start"])).days + 1
    if last["type"] != "illness" or days >= injury.SHORT_ILLNESS_DAYS:
        return None
    return {"type": last["type"], "episode_days": days, "end": last["end"]}


def _status(today: date, plan_synced: bool = False) -> dict:
    eps = injury.read_episodes(_episodes_path())
    plan = _read_plan()
    view = {"weeks": (plan or {}).get("weeks") or []}
    injury.sync_plan_periods(view, eps, today)
    active = next((e for e in eps if e["start"] <= today.isoformat() and (not e.get("end") or today.isoformat() <= e["end"])), None)
    ramp_weeks = [
        {"start": w.get("start"), "end": w.get("end"), "phase": w.get("phase"),
         "tss_target": w.get("tss_target") or 0, "easy_only": w.get("phase") == "recon"}
        for w in view["weeks"]
        if w.get("phase") in ("recon", "recovery_ramp") and str(w.get("end", "")) >= today.isoformat()
    ]
    ramp = injury.return_ramp(view.get("unavailable_periods"), today)
    return {"episodes": eps, "active": active,
            "return_ramp": ramp, "short_break": None if ramp else _short_break(eps, today),
            "ramp_weeks": ramp_weeks, "has_plan": plan is not None, "plan_synced": plan_synced,
            "method": injury.RETURN_METHOD, "note": injury.NOT_MEDICAL_ADVICE}


def _store(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(status_code=404, detail="No such episode")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/injury", responses={200: {"model": api_models.InjuryStatus}})
def injury_status():
    """Episodes, the one going on now, and the return ramp in the plan."""
    return _status(clock.today())


@router.post("/api/injury/episodes", responses={200: {"model": api_models.InjuryStatus}})
def injury_add(body: dict):
    """Records an injury or illness. Without an end it stays open, and the plan is paused, until resolved."""
    _store(lambda: injury.add_episode(
        _episodes_path(), type=str(body.get("type", "")), start=body.get("start"), end=body.get("end"),
        sport=str(body.get("sport") or "all"), body_area=body.get("body_area") or "", note=body.get("note") or ""))
    today = clock.today()
    return _status(today, _sync_plan(today))


@router.post("/api/injury/episodes/{episode_id}/resolve", responses={200: {"model": api_models.InjuryStatus}})
def injury_resolve(episode_id: str, body: dict | None = None):
    """Marks an episode over. With no ``end``, "I'm back": its last day is yesterday."""
    today = clock.today()
    end = (body or {}).get("end")
    if not end:
        ep = next((e for e in injury.read_episodes(_episodes_path()) if e.get("id") == episode_id), None)
        if ep is None:
            raise HTTPException(status_code=404, detail="No such episode")
        end = injury.back_today_end(ep, today).isoformat()
    _store(lambda: injury.resolve_episode(_episodes_path(), episode_id, end))
    return _status(today, _sync_plan(today))


@router.delete("/api/injury/episodes/{episode_id}", responses={200: {"model": api_models.InjuryStatus}})
def injury_delete(episode_id: str):
    """Removes an episode recorded by mistake, and its time off in the plan."""
    _store(lambda: injury.delete_episode(_episodes_path(), episode_id))
    today = clock.today()
    return _status(today, _sync_plan(today))


@router.get("/api/injury/ramp-rate", responses={200: {"model": api_models.RampRate}})
def injury_ramp_rate():
    """This week's training load against the 4 weeks before, combined and per sport."""
    return injury.ramp_rate(db.query_activities(days=36), clock.today())
