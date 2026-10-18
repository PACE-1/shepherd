"""Run workout library routes (#120). The templates and their science live in sessions_run (Daniels'
Running Formula 3rd ed. structures, Friel pace zones from run_metrics); this module reads the rider's
threshold pace, filters the library and renders downloads:

  * .fit: a structured RUNNING workout (fit_tool, as the cycling /api/export/fit-workout export): time
    steps, a speed range for pace targets, an open target named with the cue for effort targets and
    open-ended zones, and FIT repeat steps for reps. Not yet checked on a real Garmin device.
  * .txt: the same workout as plain text, the fallback for any watch or app.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import api_models
import clock
import multisport
import run_metrics as rm
import sessions_run as sr
import workout_builder as wb

router = APIRouter()
_BY_ID = {t.id: t for t in sr.TEMPLATES}
_STEP_LABEL = {"warmup": "Warm-up", "work": "Run", "recovery": "Recovery", "cooldown": "Cool-down"}


def _thresholds() -> dict:
    from routes_run import _thresholds_path
    return multisport.read_thresholds(_thresholds_path())


def _default_minutes(lo: int, hi: int) -> int:
    """The middle of a range, on a 5-minute step, inside it."""
    return max(lo, min(hi, int((lo + hi) / 2 // 5 * 5)))


def _row(t: sr.RunTemplate, th: dict, minutes: int) -> dict:
    w = t.builder(th, minutes)
    return {"id": t.id, "name": w["name"], "kind": t.kind, "session_type": t.session_type, "stimulus": t.stimulus,
            "daniels": t.daniels, "intent": t.intent, "hard": t.hard, "min_minutes": t.minutes[0],
            "max_minutes": t.minutes[1], "minutes": minutes, "workout": w,
            "rtss_estimate": sr.rtss_estimate(w), "profile": sr.profile(w), "source": t.source}


def _template(session_id: str, minutes: int | None) -> tuple[sr.RunTemplate, int]:
    t = _BY_ID.get(session_id)
    if t is None:
        raise HTTPException(status_code=404, detail="no such run session")
    lo, hi = t.minutes
    if minutes is None:
        return t, _default_minutes(lo, hi)
    if not lo <= minutes <= hi:
        raise HTTPException(status_code=400, detail=f"minutes must be from {lo} to {hi} for this session")
    return t, minutes


@router.get("/api/run/sessions", responses={200: {"model": api_models.RunSessions}})
def run_sessions(type: str = Query("", description="kind, stimulus or Daniels category (E, T, I, R)"),
                 min_minutes: int | None = Query(None, ge=0), max_minutes: int | None = Query(None, ge=0),
                 max_rtss: float | None = Query(None, ge=0)):
    """The run library filtered, each built for the rider's current threshold pace (effort cues without one)
    at a length inside both its own range and the filter's, with its estimated rTSS."""
    th = _thresholds()
    want = type.strip().lower()
    rows = []
    for t in sr.TEMPLATES:
        if want and want not in (t.kind, t.stimulus, t.daniels.lower()):
            continue
        lo, hi = max(t.minutes[0], min_minutes or 0), min(t.minutes[1], max_minutes if max_minutes is not None else 10**6)
        if lo > hi:
            continue
        row = _row(t, th, _default_minutes(lo, hi))
        if max_rtss is None or row["rtss_estimate"] <= max_rtss:
            rows.append(row)
    pace = sr.threshold_pace(th)
    return {"threshold_pace_s_per_km": pace, "targets": "pace" if pace else "effort", "note": sr.NOT_VALIDATED,
            "method": f"{sr.SOURCE} Targets: {rm.ZONES_METHOD} Load: TrainingPeaks rTSS at each step's intended "
                      "zone (an estimate).",
            "sessions": rows}


@router.get("/api/run/sessions/{session_id}", responses={200: {"model": api_models.RunSession}})
def run_session(session_id: str, minutes: int | None = Query(None)):
    """One run session built at ``minutes`` (default: the middle of its range)."""
    t, m = _template(session_id, minutes)
    return _row(t, _thresholds(), m)


# ── downloads ──────────────────────────────────────────────────────────────────────────────────────────
def _pace(s_per_km: float) -> str:
    s = round(s_per_km)
    return f"{s // 60}:{s % 60:02d}/km"


def target_text(tg: dict) -> str:
    zone = f"Z{tg['zone']} {sr.ZONE_NAME[tg['zone']]}"
    if tg["kind"] == "effort":
        return f"{tg['label']} ({zone} by feel)"
    fast, slow = tg.get("fast_s_per_km"), tg.get("slow_s_per_km")
    if fast and slow:
        return f"{_pace(fast)} to {_pace(slow)} ({zone})"
    # Open-ended zones: Z1 has only its fast edge (run slower than it), Z5c only its slow edge.
    return f"slower than {_pace(fast)} ({zone})" if fast else f"faster than {_pace(slow)} ({zone})"


def _dur(s: int) -> str:
    return f"{s // 60} min" + (f" {s % 60} s" if s % 60 else "") if s >= 60 else f"{s} s"


def to_text(workout: dict, minutes: int) -> str:
    lines = [workout["name"], f"{minutes} minutes. {workout['description']}", ""]
    for s in workout["steps"]:
        if s["kind"] == "repeat":
            on, off = s["on"], s["off"]
            lines.append(f"{s['count']} x: {_dur(on['duration_s'])} at {target_text(on['target'])}, "
                         f"then {_dur(off['duration_s'])} at {target_text(off['target'])}")
        else:
            lines.append(f"{_STEP_LABEL[s['kind']]} {_dur(s['duration_s'])}: {target_text(s['target'])}")
    lines += ["", sr.NOT_VALIDATED, f"Source: {sr.SOURCE}"]
    return "\n".join(lines) + "\n"


def to_fit(workout: dict) -> bytes:
    """A FIT workout file (sport running) for a VALID run workout. Pace targets become a custom speed range
    (m/s, slow end to fast end); effort targets and open-ended zones become an open target whose step name
    carries the cue. Reps use FIT's repeat-until-steps-complete step."""
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import (
        FileType,
        Intensity,
        Manufacturer,
        Sport,
        WorkoutStepDuration,
        WorkoutStepTarget,
    )

    errors, _ = wb.validate(workout, wb.RUN_TARGETS)
    if errors:
        raise ValueError("; ".join(e["message"] for e in errors))
    intensity = {"warmup": Intensity.WARMUP, "cooldown": Intensity.COOLDOWN, "recovery": Intensity.REST,
                 "work": Intensity.ACTIVE, "off": Intensity.REST}
    steps: list = []

    def timed(kind: str, block: dict) -> None:
        tg = block["target"]
        st = WorkoutStepMessage()
        st.message_index = len(steps)
        st.duration_type = WorkoutStepDuration.TIME
        st.duration_time = int(block["duration_s"])       # seconds; fit_tool applies the x1000 scale
        st.intensity = intensity[kind]
        fast, slow = tg.get("fast_s_per_km"), tg.get("slow_s_per_km")
        if tg["kind"] == "pace_pct_threshold" and fast and slow:
            st.target_type = WorkoutStepTarget.SPEED
            st.target_value = 0                             # 0 = custom range, not a zone
            st.custom_target_speed_low = round(1000 / slow, 3)
            st.custom_target_speed_high = round(1000 / fast, 3)
            st.workout_step_name = f"Z{tg['zone']} {sr.ZONE_NAME[tg['zone']]}"[:15]
        else:
            st.target_type = WorkoutStepTarget.OPEN
            st.workout_step_name = (tg.get("label") or f"Z{tg['zone']} {sr.ZONE_NAME[tg['zone']]}")[:15]
        st.notes = target_text(tg)[:50]
        steps.append(st)

    for s in workout["steps"]:
        if s["kind"] == "repeat":
            first = len(steps)
            timed("work", s["on"])
            timed("off", s["off"])
            rep = WorkoutStepMessage()
            rep.message_index = len(steps)
            rep.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
            rep.duration_step = first                       # go back to the rep's first step
            rep.target_repeat_steps = int(s["count"])       # total times through
            steps.append(rep)
        else:
            timed(s["kind"], s)

    b = FitFileBuilder()
    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value       # honest id for an unregistered app (see app.py)
    fid.product = 0
    fid.serial_number = 12345
    fid.time_created = int(clock.now().timestamp() * 1000)  # importers need it (see app._build_fit_workout)
    b.add(fid)
    wm = WorkoutMessage()
    wm.workout_name = workout["name"]
    wm.sport = Sport.RUNNING
    wm.num_valid_steps = len(steps)
    b.add(wm)
    for st in steps:
        b.add(st)
    return b.build().to_bytes()


@router.get("/api/run/sessions/{session_id}/download")
def run_session_download(session_id: str, minutes: int | None = Query(None),
                         format: str = Query("fit", pattern="^(fit|txt)$")):
    """The session as a Garmin-style structured run workout (.fit) or as plain text (.txt)."""
    t, m = _template(session_id, minutes)
    w = t.builder(_thresholds(), m)
    name = re.sub(r"[^\w.\-]", "_", f"{w['name']}_{m}min")
    if format == "txt":
        return Response(to_text(w, m), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.txt"'})
    try:
        data = to_fit(w)
    except ImportError:
        raise HTTPException(status_code=500, detail="fit_tool is not installed; download the text version")
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}.fit"'})
