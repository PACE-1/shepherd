"""#111 the race tapers in the planner: reference values from the cited taper ranges, the B-race volume
taper, and plans without B races left exactly as they were.

Sources (training_planner.B_TAPER_DAYS comment, docs/SCIENCE.md "Races and tapers"): Bosquet et al. 2007,
Med Sci Sports Exerc 39(8):1358-1368 (8-14 days, volume down 41-60 %, intensity and frequency kept) and
Mujika & Padilla 2003, Med Sci Sports Exerc 35(7):1182-1187 (progressive cut, intensity kept).
"""
from datetime import date, timedelta

import pytest

import clock
import training_planner as tp

TODAY = date(2026, 9, 14)  # a Monday
ATHLETE = {"ftp": 240, "weight_kg": 72}


# ── reference values ──────────────────────────────────────────────────────────────────────────────────
def test_the_a_taper_sits_in_the_published_ranges():
    assert 8 <= tp.TAPER_DAYS <= 14                                   # Bosquet 2007: 8-14 days
    cuts = [1 - f for f in tp.TAPER_FRACS]
    assert cuts == sorted(cuts) and cuts[0] < cuts[-1]                 # progressive: deeper into the race
    assert all(0.40 <= c <= 0.60 for c in cuts)                       # 41-60 % (0.40 rounds to its low end)
    # Over the 12 days: the race week (7 days) at the last fraction, the days before it at the first.
    first = tp.TAPER_DAYS - 7
    mean_cut = 1 - (first * tp.TAPER_FRACS[0] + 7 * tp.TAPER_FRACS[-1]) / tp.TAPER_DAYS
    assert 0.41 <= mean_cut <= 0.60


def test_the_b_taper_is_smaller_than_the_a_taper():
    b_cut = 1 - tp.TAPER_FRACS[0]
    a_mean_cut = 1 - (5 * tp.TAPER_FRACS[0] + 7 * tp.TAPER_FRACS[-1]) / 12
    assert tp.B_TAPER_DAYS < tp.TAPER_DAYS and b_cut < a_mean_cut


# ── the B-race volume taper on a hand-made plan ──────────────────────────────────────────────────────
def _s(d, kind="z2", minutes=90, tss=68, **kw):
    return tp.PlannedSession(day=d, day_name=d.strftime("%A"), session_type=kind, duration_min=minutes,
                             tss_estimate=tss, description="", **kw)


def _weeks(window_kinds=None):
    """Two Monday-Sunday weeks, every day ridden (z2 90 min / 68 TSS), then race day (a Monday)."""
    out = []
    for k in range(2):
        start = TODAY + timedelta(days=7 * k)
        kinds = window_kinds if (k == 1 and window_kinds) else ["z2"] * 7
        sessions = [_s(start + timedelta(days=i), kinds[i], 60 if kinds[i] == "vo2max" else 90,
                       80 if kinds[i] == "vo2max" else 68) for i in range(7)]
        out.append(tp.PlannedWeek(week_num=k + 1, start=start, end=start + timedelta(days=6), phase="build1",
                                  tss_target=476, is_stepback=False, sessions=sessions))
    return out


RACE = TODAY + timedelta(days=14)


def _window(weeks, lo, hi):
    return [s for w in weeks for s in w.sessions if lo <= s.day < hi and s.session_type != "rest"]


def test_the_b_taper_cuts_volume_to_its_fraction_of_the_week_before():
    weeks = _weeks()
    ref = sum(s.tss_estimate for s in _window(weeks, RACE - timedelta(days=14), RACE - timedelta(days=7)))
    tp._taper_volume_before(weeks, RACE, tp.B_TAPER_DAYS, tp.TAPER_FRACS[0])
    win = _window(weeks, RACE - timedelta(days=7), RACE)
    assert len(win) == 7                                             # frequency kept: no day turned to rest
    assert sum(s.tss_estimate for s in win) / ref == pytest.approx(tp.TAPER_FRACS[0], abs=0.02)   # a 40 % cut
    assert all(s.duration_min >= tp._VOLUME_MIN_SESSION_MIN for s in win)
    before = [(s.duration_min, s.tss_estimate) for s in win]
    tp._taper_volume_before(weeks, RACE, tp.B_TAPER_DAYS, tp.TAPER_FRACS[0])
    assert [(s.duration_min, s.tss_estimate) for s in win] == before  # idempotent (reforecast runs every sync)


def test_the_b_taper_keeps_intensity_and_frozen_days():
    weeks = _weeks(["vo2max", "z2", "vo2max", "z2", "z2", "z2", "z2"])
    done = weeks[1].sessions[1]
    done.status = "done"
    tp._taper_volume_before(weeks, RACE, tp.B_TAPER_DAYS, tp.TAPER_FRACS[0])
    hard = [s for s in weeks[1].sessions if s.session_type == "vo2max"]
    assert [(s.duration_min, s.tss_estimate) for s in hard] == [(60, 80), (60, 80)]  # intensity untouched
    assert (done.duration_min, done.tss_estimate) == (90, 68)          # a ridden day is history
    assert all(s.duration_min < 90 for s in weeks[1].sessions[3:])


def test_no_reference_load_means_no_cut():
    weeks = _weeks()
    for s in weeks[0].sessions:
        s.session_type, s.duration_min, s.tss_estimate = "rest", 0, 0
    tp._taper_volume_before(weeks, RACE, tp.B_TAPER_DAYS, tp.TAPER_FRACS[0])
    assert all(s.duration_min == 90 for s in weeks[1].sessions)


# ── in a generated plan ───────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def frozen(monkeypatch):
    class _D(date):
        @classmethod
        def today(cls):
            return cls(TODAY.year, TODAY.month, TODAY.day)
    monkeypatch.setattr(tp, "date", _D)
    clock.freeze(TODAY)
    yield
    clock.unfreeze()


AVAIL = [1, 2, 3, 4, 5, 6]


def _goal(events):
    return tp.Goal(goal_type="event", target_date=TODAY + timedelta(weeks=16), event_km=120, event_climb_m=1500,
                   rest_days=[0], available_days=AVAIL, daily_max_hours={d: 1.5 if d < 5 else 3.0 for d in AVAIL},
                   events=events)


def _plan(events):
    return tp.generate_plan(_goal(events), seed_salt=7, current_ctl=45.0, recent_weekly_tss=320.0,
                            athlete=ATHLETE)[1]


B_DAY = TODAY + timedelta(weeks=6, days=6)  # a Sunday on a load week


def test_a_b_race_gets_a_lighter_week_before_it_with_the_same_number_of_rides(frozen):
    lo = B_DAY - timedelta(days=tp.B_TAPER_DAYS)
    plain = _window(_plan([]), lo, B_DAY)
    tapered = _window(_plan([tp.TargetEvent(date=B_DAY, priority="B", name="Club race")]), lo, B_DAY)
    cut = 1 - sum(s.tss_estimate for s in tapered) / sum(s.tss_estimate for s in plain)
    assert 0.25 <= cut <= 0.60, cut
    assert len(tapered) == len(plain)
    # Intensity outside the existing 3 easy days before a B race is kept.
    early = [s.session_type for s in tapered if s.day < B_DAY - timedelta(days=3) and tp._session_is_hit(s)]
    assert early == [s.session_type for s in plain if s.day < B_DAY - timedelta(days=3) and tp._session_is_hit(s)]


def _dump(weeks):
    return [tp.week_to_dict(w) for w in weeks]


@pytest.mark.parametrize("events", [[], [tp.TargetEvent(date=B_DAY, priority="C", name="Crit")]])
def test_plans_without_b_races_never_reach_the_hook(frozen, monkeypatch, events):
    """No race list, or only C races: the #111 hook is never called, so the plan is the one it was."""
    before = _dump(_plan(events))

    def boom(*_a, **_k):
        raise AssertionError("the B-race taper ran on a plan without B races")
    monkeypatch.setattr(tp, "_taper_volume_before", boom)
    assert _dump(_plan(events)) == before
