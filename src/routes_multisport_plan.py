"""Companion sessions in the plan (run / swim / strength next to the cycling plan; ADDENDUM 5).

The planner adds them (multisport_plan.overlay, through training_planner's plan builders) to each week's
``companions`` list. These routes read them and let the rider dismiss one; ``reconcile_plan_week`` is the
completion hook app._reconcile_current_week calls after the cycling matcher.

Bricks (#123): the rider's transition-time target (``brick_transition.json`` in the profile, no default)
and a per-brick note on how the run felt off the bike (stored in the companion's ``workout``, editable).
"""
import json
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

import api_models
import atomic_io
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


TRANSITION_FILE = "brick_transition.json"
TRANSITION_MAX_S = 3600


def _out(c: dict) -> dict:
    out = {k: c.get(k) for k in _OUT_KEYS if k in c}
    w = c.get("workout") if isinstance(c.get("workout"), dict) else {}
    for k in ("brick_of", "brick_note", "limiter"):
        if w.get(k):
            out[k] = w[k]
    return out


def _transition_path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / TRANSITION_FILE


def read_transition_target() -> int | None:
    """The rider's transition-time target in seconds, or None (never set: there is no default)."""
    try:
        v = json.loads(_transition_path().read_text(encoding="utf-8")).get("transition_target_s")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 < v <= TRANSITION_MAX_S else None


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
            "today": today_list, "transition_target_s": read_transition_target(),
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


@router.put("/api/plan/bricks/transition", responses={200: {"model": api_models.BrickTransition}})
def plan_brick_transition(body: dict):
    """Stores the rider's transition-time target (whole seconds, 1-3600; null clears it)."""
    v = (body or {}).get("transition_target_s")
    if v is not None and not (isinstance(v, int) and not isinstance(v, bool) and 0 < v <= TRANSITION_MAX_S):
        raise HTTPException(status_code=400, detail="transition_target_s must be whole seconds from 1 to 3600, or null")
    atomic_io.write_json_atomic(_transition_path(), {"transition_target_s": v})
    return {"ok": True, "transition_target_s": v}


@router.post("/api/plan/companions/{companion_id}/brick-note", responses={200: {"model": api_models.CompanionDismissed}})
def plan_brick_note(companion_id: str, body: dict):
    """The rider's note on how a brick's run felt off the bike (empty clears it). Only for a brick, and
    only once its day has come. A brick with a note is kept as it is when the plan is rebuilt."""
    note = (body or {}).get("note")
    if not isinstance(note, str):
        raise HTTPException(status_code=400, detail="note must be text")
    note = note.strip()
    if len(note) > mp.BRICK_NOTE_MAX:
        raise HTTPException(status_code=400, detail=f"note can be at most {mp.BRICK_NOTE_MAX} characters")
    today = clock.today().isoformat()

    def run():
        plan = _read_plan()
        for w in (plan or {}).get("weeks") or []:
            for c in (w.get("companions") or []) if isinstance(w, dict) else []:
                if isinstance(c, dict) and c.get("id") == companion_id:
                    if not mp.is_brick(c):
                        return "not_brick"
                    if str(c.get("day", "")) > today:
                        return "future"
                    if note:
                        c["workout"]["brick_note"] = note
                    else:
                        c["workout"].pop("brick_note", None)
                    tp.atomic_write_plan(_plan_path(), plan)
                    return _out(c)
        return None
    found = tp.run_under_plan_lock(run)
    if found is None:
        raise HTTPException(status_code=404, detail="No such companion session")
    if found == "not_brick":
        raise HTTPException(status_code=400, detail="Only a brick session takes a note on the run off the bike")
    if found == "future":
        raise HTTPException(status_code=400, detail="You can add the note once the brick's day has come")
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
