"""Running zones, critical speed, grade-adjusted pace and per-run load (#118, #119).

The science lives in run_metrics (each method cited there); this module only reads the
profile's thresholds and activities. Shepherd stores no pace or gradient streams for runs
(the stream backfill keeps streams only for rides with power), so per-run numbers are
activity-level: rTSS from average pace, hrTSS from average heart rate.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

import api_models
import clock
import db
import multisport
import run_metrics as rm

router = APIRouter()

_WALKS = ("walk", "hike")


def _thresholds_path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / "sport_thresholds.json"


def _run_thresholds() -> dict:
    t = multisport.read_thresholds(_thresholds_path())
    return {"pace": t["run_threshold_pace"], "hr": t["run_threshold_hr"]}


@router.get("/api/run/zones", responses={200: {"model": api_models.RunZones}})
def run_zones():
    """Friel pace and HR zones for the current run threshold pace and threshold HR."""
    t = _run_thresholds()
    pace, hr = t["pace"]["current"], t["hr"]["current"]
    return {
        "threshold_pace_s_per_km": pace,
        "threshold_hr": hr,
        "pace_zones": rm.pace_zones(pace) if pace else [],
        "hr_zones": rm.hr_zones(hr) if hr else [],
        "pace_history": t["pace"]["history"],
        "method": rm.ZONES_METHOD,
        "confidence": rm.ZONES_CONFIDENCE,
    }


@router.post("/api/run/critical-speed", responses={200: {"model": api_models.CriticalSpeed}})
def run_critical_speed(body: dict):
    """CS and D' from two or three time trials; with save=true, CS pace becomes the run threshold pace."""
    trials = body.get("trials")
    if not isinstance(trials, list):
        raise HTTPException(status_code=400, detail="trials must be a list of {distance_m, time_s}")
    try:
        out = rm.critical_speed([(t.get("distance_m"), t.get("time_s")) if isinstance(t, dict) else (None, None) for t in trials])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["saved"] = False
    if body.get("save") is True:
        try:
            multisport.set_threshold(_thresholds_path(), "run_threshold_pace", out["cs_pace_s_per_km"], clock.today(), source="critical_speed")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        out["saved"] = True
    return out


@router.get("/api/run/gap", responses={200: {"model": api_models.RunGap}})
def run_gap(pace_s_per_km: float, grade_pct: float):
    """The flat pace that costs the same as ``pace_s_per_km`` on a ``grade_pct`` % slope (Minetti et al. 2002)."""
    try:
        gap = rm.grade_adjusted_pace(pace_s_per_km, grade_pct / 100)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "pace_s_per_km": pace_s_per_km,
        "grade_pct": grade_pct,
        "gap_s_per_km": round(gap, 1),
        "cost_j_per_kg_m": round(rm.minetti_cost(grade_pct / 100), 2),
        "flat_cost_j_per_kg_m": round(rm.minetti_cost(0.0), 2),
        "method": rm.GAP_METHOD,
        "confidence": rm.GAP_CONFIDENCE,
    }


def _hr_inputs() -> dict:
    """Resting HR (latest wellness reading in 30 days), max HR (set, or Tanaka from age) and sex."""
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    rest = next((w["rhr"] for w in reversed(db.query_wellness(days=30)) if isinstance(w.get("rhr"), (int, float)) and w["rhr"] > 0), None)
    if pm._athlete.get("max_hr"):
        max_hr, max_src = pm.max_hr, "set"
    elif pm._athlete.get("age"):
        max_hr, max_src = pm.max_hr, "estimated from age (Tanaka, Monahan and Seals 2001)"
    else:
        max_hr, max_src = None, None
    return {"rest_hr": rest, "max_hr": max_hr, "max_hr_source": max_src, "sex": pm.sex}


def _cadence(raw_json: str | None):
    try:
        raw = json.loads(raw_json or "{}")
    except ValueError:
        return None
    return raw.get("average_cadence") if isinstance(raw, dict) else None


@router.get("/api/run/activities", responses={200: {"model": api_models.RunActivities}})
def run_activities(days: int = 90):
    """Runs in the last ``days`` with rTSS, hrTSS, cadence and stride beside intervals.icu's own load."""
    days = max(1, min(int(days), 3650))
    t = _run_thresholds()
    pace, lthr = t["pace"]["current"], t["hr"]["current"]
    hr_in = _hr_inputs()
    missing = []
    if not pace:
        missing.append("Set a run threshold pace to get rTSS.")
    if not lthr:
        missing.append("Set a run threshold heart rate to get hrTSS.")
    if not hr_in["rest_hr"]:
        missing.append("hrTSS needs a resting heart rate from the last 30 days of wellness.")
    if not hr_in["max_hr"]:
        missing.append("hrTSS needs a max heart rate or your age in the profile.")
    if hr_in["sex"] not in ("M", "F"):
        missing.append("hrTSS uses Banister's coefficients for men or women; set sex in the profile to M or F.")
    runs = []
    for a in reversed(db.query_activities(days=days)):
        kind = (a.get("sport") or "").replace(" ", "").replace("_", "").lower()
        if multisport.sport_of(a.get("sport")) != "running" or kind in _WALKS:
            continue
        dur, km = a.get("duration_sec") or 0, a.get("distance_km") or 0
        speed = km * 1000 / dur if dur > 0 and km > 0 else None
        row = {
            "id": str(a["id"]), "date": a.get("date"), "name": a.get("name") or "", "type": a.get("sport") or "",
            "duration_s": dur, "distance_km": round(km, 2) if km else None,
            "pace_s_per_km": round(1000 / speed, 1) if speed else None,
            "avg_hr": a.get("avg_hr"), "icu_load": a.get("tss"),
            "intensity": round(speed * pace / 1000, 3) if speed and pace else None,
            "rtss": rm.rtss(dur, speed, 1000 / pace) if speed and pace else None,
            "hrtss": None, "cadence_spm": None, "cadence_doubled": False, "step_length_m": None, "stride_length_m": None,
        }
        if a.get("avg_hr") and lthr and hr_in["rest_hr"] and hr_in["max_hr"] and dur > 0:
            row["hrtss"] = rm.hrtss(dur, a["avg_hr"], lthr, hr_in["rest_hr"], hr_in["max_hr"], hr_in["sex"] or "")
        cad = rm.steps_per_minute(_cadence(a.get("raw_json")))
        if cad:
            row["cadence_spm"], row["cadence_doubled"] = round(cad[0], 1), cad[1]
            if speed:
                row["step_length_m"], row["stride_length_m"] = rm.step_and_stride(speed, cad[0])
        runs.append(row)
    return {
        "threshold_pace_s_per_km": pace,
        "threshold_hr": lthr,
        **hr_in,
        "runs": runs,
        "missing": missing,
        "method": ("rTSS: TrainingPeaks running TSS, hours x IF squared x 100, IF = average speed / threshold speed. "
                   "hrTSS: Banister TRIMP from average heart rate, scaled so an hour at threshold heart rate is 100. "
                   "Stride length: speed / cadence, two steps per stride."),
        "confidence": ("Shepherd keeps no pace or gradient stream for runs, so rTSS uses average pace instead of normalised "
                       "graded pace: it reads low for hilly runs and for intervals. hrTSS from an average heart rate misses "
                       "how the effort was spread. Compare both with intervals.icu's load in the same row. "
                       "Ground-contact time is not recorded, so it is not shown. Walks and hikes are left out."),
    }
