"""Swim session library (src/sessions_swim.py): every template builds with and without a CSS, the set metres
add up, durations stay in range, and the overlay engine can place the templates."""
import json
import re
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import sessions_swim as ss
import training_planner as tp
import workout_builder as wb

LIB = ss.library()
CSS_VALUES = (70.0, 90.0, 120.0, 180.0)
TODAY = date(2026, 9, 14)                       # a Monday


def _th(css):
    return {"swim_css": {"current": css}} if css else {}


def _cases():
    for t in LIB:
        for m in sorted({t.minutes[0], ss.typical_minutes(t), t.minutes[1]}):
            yield t, m


def _main_set(w):
    """(reps, distance_m) from the set line, e.g. 'Main set: 9 x 200 m at CSS ...'."""
    m = re.search(r"Main set: (\d+) x (\d+) m", w["description"])
    return int(m.group(1)), int(m.group(2))


def test_library_has_the_five_templates_and_the_placeholder_is_retired():
    assert [t.id for t in LIB] == ["swim-easy-technique", "swim-recovery", "swim-css-endurance",
                                   "swim-css-intervals", "swim-threshold-plus"]
    assert "placeholder-swim-easy" not in {t.id for t in mp.templates_for("swimming")}
    assert {t.id for t in LIB} <= {t.id for t in mp.templates_for("swimming")}
    assert {t.id: t.hard for t in LIB} == {"swim-easy-technique": False, "swim-recovery": False,
                                           "swim-css-endurance": True, "swim-css-intervals": True,
                                           "swim-threshold-plus": True}
    assert {t.session_type for t in LIB} <= {"swim_endurance", "swim_css"}
    for t in LIB:
        assert "Wakayoshi" in t.source and "not a validated protocol" in t.source


@pytest.mark.parametrize("css", [None, *CSS_VALUES])
def test_every_template_builds_with_and_without_css_and_lasts_the_asked_minutes(css):
    for t, m in _cases():
        w = t.builder(_th(css), m)
        assert w["name"] and len(w["name"]) <= wb.MAX_NAME and 0 < len(w["description"]) <= wb.MAX_DESC
        json.dumps(w)
        assert w["steps"] and "25 m" in w["note"]
        total = 0
        for s in w["steps"]:
            blocks = [s["on"], s["off"]] if s["kind"] == "repeat" else [s]
            for b in blocks:
                assert b["duration_s"] > 0 and b["duration_s"] == int(b["duration_s"])
                assert len(b["cadence_note"]) <= wb.MAX_NOTE
                tg = b["target"]
                assert tg["kind"] in ("css", "effort") and tg["label"]
                if tg["kind"] == "css":
                    assert css and tg["pace_s_per_100m"] == css
        total = wb.total_seconds(w)
        assert total == m * 60, (t.id, css, m, total)          # durations in range: exactly the asked minutes
        assert t.minutes[0] <= total / 60 <= t.minutes[1]


@pytest.mark.parametrize("css", [None, 90.0])
def test_easy_sessions_never_carry_a_pace(css):
    for t, m in _cases():
        if t.hard:
            continue
        w = t.builder(_th(css), m)
        kinds = {(b["target"]["kind"], b["target"]["label"]) for s in w["steps"] for b in [s]}
        assert kinds == {("effort", "easy, relaxed")}
        assert "CSS" not in w["description"]


@pytest.mark.parametrize("css", CSS_VALUES)
def test_set_metres_add_up_and_each_repeat_is_distance_times_css(css):
    for t, m in _cases():
        if not t.hard:
            continue
        w = t.builder(_th(css), m)
        reps, dist = _main_set(w)
        rep = next(s for s in w["steps"] if s["kind"] == "repeat")
        assert rep["count"] == reps and w["sets"] == {"reps": reps, "distance_m": dist, "rest_s": rep["off"]["duration_s"]}
        assert rep["on"]["duration_s"] == round(dist * css / 100)
        assert dist % ss.POOL_M == 0 and (reps * dist) % ss.POOL_M == 0
        assert f"{rep['off']['duration_s']} s rest" in w["description"]
        assert rep["on"]["target"]["pace_s_per_100m"] == css
        assert f"{reps} x {dist} m" in rep["on"]["cadence_note"] or f"{dist} m" in rep["on"]["cadence_note"]
        # the repeats are the main set; warm-up and cool-down are easy minutes around it
        assert [s["kind"] for s in w["steps"]] == ["warmup", "repeat", "cooldown"]
        assert wb.total_seconds(w) - reps * (rep["on"]["duration_s"] + rep["off"]["duration_s"]) > 0


def test_reference_session_worked_by_hand():
    # CSS 1:30 per 100 m = 90 s. 55 min CSS intervals: warm-up round(13.75) = 14 min, cool-down round(8.25) = 8 min,
    # main budget 33 min = 1980 s; a 200 m repeat is 180 s + 20 s rest = 200 s -> 9 repeats (1800 s), 180 s spare
    # goes 60/40 to warm-up / cool-down, so the session is exactly 3300 s.
    t = next(t for t in LIB if t.id == "swim-css-intervals")
    w = t.builder(_th(90.0), 55)
    warm, rep, cool = w["steps"]
    assert (rep["count"], rep["on"]["duration_s"], rep["off"]["duration_s"]) == (9, 180, 20)
    assert warm["duration_s"] == 14 * 60 + 108 and cool["duration_s"] == 8 * 60 + 72
    assert wb.total_seconds(w) == 3300
    assert "9 x 200 m at CSS (1:30 per 100 m)" in w["description"] and "20 s rest" in w["description"]
    # a shorter session uses 100 m repeats with 15 s rest
    w40 = t.builder(_th(90.0), 40)
    assert _main_set(w40)[1] == 100 and w40["sets"]["rest_s"] == 15


def test_css_endurance_offers_the_same_metres_as_one_continuous_swim():
    t = next(t for t in LIB if t.id == "swim-css-endurance")
    w = t.builder(_th(100.0), 55)
    reps, dist = _main_set(w)
    assert dist == 400 and "30 s rest" in w["description"]
    assert f"the same {reps * 400} m as one continuous swim at CSS" in w["description"]


def test_threshold_plus_is_at_css_or_faster_and_says_the_time_is_a_ceiling():
    t = next(t for t in LIB if t.id == "swim-threshold-plus")
    w = t.builder(_th(90.0), 45)
    assert _main_set(w)[1] == 50 and "or faster" in w["description"]
    assert next(s for s in w["steps"] if s["kind"] == "repeat")["on"]["target"]["label"] == "at CSS or faster"


def test_without_css_the_hard_sessions_are_effort_labelled_metres_sets_with_a_note():
    for t, m in _cases():
        if not t.hard:
            continue
        w = t.builder({}, m)
        assert {b["target"]["kind"] for b in w["steps"]} == {"effort"}
        reps, dist = _main_set(w)
        assert reps >= 1 and dist % ss.POOL_M == 0
        assert "effort" in w["description"] and "CSS" in w["note"] and "no times" in w["note"]
        assert not re.search(r"\d:\d\d", w["description"])          # no pace appears without a CSS
    # repeats grow with the session length, from the template's own range
    t = next(t for t in LIB if t.id == "swim-css-intervals")
    assert _main_set(t.builder({}, 40))[0] < _main_set(t.builder({}, 50))[0]


def test_thresholds_shapes_and_bad_values():
    assert ss.css_of({"swim_css": {"current": 95.0}}) == 95.0 and ss.css_of({"swim_css": 95}) == 95.0
    for bad in (None, {}, {"swim_css": {"current": None}}, {"swim_css": True}, {"swim_css": {"current": 0}}):
        assert ss.css_of(bad) is None
    assert ss.pace(95) == "1:35"


def test_session_text_is_plain_text_and_says_no_fit():
    t = next(t for t in LIB if t.id == "swim-css-intervals")
    text = ss.session_text(t, _th(95.0))
    assert "Your CSS: 1:35 per 100 m" in text and "no FIT" in text and "Wakayoshi" in text
    assert "not validated" in text.lower() and "25 m pool" in text
    assert "Your CSS: not saved" in ss.session_text(t, {})


# ── the overlay engine can place these templates ─────────────────────────────────────────────────
def _s(day, st="z2", minutes=60):
    return tp.PlannedSession(day=day, day_name=day.strftime("%a"), session_type=st, duration_min=minutes,
                             tss_estimate=minutes * 0.6, description="")


def _week(start, num, hard=(3,)):
    sessions = [_s(start, "rest", 0)]
    for k in range(1, 7):
        sessions.append(_s(start + timedelta(days=k), "vo2max" if k in hard else "z2", 60))
    return tp.PlannedWeek(week_num=num, start=start, end=start + timedelta(days=6), phase="build1", tss_target=400,
                          is_stepback=False, sessions=sessions, hit_allowance=3)


@pytest.mark.parametrize("css", [None, 95.0])
def test_overlay_places_the_swim_templates(css):
    weeks = [_week(TODAY + timedelta(days=7 * i), i + 1) for i in range(3)]
    mp.overlay(weeks, targets={"cycling": 60.0, "swimming": 40.0}, limiter="swimming", thresholds=_th(css),
               availability={"hours_per_week": 10.0, "weekday": {0: 0, 1: 2, 2: 2, 3: 2, 4: 2, 5: 4, 6: 4}, "date": {}},
               unavailable_periods=[], today=TODAY, session_library=LIB)
    placed = [c for w in weeks for c in w.companions]
    assert placed and {c.sport for c in placed} == {"swimming"}
    ids = {c.template_id for c in placed}
    assert ids <= {t.id for t in LIB} and any(i in ids for i in ("swim-easy-technique", "swim-recovery"))
    assert {c.template_id for c in placed if c.hard} <= {"swim-css-endurance", "swim-css-intervals", "swim-threshold-plus"}
    assert any(c.hard for c in placed)
    for w in weeks:
        bike_hard = {s.day for s in w.sessions if s.session_type == "vo2max"}
        for c in w.companions:
            t = next(t for t in LIB if t.id == c.template_id)
            assert t.minutes[0] <= c.duration_min <= t.minutes[1]
            assert wb.total_seconds(c.workout) == c.duration_min * 60
            if c.hard:
                assert not ({c.day - timedelta(days=1), c.day, c.day + timedelta(days=1)} & bike_hard)
            kinds = {b["target"]["kind"] for s in c.workout["steps"]
                     for b in ([s["on"], s["off"]] if s["kind"] == "repeat" else [s])}
            assert ("css" in kinds) == bool(css and c.hard)


def test_the_registry_default_library_places_swims_without_the_placeholder():
    w = _week(TODAY, 1)
    mp.overlay([w], targets={"cycling": 70.0, "swimming": 30.0}, limiter=None, thresholds={},
               availability={"hours_per_week": 10.0, "weekday": {i: 2 for i in range(7)}, "date": {}},
               unavailable_periods=[], today=TODAY)
    assert w.companions and all(c.template_id.startswith("swim-") for c in w.companions)
