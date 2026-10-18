"""The real session libraries (sessions_run/swim/strength) working with the real engine, no library overrides."""
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import training_planner as tp

TODAY = date(2026, 9, 14)           # a Monday
TARGETS = {"cycling": 50, "running": 25, "swimming": 15, "other": 10}
AVAIL = {"hours_per_week": 10.0, "weekday": {0: 0.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 4.0, 6: 4.0}, "date": {}}
THRESHOLDS = {"run_threshold_pace": {"current": 270.0}, "run_threshold_hr": {"current": 168.0},
              "swim_css": {"current": 95.0}}


@pytest.fixture(autouse=True)
def _frozen(monkeypatch):
    import clock
    clock.freeze(TODAY)
    yield
    clock.unfreeze()


def _s(day, st, minutes):
    return tp.PlannedSession(day=day, day_name=day.strftime("%a"), session_type=st, duration_min=minutes,
                             tss_estimate=minutes * 0.6, description="")


def _plan():
    weeks = []
    for n, phase in enumerate(("base1", "build1", "build2", "peak")):
        start = TODAY + timedelta(days=7 * n)
        ss = [_s(start, "rest", 0)]
        for k in range(1, 7):
            st = "vo2max" if k == 2 and phase != "base1" else "long_z2" if k == 5 else "z2"
            ss.append(_s(start + timedelta(days=k), st, 150 if st == "long_z2" else 60))
        weeks.append(tp.PlannedWeek(week_num=n + 1, start=start, end=start + timedelta(days=6), phase=phase,
                                    tss_target=400, is_stepback=False, sessions=ss, hit_allowance=2))
    return weeks


@pytest.mark.parametrize("thresholds", [THRESHOLDS, {}], ids=["with-thresholds", "no-thresholds"])
def test_real_libraries_fill_a_plan_with_valid_sessions(thresholds):
    weeks = _plan()
    mp.overlay(weeks, targets=TARGETS, limiter="running", thresholds=thresholds, availability=AVAIL,
               unavailable_periods=[], today=TODAY)
    comps = [c for w in weeks for c in w.companions]
    sports = {c.sport for c in comps}
    assert {"running", "swimming", "strength"} <= sports, sports
    assert not [c for c in comps if c.template_id.startswith("placeholder-") and c.sport != "running"], \
        "a placeholder survived: a session library did not replace it"
    for c in comps:
        steps = (c.workout or {}).get("steps")
        assert steps or (c.workout or {}).get("exercises") or c.description, f"{c.template_id}: empty workout"
        assert c.duration_min > 0
    # the cycling sessions are untouched
    assert all(s.__class__ is tp.PlannedSession for w in weeks for s in w.sessions)


def test_every_registered_template_builds_for_its_whole_minute_range():
    for t in mp._REGISTRY.values():
        for th in (THRESHOLDS, {}):
            for m in (t.minutes[0], t.minutes[1]):
                out = t.builder(th, m)
                assert isinstance(out, dict), f"{t.id}: builder returned {type(out).__name__}"
