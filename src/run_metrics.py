"""Running zones, critical speed, grade-adjusted pace and run load (#118, #119).

Pure functions, no I/O. Every number comes from a named, published method:

* Critical speed: the linear distance-time form of the two-parameter hyperbolic
  model, D = D' + CS * T (Monod and Scherrer 1965; Hill 1993; reviewed in
  Jones and Vanhatalo 2017, Sports Med 47(S1):65-78, and Poole et al. 2016,
  Med Sci Sports Exerc 48(11):2320-2334). Two trials give CS = (D2 - D1) / (T2 - T1)
  and D' = D1 - CS * T1; three are fitted by least squares. Trials of about
  2 to 15 minutes are the range those reviews recommend.
* Pace zones: Joe Friel's run pace zones as a percentage of threshold pace
  (time per km), from Friel's "Quick Guide to Setting Zones" (TrainingPeaks).
* Heart-rate zones: Friel's run zones as a percentage of lactate-threshold HR
  (same source; the running table, not the cycling one).
* Grade-adjusted pace: the energy cost of running against gradient from Minetti
  et al. 2002, J Appl Physiol 93:1039-1046 (fifth-order polynomial, gradients
  -0.45 to +0.45). The flat pace with the same metabolic power is
  pace * Cr(0) / Cr(i).
* rTSS: TrainingPeaks' running TSS, hours * IF^2 * 100 with IF = speed / threshold
  speed. TrainingPeaks uses normalised graded pace (NGP) for the speed; NGP needs a
  pace and gradient stream, which Shepherd does not store for runs, so the
  activity-level value here uses average speed and says so.
* hrTSS: Banister's training impulse, TRIMP = minutes * x * a * exp(b * x) with
  x = (HRavg - HRrest) / (HRmax - HRrest) and a, b = 0.64, 1.92 for men and
  0.86, 1.67 for women (Banister 1991; Morton, Fitz-Clarke and Banister 1990,
  J Appl Physiol 69:1171-1177), scaled so one hour at LTHR = 100.
* Step and stride length: speed / cadence; a stride is two steps.
"""
from __future__ import annotations

import math

# ── critical speed ───────────────────────────────────────────────────────────
TRIAL_MIN_S, TRIAL_MAX_S = 120, 900  # 2 to 15 min (Jones and Vanhatalo 2017; Poole et al. 2016)

CS_METHOD = ("Critical speed from the linear distance-time model D = D' + CS x T "
             "(Monod and Scherrer 1965; Hill 1993; Jones and Vanhatalo 2017; Poole et al. 2016).")


def critical_speed(trials: list[tuple[float, float]]) -> dict:
    """CS (m/s) and D' (m) from 2 or 3 all-out trials given as (distance_m, time_s).

    Raises ValueError when the trials cannot give a physiological fit.
    """
    if not 2 <= len(trials) <= 3:
        raise ValueError("give two or three time trials")
    pts = []
    for d, t in trials:
        if isinstance(d, bool) or isinstance(t, bool) or not isinstance(d, (int, float)) or not isinstance(t, (int, float)):
            raise ValueError("each trial needs a distance in metres and a time in seconds")
        if d <= 0 or t <= 0:
            raise ValueError("distances and times must be positive")
        pts.append((float(d), float(t)))
    times = [t for _, t in pts]
    if len(set(times)) != len(times):
        raise ValueError("the trials need different durations")
    n = len(pts)
    mt = sum(times) / n
    md = sum(d for d, _ in pts) / n
    sxx = sum((t - mt) ** 2 for t in times)
    cs = sum((t - mt) * (d - md) for d, t in pts) / sxx  # equals (D2 - D1) / (T2 - T1) for two trials
    dprime = md - cs * mt
    if cs <= 0:
        raise ValueError("the longer trial must cover more distance")
    if dprime <= 0:
        raise ValueError("these trials give no distance above critical speed (D' <= 0); check the numbers or run them all-out")
    r2 = None
    if n == 3:
        ss_res = sum((d - (dprime + cs * t)) ** 2 for d, t in pts)
        ss_tot = sum((d - md) ** 2 for d, _ in pts)
        r2 = round(1 - ss_res / ss_tot, 4) if ss_tot else None
    warnings = [f"A {round(t)} s trial is outside the 2 to 15 minute range the method is built on."
                for t in times if not TRIAL_MIN_S <= t <= TRIAL_MAX_S]
    return {
        "cs_m_per_s": round(cs, 3),
        "cs_pace_s_per_km": round(1000 / cs, 1),
        "d_prime_m": round(dprime, 1),
        "r2": r2,
        "n_trials": n,
        "warnings": warnings,
        "method": CS_METHOD,
        "confidence": (
            ("Two trials fit the line exactly, so there is no error estimate; a third trial gives one (R squared). " if n == 2
             else "Three trials: R squared shows how well they agree with the model. ")
            + "Critical speed marks the heavy-severe boundary and usually sits a little faster than the pace you can hold "
              "for an hour (Jones et al. 2019, Physiol Rep 7:e14098), so zones built from it run slightly hard."),
    }


# ── zones (Friel) ────────────────────────────────────────────────────────────
# Pace: (zone, name, slow %, fast %) of threshold pace as time per km, so slow % >= fast %; None = open-ended.
# Friel's published table overlaps at 99-100 % (Z4 and Z5a); kept as published.
FRIEL_PACE = (
    ("1", "Recovery", None, 129),
    ("2", "Aerobic", 129, 114),
    ("3", "Tempo", 113, 106),
    ("4", "Sub-threshold", 105, 99),
    ("5a", "Super-threshold", 100, 97),
    ("5b", "Aerobic capacity", 96, 90),
    ("5c", "Anaerobic capacity", 90, None),
)
# HR: (zone, name, low %, high %) of LTHR.
FRIEL_HR = (
    ("1", "Recovery", None, 85),
    ("2", "Aerobic", 85, 89),
    ("3", "Tempo", 90, 94),
    ("4", "Sub-threshold", 95, 99),
    ("5a", "Super-threshold", 100, 102),
    ("5b", "Aerobic capacity", 103, 106),
    ("5c", "Anaerobic capacity", 106, None),
)
ZONES_METHOD = "Joe Friel's run zones: pace as a percentage of threshold pace, heart rate as a percentage of lactate-threshold heart rate."
ZONES_CONFIDENCE = ("Friel's zones are a coaching convention built on the threshold you enter; they are only as good as "
                    "that threshold, and the boundaries are not individually tested.")


def pace_zones(threshold_s_per_km: float) -> list[dict]:
    """Friel pace zones with s/km bounds; None is open-ended (Z1 has no slow bound, Z5c no fast bound)."""
    def at(pct):
        return round(threshold_s_per_km * pct / 100, 1) if pct is not None else None
    return [{"zone": zone, "name": name, "slow_pct": slow, "fast_pct": fast,
             "slow_s_per_km": at(slow), "fast_s_per_km": at(fast)}
            for zone, name, slow, fast in FRIEL_PACE]


def hr_zones(lthr: float) -> list[dict]:
    """Friel run HR zones in bpm (rounded); None is open-ended."""
    return [{"zone": zone, "name": name, "low_pct": lo, "high_pct": hi,
             "low_bpm": round(lthr * lo / 100) if lo is not None else None,
             "high_bpm": round(lthr * hi / 100) if hi is not None else None}
            for zone, name, lo, hi in FRIEL_HR]


# ── grade-adjusted pace (Minetti et al. 2002) ────────────────────────────────
MINETTI_MAX_GRADE = 0.45
GAP_METHOD = "Minetti et al. 2002 energy cost of running against gradient; the flat pace with the same metabolic power."
GAP_CONFIDENCE = ("Measured on a treadmill in trained runners at steady speeds; downhill benefit is the least certain part, "
                  "and technical or loose terrain costs more than the model says.")


def minetti_cost(grade: float) -> float:
    """Energy cost of running, J/kg/m, at gradient ``grade`` (rise/run fraction, -0.45 to 0.45)."""
    if not -MINETTI_MAX_GRADE <= grade <= MINETTI_MAX_GRADE:
        raise ValueError("the Minetti model covers gradients from -45 % to +45 %")
    i = grade
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def grade_adjusted_pace(pace_s_per_km: float, grade: float) -> float:
    """Flat-ground pace (s/km) needing the same metabolic power as ``pace_s_per_km`` on ``grade``."""
    if pace_s_per_km <= 0:
        raise ValueError("pace must be positive")
    return pace_s_per_km * minetti_cost(0.0) / minetti_cost(grade)


# ── load ─────────────────────────────────────────────────────────────────────
def rtss(duration_s: float, speed_m_per_s: float, threshold_speed_m_per_s: float) -> float | None:
    """TrainingPeaks rTSS = hours * IF^2 * 100, IF = speed / threshold speed."""
    if duration_s <= 0 or speed_m_per_s <= 0 or threshold_speed_m_per_s <= 0:
        return None
    intensity = speed_m_per_s / threshold_speed_m_per_s
    return round(duration_s / 3600 * intensity**2 * 100, 1)


_TRIMP = {"M": (0.64, 1.92), "F": (0.86, 1.67)}  # Morton, Fitz-Clarke and Banister 1990


def banister_trimp(minutes: float, avg_hr: float, rest_hr: float, max_hr: float, sex: str) -> float | None:
    """Banister TRIMP. None when sex is not M or F (the model has no other coefficients) or HR is out of range."""
    if sex not in _TRIMP or minutes <= 0 or not rest_hr < avg_hr <= max_hr:
        return None
    a, b = _TRIMP[sex]
    x = (avg_hr - rest_hr) / (max_hr - rest_hr)
    return minutes * x * a * math.exp(b * x)


def hrtss(duration_s: float, avg_hr: float, lthr: float, rest_hr: float, max_hr: float, sex: str) -> float | None:
    """TRIMP of the session scaled so 60 minutes at LTHR scores 100."""
    if not rest_hr < lthr <= max_hr:
        return None
    t = banister_trimp(duration_s / 60, avg_hr, rest_hr, max_hr, sex)
    ref = banister_trimp(60, lthr, rest_hr, max_hr, sex)
    return round(100 * t / ref, 1) if t is not None and ref else None


# ── cadence and stride ───────────────────────────────────────────────────────
def steps_per_minute(cadence: float | None) -> tuple[float, bool] | None:
    """Reads a recorded running cadence as steps per minute: (spm, doubled).

    FIT files store running cadence per foot (strides per minute), while most apps show
    steps per minute, twice that. A running value below 120 can only be per-foot, so it is
    doubled and flagged. This is a unit check, not a physiological model; anything under 60
    is treated as no reading.
    """
    if isinstance(cadence, bool) or not isinstance(cadence, (int, float)) or cadence < 60:
        return None
    return (float(cadence), False) if cadence >= 120 else (2.0 * cadence, True)


def step_and_stride(speed_m_per_s: float, cadence_spm: float) -> tuple[float, float] | None:
    """(step length, stride length) in metres from speed and cadence in steps per minute."""
    if speed_m_per_s <= 0 or cadence_spm <= 0:
        return None
    step = speed_m_per_s * 60 / cadence_spm
    return round(step, 2), round(2 * step, 2)
