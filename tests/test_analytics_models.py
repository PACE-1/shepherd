"""Weight trend, W/kg, critical power model and ride comparison (#114, #116)."""
import math
from datetime import date, timedelta

import pytest

import cp_model
import ride_compare
import weight_trend as wt
from fitness_estimation import compute_cp_wprime

TODAY = date(2026, 6, 30)


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


# ── weight trend: exponential smoothing with a 7-day time constant ──────────
def test_a_step_in_daily_weight_closes_by_one_minus_exp_minus_k_over_tau():
    rows = [{"date": day(30), "value": 70.0}] + [{"date": day(29 - k), "value": 72.0} for k in range(30)]
    trend = wt.ewma_trend(wt.merge_readings(rows, []))
    assert trend[0]["trend_kg"] == 70.0
    for k in (1, 7, 14, 30):
        assert trend[k]["trend_kg"] == pytest.approx(72 - 2 * math.exp(-k / 7), abs=0.01)


def test_a_long_gap_moves_the_trend_further_than_one_day():
    t = wt.ewma_trend(wt.merge_readings([{"date": day(7), "value": 70}, {"date": day(0), "value": 71}], []))
    assert t[-1]["trend_kg"] == pytest.approx(70 + (1 - math.exp(-1)), abs=0.01)


def test_typed_weight_wins_over_synced_on_the_same_day_and_impossible_values_drop():
    r = wt.merge_readings([{"date": day(1), "value": 71.0, "source": "manual"}, {"date": day(2), "value": 500}],
                          [{"date": day(1), "value": 75.0}, {"date": day(3), "value": 70.5}, {"date": "bad", "value": 70}])
    assert [(x["date"], x["weight_kg"], x["source"]) for x in r] == [(day(3), 70.5, "intervals.icu"), (day(1), 71.0, "manual")]


def test_w_per_kg_uses_the_ftp_in_force_over_the_trend_weight():
    trend = wt.ewma_trend(wt.merge_readings([{"date": day(10), "value": 70}, {"date": day(0), "value": 70}], []))
    h = wt.wkg_history(trend, [{"date": day(20), "ftp": 250}, {"date": day(5), "ftp": 280}])
    assert [(x["date"], x["w_per_kg"]) for x in h] == [(day(10), round(250 / 70, 2)), (day(5), 4.0), (day(0), 4.0)]


def test_change_over_28_days_needs_a_reading_that_old():
    trend = wt.ewma_trend(wt.merge_readings([{"date": day(3), "value": 70}, {"date": day(0), "value": 70}], []))
    assert wt.change_over(trend, 28, TODAY) is None
    assert wt.change_over([], 28, TODAY) is None


# ── critical power: P = CP + W'/t, linear work-time fit ─────────────────────
def model(cp, wp, durations=(180, 300, 480, 600, 1200)):
    return {t: cp + wp / t for t in durations}


@pytest.mark.parametrize("cp,wp", [(250, 20000), (180, 12000), (380, 30000)])
def test_exact_model_data_recovers_cp_and_wprime(cp, wp):
    f = cp_model.fit_cp(model(cp, wp))
    assert f["status"] == "ok" and f["n_points"] == 5
    assert f["cp_w"] == pytest.approx(cp, abs=0.1) and f["wprime_j"] == pytest.approx(wp, abs=1)
    assert f["cp_se_w"] == pytest.approx(0, abs=0.05) and f["r2"] == 1.0
    # The 1/t linearisation already used for the profile agrees on exact data.
    cp2, wp2 = compute_cp_wprime({t: round(p) for t, p in model(cp, wp, (180, 300, 600, 1200)).items()})
    assert cp2 == pytest.approx(cp, abs=1.5) and wp2 == pytest.approx(wp, rel=0.03)


def test_noisy_efforts_give_the_least_squares_values_and_a_95_interval_holding_the_truth():
    # Reference values: OLS of W = P*t on t, computed independently (numpy.polyfit, cov).
    f = cp_model.fit_cp({180: 365, 300: 314, 600: 284, 1200: 266})
    assert f["cp_w"] == pytest.approx(249.1, abs=0.05) and f["wprime_j"] == pytest.approx(20377, abs=1)
    assert f["cp_se_w"] == pytest.approx(1.05, abs=0.06) and f["wprime_se_j"] == pytest.approx(731, abs=1)
    assert f["see_j"] == 832
    # t(0.975, df=2) = 4.303
    assert f["cp_ci95_w"] == pytest.approx([249.12 - 4.303 * 1.0539, 249.12 + 4.303 * 1.0539], abs=0.1)
    assert f["cp_ci95_w"][0] < 250 < f["cp_ci95_w"][1] and f["wprime_ci95_j"][0] < 20000 < f["wprime_ci95_j"][1]


def test_only_three_to_twenty_minute_efforts_enter_the_fit():
    best = {**model(250, 20000), 5: 1100, 60: 600, 3600: 200}
    f = cp_model.fit_cp(best)
    assert [p["duration_s"] for p in f["points"]] == [180, 300, 480, 600, 1200]
    assert f["cp_w"] == pytest.approx(250, abs=0.1)


def test_too_few_durations_refuse_to_report():
    f = cp_model.fit_cp({300: 320, 1200: 270, 60: 500})
    assert f["status"] == "insufficient" and f["cp_w"] is None and f["wprime_j"] is None and "found 2" in f["reason"]
    assert cp_model.fit_cp({})["status"] == "insufficient"


def test_a_fit_outside_physiological_ranges_is_withheld():
    f = cp_model.fit_cp(model(250, 60000))
    assert f["status"] == "out_of_range" and f["cp_w"] is None and f["cp_ci95_w"] is None


def ride(i, started, efforts):
    return {"ride_id": f"icu_{i}", "started_at": started + "T08:00:00", "np_w": 200, "hr_max": 180,
            "efforts": [{"secs": s, "watts": w} for s, w in efforts.items()]}


def test_history_fits_each_month_end_window_and_skips_runs():
    rides = [ride(1, day(10), {round(t): round(p) for t, p in model(260, 18000).items()} | {1: 900}),
             ride(2, day(200), {round(t): round(p) for t, p in model(230, 22000).items()}),
             {**ride(3, day(5), {t: 600 for t in (180, 300, 600, 1200)}), "np_w": None}]  # a run: no bike power summary
    h = cp_model.history(rides, TODAY, {"ftp": 250, "weight_kg": 70, "max_hr": 190}, months=12, window_days=90)
    assert len(h) == 12 and h[-1]["end_date"] == TODAY.isoformat()
    assert h[-1]["status"] == "ok" and h[-1]["cp_w"] == pytest.approx(260, abs=1) and h[-1]["pmax_w"] == 900
    assert any(x["status"] == "ok" and x["cp_w"] == pytest.approx(230, abs=1) for x in h[:-1])
    assert h[0]["status"] == "insufficient"


# ── ride comparison ─────────────────────────────────────────────────────────
def rec(rid, watts, hr, n, bucket=1, **summary):
    t = list(range(0, n, bucket))
    return {"ride_id": rid, "name": rid, "started_at": "2026-06-01T08:00:00", "ftp_at_ride": 250,
            "samples": {"t_s": t, "power_w": [watts] * len(t), "hr_bpm": [hr] * len(t)}, **summary}


def test_two_whole_rides_keep_their_own_summaries_and_show_b_minus_a():
    a = ride_compare.side(rec("a", 200, 140, 3600, np_w=205, tss=67, duration_s=3600, avg_hr=140), None, None, 250)
    b = ride_compare.side(rec("b", 220, 150, 1800, np_w=225, tss=40, duration_s=1800, avg_hr=150), None, None, 250)
    c = ride_compare.compare(a, b)
    assert c["a"]["summary"]["np_w"] == 205 and c["delta"]["np_w"] == 20 and c["delta"]["duration_s"] == -1800
    assert c["bin_s"] == 6 and len(c["a"]["power_w"]) == 600 and len(c["b"]["power_w"]) == 300
    assert c["a"]["power_w"][0] == 200 and c["b"]["hr_bpm"][0] == 150
    deltas = {e["duration_s"]: e["delta_w"] for e in c["best_efforts"]}
    assert deltas[300] == 20 and deltas[1200] == 20 and 3600 not in deltas  # b is only 30 min long


def test_an_effort_is_summarised_from_its_samples():
    s = ride_compare.side(rec("a", 250, 150, 3600), 600, 1800, 250)
    assert s["start_s"] == 600 and s["end_s"] == 1800
    sm = s["summary"]
    assert sm["duration_s"] == 1200 and sm["np_w"] == 250 and sm["if_pct"] == 100.0
    assert sm["tss"] == pytest.approx(1200 / 3600 * 100, abs=0.1)  # 20 min at FTP = 33.3 TSS
    assert sm["avg_hr"] == 150 and sm["distance_km"] is None


def test_bucketed_samples_expand_to_seconds_and_short_best_efforts_are_dropped():
    a = ride_compare.side(rec("a", 200, 140, 7200, bucket=4), None, None, 250)
    assert len(a["_power"]) == 7200
    c = ride_compare.compare(a, ride_compare.side(rec("b", 210, 140, 7200, bucket=4), None, None, 250))
    assert c["min_best_effort_s"] == 40 and min(e["duration_s"] for e in c["best_efforts"]) == 60
