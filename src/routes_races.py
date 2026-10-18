"""Races (#111): the A/B/C race list, the taper each gets in the plan, and a race-day plan.

The list is stored per profile (races.py). Every change is mirrored into the plan's goal block
(``goal.events`` and the A race's event fields), and the client then rebuilds the plan with
/api/plan/regenerate, as the Plan's "Time off" form does.

The race-day plan reuses the existing event projection (training_planner._project_event_capability, the
model behind /api/event/projection) for the expected duration and power. Fueling is not planned here.
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

import api_models
import clock
import races
import training_planner as tp
from paths import _plan_dir
from workout_gen import _WARMUP_S

router = APIRouter()

# The warm-up the app's generated workouts use (workout_gen._WARMUP_S, 15 min ramping 50 -> 70 % FTP).
WARMUP_MIN = _WARMUP_S // 60
FUELING_TEXT = "Fueling plan comes from the Nutrition settings."
POWER_METHOD = ("The event projection (Allen & Coggan duration-to-IF table blended with the event type's IF "
                "ceiling, Pinot & Grappe 2011 power profile). The range runs between those two IFs; the "
                "projection's own estimate sits inside it.")
POWER_CONFIDENCE = ("Low to moderate: a model estimate from your FTP, weight and fitness, not a pacing plan. "
                    "Terrain, weather, drafting and the day's form move it; ride by feel and heart rate too.")
TAPER_METHOD = ("Volume is cut and intensity kept (Bosquet et al. 2007 meta-analysis: 8-14 days, volume down "
                "41-60 %, intensity and frequency kept; Mujika & Padilla 2003). A race: the plan's taper, about "
                "60 % then 40 % of the load before it over the last 12 days. B race: about 60 % over its last 7 "
                "days, easy for the last 3 with openers the day before. C race: no taper, an easy day before.")
TAPER_CONFIDENCE = ("Moderate for the A taper (group averages, mostly swimmers and runners; how much you gain "
                    "from it varies from rider to rider), low for the B taper (no study covers secondary races).")


def _races_path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / races.FILE_NAME


def _plan_path():
    return _plan_dir() / "current_plan.json"


def _read_plan() -> dict | None:
    try:
        plan = json.loads(_plan_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return plan if isinstance(plan, dict) else None


def _goal() -> dict | None:
    return ((_read_plan() or {}).get("goal")) or None


def _sync_plan() -> bool:
    """Mirrors the race list into the plan's goal block. True when the plan changed."""
    def run():
        plan = _read_plan()
        # The saved list, not the merged view: a race the rider deleted must leave the plan too.
        saved = races.read_stored(_races_path())
        if plan is None or saved is None or not races.sync_plan_goal(plan, saved):
            return False
        tp.atomic_write_plan(_plan_path(), plan)
        return True
    return tp.run_under_plan_lock(run)


# ── what the plan does before each race ────────────────────────────────────────────────────────────
def _sessions(plan: dict | None):
    for w in (plan or {}).get("weeks") or []:
        for s in w.get("sessions") or []:
            if isinstance(s, dict) and s.get("day") and s.get("session_type") != "rest" and not s.get("is_race"):
                yield s


def _planned_tss(plan: dict | None, lo: date, hi: date) -> float:
    """Planned TSS on the days lo <= day < hi."""
    return round(sum(float(s.get("tss_estimate") or 0) for s in _sessions(plan)
                     if lo.isoformat() <= str(s["day"])[:10] < hi.isoformat()), 1)


def _week_of(plan: dict | None, d: date) -> dict | None:
    return next((w for w in (plan or {}).get("weeks") or []
                 if str(w.get("start")) <= d.isoformat() <= str(w.get("end"))), None)


def _taper(race: dict, plan: dict | None, goal: dict | None, on_plan: bool) -> dict:
    d = date.fromisoformat(race["date"])
    if not on_plan:
        why = ("not in your plan: build an event plan for it on the Plan screen to get its taper, or make it a B race"
               if race["priority"] == "A" else "not in your plan yet")
        return {"kind": "none", "start": None, "end": None, "text": why[0].upper() + why[1:] + "."}
    if race["priority"] == "C":
        return {"kind": "easy_day", "start": (d - timedelta(days=1)).isoformat(), "end": d.isoformat(),
                "text": "No taper: an easy day before, then race through your training."}
    if race["priority"] == "A":
        start = d - timedelta(days=tp.TAPER_DAYS)
        return {"kind": "full", "start": start.isoformat(), "end": (d - timedelta(days=1)).isoformat(),
                "planned_tss": _planned_tss(plan, start, d),
                "text": f"Full taper over the last {tp.TAPER_DAYS} days: volume down to about "
                        f"{round(tp.TAPER_FRACS[0] * 100)} % then {round(tp.TAPER_FRACS[-1] * 100)} % of the load "
                        "before it, intensity kept."}
    a = races.goal_event_date(goal)
    if a and d >= a - timedelta(days=tp.TAPER_DAYS):
        return {"kind": "none", "start": None, "end": None,
                "text": "Inside your A race taper, so no extra taper."}
    if (_week_of(plan, d) or {}).get("is_stepback"):
        return {"kind": "opener", "start": (d - timedelta(days=1)).isoformat(), "end": d.isoformat(),
                "text": "On an easier week already: easy days and openers before it, no extra cut."}
    start = d - timedelta(days=tp.B_TAPER_DAYS)
    before = _planned_tss(plan, start - timedelta(days=tp.B_TAPER_DAYS), start)
    return {"kind": "short", "start": start.isoformat(), "end": (d - timedelta(days=1)).isoformat(),
            "planned_tss": _planned_tss(plan, start, d), "before_tss": before,
            "text": f"Smaller taper over the last {tp.B_TAPER_DAYS} days: volume down to about "
                    f"{round(tp.TAPER_FRACS[0] * 100)} % of the week before, intensity kept; easy for the last "
                    "3 days with openers the day before."}


def _status(plan_synced: bool = False) -> dict:
    today = clock.today()
    plan = _read_plan()
    goal = (plan or {}).get("goal") or None
    path = _races_path()
    out = []
    for r in races.read_races(path, goal):
        on = plan is not None and races.in_plan(r, goal)
        out.append({**r, "in_plan": on, "days_to_go": (date.fromisoformat(r["date"]) - today).days,
                    "taper": _taper(r, plan, goal, on)})
    taper_weeks = [{"start": w.get("start"), "end": w.get("end"), "tss_target": w.get("tss_target") or 0,
                    "planned_tss": _planned_tss(plan, date.fromisoformat(str(w["start"])[:10]),
                                                date.fromisoformat(str(w["end"])[:10]) + timedelta(days=1))}
                   for w in (plan or {}).get("weeks") or []
                   if w.get("phase") == "taper" and w.get("start") and w.get("end")]
    a = races.goal_event_date(goal)
    return {"races": out, "stored": races.read_stored(path) is not None, "has_plan": plan is not None,
            "plan_a_date": a.isoformat() if a else None, "taper_weeks": taper_weeks, "plan_synced": plan_synced,
            "method": TAPER_METHOD, "confidence": TAPER_CONFIDENCE}


def _store(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(status_code=404, detail="No such race")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/races", responses={200: {"model": api_models.RacesStatus}})
def races_status():
    """The race list (read from the plan's goal for a rider who has not saved one) and each race's taper."""
    return _status()


@router.post("/api/races", responses={200: {"model": api_models.RacesStatus}})
def races_add(body: dict):
    """Adds a race. B and C races go into the plan; rebuild it afterwards (/api/plan/regenerate)."""
    _store(lambda: races.add_race(_races_path(), _goal(), body or {}, clock.today()))
    return _status(_sync_plan())


@router.put("/api/races/{race_id}", responses={200: {"model": api_models.RacesStatus}})
def races_update(race_id: str, body: dict):
    _store(lambda: races.update_race(_races_path(), _goal(), race_id, body or {}))
    return _status(_sync_plan())


@router.delete("/api/races/{race_id}", responses={200: {"model": api_models.RacesStatus}})
def races_delete(race_id: str):
    _store(lambda: races.delete_race(_races_path(), _goal(), race_id))
    return _status(_sync_plan())


@router.post("/api/races/sync", responses={200: {"model": api_models.RacesStatus}})
def races_sync():
    """Puts saved races the plan lacks (it was rebuilt from the Plan screen since) back into it."""
    return _status(_sync_plan())


# ── race day ───────────────────────────────────────────────────────────────────────────────────────
def _fitness_inputs() -> tuple[dict, float, float | None, dict]:
    """(athlete, current CTL, longest ride in 90 days, best efforts): the inputs /api/event/projection
    gives the same model, read through the app's own helpers."""
    import app as _app
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager.get()
        athlete = {"ftp": pm.ftp, "weight_kg": pm.weight_kg}
    except Exception:
        athlete = {"ftp": 200, "weight_kg": 70.0}
    try:
        ctl = _app._planning_ctl()
    except Exception:
        ctl = _app._PLANNING_CTL_UNKNOWN
    rides = _app._load_all_rides_safe()
    best: dict = {}
    try:
        cutoff = (clock.today() - timedelta(days=30)).isoformat()
        if sum(1 for r in rides or [] if (r.get("started_at") or "")[:10] >= cutoff) >= 5:
            best = _app._aggregate_best_efforts_90d(rides)
    except Exception:
        best = {}
    return athlete, ctl, _app._longest_ride_h_90d(rides), best


def _power(race: dict) -> dict:
    if not race.get("event_km"):
        return {"available": False, "reason": "Add the race distance to get a duration and power estimate."}
    athlete, ctl, longest, best = _fitness_inputs()
    goal = tp.Goal(goal_type="event", target_date=date.fromisoformat(race["date"]), event_name=race.get("name", ""),
                   event_km=race["event_km"], event_climb_m=race.get("event_climb_m") or 0,
                   event_type=race.get("event_type") or "granfondo", longest_ride_h_90d=longest)
    p = tp._project_event_capability(goal, athlete, {"current_ctl": ctl}, best_efforts_90d=best or None)
    ftp = int(athlete.get("ftp") or 200)
    hours = float(p["predicted_finish_h"])
    # The projection blends these two IFs; the range is the span between them (no new coefficient).
    ifs = sorted([tp._interp_if_by_duration(hours * 60.0), tp.EVENT_TYPE_IF.get(goal.event_type, 0.74)])
    return {"available": True, "ftp": ftp, "projected_duration_h": hours,
            "if_low": round(ifs[0], 2), "if_high": round(ifs[1], 2),
            "np_low": round(ifs[0] * ftp), "np_high": round(ifs[1] * ftp),
            "predicted_np": p["predicted_np"], "predicted_if": round(p["predicted_np"] / ftp, 2),
            "predicted_tss": p["predicted_tss"], "method": POWER_METHOD, "confidence": POWER_CONFIDENCE}


@router.get("/api/races/{race_id}/race-day", responses={200: {"model": api_models.RaceDayPlan}})
def race_day(race_id: str):
    """The race day: timeline, expected duration and an NP/IF range from the event projection."""
    plan = _read_plan()
    goal = (plan or {}).get("goal") or None
    race = next((r for r in races.read_races(_races_path(), goal) if r.get("id") == race_id), None)
    if race is None:
        raise HTTPException(status_code=404, detail="No such race")
    power = _power(race)
    duration = race.get("expected_duration_h") or power.get("projected_duration_h")
    return {"race": {**race, "in_plan": plan is not None and races.in_plan(race, goal),
                     "days_to_go": (date.fromisoformat(race["date"]) - clock.today()).days,
                     "taper": _taper(race, plan, goal, plan is not None and races.in_plan(race, goal))},
            "warmup_min": WARMUP_MIN, "timeline": races.timeline(race, WARMUP_MIN, duration),
            "expected_duration_h": race.get("expected_duration_h"), "power": power, "fueling": FUELING_TEXT}
