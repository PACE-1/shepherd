"""Companion sessions in the plan (run / swim / strength next to the cycling plan; ADDENDUM 5).

The planner adds them (multisport_plan.overlay, through training_planner's plan builders) to each week's
``companions`` list. These routes read them and let the rider dismiss one; ``reconcile_plan_week`` is the
completion hook app._reconcile_current_week calls after the cycling matcher.
"""
import json
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

import api_models
import clock
import db
import multisport_plan as mp
import sport_balance as sb
import training_planner as tp
from paths import _plan_dir

router = APIRouter()
log = logging.getLogger(__name__)
_OUT_KEYS = ("id", "day", "day_name", "sport", "session_type", "duration_min", "description", "status",
             "hard", "template_id", "workout", "dismissed_at", "completion_matches")


def _plan_path():
    return _plan_dir() / "current_plan.json"


def _read_plan() -> dict | None:
    try:
        plan = json.loads(_plan_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return plan if isinstance(plan, dict) else None


def _enabled() -> bool:
    try:
        from profile_manager import ProfileManager
        return mp.overlay_on(sb.read_targets(ProfileManager.get().active_dir / sb.FILE_NAME)["targets"])
    except Exception:  # noqa: BLE001
        return False


def _out(c: dict) -> dict:
    return {k: c.get(k) for k in _OUT_KEYS if k in c}


def _visible(week: dict, today: date) -> list[dict]:
    """A week's companions as the rider sees them: an ended week shows no missed ones (they are dropped)."""
    ended = str(week.get("end", "")) < today.isoformat()
    return [_out(c) for c in week.get("companions") or []
            if isinstance(c, dict) and not (ended and c.get("status") == "missed")]


@router.get("/api/plan/companions", responses={200: {"model": api_models.PlanCompanions}})
def plan_companions(start: str | None = Query(None, description="a day in the first week shown (default today)")):
    """Companion sessions of the plan week holding ``start`` (default today) and the week after it."""
    today = clock.today()
    try:
        anchor = date.fromisoformat(start) if start else today
    except ValueError:
        raise HTTPException(status_code=400, detail="start must be a date (YYYY-MM-DD)")
    plan = _read_plan()
    weeks = [w for w in (plan or {}).get("weeks") or [] if isinstance(w, dict)]
    shown = [w for w in weeks if str(w.get("end", "")) >= anchor.isoformat()][:2]
    today_list = [_out(c) for w in weeks for c in w.get("companions") or []
                  if isinstance(c, dict) and c.get("day") == today.isoformat() and c.get("status") != "dismissed"]
    return {"enabled": _enabled(), "has_plan": plan is not None, "note": mp.NOT_VALIDATED,
            "today": today_list,
            "weeks": [{"week_num": w.get("week_num"), "start": w.get("start"), "end": w.get("end"),
                       "companions": _visible(w, today)} for w in shown]}


@router.post("/api/plan/companions/{companion_id}/dismiss", responses={200: {"model": api_models.CompanionDismissed}})
def plan_companion_dismiss(companion_id: str):
    """Dismisses a companion session: it stays in the plan, greyed, and a rebuild does not plan it again."""
    def run():
        plan = _read_plan()
        for w in (plan or {}).get("weeks") or []:
            for c in (w.get("companions") or []) if isinstance(w, dict) else []:
                if isinstance(c, dict) and c.get("id") == companion_id:
                    c["status"] = "dismissed"
                    c["dismissed_at"] = clock.now().isoformat()
                    tp.atomic_write_plan(_plan_path(), plan)
                    return _out(c)
        return None
    found = tp.run_under_plan_lock(run)
    if found is None:
        raise HTTPException(status_code=404, detail="No such companion session")
    return {"ok": True, "companion": found}


def reconcile_plan_week(week: dict, today: date) -> int:
    """Marks one stored plan week's companions done / missed from the activities table (see
    multisport_plan.reconcile_week). Never raises: the cycling matcher that calls it must not be affected."""
    try:
        if not isinstance(week, dict) or not week.get("companions"):
            return 0
        start = date.fromisoformat(str(week.get("start"))[:10])
        return mp.reconcile_week(week, db.query_activities(days=max(1, (today - start).days + 1)), today)
    except Exception:
        log.exception("companion reconcile skipped")
        return 0
