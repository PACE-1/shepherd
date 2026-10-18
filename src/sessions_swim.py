"""Swim session library for the multi-sport plan (follow-on to #122; MASTER_DECISIONS ADDENDUM 5/6).

Registers five swim ``SessionTemplate``s with ``multisport_plan`` and retires ``placeholder-swim-easy``.
Pure: no I/O. ``multisport_plan`` imports this module automatically (``_load_libraries``).

Pace. The only pace a session uses is the rider's own saved CSS (``swim_css``, s/100 m): "at CSS" is the
CSS pace itself. No percentage zones are used or invented (none could be cited; see
swim_metrics.ZONES_NOTE and docs/ROADMAP.md). Easy swimming has no pace: it carries the effort label
"easy, relaxed" and is written in minutes. Sets are written in metres with rests in seconds; with a saved
CSS the builder turns each repeat into seconds from the CSS pace (distance x CSS / 100) and fits the
number of repeats to the session length, without one it gives the metres set under an effort label and a
fixed-size time budget, and says that times need a CSS.

Sources. CSS as a concept and its two-swim estimate: Wakayoshi et al. 1992 (Eur J Appl Physiol
64:153-157) and 1993 (Int J Sports Med 14(7):368-372), see swim_metrics. The SET SHAPES (repeats of
50-400 m at CSS with short rests, long repeats, short repeats at or faster than CSS) are common coaching
practice templates, not a validated protocol: the rests, the repeat counts, the warm-up and cool-down
shares are design choices of this library with no published dose-response behind them. NOT validated
against real recorded swims.

Pool. A 25 m pool is assumed (every distance here is a whole number of 25 m lengths); the open-water
case is not paced (swim_metrics notes GPS distance is rough in water).

Step shape (src/workout_builder.py): warmup / work / cooldown steps and one ``repeat`` step
({"count", "on", "off"}). Target kinds used: ``{"kind": "css", "pace_s_per_100m": s, "label": ...}`` (the
rider's CSS pace; present only when a CSS is saved) and ``{"kind": "effort", "label": ...}``.
workout_builder.validate does not know these two kinds yet; this module does not edit it.
"""
from __future__ import annotations

import multisport_plan as mp

POOL_M = 25
POOL_NOTE = ("A 25 m pool is assumed (every distance is a whole number of 25 m lengths). Open-water pacing "
             "is not given: distance and pace from GPS are rough in water.")
SOURCE = ("CSS: Wakayoshi et al. 1992 (Eur J Appl Physiol 64:153-157) and 1993 (Int J Sports Med "
          "14(7):368-372). The set shapes are common coaching practice templates, not a validated protocol.")
NO_CSS_NOTE = ("No swim CSS is saved, so these sets have no times: swim them at a comfortably hard, steady "
               "effort. Save a CSS test (400 m and 200 m, all-out) to get a time for every repeat.")
EASY = "easy, relaxed"
HARD_NO_CSS = "comfortably hard, steady (CSS effort)"
NO_FIT = "Plain text only: no FIT or watch file is made for swim sessions."

WARM_SHARE, COOL_SHARE = 0.25, 0.15      # of the session; design choices, not published values


def css_of(thresholds) -> float | None:
    """The rider's saved CSS in s/100 m from multisport.read_thresholds output, else None."""
    v = (thresholds or {}).get("swim_css")
    v = v.get("current") if isinstance(v, dict) else v
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def pace(s: float) -> str:
    """Seconds per 100 m as m:ss."""
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def _min(s: float) -> str:
    return f"{max(1, round(s / 60))} min"


def _effort(label: str) -> dict:
    return {"kind": "effort", "label": label}


def _step(kind: str, seconds: int, label: str, note: str = "") -> dict:
    return {"kind": kind, "duration_s": int(seconds), "target": _effort(label), "cadence_note": note}


def _wrap(name: str, lines: list[str], steps: list[dict], css: float | None) -> dict:
    return {"name": name, "description": "\n".join(lines), "steps": steps,
            "note": POOL_NOTE + ("" if css else " " + NO_CSS_NOTE)}


# ── easy sessions: minutes and an effort label, no pace ───────────────────────────────────────
def _easy_technique(th: dict, minutes: int) -> dict:
    total = minutes * 60
    warm = round(total * 0.2 / 60) * 60
    tech = round(total * 0.3 / 60) * 60
    cool = round(total * 0.1 / 60) * 60
    aerobic = total - warm - tech - cool
    steps = [_step("warmup", warm, EASY, "easy swimming, any stroke"),
             _step("work", tech, EASY, "technique: drills and short easy lengths, rest as needed"),
             _step("work", aerobic, EASY, "continuous easy swimming, steady and smooth"),
             _step("cooldown", cool, EASY, "easy, loosen off")]
    lines = [f"Warm-up {_min(warm)}: easy swimming, any stroke.",
             f"Technique {_min(tech)}: drills and short easy lengths of your choice, rest as needed.",
             f"Aerobic {_min(aerobic)}: continuous easy swimming, relaxed and smooth.",
             f"Cool-down {_min(cool)}: easy.",
             f"Effort: {EASY} throughout; you could talk between lengths."]
    return _wrap("Easy swim and technique", lines, steps, css_of(th))


def _recovery(th: dict, minutes: int) -> dict:
    steps = [_step("work", minutes * 60, EASY, "very easy, loose; stop early if tired")]
    lines = [f"{minutes} min of easy swimming, mixing strokes freely.",
             f"Effort: {EASY}; this is a recovery swim, keep it loose and stop early if you feel tired."]
    return _wrap("Recovery swim", lines, steps, css_of(th))


# ── CSS sets ───────────────────────────────────────────────────────────────────────────────────
def _css_set(th: dict, minutes: int, *, name: str, dist: int, rest: int, reps_max: int, reps_min: int,
             lo: int, hi: int, at_or_faster: bool = False, tail: str = "") -> dict:
    """Warm-up, ``reps`` x ``dist`` m with ``rest`` s, cool-down.

    With a CSS: reps = as many as fit after the warm-up and cool-down shares (capped at ``reps_max``, at
    least 1); the seconds left over go to the warm-up and cool-down, so the workout lasts exactly
    ``minutes``. Without: reps run from ``reps_min`` to ``reps_max`` across the template's minute range
    (``lo``..``hi``), and the main set gets the time the warm-up and cool-down leave.
    """
    css = css_of(th)
    total = minutes * 60
    warm, cool = round(total * WARM_SHARE / 60) * 60, round(total * COOL_SHARE / 60) * 60
    what = f"{dist} m"
    if css:
        rep_s = round(dist * css / 100)
        reps = max(1, min(reps_max, (total - warm - cool) // (rep_s + rest)))
        main = reps * (rep_s + rest)
        spare = total - warm - cool - main
        warm += spare * 6 // 10
        cool = max(60, total - warm - main)      # the floor is reached only by out-of-range minutes
        target = {"kind": "css", "pace_s_per_100m": css,
                  "label": "at CSS or faster" if at_or_faster else "at CSS"}
        where = f"at CSS ({pace(css)} per 100 m)" + (" or faster" if at_or_faster else "")
        note = f"{dist} m {where}"[:120]
        rep_line = (f"{reps} x {dist} m {where}, about {rep_s} s each at CSS pace, {rest} s rest")
        steps = [_step("warmup", warm, EASY, "easy swimming"),
                 {"kind": "repeat", "count": reps,
                  "on": {"duration_s": rep_s, "target": target, "cadence_note": note},
                  "off": {"duration_s": rest, "target": _effort("rest at the wall"), "cadence_note": f"{rest} s rest"}},
                 _step("cooldown", cool, EASY, "easy, loosen off")]
        extra = tail
    else:
        reps = round(reps_min + (reps_max - reps_min) * (minutes - lo) / max(1, hi - lo))
        main = total - warm - cool
        label = HARD_NO_CSS + (", or a little faster" if at_or_faster else "")
        rep_line = f"{reps} x {dist} m, {rest} s rest, effort {label}"
        steps = [_step("warmup", warm, EASY, "easy swimming"),
                 _step("work", main, label, f"{reps} x {dist} m, {rest} s rest"),
                 _step("cooldown", cool, EASY, "easy, loosen off")]
        extra = ""
    lines = [f"Warm-up {_min(warm)}: {EASY} swimming.", f"Main set: {rep_line}.",
             f"Cool-down {_min(cool)}: easy."]
    if extra:
        lines.append(extra)
    w = _wrap(name, lines, steps, css)
    w["sets"] = {"reps": reps, "distance_m": dist, "rest_s": rest}
    return w


def _css_endurance(th: dict, minutes: int) -> dict:
    css = css_of(th)
    w = _css_set(th, minutes, name="CSS endurance", dist=400, rest=30, reps_max=6, reps_min=3, lo=40, hi=70)
    if css:
        total_m = w["sets"]["reps"] * 400
        w["description"] += (f"\nOr swim the same {total_m} m as one continuous swim at CSS, "
                             f"about {_min(total_m * css / 100)}.")
    return w


def _css_intervals(th: dict, minutes: int) -> dict:
    return _css_set(th, minutes, name="CSS intervals", dist=100 if minutes <= 50 else 200,
                    rest=15 if minutes <= 50 else 20, reps_max=20, reps_min=8, lo=40, hi=70)


def _threshold_plus(th: dict, minutes: int) -> dict:
    return _css_set(th, minutes, name="Threshold-plus short repeats", dist=50, rest=15, reps_max=24, reps_min=10,
                    lo=35, hi=55, at_or_faster=True,
                    tail="Hold the same pace on every repeat; the time per repeat above is for CSS pace, so "
                         "repeats at a faster pace finish early and leave a little more rest.")


def _template(tid, kind, session_type, intent, minutes, hard, builder) -> mp.SessionTemplate:
    return mp.register(mp.SessionTemplate(id=tid, sport="swimming", kind=kind, session_type=session_type,
                                          intent=intent, minutes=minutes, hard=hard, builder=builder,
                                          source=SOURCE))


_template("swim-easy-technique", "easy", "swim_endurance",
          "Easy aerobic swim with a technique block, in an easy, relaxed effort.", (30, 60), False, _easy_technique)
_template("swim-recovery", "recovery", "swim_endurance",
          "Short, loose recovery swim.", (20, 40), False, _recovery)
_template("swim-css-endurance", "endurance", "swim_endurance",
          "Long repeats at CSS pace with short rests.", (40, 70), True, _css_endurance)
_template("swim-css-intervals", "css", "swim_css",
          "Repeats of 100-200 m at CSS pace with short rests.", (40, 70), True, _css_intervals)
_template("swim-threshold-plus", "threshold", "swim_css",
          "Short repeats at CSS pace or a little faster, short rests.", (35, 55), True, _threshold_plus)
mp.unregister("placeholder-swim-easy")


# ── text for the screen and the download ───────────────────────────────────────────────────────
def typical_minutes(t: mp.SessionTemplate) -> int:
    """The midpoint of the template's range, in whole 5-minute steps."""
    return int(round((t.minutes[0] + t.minutes[1]) / 2 / 5)) * 5


def library() -> list[mp.SessionTemplate]:
    return [t for t in mp.templates_for("swimming") if t.id.startswith("swim-")]


def session_text(t: mp.SessionTemplate, thresholds: dict, minutes: int | None = None) -> str:
    """The session as plain text (what the download serves)."""
    m = minutes or typical_minutes(t)
    w = t.builder(thresholds, m)
    css = css_of(thresholds)
    head = [f"{w['name']} ({m} min, {'hard' if t.hard else 'easy'})", t.intent,
            f"Your CSS: {pace(css)} per 100 m" if css else "Your CSS: not saved", ""]
    return "\n".join(head + w["description"].split("\n") + ["", w["note"], SOURCE,
                                                           "Not validated against real recorded swims.", NO_FIT]) + "\n"
