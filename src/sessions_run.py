"""Run session library (#120): the running templates the companion planner (multisport_plan) places and
the Library's run workouts screen lists.

DESIGN TEMPLATES, NOT VALIDATED: the structures follow the guidelines Jack Daniels states in Daniels'
Running Formula, 3rd ed. (Human Kinetics, 2014); none has been checked against real recorded runs.
Figures marked "verify" are Daniels' guidelines as recalled here and should be checked against the book.

Daniels' intensity categories and the guidelines used (Daniels 3rd ed., chapter on training types):
  E  easy running, conversational. The long run (L) is E running; Daniels caps it at the lesser of about
     25 % of the week's running and 150 minutes (2.5 h). Only the 150-minute cap is implemented (the
     template's longest duration): a template does not know the week's running total ("verify" the 25 %).
  M  marathon pace. No template here (the brief's list has no M session).
  T  threshold, "comfortably hard": a steady tempo run of about 20 minutes, or cruise intervals of about
     5 to 15 minutes with a short rest, about 1 minute per 5 minutes of running ("verify" the 1:5).
  I  interval pace: hard reps of about 3 to 5 minutes with a jog recovery of equal or slightly shorter
     time.
  R  repetition pace; strides are short, light, fast runs of about 20 to 30 seconds with full recovery
     ("verify" the stride length and the 1-minute recovery used here).

Targets: % of the rider's threshold pace in Joe Friel's pace zones (run_metrics.FRIEL_PACE, reused, not
copied). Placing Daniels' categories in Friel's zones is Shepherd's mapping, made by matching Daniels'
descriptions to Friel's zone names; it is in neither source ("verify"):
  recovery jog -> Z1 Recovery, E/L -> Z2 Aerobic, T -> Z4 Sub-threshold, I -> Z5b Aerobic capacity,
  R (strides) -> Z5c Anaerobic capacity.
Without a saved threshold pace every target is an effort label instead (never an invented pace). Hill
repeats are always by effort: a pace target means little uphill.

Warm-up and cool-down lengths (at least 10 minutes of easy running each), rep counts and the duration
ranges below are Shepherd's structural choices, not figures from Daniels. ``rtss_estimate`` uses
run_metrics.rtss at the template's intended zone (an estimate, not a measured load).
"""
from __future__ import annotations

from dataclasses import dataclass

import run_metrics as rm
from multisport_plan import SessionTemplate, register, unregister

SOURCE = "Daniels J. Daniels' Running Formula, 3rd ed. Human Kinetics, 2014 (training intensities E/T/I/R)."
NOT_VALIDATED = "Design templates after Daniels; not validated against recorded runs."
LONG_RUN_CAP_MIN = 150      # Daniels: long run at most about 2.5 h (and about 25 % of weekly running: not implemented)

# Friel zone id -> (slow %, fast %) of threshold pace, None = open-ended; and its name.
ZONES = {z: (slow, fast) for z, _name, slow, fast in rm.FRIEL_PACE}
ZONE_NAME = {z: name for z, name, _slow, _fast in rm.FRIEL_PACE}
# Effort cues when no threshold pace is saved (Daniels' own descriptions where he gives one).
EFFORT = {"1": "very easy jog", "2": "easy, conversational", "4": "comfortably hard",
          "5b": "hard, about 3 to 5 km race effort", "5c": "fast but relaxed, not a sprint"}
HILL_EFFORT = "hard uphill effort, about 3 to 5 km race effort"


@dataclass(frozen=True)
class RunTemplate(SessionTemplate):
    """A SessionTemplate plus how the run library classifies it. ``stimulus`` is the training stimulus
    (recovery | aerobic | threshold | vo2max | speed), ``daniels`` the Daniels category (E | T | I | R)."""
    stimulus: str = ""
    daniels: str = ""


def threshold_pace(thresholds: dict | None) -> float | None:
    """The rider's current run threshold pace (s/km) from multisport.read_thresholds output, else None."""
    v = ((thresholds or {}).get("run_threshold_pace") or {}).get("current")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def target(zone: str, pace: float | None, effort: str | None = None) -> dict:
    """A step target for Friel zone ``zone``: % of threshold pace when ``pace`` is known (with the s/km it
    gives), else an effort label. ``effort`` forces an effort target (hills). ``zone`` rides along so the
    load estimate and the chart know the intended intensity either way."""
    if pace is None or effort is not None:
        return {"kind": "effort", "label": effort or EFFORT[zone], "zone": zone}
    slow, fast = ZONES[zone]
    at = (lambda pct: round(pace * pct / 100, 1) if pct is not None else None)
    return {"kind": "pace_pct_threshold", "lo": fast, "hi": slow, "zone": zone,
            "fast_s_per_km": at(fast), "slow_s_per_km": at(slow)}


def _step(kind: str, minutes: float, tgt: dict, note: str = "") -> dict:
    return {"kind": kind, "duration_s": round(minutes * 60), "target": tgt, "cadence_note": note}


def _repeat(count: int, on_s: int, on: dict, off_s: int, off: dict, note: str = "") -> dict:
    return {"kind": "repeat", "count": count,
            "on": {"duration_s": on_s, "target": on, "cadence_note": note},
            "off": {"duration_s": off_s, "target": off, "cadence_note": ""}}


def _with_wu_cd(name: str, desc: str, minutes: int, pace, main: list[dict], main_s: int) -> dict:
    """Easy warm-up and cool-down around ``main`` so the whole workout is exactly ``minutes`` long."""
    rest = minutes * 60 - main_s
    wu = (rest + 60) // 120 * 60          # whole minutes, the warm-up gets the odd one
    steps = [_step("warmup", wu / 60, target("2", pace)), *main, _step("cooldown", (rest - wu) / 60, target("2", pace))]
    return {"name": name, "description": desc, "steps": steps}


# ── builders: builder(thresholds, minutes) -> workout dict (workout_builder shape) ─────────────────────
def _easy(th: dict, m: int) -> dict:
    return {"name": "Easy run", "description": "Daniels E running: easy and conversational.",
            "steps": [_step("work", m, target("2", threshold_pace(th)))]}


def _long(th: dict, m: int) -> dict:
    return {"name": "Long run", "description": "Daniels L run at E pace; capped at 2.5 h.",
            "steps": [_step("work", m, target("2", threshold_pace(th)))]}


def _recovery(th: dict, m: int) -> dict:
    return {"name": "Recovery run", "description": "A short, very easy jog.",
            "steps": [_step("work", m, target("1", threshold_pace(th)))]}


def _strides(th: dict, m: int) -> dict:
    p = threshold_pace(th)
    reps, on_s, off_s = 6, 20, 60     # 6 x 20 s strides, 1 min easy jog between (verify against Daniels)
    block = reps * (on_s + off_s)
    return {"name": "Easy run with strides",
            "description": "E running, then strides: light, quick, relaxed (Daniels R), not sprints.",
            "steps": [_step("work", (m * 60 - block) / 60, target("2", p)),
                      _repeat(reps, on_s, target("5c", p), off_s, target("1", p), "relaxed, quick turnover")]}


def _tempo(th: dict, m: int) -> dict:
    p = threshold_pace(th)
    return _with_wu_cd("Tempo run", "Daniels T: 20 minutes steady at threshold, comfortably hard.", m, p,
                       [_step("work", 20, target("4", p))], 20 * 60)


def _cruise(th: dict, m: int) -> dict:
    p = threshold_pace(th)
    on, off = 10 * 60, 2 * 60          # 10-minute T reps, 1 minute rest per 5 minutes of running
    count = max(2, min(4, (m * 60 - 20 * 60) // (on + off)))
    return _with_wu_cd("Cruise intervals", "Daniels T cruise intervals: threshold reps with a short rest.", m, p,
                       [_repeat(count, on, target("4", p), off, target("1", p))], count * (on + off))


def _intervals(th: dict, m: int) -> dict:
    p = threshold_pace(th)
    on = off = 4 * 60                  # 4-minute I reps, equal-time jog recovery
    count = max(3, min(5, (m * 60 - 20 * 60) // (on + off)))
    return _with_wu_cd("Interval reps", "Daniels I: hard reps of about 4 minutes with an equal jog recovery.", m, p,
                       [_repeat(count, on, target("5b", p), off, target("1", p))], count * (on + off))


def _hills(th: dict, m: int) -> dict:
    p = threshold_pace(th)
    on = off = 3 * 60                  # 3 minutes uphill at I effort, jog down (verify: structure is I reps on a hill)
    count = max(4, min(6, (m * 60 - 20 * 60) // (on + off)))
    return _with_wu_cd("Hill repeats", "I-effort reps uphill by feel, easy jog back down.", m, p,
                       [_repeat(count, on, target("5b", p, HILL_EFFORT), off, target("1", p))], count * (on + off))


TEMPLATES = (
    RunTemplate(id="run-easy", sport="running", kind="easy", session_type="run_easy",
                intent="Easy aerobic run at a conversational effort (Daniels E).", minutes=(30, 60), hard=False,
                builder=_easy, source=SOURCE, stimulus="aerobic", daniels="E"),
    RunTemplate(id="run-long", sport="running", kind="long", session_type="run_long",
                intent="Long run at easy pace, at most 2.5 h (Daniels L).", minutes=(60, LONG_RUN_CAP_MIN),
                hard=False, builder=_long, source=SOURCE, stimulus="aerobic", daniels="E"),
    RunTemplate(id="run-recovery", sport="running", kind="recovery", session_type="run_easy",
                intent="Short, very easy recovery jog.", minutes=(20, 40), hard=False,
                builder=_recovery, source=SOURCE, stimulus="recovery", daniels="E"),
    RunTemplate(id="run-strides", sport="running", kind="strides", session_type="run_easy",
                intent="Easy run finishing with 6 relaxed 20-second strides (Daniels R).", minutes=(30, 50),
                hard=False, builder=_strides, source=SOURCE, stimulus="speed", daniels="R"),
    RunTemplate(id="run-tempo", sport="running", kind="tempo", session_type="run_tempo",
                intent="20 minutes steady at threshold, comfortably hard (Daniels T).", minutes=(40, 60),
                hard=True, builder=_tempo, source=SOURCE, stimulus="threshold", daniels="T"),
    RunTemplate(id="run-cruise", sport="running", kind="cruise", session_type="run_tempo",
                intent="Cruise intervals: 10-minute threshold reps with 2 minutes easy (Daniels T).",
                minutes=(45, 70), hard=True, builder=_cruise, source=SOURCE, stimulus="threshold", daniels="T"),
    RunTemplate(id="run-intervals", sport="running", kind="intervals", session_type="run_intervals",
                intent="Hard 4-minute reps with equal jog recoveries (Daniels I).", minutes=(45, 60),
                hard=True, builder=_intervals, source=SOURCE, stimulus="vo2max", daniels="I"),
    RunTemplate(id="run-hills", sport="running", kind="hills", session_type="run_intervals",
                intent="3-minute uphill reps at I effort, jog back down.", minutes=(45, 60),
                hard=True, builder=_hills, source=SOURCE, stimulus="vo2max", daniels="I"),
)


# ── load and chart from the intended zones ─────────────────────────────────────────────────────────────
def zone_pct(zone: str) -> float:
    """The intended % of threshold pace of a Friel zone: the middle of its bounds, or its one published bound
    for an open-ended zone (Z1 then reads as its fast edge, Z5c as its slow edge: a conservative choice)."""
    bounds = [v for v in ZONES[zone] if v is not None]
    return sum(bounds) / len(bounds)


def _segments(workout: dict) -> list[tuple[int, str]]:
    out = []
    for s in workout["steps"]:
        if s["kind"] == "repeat":
            out += [(s["on"]["duration_s"], s["on"]["target"]["zone"]),
                    (s["off"]["duration_s"], s["off"]["target"]["zone"])] * int(s["count"])
        else:
            out.append((s["duration_s"], s["target"]["zone"]))
    return out


def rtss_estimate(workout: dict) -> float:
    """rTSS (run_metrics.rtss, hours x IF^2 x 100) of a library workout run exactly at each step's intended
    zone. IF = threshold pace / pace = 100 / zone %, so it needs no saved threshold. An estimate only."""
    return round(sum(rm.rtss(d, 100 / zone_pct(z), 1.0) or 0 for d, z in _segments(workout)), 1)


def profile(workout: dict) -> list[dict]:
    """[{x: minutes, y: % of threshold speed}] for the intensity chart: each step flat at its intended zone."""
    pts, t = [], 0
    for d, z in _segments(workout):
        y = round(10000 / zone_pct(z), 1)
        pts += [{"x": round(t / 60, 3), "y": y}, {"x": round((t + d) / 60, 3), "y": y}]
        t += d
    return pts


unregister("placeholder-run-easy")
for _t in TEMPLATES:
    register(_t)
