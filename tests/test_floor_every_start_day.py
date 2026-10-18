"""A continuous plan keeps its anaerobic and neuromuscular floor on every start day.

test_354 caught it on a Friday. The floor put its anaerobic session on the
Saturday after Friday's sprint, the 48 h spacing pass eased it, and the plan
had none; on a Saturday start the neuromuscular session went the same way.
Spacing outranks a variety floor (notes/overhaul-plan.md D1), so the floor
now takes a day the 48 h rule allows, anywhere in the phase, before it takes
a clashing one.
"""
import collections
from datetime import date, timedelta

import pytest

import plan_invariants as pi
import training_planner as tp

WEEK = [date(2026, 9, 7) + timedelta(days=k) for k in range(7)]


def _classes(weeks):
    return collections.Counter(tp._content_class_for_zwo(s.zwo_file or "")
                               for w in weeks for s in w.sessions
                               if s.session_type != "rest")


@pytest.mark.parametrize("start", WEEK, ids=lambda d: d.strftime("%a"))
def test_the_floor_holds_on_every_start_day(start, monkeypatch):
    class _Today(date):
        @classmethod
        def today(cls):
            return cls(start.year, start.month, start.day)
    monkeypatch.setattr(tp, "date", _Today)
    goal = tp.Goal(goal_type="continuous", target_date=None, hours_per_week=8.0, focus="both")
    _p, weeks = tp.generate_plan(goal, current_ctl=50.0, recent_weekly_tss=500.0)
    classes = _classes(weeks)
    if not (classes["anaerobic"] >= 1 and classes["neuromuscular"] >= 1):
        # #11 "rail wins" (owner, 2026-10-18): the z5+ ceiling outranks the
        # floor too. On a Sunday start week 1 is that one day and the floor's
        # anaerobic ride alone is over 18 % of it at z5+, so the rail eases it.
        # The floor must then hold in the plan the floor pass left (the rail
        # runs last, so: rail off), and every week the rail changed must have
        # been over the line.
        with monkeypatch.context() as m:
            m.setattr(tp, "_enforce_z5plus_share_ceiling", lambda *a, **k: None)
            floored = tp.generate_plan(goal, current_ctl=50.0, recent_weekly_tss=500.0)[1]
        placed = _classes(floored)
        assert placed["anaerobic"] >= 1 and placed["neuromuscular"] >= 1, dict(placed)
        lib = {r["File"]: r for r in tp.load_workout_library()}
        changed = [b for b, w in zip(floored, weeks) if _classes([b]) != _classes([w])]
        assert changed
        assert all(tp._week_z5plus_share(b, lib)[0] > tp._MAX_Z5PLUS_SHARE
                   for b in changed), [b.week_num for b in changed]
    spacing = [str(v) for v in pi.audit(weeks, goal, today=start) if v.rule == "spacing"]
    assert not spacing, spacing
