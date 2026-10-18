"""Readiness across sports (#128): the form input is all-sports already, and a cycling-only rider sees no change."""
from datetime import date, timedelta

import fitness
import multisport as ms
from readiness import compute_readiness

TODAY = date(2026, 10, 18)


def act(days_ago, sport, tss):
    return {"date": (TODAY - timedelta(days=days_ago)).isoformat(), "sport": sport, "tss": tss}


def test_cycling_only_history_has_combined_load_equal_to_the_cycling_line():
    # If a combined line ever feeds readiness, a rider who only rides must get the same numbers.
    rides = [act(i, "Ride", 40 + i % 5) for i in range(0, 120, 2)] + [act(3, "VirtualRide", 55)]
    r = ms.load_by_sport(rides, TODAY)
    assert list(r["sports"]) == ["cycling"]
    assert r["combined"] == r["sports"]["cycling"]


def test_other_sports_add_to_combined_load_and_leave_the_cycling_line_alone():
    rides = [act(i, "Ride", 50) for i in range(0, 60, 2)]
    both = ms.load_by_sport(rides + [act(1, "Run", 60), act(2, "Swim", 30)], TODAY)
    only = ms.load_by_sport(rides, TODAY)
    assert both["sports"]["cycling"] == only["sports"]["cycling"]
    assert both["combined"]["week_load"] == only["combined"]["week_load"] + 90
    assert both["combined"]["atl"] > only["combined"]["atl"]


def test_readiness_form_is_intervals_icu_fitness_not_derived_from_rides():
    # The TSB readiness scores comes from fitness.state (intervals.icu's all-sports CTL/ATL), whatever rides are stored.
    s = fitness.state({"ctl": 50, "atl": 60}, TODAY)
    assert (s["tsb"], s["source"]) == (-10.0, "icu")
    low = compute_readiness(ln_rmssd_7d=3.2, swc_lower=3.0, swc_upper=3.4, tsb=s["tsb"], sleep_h=7.5, rhr_delta=0.0)
    assert low["components"]["tsb"] == 50.0  # (-10 - -30) / 40
