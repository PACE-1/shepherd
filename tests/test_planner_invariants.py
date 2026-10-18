"""#11: the shared planner invariants, entry point by entry point, measured.

docs/PLANNER_AUDIT.md reads these results. Each case is driven through the
characterization drivers in tests/_gate_env.py, so this file and the golden
(tests/characterize_planner.py) cannot drift apart in how they call the
planner: a frozen clock (2026-09-14, a Monday), an explicit athlete (FTP 240 W,
72 kg), a pinned athlete id, seed 20260914, explicit CTL and weekly TSS, an
empty data home, no network. Production mode: _USE_TRAINING_WEEK False.

An invariant that holds is asserted as such. Where one does not, the test pins
the exact exception and its reason, so a change in either direction fails here
and the audit is updated with it. Nothing here was blessed from a run alone:
each pinned exception was read session by session first (see the audit).

Results do not depend on PYTHONHASHSEED (checked with 0 and 12345 over all 79
characterization cases plus the two hook cases below).
"""
import copy
import datetime as dt
import os

import pytest

import clock
import config
import training_planner as tp
import week_plan as wp

# ── the hermetic environment, borrowed for this module only ─────────────────
# Importing _gate_env re-points SHEPHERD_HOME, replaces tp.date, pins the
# athlete id and freezes the one clock. Left in place, the conftest shim would
# keep every later test in this worker on 2026-09-14, so all of it is undone.


@pytest.fixture(scope="module")
def env():
    saved_env = {k: os.environ.get(k) for k in ("SHEPHERD_HOME", "SHEPHERD_NO_NET")}
    saved = (config.ICU_ATHLETE_ID, tp.date, tp._USE_TRAINING_WEEK)
    import _gate_env as g
    # Re-assert, in case another module imported _gate_env earlier in this worker.
    config.ICU_ATHLETE_ID = "gate-athlete"
    tp.date = g._FrozenDate
    g.set_owner(0)
    g.at(g.ANCHOR)
    try:
        yield g
    finally:
        config.ICU_ATHLETE_ID, tp.date, tp._USE_TRAINING_WEEK = saved
        clock.unfreeze()
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── cases ───────────────────────────────────────────────────────────────────
CONT, EVENT, EVENT3 = "cont/mon-fri/1h", "event/wkend5h", "event/wkend3h"
INJURY, BRACE = "x/injury", "x/b-race"
CASES = (
    [f"{CONT}/{d}" for d in ("generate", "generate-thu", "regenerate@3", "extend@9",
                             "extend@30", "refit@3", "refit@24")]
    + [f"{EVENT}/{d}" for d in ("generate", "generate-thu", "regenerate@17",
                                "recalculate@21", "refit@3", "reforecast@21",
                                "reforecast-dict@3")]
    + [f"{EVENT3}/{d}" for d in ("generate-thu", "recalculate@21")]
    + [f"{INJURY}/regenerate-injury@17", f"{BRACE}/generate", f"{BRACE}/reforecast@21"]
)
EVENT_CASES = [c for c in CASES if not c.startswith((CONT, INJURY))]
B_DAY_OFFSET = 7 * 6 + 6          # a Sunday on load week 7, the week before a stepback


def _extra_riders(g):
    """The two hooks added this week, on the gate's own athletes."""
    def b_goal():
        goal = g.event(5.0)
        goal.events = [tp.TargetEvent(date=g._day(B_DAY_OFFSET), priority="B",
                                      name="Club race")]
        return goal
    return {INJURY: g.Rider(INJURY, lambda: g.continuous((5, 6), 2.0), ()),
            BRACE: g.Rider(BRACE, b_goal, (), ctl=50.0, rwt=380.0)}


def _injury_regenerate(g):
    """#113: a 10-day illness that ended 3 days before the rebuild, every
    planned session before it ridden as planned."""
    def drive(r, base):
        t = g._day(17)
        periods = [{"start": (t - dt.timedelta(days=12)).isoformat(),
                    "end": (t - dt.timedelta(days=3)).isoformat(), "type": "injury",
                    "episode_id": "audit", "reason": "injury"}]
        rides = [{"date": s.day.isoformat(), "tss": s.tss_estimate}
                 for w in base for s in w.sessions if s.day < t and s.tss_estimate]
        g.at(t)
        weeks = tp.regenerate_from_today(r.goal(), copy.deepcopy(base), r.ctl,
                                         unavailable_periods=periods, activities=rides,
                                         seed_salt=r.salt, athlete=g.ATHLETE,
                                         recent_weekly_tss=r.rwt)[1]
        return weeks, rides, t
    return drive


@pytest.fixture(scope="module")
def plans(env):
    riders = {r.name: r for r in env.characterization_riders()}
    riders.update(_extra_riders(env))
    drivers = dict(env.DRIVERS, **{"regenerate-injury@17": _injury_regenerate(env)})
    bases, out = {}, {}
    for key in CASES:
        name, dname = key.rsplit("/", 1)
        r = riders[name]
        if name not in bases:
            bases[name] = r.base()
        weeks, rides, today = drivers[dname](r, bases[name])
        out[key] = (weeks, r.goal(), rides, today)
    env.at(env.ANCHOR)              # the drivers move the clock; put it back
    return out


@pytest.fixture(scope="module")
def by_file(env):
    return {r["File"]: r for r in tp.load_workout_library()}


def _ahead(weeks, today):
    return [w for w in weeks if w.end >= today]


def _full(w):
    return (w.end - w.start).days >= 6


def _cls(s):
    return tp._content_class_for_zwo(s.zwo_file or "") or s.session_type


# ── 1. the intensity ceiling (z5+ share of a week's minutes) ────────────────
# The line itself, held here rather than read from tp._MAX_Z5PLUS_SHARE, so
# moving the planner's constant cannot move the test (the same 18 % as
# tests/test_tid_plan_properties.py MAX_Z3_PCT).
MAX_Z5PLUS_SHARE = 0.18
# Partial weeks (a 2-day stub before the taper) the rail runs on but cannot
# fix: their only z5+ session is a class on its phase floor, which
# _enforce_z5plus_share_ceiling never sheds.
SHORT_WEEKS_OVER = {
    f"{EVENT3}/generate-thu": [(13, "peak", 20.8)],
    f"{EVENT3}/recalculate@21": [(13, "build2", 25.0)],
}


@pytest.mark.parametrize("case", CASES)
def test_no_full_load_week_ahead_breaches_the_z5plus_ceiling(plans, by_file, case):
    weeks, _g, _r, today = plans[case]
    over = [(w.week_num, w.phase, round(100 * tp._week_z5plus_share(w, by_file)[0], 1))
            for w in _ahead(weeks, today)
            if _full(w) and not w.is_stepback
            and tp._week_z5plus_share(w, by_file)[0] > MAX_Z5PLUS_SHARE]
    assert over == []


@pytest.mark.parametrize("case", CASES)
def test_short_weeks_over_the_ceiling_are_the_pinned_floor_cases(plans, by_file, case):
    weeks, _g, _r, today = plans[case]
    over = []
    for w in _ahead(weeks, today):
        share, parts = tp._week_z5plus_share(w, by_file)
        if _full(w) or share <= MAX_Z5PLUS_SHARE:
            continue
        over.append((w.week_num, w.phase, round(100 * share, 1)))
        # The reason, not just the number: every z5+ carrier is a floor class.
        floors = tp._PHASE_HARD_FLOORS.get(w.phase, {})
        carriers = {_cls(w.sessions[i]) for z5, i in parts if z5 > 0}
        assert carriers and carriers <= set(floors), (case, w.week_num, carriers)
    assert over == SHORT_WEEKS_OVER.get(case, [])


# The expectedFailure in tests/test_tid_plan_properties.py, reproduced with its
# own construction (6 h shape, 300 TSS/week, CTL 50, seed 3, today 2026-09-14,
# no athlete dict, blank athlete id as in the pytest sandbox), and its cause:
# the phase-floor pass fills the whole vo2_short deficit in ONE week (every
# build2 week ties on HIT count and a HIT-for-HIT swap is always allowed, so
# the greedy loop never leaves the first week), and the last-pass rail never
# sheds a class sitting on its phase floor.
CEILING_BREACHES = [
    # (model, week, z5+ %, vo2_short in the week before -> after the floor pass)
    ("pyramidal", 9, 20.7, 1, 3),
    ("threshold", 10, 18.4, 0, 3),
]


@pytest.mark.parametrize("model,week,pct,before,after", CEILING_BREACHES)
def test_the_ceiling_breach_is_the_floor_pass_concentrating_one_class(
        env, by_file, monkeypatch, model, week, pct, before, after):
    import test_tid_plan_properties as T
    monkeypatch.setattr(config, "ICU_ATHLETE_ID", "")
    env.at(T.PIN)
    seen = {}
    orig = tp._enforce_build2_peak_hard_floor

    def count(weeks):
        w = next(x for x in weeks if x.week_num == week)
        return sum(1 for s in w.sessions if _cls(s) == "vo2_short")

    def spy(weeks, *a, **k):
        seen["before"] = count(weeks)
        orig(weeks, *a, **k)
        seen["after"] = count(weeks)
    monkeypatch.setattr(tp, "_enforce_build2_peak_hard_floor", spy)
    weeks = tp.generate_plan(T._goal(T.SHAPES["6h"], distribution=model), seed_salt=3,
                             current_ctl=T.CTL, recent_weekly_tss=T.LOADS["6h"])[1]
    wk = next(w for w in weeks if w.week_num == week)
    assert (wk.phase, wk.is_stepback, _full(wk)) == ("build2", False, True)
    assert round(100 * tp._week_z5plus_share(wk, by_file)[0], 1) == pct
    assert (seen["before"], seen["after"]) == (before, after)
    # The whole phase holds exactly its floor, all of it in this week ...
    phase_n = sum(1 for w in weeks if w.phase == "build2" and not w.is_stepback
                  for s in w.sessions if _cls(s) == "vo2_short")
    assert phase_n == tp._PHASE_HARD_FLOORS["build2"]["vo2_short"] == after
    # ... so the rail, run again, sheds nothing ...
    again = copy.deepcopy(wk)
    tp._enforce_z5plus_share_ceiling([again], list(by_file.values()))
    assert [s.zwo_file for s in again.sessions] == [s.zwo_file for s in wk.sessions]
    # ... and the same week outside a floored phase is brought under the line.
    unfloored = copy.deepcopy(wk)
    unfloored.phase = "base"
    assert "base" not in tp._PHASE_HARD_FLOORS
    tp._enforce_z5plus_share_ceiling([unfloored], list(by_file.values()))
    assert tp._week_z5plus_share(unfloored, by_file)[0] <= MAX_Z5PLUS_SHARE


# ── 2. the weekly hard-session cap ──────────────────────────────────────────
def _hit(w):
    return [s for s in w.sessions
            if tp._session_is_hit(s) and not getattr(s, "is_opener", False)
            and not tp._protect_race(s) and getattr(s, "status", "pending") == "pending"]


@pytest.mark.parametrize("case", CASES)
def test_no_load_week_ahead_exceeds_its_phase_hit_cap(plans, case):
    """Holds on every entry point, including regenerate, refit and reforecast,
    which never call _enforce_weekly_hit_cap (static map, docs/code-bloat/
    planner-audit.md): on these cases nothing they build needs it."""
    weeks, _g, _r, today = plans[case]
    over = [(w.week_num, w.phase, len(_hit(w)))
            for w in _ahead(weeks, today) if not w.is_stepback
            and len(_hit(w)) > tp.get_budget_for_phase(w.phase).hit_count_max]
    assert over == []


# A stepback week's cap is 0, but the scheduled FTP test counts and is never
# demoted (3.3.1 hotfix). The one other hard session is the harness's own:
# miss_a_hard_day relabels a session vo2max when the week has none, and refit
# re-serves that missed hard day later in the same (stepback) week.
STEPBACK_HIT_NOT_FTP = {f"{CONT}/refit@24": [(4, "vo2max")]}


@pytest.mark.parametrize("case", CASES)
def test_stepback_weeks_ahead_carry_no_hit_but_the_ftp_test(plans, case):
    weeks, _g, _r, today = plans[case]
    extra = [(w.week_num, s.session_type) for w in _ahead(weeks, today) if w.is_stepback
             for s in _hit(w) if s.session_type != "ftp_test"]
    assert extra == STEPBACK_HIT_NOT_FTP.get(case, [])


# ── 3. availability ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", CASES)
def test_rest_days_are_respected(env, plans, case):
    weeks, goal, _r, _t = plans[case]
    assert env.pi.check_rest_days_respected(weeks, goal) == []


# reforecast@21 is driven with a per-day override that frees 3 h on Wednesday
# 2026-10-07 (a 2 h weekday for this goal). The auditor reads the goal's caps,
# not the override, so the session the override allowed is flagged.
DAY_CAP_FLAGS = {f"{EVENT}/reforecast@21": [4], f"{BRACE}/reforecast@21": [4]}


@pytest.mark.parametrize("case", CASES)
def test_day_caps_hold_except_where_an_override_raised_them(env, plans, case):
    weeks, goal, _r, today = plans[case]
    flagged = [v.week_num for v in env.pi.check_daily_duration_cap(weeks, goal)]
    assert flagged == DAY_CAP_FLAGS.get(case, [])
    if flagged:
        day = today + dt.timedelta(days=2)      # the day _gate_env's override frees
        cap_h = goal.max_weekday_hours
        long_ = [s.day for w in weeks for s in w.sessions
                 if (s.duration_min or 0) > cap_h * 60 and s.day.weekday() < 5]
        assert long_ == [day]


# ── 4. the A-race taper ─────────────────────────────────────────────────────
@pytest.mark.parametrize("case", EVENT_CASES)
def test_taper_weeks_hold_the_volume_ceiling(plans, case):
    """TAPER_FRACS x the pre-taper reference (max of the last 3 full load
    weeks), with the pass's own 5 % tolerance. The race session itself is not
    shed by the pass and is left out of the sum."""
    weeks, _g, _r, today = plans[case]
    taper = [w for w in weeks if w.phase == "taper"]
    assert taper
    builds = [w for w in weeks if w.phase != "taper" and not w.is_stepback
              and (w.end - w.start).days + 1 >= 7 and w.start < taper[0].start]
    ref = max(sum(s.tss_estimate or 0 for s in b.sessions if s.session_type != "rest")
              for b in builds[-3:])
    for i, w in enumerate(taper):
        frac = tp.TAPER_FRACS[max(0, len(tp.TAPER_FRACS) - (len(taper) - i))]
        load = sum(s.tss_estimate or 0 for s in w.sessions
                   if s.session_type != "rest" and not getattr(s, "is_race", False))
        assert load <= ref * frac * tp._VOLUME_CEILING_TOLERANCE, (w.week_num, load, ref * frac)


# ── 5. the hooks added this week ────────────────────────────────────────────
def test_b_race_taper_leaves_the_stepback_heavier_than_the_week_it_lightened(env, plans):
    """#111 measured against the plain plan: the B race sits on load week 7,
    its volume taper lightens week 7, and stepback week 8 is then no longer the
    lightest of its block. The plain plan is clean. Pinned for review: whether
    a stepback after a B race may be heavier is an owner decision."""
    def audit(key):
        weeks, goal, rides, today = plans[key]
        return sorted(f"{v.rule}:{v.week_num}" for v in env.pi.audit(weeks, goal, rides, today))
    assert audit(f"{EVENT}/generate") == []
    assert audit(f"{BRACE}/generate") == ["stepback_lightest:8"]
    weeks = plans[f"{BRACE}/generate"][0]
    assert weeks[6].start <= env._day(B_DAY_OFFSET) <= weeks[6].end
    assert weeks[7].is_stepback


def test_injury_rebuild_puts_no_hard_session_in_its_ramp(plans):
    """#113 on the shared rail: the return ramp is easy only. Its own tests
    (tests/test_injury.py) cover sizing; here it is one more regenerate case
    and holds the z5+, HIT-cap and availability checks above."""
    weeks, _g, _r, today = plans[f"{INJURY}/regenerate-injury@17"]
    ramp = [w for w in _ahead(weeks, today) if w.phase in ("recon", "recovery_ramp")]
    assert ramp
    assert [s for w in ramp for s in _hit(w)] == []


# ── 6. TrainingWeek sealing in practice ─────────────────────────────────────
@pytest.mark.parametrize("case", CASES)
def test_production_plans_are_never_sealed(plans, case):
    """_USE_TRAINING_WEEK is False, so TrainingWeek.seal() never runs and no
    session carries _sealed. STRICT_SEAL guards nothing in production."""
    weeks = plans[case][0]
    assert not any(getattr(s, "_sealed", False) for w in weeks for s in w.sessions)


def test_no_product_code_installs_the_seal_guard():
    """_install_seal is the only way a sealed session can notice a write; it is
    called from tests and probes, never from src/."""
    import pathlib
    src = pathlib.Path(tp.__file__).resolve().parent
    uses = {p.name: p.read_text(encoding="utf-8").count("_install_seal(")
            for p in src.glob("*.py")}
    assert {k: n for k, n in uses.items() if n} == {"week_plan.py": 1}   # the def


@pytest.fixture
def seal_audit():
    """Arm the seal in audit mode for one test, then put PlannedSession back."""
    cls = tp.PlannedSession
    had = cls.__dict__.get("_seal_installed", False)
    strict = wp.STRICT_SEAL
    wp.STRICT_SEAL = False
    wp._install_seal(cls)
    wp.SEAL_TRIPS.clear()
    import logging
    lg = logging.getLogger("week_plan")
    level = lg.level
    lg.setLevel(logging.ERROR)
    try:
        yield wp.SEAL_TRIPS
    finally:
        lg.setLevel(level)
        wp.SEAL_TRIPS.clear()
        wp.STRICT_SEAL = strict
        if not had:
            del cls.__setattr__
            del cls._seal_installed


@pytest.mark.parametrize("rider,driver,writers", [
    # generate: the coherence pass re-serves files after finish() sealed the week.
    (CONT, "generate", {"training_planner._enforce_slot_file_coherence",
                        "training_planner._match_zwo_unclamped"}),
    # reforecast edits the stored (sealed) plan directly.
    (EVENT, "reforecast@21", {"training_planner.reforecast",
                              "training_planner._match_zwo_unclamped"}),
])
def test_owner_mode_post_seal_writers(env, seal_audit, rider, driver, writers):
    """With the dormant owner on (_USE_TRAINING_WEEK True) the seal is set, and
    these passes write to sealed sessions. None goes through amend()."""
    r = {x.name: x for x in env.characterization_riders()}[rider]
    env.set_owner(1)
    try:
        base = r.base()
        seal_audit.clear()               # the build itself; generate writes here
        if driver != "generate":
            env.DRIVERS[driver](r, base)
        else:
            r.base()
    finally:
        env.set_owner(0)
    assert set(seal_audit) == writers
