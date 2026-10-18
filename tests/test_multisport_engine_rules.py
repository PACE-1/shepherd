"""Companion engine rules, wave 2 (ENGINE): bricks (#123), limiter emphasis (#124), strength placement
(#127) and the companion taper (#125). Each rule in multisport_plan's docstring has a test here.

The no-limiter golden below was captured from the engine BEFORE these rules were added (commit d678f966):
a rider with no limiter (or a cycling one) and no brick / strength templates in the library gets exactly
the companions they got before.
"""
import json
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import training_planner as tp

TODAY = date(2026, 9, 14)                       # a Monday
WEEKDAY_H = {0: 0.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 4.0, 6: 4.0}
AVAIL = {"hours_per_week": 10.0, "weekday": WEEKDAY_H, "date": {}}
RUN = {"cycling": 75.0, "running": 25.0, "swimming": 0.0, "other": 0.0}
D = lambda k: TODAY + timedelta(days=k)        # noqa: E731


@pytest.fixture(autouse=True)
def _frozen_today():
    import clock
    clock.freeze(TODAY)
    yield
    clock.unfreeze()


def _s(day, st="z2", minutes=60):
    return tp.PlannedSession(day=day, day_name=day.strftime("%a"), session_type=st, duration_min=minutes,
                             tss_estimate=minutes * 0.6, description="")


def _week(types, start=TODAY, num=1, phase="build1", stepback=False, allowance=3):
    """Rest Monday, then ``types`` = [(session_type, minutes)] for Tuesday..Sunday."""
    ss = [_s(start, "rest", 0)] + [_s(start + timedelta(days=k), t, m) for k, (t, m) in enumerate(types, 1)]
    return tp.PlannedWeek(week_num=num, start=start, end=start + timedelta(days=6), phase=phase, tss_target=400,
                          is_stepback=stepback, sessions=ss, hit_allowance=allowance)


KEY_WEEK = [("z2", 60), ("vo2max", 60), ("z2", 60), ("z2", 45), ("long_z2", 150), ("z2", 90)]


def _t(id, sport, kind, minutes, hard=False, st=None, builder=None):
    return mp.SessionTemplate(id=id, sport=sport, kind=kind, session_type=st or f"{sport}_{kind}", intent=id,
                              minutes=minutes, hard=hard, builder=builder or (lambda th, m: {"steps": []}))


# Fixtures that mirror the engine's original placeholders, so the pinned plans below do not depend on which
# session libraries (src/sessions_*.py) happen to be loaded.
RUN_EASY = _t("placeholder-run-easy", "running", "easy", (30, 60), st="run_easy")
SWIM_EASY = _t("placeholder-swim-easy", "swimming", "endurance", (30, 60), st="swim_endurance")
HARD_RUN = _t("t-run-hard", "running", "intervals", (40, 50), hard=True)
HARD_SWIM = _t("t-swim-hard", "swimming", "css", (30, 45), hard=True)


def _overlay(weeks, **kw):
    args = dict(targets=RUN, limiter=None, thresholds={}, availability=AVAIL, unavailable_periods=[], today=TODAY,
                session_library=[RUN_EASY, mp.PLACEHOLDER_BRICK])
    args.update(kw)
    return mp.overlay(weeks, **args)


def _bricks(weeks):
    return [c for w in weeks for c in w.companions if mp.is_brick(c)]


# ── bricks (#123) ──────────────────────────────────────────────────────────────────────────────────
def test_a_brick_follows_the_long_ride_and_links_to_it():
    w = _week(KEY_WEEK)
    before = [tp.session_to_dict(s) for s in w.sessions]
    _overlay([w])
    [b] = _bricks([w])
    assert b.day == D(5) and b.sport == "running" and b.session_type == "brick_run"
    assert b.workout["brick_of"] == mp.bike_session_id(w.sessions[5]) == f"cycling-{D(5).isoformat()}"
    assert b.template_id == "placeholder-run-brick" and 10 <= b.duration_min <= 20
    assert not b.hard
    assert sum(1 for c in w.companions if c.day == b.day and c.sport == "running") == 1
    assert [tp.session_to_dict(s) for s in w.sessions] == before            # the ride is not changed


def test_a_brick_round_trips_through_the_codec():
    w = _week(KEY_WEEK)
    _overlay([w])
    back = tp.week_from_dict(json.loads(json.dumps(tp.week_to_dict(w))))
    assert [c.workout.get("brick_of") for c in back.companions if mp.is_brick(c)] == [f"cycling-{D(5).isoformat()}"]


def test_at_most_one_brick_a_week_and_a_kept_one_counts():
    w1, w2 = _week(KEY_WEEK), _week(KEY_WEEK, start=D(7), num=2)
    _overlay([w1, w2])
    assert [len(_bricks([w])) for w in (w1, w2)] == [1, 1]
    b = _bricks([w1])[0]
    b.status, b.dismissed_at = "dismissed", "2026-09-14T08:00:00"
    _overlay([w1])
    assert _bricks([w1]) == [b]


def test_a_brick_stays_clear_of_a_hard_companion():
    w = _week(KEY_WEEK)
    hard = tp.CompanionSession(day=D(4), day_name="Fri", session_type="run_intervals", duration_min=40,
                               tss_estimate=0.0, description="", id=f"running-{D(4)}", sport="running",
                               template_id="t-run-hard", hard=True, status="done", workout={"steps": []})
    w.companions = [hard]
    _overlay([w])
    [b] = _bricks([w])
    assert b.day == D(2)                                    # the hard bike day; Saturday sits next to Friday
    assert b.workout["brick_of"] == f"cycling-{D(2).isoformat()}"


def test_no_brick_without_a_key_ride_or_without_running():
    flat = _week([("z2", 60)] * 6)
    _overlay([flat])
    assert _bricks([flat]) == []
    w = _week(KEY_WEEK)
    _overlay([w], targets={"cycling": 70, "running": 0, "swimming": 30, "other": 0},
             session_library=[SWIM_EASY, mp.PLACEHOLDER_BRICK])
    assert _bricks([w]) == [] and w.companions


def test_a_hard_brick_template_goes_only_on_a_hard_bike_day():
    w = _week(KEY_WEEK)
    _overlay([w], session_library=[RUN_EASY, _t("t-brick-hard", "running", "brick", (15, 30), hard=True, st="brick_run")])
    [b] = _bricks([w])
    assert b.day == D(2) and b.hard


def test_the_placeholder_brick_is_used_only_when_no_brick_is_registered():
    assert "placeholder-run-brick" not in mp._REGISTRY
    saved = dict(mp._REGISTRY)
    try:
        for t in mp.templates_for("running", "brick"):
            mp.unregister(t.id)
        w = _week(KEY_WEEK)
        _overlay([w], session_library=None)
        assert [b.template_id for b in _bricks([w])] == ["placeholder-run-brick"]
        mp.register(_t("t-brick", "running", "brick", (10, 25), st="brick_run"))
        w = _week(KEY_WEEK)
        _overlay([w], session_library=None)
        assert [b.template_id for b in _bricks([w])] == ["t-brick"]
    finally:
        mp._REGISTRY.clear()
        mp._REGISTRY.update(saved)


def test_a_brick_with_the_riders_note_is_kept_on_its_day():
    w = _week(KEY_WEEK)
    _overlay([w])
    b = _bricks([w])[0]
    b.workout["brick_note"] = "Legs heavy for 5 minutes, then fine."
    _overlay([w], today=b.day)
    assert b in w.companions and b.workout["brick_note"].startswith("Legs heavy")


# ── limiter (#124) ─────────────────────────────────────────────────────────────────────────────────
GOLDEN_NO_LIMITER = {
    "run_swim": [["2026-09-18", "swimming", 50, "placeholder-swim-easy", False], ["2026-09-19", "running", 30, "placeholder-run-easy", False],
                 ["2026-09-20", "running", 50, "g-run-hard", True], ["2026-09-22", "running", 30, "placeholder-run-easy", False],
                 ["2026-09-23", "swimming", 50, "placeholder-swim-easy", False], ["2026-09-27", "running", 50, "g-run-hard", True],
                 ["2026-09-29", "running", 50, "placeholder-run-easy", False], ["2026-09-30", "swimming", 45, "placeholder-swim-easy", False],
                 ["2026-10-01", "swimming", 45, "placeholder-swim-easy", False], ["2026-10-03", "running", 50, "placeholder-run-easy", False],
                 ["2026-10-04", "running", 50, "placeholder-run-easy", False]],
    "run_only": [["2026-09-18", "running", 40, "placeholder-run-easy", False], ["2026-09-19", "running", 40, "placeholder-run-easy", False],
                 ["2026-09-20", "running", 50, "g-run-hard", True], ["2026-09-22", "running", 40, "placeholder-run-easy", False],
                 ["2026-09-23", "running", 40, "placeholder-run-easy", False], ["2026-09-27", "running", 50, "g-run-hard", True],
                 ["2026-09-29", "running", 50, "placeholder-run-easy", False], ["2026-10-03", "running", 50, "placeholder-run-easy", False],
                 ["2026-10-04", "running", 50, "placeholder-run-easy", False]],
}
GOLDEN_TARGETS = {"run_swim": {"cycling": 60, "running": 25, "swimming": 15, "other": 0},
                  "run_only": {"cycling": 70, "running": 30, "swimming": 0, "other": 0}}


def _golden_weeks():
    return [_week([("z2", 60), ("vo2max", 60), ("z2", 60), ("z2", 45), ("long_z2", 150), ("z2", 90)], num=1),
            _week([("threshold", 60), ("z2", 60), ("vo2max", 60), ("z2", 60), ("long_z2", 180), ("recovery", 45)],
                  start=D(7), num=2),
            _week([("z2", 45)] * 4 + [("long_z2", 120), ("z2", 60)], start=D(14), num=3, stepback=True)]


@pytest.mark.parametrize("name", sorted(GOLDEN_NO_LIMITER))
@pytest.mark.parametrize("limiter", [None, "cycling"])
def test_no_limiter_plans_are_unchanged(name, limiter):
    lib = [RUN_EASY, SWIM_EASY, _t("g-run-hard", "running", "intervals", (40, 50), hard=True)]
    weeks = _golden_weeks()
    _overlay(weeks, targets=GOLDEN_TARGETS[name], limiter=limiter, session_library=lib)
    got = [[c.day.isoformat(), c.sport, c.duration_min, c.template_id, c.hard] for w in weeks for c in w.companions]
    assert got == GOLDEN_NO_LIMITER[name]
    assert not any(c.workout and "limiter" in c.workout for w in weeks for c in w.companions)


def test_a_cycling_limiter_is_the_same_as_none():
    lib = [RUN_EASY, SWIM_EASY, HARD_RUN, HARD_SWIM, mp.PLACEHOLDER_BRICK]
    a, b = _golden_weeks(), _golden_weeks()
    _overlay(a, targets=GOLDEN_TARGETS["run_swim"], limiter=None, session_library=lib)
    _overlay(b, targets=GOLDEN_TARGETS["run_swim"], limiter="cycling", session_library=lib)
    dump = lambda ws: json.dumps([tp.week_to_dict(w) for w in ws], default=str)  # noqa: E731
    assert dump(a) == dump(b)


SPLIT = {"cycling": 50, "running": 30, "swimming": 20, "other": 0}
LONG_RUN = _t("t-run-long", "running", "long", (60, 120), st="run_long")
LONG_SWIM = _t("t-swim-long", "swimming", "long", (45, 90), st="swim_endurance")


@pytest.mark.parametrize("limiter,sport,minutes", [("running", "running", 120), ("swimming", "swimming", 90)])
def test_the_limiter_gets_the_longest_free_day_and_no_hours_move(limiter, sport, minutes):
    w = _week([("z2", 50)] * 6)                             # Saturday and Sunday have the most free time
    _overlay([w], targets=SPLIT, limiter=limiter, session_library=[RUN_EASY, SWIM_EASY, LONG_RUN, LONG_SWIM])
    sat = [c for c in w.companions if c.day == D(5)]
    assert [(c.sport, c.duration_min) for c in sat] == [(sport, minutes)]
    assert sat[0].workout["limiter"] == mp.LIMITER_LONG
    by = {s: sum(c.duration_min for c in w.companions if c.sport == s) for s in ("running", "swimming")}
    assert by["running"] <= 180 and by["swimming"] <= 120     # each sport keeps its own share of 10 h
    assert all("limiter" not in (c.workout or {}) for c in w.companions if c.sport != sport)


def test_the_limiters_hard_session_is_tagged():
    w = _week([("vo2max", 60), ("z2", 60), ("z2", 60), ("vo2max", 60), ("z2", 60), ("z2", 60)], allowance=3)
    _overlay([w], targets={"cycling": 60, "running": 25, "swimming": 15, "other": 0}, limiter="swimming",
             session_library=[RUN_EASY, SWIM_EASY, HARD_RUN, HARD_SWIM])
    hard = [c for c in w.companions if c.hard]
    assert [c.sport for c in hard] == ["swimming"] and hard[0].workout["limiter"] == mp.LIMITER_HARD


# ── strength (#127) ────────────────────────────────────────────────────────────────────────────────
STR_A = _t("t-str-a", "strength", "strength", (30, 45), st="strength")
STR_M = _t("t-str-m", "strength", "maintenance", (20, 30), st="strength")
MOB = _t("t-mob", "strength", "mobility", (10, 20), st="strength")
STRENGTH = {"cycling": 80, "running": 0, "swimming": 0, "other": 20}


def _strength(weeks, lib=(STR_A, MOB), **kw):
    return _overlay(weeks, **{"targets": STRENGTH, **kw}, session_library=list(lib))


def test_strength_avoids_hard_days_and_the_day_before_a_key_session():
    w = _week([("vo2max", 60), ("z2", 60), ("z2", 60), ("z2", 60), ("long_z2", 150), ("z2", 60)])
    _strength([w])
    res = [c for c in w.companions if c.session_type == "strength"]
    assert 1 <= len(res) <= mp.STRENGTH_MAX_PER_WEEK
    for c in res:
        assert c.day not in (D(1),)                         # the hard bike day
        assert c.day not in (D(0), D(4))                    # the day before the hard day / the long ride
    mob = [c for c in w.companions if c.session_type == "mobility"]
    assert mob and all(c.day != D(1) for c in mob)          # mobility: any easy day


def test_at_most_two_resistance_sessions_a_week_however_big_the_share():
    w = _week([("z2", 30)] * 6)
    _strength([w], targets={"cycling": 50, "running": 0, "swimming": 0, "other": 50}, lib=(STR_A,))
    assert len([c for c in w.companions if c.sport == "strength"]) == 2


def test_no_strength_the_day_before_a_race():
    w = _week([("z2", 60)] * 6)
    w.sessions[6].is_race = True
    _strength([w], lib=(STR_A,))
    assert {c.day for c in w.companions} & {D(5), D(6)} == set()


def test_a_hard_companion_never_follows_a_strength_day():
    w = _week([("z2", 60)] * 6)
    lift = tp.CompanionSession(day=D(1), day_name="Tue", session_type="strength", duration_min=40, tss_estimate=0.0,
                               description="", id=f"strength-{D(1)}", sport="strength", template_id="t-str-a",
                               status="done", workout={"steps": []})
    w.companions = [lift]
    roomy = {**AVAIL, "date": {D(2).isoformat(): 6.0}}     # the day after the lift is the most free day
    _overlay([w], targets={"cycling": 60, "running": 30, "swimming": 0, "other": 10}, availability=roomy,
             session_library=[RUN_EASY, HARD_RUN, STR_A])
    hard = [c for c in w.companions if c.hard]
    assert hard and all(c.day != D(2) for c in hard)


@pytest.mark.parametrize("phase,kind", [("build1", "t-str-m"), ("peak", "t-str-m"), ("base", "t-str-a")])
def test_maintenance_strength_is_preferred_in_build_and_peak(phase, kind):
    w = _week([("z2", 60)] * 6, phase=phase)
    _strength([w], lib=(STR_A, STR_M))
    assert {c.template_id for c in w.companions if c.session_type == "strength"} == {kind}


def test_a_builder_that_takes_phase_gets_it_and_two_argument_builders_still_work():
    seen = []
    phased = _t("t-phased", "strength", "strength", (30, 45), st="strength",
                builder=lambda th, m, phase=None: seen.append(phase) or {"steps": []})
    w = _week([("z2", 60)] * 6, phase="build2")
    _strength([w], lib=(phased,))
    assert seen and set(seen) == {"build2"}
    w = _week([("z2", 60)] * 6)
    _strength([w], lib=(STR_A,))                             # (thresholds, minutes) only: no error
    assert w.companions


# ── companion taper (#125) ─────────────────────────────────────────────────────────────────────────
def _taper_weeks():
    return [_week([("z2", 60)] * 6, num=1, phase="taper"), _week([("z2", 60)] * 6, start=D(7), num=2, phase="taper")]


def _run_minutes(weeks):
    return [sum(c.duration_min for c in w.companions if c.sport == "running") for w in weeks]


def test_companions_taper_by_the_planners_own_fractions(monkeypatch):
    weeks = _taper_weeks()
    _overlay(weeks, session_library=[RUN_EASY])
    share = 10 * 60 * 0.25                                  # 150 minutes of running a full week
    got = _run_minutes(weeks)
    for minutes, frac in zip(got, tp.TAPER_FRACS):
        assert share * frac - 2 * mp.STEP_MIN <= minutes <= share * frac
    assert not any(c.hard for w in weeks for c in w.companions)
    monkeypatch.setattr(tp, "TAPER_FRACS", (0.8, 0.6))     # imported, not copied
    weeks = _taper_weeks()
    _overlay(weeks, session_library=[RUN_EASY])
    assert _run_minutes(weeks) != got and _run_minutes(weeks)[0] <= share * 0.8
