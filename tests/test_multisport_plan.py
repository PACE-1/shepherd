"""Companion sessions (MASTER_DECISIONS ADDENDUM 5): the overlay engine, the plan codec and the planner hook.

The byte-identical guarantee for cycling-only riders is pinned three ways: the characterization golden
(tests/test_injury_planner_unchanged.py runs tests/characterize_planner.py), the plan JSON of a generated
plan against the codec's pre-companion output, and the wrapped entry point against the unwrapped one.
"""
import json
from dataclasses import fields
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import training_planner as tp

TODAY = date(2026, 9, 14)                       # a Monday
TARGETS = {"cycling": 60.0, "running": 25.0, "swimming": 10.0, "other": 5.0}
WEEKDAY_H = {0: 0.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 4.0, 6: 4.0}
AVAIL = {"hours_per_week": 10.0, "weekday": WEEKDAY_H, "date": {}}


class _Today(date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    import clock
    monkeypatch.setattr(tp, "date", _Today)
    clock.freeze(TODAY)
    yield
    clock.unfreeze()


def _s(day, st="z2", minutes=60):
    return tp.PlannedSession(day=day, day_name=day.strftime("%a"), session_type=st, duration_min=minutes,
                             tss_estimate=minutes * 0.6, description="")


def _week(start=TODAY, hard=(), num=1, phase="build1", stepback=False, bike_min=60, allowance=3):
    """A Monday-Sunday cycling week: rest Monday, ``bike_min`` z2 Tue-Sun, vo2max on the ``hard`` offsets."""
    sessions = [_s(start, "rest", 0)]
    for k in range(1, 7):
        sessions.append(_s(start + timedelta(days=k), "vo2max" if k in hard else "z2", bike_min))
    return tp.PlannedWeek(week_num=num, start=start, end=start + timedelta(days=6), phase=phase, tss_target=400,
                          is_stepback=stepback, sessions=sessions, hit_allowance=allowance)


def _overlay(weeks, **kw):
    args = dict(targets=TARGETS, limiter=None, thresholds={}, availability=AVAIL, unavailable_periods=[],
                today=TODAY)
    args.update(kw)
    return mp.overlay(weeks, **args)


def _hard_run(minutes=(40, 50)):
    return mp.SessionTemplate(id="t-run-hard", sport="running", kind="intervals", session_type="run_intervals",
                              intent="test", minutes=minutes, hard=True, builder=lambda th, m: {"steps": []})


def _hard_swim():
    return mp.SessionTemplate(id="t-swim-hard", sport="swimming", kind="css", session_type="swim_css",
                              intent="test", minutes=(30, 45), hard=True, builder=lambda th, m: {"steps": []})


def _lib(*extra):
    return [*mp.templates_for("running"), *mp.templates_for("swimming"), *mp.templates_for("strength"), *extra]


# ── opt-in ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("targets", [None, {}, {"cycling": 100, "running": 0, "swimming": 0, "other": 0},
                                     {"cycling": 0, "running": 100, "swimming": 0, "other": 0}])
def test_overlay_is_off_without_a_non_cycling_share(targets):
    w = _week()
    _overlay([w], targets=targets)
    assert w.companions == []
    assert mp.scaled_cycling_hours(10.0, targets) == 10.0


def test_overlay_is_on_with_a_share_and_scales_cycling_hours():
    assert mp.overlay_on(TARGETS)
    assert mp.scaled_cycling_hours(10.0, TARGETS) == 6.0
    w = _week()
    _overlay([w])
    assert w.companions and {c.sport for c in w.companions} <= set(mp.COMPANION_SPORTS)


# ── hours ──────────────────────────────────────────────────────────────────────────────────────────
def test_hours_split_never_exceeds_each_share_or_the_hours_left():
    w = _week(bike_min=60)                                   # 360 bike minutes = the full 60 % of 10 h
    _overlay([w])
    by = {s: sum(c.duration_min for c in w.companions if c.sport == s) for s in mp.COMPANION_SPORTS}
    assert by["running"] <= 150 and by["swimming"] <= 60 and by["strength"] <= 30
    assert by["running"] >= 120 and by["swimming"] >= 30      # filled to within one 5-minute step per session
    assert 360 + sum(by.values()) <= 600


def test_a_lighter_cycling_week_shrinks_companions_in_step():
    full, light = _week(bike_min=60), _week(bike_min=30)
    _overlay([full])
    _overlay([light])
    assert sum(c.duration_min for c in light.companions) < sum(c.duration_min for c in full.companions)
    assert sum(c.duration_min for c in light.companions if c.sport == "running") <= 75


# ── availability, time off, injuries ───────────────────────────────────────────────────────────────
def test_companions_respect_rest_days_day_caps_and_date_overrides():
    w = _week()
    off = (TODAY + timedelta(days=5)).isoformat()             # Saturday: 0 h
    _overlay([w], availability={**AVAIL, "date": {off: 0.0}})
    days = {c.day for c in w.companions}
    assert TODAY not in days                                 # Monday is a rest day
    assert date.fromisoformat(off) not in days
    for d in days:
        bike = sum(s.duration_min for s in w.sessions if s.day == d and s.session_type != "rest")
        comp = sum(c.duration_min for c in w.companions if c.day == d)
        assert bike + comp <= WEEKDAY_H[d.weekday()] * 60


def test_nothing_is_planned_before_today():
    w = _week()
    _overlay([w], today=TODAY + timedelta(days=4))
    assert w.companions and all(c.day >= TODAY + timedelta(days=4) for c in w.companions)


def test_a_time_off_row_blocks_every_sport():
    w = _week()
    _overlay([w], unavailable_periods=[(TODAY, TODAY + timedelta(days=6))])
    assert w.companions == []


@pytest.mark.parametrize("sport,blocked", [("running", {"running"}), ("swimming", {"swimming"}),
                                           ("other", {"strength"}), ("cycling", set()),
                                           ("all", set(mp.COMPANION_SPORTS))])
def test_an_injury_blocks_only_the_sport_it_names(sport, blocked):
    w, ref = _week(), _week()
    _overlay([ref])
    _overlay([w], unavailable_periods=[{"start": TODAY.isoformat(), "end": None, "sport": sport}])
    got = {c.sport for c in w.companions}
    assert not got & blocked
    assert got == {c.sport for c in ref.companions} - blocked


def test_no_companion_on_a_race_day():
    w = _week()
    race = TODAY + timedelta(days=6)
    w.sessions[6].is_race = True
    _overlay([w], targets={"cycling": 50, "running": 50, "swimming": 0, "other": 0})
    assert race not in {c.day for c in w.companions}


# ── hard days ──────────────────────────────────────────────────────────────────────────────────────
def _adjacent(d, days):
    return bool({d - timedelta(days=1), d, d + timedelta(days=1)} & set(days))


def test_a_hard_companion_never_sits_on_or_next_to_a_hard_bike_day():
    w = _week(hard=(2,), allowance=3)                        # VO2 on Wednesday
    _overlay([w], session_library=_lib(_hard_run()))
    hard = [c for c in w.companions if c.hard]
    assert len(hard) == 1
    bike_hard = [s.day for s in w.sessions if tp._session_is_hit(s)]
    assert not _adjacent(hard[0].day, bike_hard)


def test_hard_spacing_holds_across_the_week_boundary():
    w1 = _week(hard=(), allowance=3)
    w2 = _week(start=TODAY + timedelta(days=7), hard=(), num=2, allowance=3)
    w2.sessions[0] = _s(w2.start, "vo2max", 60)              # next Monday is hard
    _overlay([w1, w2], session_library=_lib(_hard_run()))
    for c in w1.companions:
        if c.hard:
            assert c.day != w1.end


def test_hard_companions_use_only_what_the_bike_leaves_of_the_budget():
    w = _week(hard=(1, 3, 5), allowance=3)                   # the bike already holds 3 hard days
    _overlay([w], session_library=_lib(_hard_run()))
    assert not any(c.hard for c in w.companions)
    assert any(c.sport == "running" for c in w.companions)   # the run hours still go to easy runs


@pytest.mark.parametrize("kw", [{"stepback": True}, {"phase": "taper"}, {"phase": "recon"}])
def test_no_hard_companion_in_a_stepback_week_or_an_easy_phase(kw):
    w = _week(**kw)
    _overlay([w], session_library=_lib(_hard_run()))
    assert not any(c.hard for c in w.companions)


def test_the_limiter_gets_first_claim_on_the_one_free_hard_slot():
    lib = _lib(_hard_run(), _hard_swim())
    for limiter, wins in (("running", "running"), ("swimming", "swimming")):
        w = _week(hard=(1, 2), allowance=3)                  # 3 slots for 10 h, bike holds 2: one left
        _overlay([w], limiter=limiter, session_library=lib)
        assert [c.sport for c in w.companions if c.hard] == [wins]


def test_bike_sessions_are_never_changed():
    w = _week(hard=(2,))
    before = [tp.session_to_dict(s) for s in w.sessions]
    _overlay([w], session_library=_lib(_hard_run()))
    assert [tp.session_to_dict(s) for s in w.sessions] == before


# ── kept companions ────────────────────────────────────────────────────────────────────────────────
def test_overlay_is_deterministic_and_keeps_dismissed_and_done_companions():
    w = _week()
    _overlay([w])
    first = [tp.session_to_dict(c) for c in w.companions]
    _overlay([w])
    assert [tp.session_to_dict(c) for c in w.companions] == first
    w.companions[0].status, w.companions[0].dismissed_at = "dismissed", "2026-09-14T08:00:00"
    gone = w.companions[0]
    _overlay([w])
    assert gone in w.companions
    assert sum(1 for c in w.companions if c.sport == gone.sport and c.day == gone.day) == 1
    # the dismissed minutes still count: the sport is not topped up elsewhere
    assert sum(c.duration_min for c in w.companions if c.sport == gone.sport) <= \
        sum(c["duration_min"] for c in first if c["sport"] == gone.sport)


def test_templates_register_and_filter():
    t = mp.register(mp.SessionTemplate(id="t-x", sport="running", kind="long", session_type="run_long",
                                       intent="x", minutes=(60, 90), hard=False, builder=lambda th, m: {}))
    try:
        assert t in mp.templates_for("running", "long")
        assert t not in mp.templates_for("swimming")
        with pytest.raises(ValueError):
            mp.register(mp.SessionTemplate(id="bad", sport="rowing", kind="x", session_type="x", intent="",
                                           minutes=(1, 2), hard=False, builder=lambda th, m: {}))
        with pytest.raises(ValueError):
            mp.register(mp.SessionTemplate(id="bad", sport="running", kind="x", session_type="x", intent="",
                                           minutes=(50, 40), hard=False, builder=lambda th, m: {}))
    finally:
        mp._REGISTRY.pop("t-x", None)


# ── codec ──────────────────────────────────────────────────────────────────────────────────────────
def test_companions_round_trip_through_the_codec():
    w = _week()
    _overlay([w])
    d = tp.week_to_dict(w)
    assert d["companions"] and d["companions"][0]["sport"] in mp.COMPANION_SPORTS
    back = tp.week_from_dict(json.loads(json.dumps(d)))
    assert all(isinstance(c, tp.CompanionSession) for c in back.companions)
    assert tp.week_to_dict(back) == d
    c = w.companions[0]
    assert tp.session_from_dict(tp.session_to_dict(c)) == c       # the app's _planned_session_to/from_json


def test_a_week_without_companions_serialises_as_before():
    w = _week()
    d = tp.week_to_dict(w)
    assert "companions" not in d
    old = {f.name: getattr(w, f.name) for f in fields(tp.PlannedWeek) if f.name != "companions"}
    old.update(start=w.start.isoformat(), end=w.end.isoformat(), sessions=[tp.session_to_dict(s) for s in w.sessions])
    assert json.dumps(d) == json.dumps(old)
    assert all("sport" not in s for s in d["sessions"])


# ── the planner hook ───────────────────────────────────────────────────────────────────────────────
def _goal():
    return tp.Goal(goal_type="ftp", hours_per_week=10.0, plan_weeks=4, available_days=[1, 2, 3, 4, 5, 6],
                   rest_days=[0], max_weekday_hours=2.0, max_weekend_hours=4.0)


def _gen(fn=None):
    return (fn or tp.generate_plan)(_goal(), seed_salt=3, current_ctl=50.0, recent_weekly_tss=400.0,
                                    athlete={"ftp": 240, "weight_kg": 72})


def _json(weeks):
    return json.dumps([tp.week_to_dict(w) for w in weeks], default=str)


def test_cycling_only_rider_gets_exactly_the_unwrapped_plan(monkeypatch):
    monkeypatch.setattr(tp, "_companion_context", lambda: None)
    wrapped, plain = _gen()[1], _gen(tp.generate_plan.__wrapped__)[1]
    assert _json(wrapped) == _json(plain)
    assert '"companions"' not in _json(wrapped)


def test_no_targets_file_means_overlay_off(tmp_path, monkeypatch):
    import profile_manager
    monkeypatch.setattr(profile_manager.ProfileManager, "get", classmethod(lambda cls: type("P", (), {"active_dir": tmp_path})()))
    assert tp._companion_context() is None
    (tmp_path / "balance_targets.json").write_text(json.dumps({"targets": TARGETS, "limiter": "running"}))
    assert tp._companion_context()["targets"] == TARGETS


def test_the_hook_scales_cycling_adds_companions_and_restores_the_goal(monkeypatch):
    ctx = {"targets": TARGETS, "limiter": "running", "thresholds": {}, "episodes": []}
    seen = []
    plain = tp.generate_plan.__wrapped__

    def spy(goal, *a, **k):
        seen.append(goal.hours_per_week)
        return plain(goal, *a, **k)
    monkeypatch.setattr(tp, "_companion_context", lambda: ctx)
    wrapped = tp._companion_overlay(spy)
    goal = _goal()
    _p, weeks = wrapped(goal, seed_salt=3, current_ctl=50.0, recent_weekly_tss=400.0,
                        athlete={"ftp": 240, "weight_kg": 72})
    assert seen == [6.0] and goal.hours_per_week == 10.0
    assert any(w.companions for w in weeks)
    for w in weeks:
        assert all(s.__class__ is tp.PlannedSession for s in w.sessions)


def test_regenerate_keeps_a_dismissed_companion(monkeypatch):
    ctx = {"targets": TARGETS, "limiter": None, "thresholds": {}, "episodes": []}
    monkeypatch.setattr(tp, "_companion_context", lambda: ctx)
    goal = _goal()
    _p, weeks = tp.generate_plan(goal, seed_salt=3, current_ctl=50.0, recent_weekly_tss=400.0,
                                 athlete={"ftp": 240, "weight_kg": 72})
    later = [c for w in weeks for c in w.companions if c.day > TODAY + timedelta(days=8)][0]
    later.status, later.dismissed_at = "dismissed", "2026-09-14T09:00:00"
    stored = [tp.week_from_dict(json.loads(json.dumps(tp.week_to_dict(w)))) for w in weeks]
    goal.target_date = TODAY + timedelta(weeks=4)
    goal.plan_weeks = 0
    _p, new_weeks, _info = tp.regenerate_from_today(goal, stored, 50.0, recent_weekly_tss=400.0)
    kept = [c for w in new_weeks for c in w.companions if c.id == later.id]
    assert kept and kept[0].status == "dismissed"


# ── completion ─────────────────────────────────────────────────────────────────────────────────────
def _stored_week(end=TODAY + timedelta(days=6)):
    return {"start": TODAY.isoformat(), "end": end.isoformat(), "sessions": [], "companions": [
        {"id": "running-2026-09-15", "day": "2026-09-15", "sport": "running", "duration_min": 40,
         "status": "pending", "workout": None},
        {"id": "swimming-2026-09-16", "day": "2026-09-16", "sport": "swimming", "duration_min": 40,
         "status": "pending", "workout": None},
        {"id": "strength-2026-09-17", "day": "2026-09-17", "sport": "strength", "duration_min": 30,
         "status": "pending", "workout": None}]}


def test_a_companion_is_done_by_the_same_sport_on_the_same_day_within_half_its_length():
    wk = _stored_week()
    acts = [{"id": "a1", "date": "2026-09-15", "sport": "Run", "duration_sec": 59 * 60},
            {"id": "a2", "date": "2026-09-16", "sport": "Ride", "duration_sec": 40 * 60},
            {"id": "a3", "date": "2026-09-17", "sport": "WeightTraining", "duration_sec": 30 * 60}]
    n = mp.reconcile_week(wk, acts, TODAY + timedelta(days=4))
    st = {c["sport"]: c["status"] for c in wk["companions"]}
    assert st == {"running": "done", "swimming": "missed", "strength": "done"} and n == 3
    assert wk["companions"][0]["completion_matches"][0]["activity_id"] == "a1"
    assert mp.reconcile_week(wk, acts, TODAY + timedelta(days=4)) == 0     # idempotent


@pytest.mark.parametrize("minutes,done", [(19, False), (20, True), (60, True), (61, False)])
def test_the_duration_window_is_plus_minus_half(minutes, done):
    wk = _stored_week()
    mp.reconcile_week(wk, [{"id": "a", "date": "2026-09-15", "sport": "Run", "duration_sec": minutes * 60}],
                      TODAY + timedelta(days=1))
    assert (wk["companions"][0]["status"] == "done") is done


def test_missed_companions_are_dropped_at_week_end():
    wk = _stored_week()
    acts = [{"id": "a1", "date": "2026-09-15", "sport": "Run", "duration_sec": 40 * 60}]
    mp.reconcile_week(wk, acts, TODAY + timedelta(days=8))
    assert [c["status"] for c in wk["companions"]] == ["done"]
    wk2 = _stored_week()
    mp.reconcile_week(wk2, [], TODAY + timedelta(days=8))
    assert "companions" not in wk2


def test_cycling_weeks_without_companions_are_untouched():
    wk = {"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=6)).isoformat(), "sessions": [{"x": 1}]}
    before = json.dumps(wk)
    assert mp.reconcile_week(wk, [{"id": "a", "date": "2026-09-15", "sport": "Run", "duration_sec": 1}], TODAY) == 0
    assert json.dumps(wk) == before


def test_a_library_module_registers_on_import_and_can_retire_its_placeholder(tmp_path, monkeypatch):
    import sys
    import multisport_plan as mp
    src = tmp_path / "sessions_zzdemo.py"
    src.write_text(
        "from multisport_plan import SessionTemplate, register, unregister\n"
        "unregister('placeholder-run-easy')\n"
        "register(SessionTemplate(id='demo-run', sport='running', kind='easy', session_type='run_easy',\n"
        "    intent='demo', minutes=(20, 40), hard=False, builder=lambda th, m: {'steps': []}))\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    saved = dict(mp._REGISTRY)
    try:
        mod = __import__("sessions_zzdemo")
        ids = [t.id for t in mp.templates_for("running", "easy")]   # the real run library may be loaded too
        assert "demo-run" in ids and "placeholder-run-easy" not in ids
        assert mp.unregister("demo-run") is True and mp.unregister("demo-run") is False
    finally:
        sys.modules.pop("sessions_zzdemo", None)
        mp._REGISTRY.clear(); mp._REGISTRY.update(saved)
