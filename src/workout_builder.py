"""Structured-workout model for the workout builder (#110, cycling slice).

Pure: no I/O, no app state. A workout is a plain JSON-able dict::

    {"name": str, "description": str, "steps": [Step, ...]}

    Step (kind "warmup" | "work" | "recovery" | "cooldown"):
        {"kind", "duration_s", "target", "cadence_note"}
    Step (kind "repeat"):
        {"kind": "repeat", "count", "on": Block, "off": Block}
        Block = {"duration_s", "target", "cadence_note"}

    target = {"kind": "power", "lo": %FTP, "hi": %FTP}
           | {"kind": "hr",    "lo": %LTHR, "hi": %LTHR}

``target`` is a tagged dict so pace (run/swim, #109) can join later without
reshaping a step; any other kind is rejected for now ("not_supported_yet").

How a step becomes ZWO (the library's format; the existing parsers read it):
  * warmup  -> <Warmup>, ramp lo -> hi
  * cooldown-> <Cooldown>, ramp hi -> lo (a cool-down ramps down)
  * work / recovery -> <SteadyState> at the MIDPOINT of lo..hi (ZWO has no
    range; the range is the rider's tolerance, the midpoint is what a head
    unit is told to hold)
  * repeat  -> <IntervalsT>, on/off each at their midpoint

HR targets: the library is power-canonical (an HR-only rider gets bpm from
hr_targets.power_target_to_hr at export time), so an HR target is stored as
%LTHR and written to ZWO as the %FTP that hr_targets maps to that %LTHR.
The mapping is hr_targets' own Coggan dual table (%FTP zone tops 55/75/90/105
<-> %LTHR tops 68/83/94/105), interpolated piecewise-linearly between those
tops exactly as hr_targets does for ramps -- i.e. its inverse. Below the Z1
top it is flat 55 %FTP. Confidence: moderate (Coggan's table is a population
guide, zones are bands, HR lags ~30 s: steps under hr_targets.HR_MIN_SEG_S
get a warning). No coefficient here is new.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import hr_targets
from structure_fidelity import parse_zwo_text

STEP_KINDS = ("warmup", "work", "recovery", "cooldown")
MAX_STEPS = 60                      # top-level steps (a repeat counts as one)
MAX_REPEATS = 99
MAX_STEP_S = 6 * 3600
MAX_TOTAL_S = 12 * 3600
POWER_MIN, POWER_MAX = 10, 300      # % FTP
HR_MIN, HR_MAX = 50, 105            # % LTHR: Coggan L1-L4, the HR-guidable band
MAX_NAME, MAX_DESC, MAX_NOTE = 80, 500, 120
# Target kinds each sport's workouts may use. validate() defaults to the cycling set, so the builder's
# routes and to_zwo never see a running target.
CYCLING_TARGETS = ("power", "hr")
# Running (#120, src/sessions_run.py): pace as % of threshold pace (time per km, Friel's convention in
# run_metrics, so a lower % is faster): lo = the fast end, hi = the slow end; either may be None for
# Friel's open-ended zones (Z1 has no slow bound, Z5c no fast bound). effort = a text cue only.
RUN_TARGETS = ("pace_pct_threshold", "effort")
PACE_PCT_MIN, PACE_PCT_MAX = 50, 200    # input sanity limits, not physiology

# (lthr %, ftp %) anchors: hr_targets' zone tops, from its own table.
_HR_ANCHORS = [(row[3] * 100.0, row[1]) for row in hr_targets._HR_ROWS]


def hr_to_ftp_pct(lthr_pct: float) -> float:
    """%LTHR -> the %FTP hr_targets maps to it (see module docstring)."""
    if lthr_pct <= _HR_ANCHORS[0][0]:
        return _HR_ANCHORS[0][1]
    for (x1, y1), (x2, y2) in zip(_HR_ANCHORS, _HR_ANCHORS[1:]):
        if lthr_pct <= x2:
            return y1 + (y2 - y1) * (lthr_pct - x1) / (x2 - x1)
    return _HR_ANCHORS[-1][1]


# ── validation ───────────────────────────────────────────────────────────────

def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v and abs(v) != float("inf") else None


def _check_run_target(t: dict, path: str, errors: list) -> None:
    if t.get("kind") == "effort":
        label = t.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > MAX_NOTE:
            errors.append({"path": path + ".label", "message": f"An effort target needs a label of at most {MAX_NOTE} characters."})
        return
    given = [v for v in (t.get("lo"), t.get("hi")) if v is not None]
    nums = [n for n in (_num(v) for v in given) if n is not None]
    if not given or len(nums) != len(given):
        errors.append({"path": path, "message": "A pace target needs a fast end, a slow end or both (% of threshold pace)."})
    elif not all(PACE_PCT_MIN <= v <= PACE_PCT_MAX for v in nums):
        errors.append({"path": path, "message": f"A pace target must be between {PACE_PCT_MIN} and {PACE_PCT_MAX} % of threshold pace."})
    elif len(nums) == 2 and nums[0] > nums[1]:
        errors.append({"path": path, "message": "The fast end of a pace target is slower than its slow end."})


def _check_target(t, path: str, dur_s, errors: list, warnings: list, kinds=CYCLING_TARGETS) -> None:
    if not isinstance(t, dict):
        errors.append({"path": path, "message": "A target is required."})
        return
    kind = t.get("kind")
    if kinds != CYCLING_TARGETS:
        if kind in kinds and kind in RUN_TARGETS:
            _check_run_target(t, path, errors)
        else:
            errors.append({"path": path + ".kind", "message": f"Target '{kind}' is not supported for this sport."})
        return
    if kind == "power":
        lo_b, hi_b, unit = POWER_MIN, POWER_MAX, "% FTP"
    elif kind == "hr":
        lo_b, hi_b, unit = HR_MIN, HR_MAX, "% LTHR"
    else:
        errors.append({"path": path + ".kind", "message": f"Target '{kind}' is not supported yet (power or heart rate only)."})
        return
    lo, hi = _num(t.get("lo")), _num(t.get("hi"))
    if lo is None or hi is None:
        errors.append({"path": path, "message": "Target needs a low and a high number."})
        return
    if not (lo_b <= lo <= hi_b and lo_b <= hi <= hi_b):
        errors.append({"path": path, "message": f"Target must be between {lo_b} and {hi_b} {unit}."})
    elif lo > hi:
        errors.append({"path": path, "message": "Target low is above its high."})
    elif kind == "hr" and dur_s is not None and dur_s < hr_targets.HR_MIN_SEG_S:
        warnings.append(f"{path}: heart rate lags about 30 s, so a heart-rate target on a step "
                        f"under {hr_targets.HR_MIN_SEG_S} s is hard to hit; consider power.")


def _check_block(b, path: str, errors: list, warnings: list, kinds=CYCLING_TARGETS) -> float:
    """Validate one timed block; return its seconds (0 when invalid)."""
    if not isinstance(b, dict):
        errors.append({"path": path, "message": "Step is missing."})
        return 0
    d = _num(b.get("duration_s"))
    if d is None or d != int(d) or d <= 0:
        errors.append({"path": path + ".duration_s", "message": "Duration must be a positive whole number of seconds."})
        d = None
    elif d > MAX_STEP_S:
        errors.append({"path": path + ".duration_s", "message": f"A step can be at most {MAX_STEP_S // 3600} hours."})
        d = None
    _check_target(b.get("target"), path + ".target", d, errors, warnings, kinds)
    note = b.get("cadence_note", "")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        errors.append({"path": path + ".cadence_note", "message": f"Cadence note must be text of at most {MAX_NOTE} characters."})
    return d or 0


def validate(workout, kinds=CYCLING_TARGETS) -> "tuple[list[dict], list[str]]":
    """(errors, warnings). errors = [{"path", "message"}]; empty means exportable.
    ``kinds``: the target kinds allowed (CYCLING_TARGETS, the default, or RUN_TARGETS)."""
    errors: list = []
    warnings: list = []
    if not isinstance(workout, dict):
        return [{"path": "", "message": "Workout must be an object."}], warnings
    name = workout.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append({"path": "name", "message": "Give the workout a name."})
    elif len(name.strip()) > MAX_NAME:
        errors.append({"path": "name", "message": f"Name can be at most {MAX_NAME} characters."})
    desc = workout.get("description", "")
    if desc is not None and (not isinstance(desc, str) or len(desc) > MAX_DESC):
        errors.append({"path": "description", "message": f"Description can be at most {MAX_DESC} characters."})
    steps = workout.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append({"path": "steps", "message": "Add at least one step."})
        return errors, warnings
    if len(steps) > MAX_STEPS:
        errors.append({"path": "steps", "message": f"At most {MAX_STEPS} steps."})
        return errors, warnings
    total = 0.0
    for i, s in enumerate(steps):
        p = f"steps[{i}]"
        if not isinstance(s, dict):
            errors.append({"path": p, "message": "Step must be an object."})
            continue
        kind = s.get("kind")
        if kind in STEP_KINDS:
            total += _check_block(s, p, errors, warnings, kinds)
        elif kind == "repeat":
            c = _num(s.get("count"))
            if c is None or c != int(c) or not 1 <= c <= MAX_REPEATS:
                errors.append({"path": p + ".count", "message": f"Repeats must be a whole number from 1 to {MAX_REPEATS}."})
                c = 0
            on = _check_block(s.get("on"), p + ".on", errors, warnings, kinds)
            off = _check_block(s.get("off"), p + ".off", errors, warnings, kinds)
            total += c * (on + off)
        else:
            errors.append({"path": p + ".kind", "message": f"Unknown step type '{kind}'."})
    if total > MAX_TOTAL_S:
        errors.append({"path": "steps", "message": f"The workout can be at most {MAX_TOTAL_S // 3600} hours long."})
    return errors, warnings


def total_seconds(workout: dict) -> int:
    """Planned duration. Assumes a validated workout."""
    t = 0
    for s in workout["steps"]:
        if s["kind"] == "repeat":
            t += int(s["count"]) * (int(s["on"]["duration_s"]) + int(s["off"]["duration_s"]))
        else:
            t += int(s["duration_s"])
    return t


# ── export ───────────────────────────────────────────────────────────────────

def _ftp_frac(target: dict, which: str) -> float:
    """A target end as a ZWO power fraction (1.0 = 100 % FTP)."""
    v = float(target[which])
    pct = hr_to_ftp_pct(v) if target["kind"] == "hr" else v
    return round(pct / 100.0, 3)


def _mid(target: dict) -> float:
    return round((_ftp_frac(target, "lo") + _ftp_frac(target, "hi")) / 2.0, 3)


def _note(el: ET.Element, block: dict) -> None:
    note = (block.get("cadence_note") or "").strip()
    if note:
        ET.SubElement(el, "textevent", timeoffset="0", message=note)


def to_zwo(workout: dict) -> str:
    """Render a VALID workout as ZWO XML (raises ValueError if it is not)."""
    errors, _ = validate(workout)
    if errors:
        raise ValueError("; ".join(e["message"] for e in errors))
    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "Shepherd (builder)"
    ET.SubElement(root, "name").text = workout["name"].strip()
    ET.SubElement(root, "description").text = (workout.get("description") or "").strip()
    ET.SubElement(root, "sportType").text = "bike"
    tags = ET.SubElement(root, "tags")
    ET.SubElement(tags, "tag", name="builder")
    w = ET.SubElement(root, "workout")
    for s in workout["steps"]:
        k, t = s["kind"], s.get("target")
        if k == "warmup":
            el = ET.SubElement(w, "Warmup", Duration=str(int(s["duration_s"])),
                               PowerLow=f"{_ftp_frac(t, 'lo')}", PowerHigh=f"{_ftp_frac(t, 'hi')}")
        elif k == "cooldown":
            el = ET.SubElement(w, "Cooldown", Duration=str(int(s["duration_s"])),
                               PowerLow=f"{_ftp_frac(t, 'hi')}", PowerHigh=f"{_ftp_frac(t, 'lo')}")
        elif k == "repeat":
            on, off = s["on"], s["off"]
            el = ET.SubElement(w, "IntervalsT", Repeat=str(int(s["count"])),
                               OnDuration=str(int(on["duration_s"])), OffDuration=str(int(off["duration_s"])),
                               OnPower=f"{_mid(on['target'])}", OffPower=f"{_mid(off['target'])}")
            s = on
        else:
            el = ET.SubElement(w, "SteadyState", Duration=str(int(s["duration_s"])), Power=f"{_mid(t)}")
        _note(el, s)
    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def intensity_profile(zwo_text: str) -> "list[dict]":
    """[{x: minutes, y: %FTP}] for the intensity chart, from the library's own
    ZWO parser: each segment contributes its start and end point."""
    pts: list = []
    for seg in parse_zwo_text(zwo_text):
        if seg["lo"] is None:
            continue
        pts.append({"x": round(seg["start_s"] / 60, 3), "y": round(seg["lo"] * 100, 1)})
        pts.append({"x": round((seg["start_s"] + seg["dur_s"]) / 60, 3), "y": round(seg["hi"] * 100, 1)})
    return pts
