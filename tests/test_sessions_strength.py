"""Strength and mobility library (#127): templates, progression ranges, session-RPE load, the route, and
that multisport_plan.overlay can place the templates."""
import math
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import sessions_strength as ss
import training_planner as tp

TODAY = date(2026, 9, 14)                       # a Monday
TARGETS = {"cycling": 80.0, "running": 0.0, "swimming": 0.0, "other": 20.0}
AVAIL = {"hours_per_week": 10.0, "weekday": {0: 0.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 4.0, 6: 4.0}, "date": {}}


# ── templates ──────────────────────────────────────────────────────────────────────────────────────
def test_registered_and_placeholder_retired():
    ids = {t.id for t in mp.templates_for("strength")}
    assert ids == {p.id for p in ss.PLANS}
    assert "placeholder-strength-general" not in ids
    assert all(not t.hard and t.session_type == "strength" and t.sport == "strength" for t in mp.templates_for("strength"))
    kinds = {t.kind for t in mp.templates_for("strength")}
    assert kinds == {"strength", "maintenance", "mobility"}


def test_four_templates_a_b_maintenance_mobility():
    assert [p.id for p in ss.PLANS] == ["strength-general-a", "strength-general-b", "strength-maintenance", "mobility-flexibility"]


@pytest.mark.parametrize("plan", ss.PLANS, ids=lambda p: p.id)
@pytest.mark.parametrize("stage", [s.id for s in ss.STAGES])
def test_every_exercise_is_complete_and_sets_reps_are_in_range(plan, stage):
    s = ss.build_session(plan.id, stage)
    assert s["exercises"] and s["disclaimer"] == ss.DISCLAIMER
    st = ss.STAGE[stage]
    for e in s["exercises"]:
        assert e["name"] and e["cue"].endswith((".", "!")) and "\n" not in e["cue"] and e["effort"] and e["rest"]
        assert 1 <= e["sets"][0] <= e["sets"][1] <= 4
        assert 0 <= e["rpe"][0] <= e["rpe"][1] <= 10
        if e["hold_s"]:
            assert e["reps"] is None and 10 <= e["hold_s"] <= 60
        elif e["pattern"] != "mobility":
            assert e["reps"] == list(st.reps)
            if not plan.maintenance:
                assert e["sets"] == list(st.sets)


def test_mobility_holds_and_cat_cow_reps():
    ex = {e["id"]: e for e in ss.build_session("mobility-flexibility", minutes=20)["exercises"]}
    assert ex["hamstring"]["hold_s"] == ss.STRETCH_HOLD_S == 30 and ex["hamstring"]["per_side"]
    assert ex["cat-cow"]["reps"] == [8, 10] and ex["cat-cow"]["hold_s"] is None


def test_progression_by_stage_novice_acsm_then_more_sets_fewer_reps():
    n, p, x = ss.STAGES
    assert (n.sets, n.reps) == ((1, 3), (8, 12)) and not n.verify          # ACSM 2009 novice
    assert n.sets[1] <= p.sets[1] <= x.sets[1] and p.sets[0] > n.sets[0]
    assert x.reps[1] < p.reps[1] < n.reps[1] and x.reps[0] < p.reps[0] < n.reps[0]
    assert p.verify and x.verify                                           # flagged, not certain
    assert all(a.rpe[1] <= b.rpe[1] for a, b in zip(ss.STAGES, ss.STAGES[1:]))
    assert ss.DEFAULT_STAGE == "novice"


def test_maintenance_is_short_with_two_sets_and_fewer_exercises():
    m = ss.build_session("strength-maintenance", "novice")
    a = ss.build_session("strength-general-a", "novice")
    assert m["minutes"] < a["minutes"] and len(m["exercises"]) < len(a["exercises"])
    assert all(e["sets"] == [2, 2] for e in m["exercises"])
    assert m["rpe_range"][1] <= a["rpe_range"][1]


def test_short_session_keeps_the_first_exercises_and_minutes_clamp():
    short = ss.build_session("strength-general-a", minutes=30)
    long = ss.build_session("strength-general-a", minutes=45)
    assert 5 <= len(short["exercises"]) < len(long["exercises"]) == 8
    assert [e["id"] for e in long["exercises"]][:5] == [e["id"] for e in short["exercises"]]
    assert ss.build_session("strength-general-a", minutes=500)["minutes"] == 45
    assert ss.build_session("strength-general-a", minutes=1)["minutes"] == 30


def test_unknown_stage_rejected():
    with pytest.raises(ValueError):
        ss.build_session("strength-general-a", "elite")


def test_builder_output_is_a_workout_dict_with_effort_targets_only():
    w = mp.templates_for("strength", "strength")[0].builder({}, 40)
    assert w["name"] and w["description"] and w["exercises"]
    assert sum(s["duration_s"] for s in w["steps"]) == 40 * 60
    assert all(s["target"]["kind"] == "effort" and s["target"]["label"] for s in w["steps"])
    assert w["load_note"] == "arbitrary units (session-RPE), not comparable with TSS"
    mob = mp.templates_for("strength", "mobility")[0].builder({}, 10)
    assert sum(s["duration_s"] for s in mob["steps"]) == 600 and [s["kind"] for s in mob["steps"]] == ["work"]


# ── load: session-RPE ──────────────────────────────────────────────────────────────────────────────
def test_strength_load_au_is_minutes_times_rpe():
    assert ss.strength_load_au(45, 6) == 270.0                    # Foster 2001: minutes x CR10
    assert ss.strength_load_au(30, 4.5) == 135.0
    assert ss.strength_load_au(0, 7) == 0.0 and ss.strength_load_au(40, 0) == 0.0


@pytest.mark.parametrize("minutes,rpe", [(-1, 5), (30, -1), (30, 10.5), (True, 5), (30, "5"), (math.nan, 5), (30, math.inf)])
def test_strength_load_au_rejects_bad_input(minutes, rpe):
    with pytest.raises(ValueError):
        ss.strength_load_au(minutes, rpe)


def test_session_load_range_uses_rpe_range_and_carries_the_not_tss_note():
    s = ss.build_session("strength-general-a", minutes=40)
    lo, hi = s["rpe_range"]
    assert s["load_au"] == [ss.strength_load_au(40, lo), ss.strength_load_au(40, hi)]
    assert s["load_note"] == "arbitrary units (session-RPE), not comparable with TSS"


def test_no_tss_in_a_placed_strength_companion():
    c = _overlay([_week()], session_library=mp.templates_for("strength"))[0].companions
    assert c and all(x.tss_estimate == 0.0 for x in c)


# ── overlay can place the templates ────────────────────────────────────────────────────────────────
def _s(day, st="z2", minutes=60):
    return tp.PlannedSession(day=day, day_name=day.strftime("%a"), session_type=st, duration_min=minutes,
                             tss_estimate=minutes * 0.6, description="")


def _week(start=TODAY, hard=(2, 5), num=1):
    sessions = [_s(start, "rest", 0)] + [_s(start + timedelta(days=k), "vo2max" if k in hard else "z2", 60) for k in range(1, 7)]
    return tp.PlannedWeek(week_num=num, start=start, end=start + timedelta(days=6), phase="build1", tss_target=400,
                          is_stepback=False, sessions=sessions, hit_allowance=3)


def _overlay(weeks, **kw):
    import clock
    clock.freeze(TODAY)
    try:
        args = dict(targets=TARGETS, limiter=None, thresholds={}, availability=AVAIL, unavailable_periods=[], today=TODAY)
        args.update(kw)
        return mp.overlay(weeks, **args)
    finally:
        clock.unfreeze()


def test_overlay_places_the_library_templates_away_from_hard_days():
    weeks = [_week(TODAY + timedelta(weeks=i), num=i) for i in range(4)]
    _overlay(weeks)                                               # the registry, as the planner uses it
    placed = [c for w in weeks for c in w.companions]
    assert placed and {c.sport for c in placed} == {"strength"}
    ids = {t.id for t in mp.templates_for("strength")}
    assert {c.template_id for c in placed} <= ids and not any(c.hard for c in placed)
    for c in placed:
        assert c.workout["exercises"] and c.tss_estimate == 0.0
        assert c.duration_min in range(10, 46)
    assert len({c.template_id for c in placed}) > 1               # the weeks rotate through the library
    for w in weeks:
        assert len([c for c in w.companions if c.sport == "strength"]) <= 7
