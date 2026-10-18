"""Swim critical speed (CSS), swim load (sTSS) and the stroke data intervals.icu stores (#122).

Pure functions, no I/O. Every number comes from a named, published method:

* Critical swim speed: the slope of the distance-time line from all-out swims,
  D = a + CS * T (Wakayoshi et al. 1992, Eur J Appl Physiol 64:153-157, fitted over
  50 to 400 m). The common two-swim test, CS = (D400 - D200) / (T400 - T200), is the
  simplified method of Wakayoshi et al. 1993, Int J Sports Med 14(7):368-372. Pace per
  100 m = 100 / CS. The fit itself is run_metrics.critical_speed (the same linear model).
* sTSS: TrainingPeaks' swim training stress score, hours * IF^3 * 100 with
  IF = swim speed / threshold swim speed (TrainingPeaks help centre, "Calculating Swim
  Training Stress Score (sTSS)"). The cube is TrainingPeaks' convention for drag in
  water; it is a load convention, not a validated physiological model. TrainingPeaks
  uses a normalised swim speed; Shepherd keeps no swim pace stream, so the
  activity-level value uses average speed and says so.

Swim pace zones are NOT here: no zone table with exact percentages of CSS could be
cited precisely, so none is shipped (science rule). See ZONES_NOTE.

Stroke data: intervals.icu's activity summary (the ``raw_json`` Shepherd stores) has
``pool_length``, ``lengths`` and ``average_cadence`` for swims, and no stroke count or
SWOLF field (checked against the generated intervals.icu API types in
paladini/node-intervals-icu src/types/activity.ts @27659b8 and the full activity column
list in mvanhorn/printing-press-library library/other/intervals-icu/internal/store/store.go
@a09fb04). So stroke count and SWOLF are not shown.
"""
from __future__ import annotations

import run_metrics as rm

CSS_METHOD = ("Critical swim speed: the slope of distance against time from all-out swims (Wakayoshi et al. 1992); "
              "the 400 m and 200 m test, CSS = (400 - 200) / (T400 - T200), is Wakayoshi et al. 1993's simple method.")
CSS_CONFIDENCE = ("Two swims fit the line exactly, so there is no error estimate. In Wakayoshi's swimmers CSS tracked "
                  "the speed at a blood lactate of 4 mmol/l and 400 m performance, but later work found it can sit a "
                  "little above the speed you can hold at a steady lactate (Dekerle et al. 2005, Int J Sports Med "
                  "26:524-530). Swim both trials all-out, in the same pool.")
ZONES_NOTE = ("Swim pace zones are not shown: Shepherd could not cite a published zone table with exact percentages "
              "of CSS, so it gives the CSS pace itself and leaves zones out rather than guess them.")

STSS_METHOD = "sTSS: TrainingPeaks swim TSS, hours x IF cubed x 100, IF = average speed / CSS."
STSS_CONFIDENCE = ("Low to moderate. The cube is TrainingPeaks' convention (drag in water rises steeply with speed), "
                   "not a tested measure of strain. Shepherd keeps no swim pace stream, so IF uses average speed over "
                   "moving time instead of TrainingPeaks' normalised swim speed; rests and drills pull it down. "
                   "Open-water distance comes from GPS, which is rougher in water than a counted pool length, so pace "
                   "and sTSS there are less certain. Compare with intervals.icu's load in the same row.")
STROKE_NOTE = ("Stroke rate is intervals.icu's average cadence for the swim, as the watch recorded it; devices differ "
               "in whether one stroke is one arm pull or a full cycle. Stroke count and SWOLF are not in the activity "
               "summary Shepherd stores, so they are not shown.")


def css(trials: list[tuple[float, float]]) -> dict:
    """CSS from two (or three) all-out swims given as (distance_m, time_s).

    Raises ValueError when the swims cannot give a fit (same as run_metrics.critical_speed).
    """
    fit = rm.critical_speed(trials)
    cs = fit["cs_m_per_s"]
    return {
        "css_m_per_s": cs,
        "css_s_per_100m": round(100 / cs, 1),
        "anaerobic_distance_m": fit["d_prime_m"],
        "r2": fit["r2"],
        "n_trials": fit["n_trials"],
        "method": CSS_METHOD,
        "confidence": CSS_CONFIDENCE,
    }


def stss(duration_s: float, speed_m_per_s: float, css_m_per_s: float) -> float | None:
    """TrainingPeaks sTSS = hours * IF^3 * 100, IF = speed / CSS."""
    if duration_s <= 0 or speed_m_per_s <= 0 or css_m_per_s <= 0:
        return None
    intensity = speed_m_per_s / css_m_per_s
    return round(duration_s / 3600 * intensity**3 * 100, 1)


def water(activity_type: str | None, raw: dict) -> str:
    """'open_water' for intervals.icu's OpenWaterSwim, 'pool' when a pool length is recorded, else 'unknown'."""
    kind = (activity_type or "").replace(" ", "").replace("_", "").lower()
    if kind == "openwaterswim":
        return "open_water"
    pool = raw.get("pool_length")
    return "pool" if isinstance(pool, (int, float)) and not isinstance(pool, bool) and pool > 0 else "unknown"


def stroke_fields(raw: dict) -> dict:
    """The swim fields intervals.icu stores, as they are: pool length (m), lengths, average cadence."""
    def num(k):
        v = raw.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None
    lengths = num("lengths")
    return {"pool_length_m": num("pool_length"), "lengths": int(lengths) if lengths else None,
            "stroke_rate": num("average_cadence")}
