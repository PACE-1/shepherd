"""Two-parameter critical power model fitted to the rider's power curve (#114).

Model: P(t) = CP + W'/t (Monod & Scherrer 1965), the boundary between heavy
and severe exercise (Jones et al. 2019, Physiol Rep 7:e14098). Fitted by the
linear work-time form W = CP * t + W' (W = P * t, the work done in the best
effort of duration t): ordinary least squares, slope = CP, intercept = W'
(Hill 1993, Sports Med 16:237-54, lists it with the 1/t form that
``fitness_estimation.compute_cp_wprime`` uses for the profile value).

Inputs are the best efforts of 3-20 min (``MONOD_DURATIONS_S`` bounds;
shorter is VO2max/sprint dominated, longer drifts towards FTP). Confidence is
the 95 % interval from the regression's standard errors (Student t, n-2
degrees of freedom), fit quality is R^2 and the standard error of the
estimate. Caveat stated in the response: a mean-max curve takes each duration
from the best ride in the window, not from separate exhaustive trials, so CP
is an estimate from training data, not a laboratory test.

No fit is reported with fewer than ``MONOD_MIN_POINTS`` durations, or when CP
or W' fall outside the ranges the profile accepts (same gate as
``compute_cp_wprime``).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from fitness_estimation import MONOD_DURATIONS_S, MONOD_MIN_POINTS

T_MIN_S, T_MAX_S = min(MONOD_DURATIONS_S), max(MONOD_DURATIONS_S)
# Same physiological gates as fitness_estimation.compute_cp_wprime (profile validators).
CP_RANGE_W = (100.0, 500.0)
WPRIME_RANGE_J = (5000.0, 40000.0)
METHOD = ("Two-parameter critical power model P = CP + W'/t (Monod & Scherrer 1965), "
          "fitted by linear work-time regression W = CP*t + W' on your best 3-20 min efforts; "
          "95% intervals from the regression standard errors.")
CAVEAT = ("Your best efforts come from training rides, not separate all-out trials, "
          "so treat CP and W' as estimates.")

# Two-sided 95 % Student t critical values, df = 1..30; 1.96 beyond.
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


def _t95(df: int) -> float:
    return _T95[df - 1] if 1 <= df <= len(_T95) else 1.96


def fit_cp(best: dict[int, float]) -> dict:
    """Fit CP and W' to {duration_s: watts}. Always returns a dict with
    ``status`` ok | insufficient | out_of_range and a ``reason``."""
    pts = sorted((int(t), float(p)) for t, p in (best or {}).items()
                 if p and p > 0 and T_MIN_S <= int(t) <= T_MAX_S)
    base = {"status": "insufficient", "reason": "", "n_points": len(pts),
            "points": [{"duration_s": t, "watts": round(p), "work_j": round(p * t)} for t, p in pts],
            "cp_w": None, "wprime_j": None, "cp_ci95_w": None, "wprime_ci95_j": None,
            "cp_se_w": None, "wprime_se_j": None, "r2": None, "see_j": None}
    if len(pts) < MONOD_MIN_POINTS:
        base["reason"] = (f"Needs best efforts at {MONOD_MIN_POINTS} or more durations between "
                          f"{T_MIN_S // 60} and {T_MAX_S // 60} min; found {len(pts)}.")
        return base
    n = len(pts)
    xs = [t for t, _ in pts]
    ys = [p * t for t, p in pts]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    cp = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    wp = my - cp * mx
    ss_res = sum((y - (cp * x + wp)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    s = math.sqrt(ss_res / (n - 2))
    se_cp = s / math.sqrt(sxx)
    se_wp = s * math.sqrt(1.0 / n + mx * mx / sxx)
    t = _t95(n - 2)
    base.update({
        "cp_w": round(cp, 1), "wprime_j": round(wp),
        "cp_se_w": round(se_cp, 1), "wprime_se_j": round(se_wp),
        "cp_ci95_w": [round(cp - t * se_cp, 1), round(cp + t * se_cp, 1)],
        "wprime_ci95_j": [round(wp - t * se_wp), round(wp + t * se_wp)],
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "see_j": round(s),
    })
    if not (CP_RANGE_W[0] <= cp <= CP_RANGE_W[1]) or not (WPRIME_RANGE_J[0] <= wp <= WPRIME_RANGE_J[1]):
        base["status"] = "out_of_range"
        base["reason"] = (f"The fit (CP {cp:.0f} W, W' {wp / 1000:.1f} kJ) is outside "
                          f"{CP_RANGE_W[0]:.0f}-{CP_RANGE_W[1]:.0f} W or "
                          f"{WPRIME_RANGE_J[0] / 1000:.0f}-{WPRIME_RANGE_J[1] / 1000:.0f} kJ, so it is not shown.")
        for k in ("cp_w", "wprime_j", "cp_ci95_w", "wprime_ci95_j", "cp_se_w", "wprime_se_j"):
            base[k] = None
        return base
    base["status"] = "ok"
    return base


def window_bests(rides: list[dict], end: date, days: int, profile: dict) -> tuple[dict[int, int], int | None]:
    """Best watts per duration over cycling rides started in (end-days, end],
    plus Pmax (best 1 s, else 5 s), applying power_curve's cycling and
    sensor-glitch filters, the same rules as ``aggregate_power_curve``."""
    from power_curve import _is_cycling_power_ride, _ride_started_iso_date, is_sensor_glitch
    lo, hi = (end - timedelta(days=days)).isoformat(), end.isoformat()
    best: dict[int, int] = {}
    for r in rides:
        if not (lo <= _ride_started_iso_date(r) <= hi) or not _is_cycling_power_ride(r):
            continue
        for e in r.get("efforts") or []:
            if not isinstance(e, dict):
                continue
            try:
                secs, watts = int(e.get("secs") or 0), int(e.get("watts") or 0)
            except (TypeError, ValueError):
                continue
            if secs > 0 and watts > 0 and not is_sensor_glitch(e, r, profile) and watts > best.get(secs, 0):
                best[secs] = watts
    return best, best.get(1) or best.get(5)


def history(rides: list[dict], today: date, profile: dict, months: int = 12, window_days: int = 90,
            weight_at=None) -> list[dict]:
    """CP, W' and Pmax from the ``window_days`` before each month end over the
    last ``months`` months (the current month ends today), plus the best 5 and
    20 minute power in the same window and, when ``weight_at(iso_date)`` gives a
    trend weight, those as W/kg."""
    ends, d = [], today
    for _ in range(months):
        ends.append(d)
        d = d.replace(day=1) - timedelta(days=1)
    out = []
    for end in reversed(ends):
        best, pmax = window_bests(rides, end, window_days, profile)
        f = fit_cp(best)
        kg = weight_at(end.isoformat()) if weight_at else None
        w5, w20 = best.get(300), best.get(1200)
        out.append({"end_date": end.isoformat(), "status": f["status"], "cp_w": f["cp_w"],
                    "wprime_j": f["wprime_j"], "cp_ci95_w": f["cp_ci95_w"], "pmax_w": pmax,
                    "w_5min": w5, "w_20min": w20,
                    "w_per_kg_5min": round(w5 / kg, 2) if w5 and kg else None,
                    "w_per_kg_20min": round(w20 / kg, 2) if w20 and kg else None})
    return out
