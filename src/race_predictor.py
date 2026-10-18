"""Race predictor: 5K, 10K, half marathon and marathon from current fitness (#121).

Pure functions, no I/O. Two published models, each with the error its sources report:

* Riegel's endurance model, T2 = T1 * (D2 / D1) ** 1.06 (Riegel PS 1981, "Athletic records
  and human endurance", American Scientist 69(3):285-290). Riegel fitted it to world records
  and gave it for efforts of about 3.5 to 230 minutes. In 2,303 recreational runners
  Vickers and Vertosick (2016, BMC Sports Sci Med Rehabil 8:26) found it well calibrated
  up to the half marathon, but too fast for the marathon: at least 10 minutes too fast for
  half of the runners. So it overestimates ability at long distances for runners without
  specific endurance training. They give no individual error band for the shorter races,
  so none is shown for those.
* The critical-speed hyperbolic model: an effort above critical speed (CS) is exhausted
  when the distance above CS reaches D', so the time for distance D is T = (D - D') / CS
  (Monod and Scherrer 1965; Hill 1993; Jones et al. 2010, Med Sci Sports Exerc
  42(10):1876-1890; Poole et al. 2016, Med Sci Sports Exerc 48(11):2320-2334). It holds
  for efforts of roughly 2 to 30 minutes, so it predicts the 5K and 10K only, and only
  when the predicted time falls in that range. No published error for an individual race
  prediction from CS is cited here, so no range is shown.

The long-run check (longest recent run at least half the race distance before a half
marathon or marathon time is shown) is a coaching rule of thumb, a heuristic and not a
validated model; it is labelled as such wherever it is used.
"""
from __future__ import annotations

RACES = (
    ("5k", "5K", 5000.0),
    ("10k", "10K", 10000.0),
    ("half", "Half marathon", 21097.5),
    ("marathon", "Marathon", 42195.0),
)
LONG_RACES = ("half", "marathon")

RIEGEL_EXPONENT = 1.06
RIEGEL_MIN_S, RIEGEL_MAX_S = 3.5 * 60, 230 * 60   # Riegel 1981
MIN_INPUT_M = 3000.0                               # only runs of 3 km or more feed Riegel
CS_MIN_S, CS_MAX_S = 2 * 60, 30 * 60               # Jones et al. 2010; Poole et al. 2016
LONG_RUN_FRACTION = 0.5                            # heuristic, see module docstring

RIEGEL_METHOD = ("Riegel's endurance model, time = known time x (race distance / known distance) ^ 1.06 "
                 "(Riegel 1981, American Scientist 69:285-290), from your best recent run.")
RIEGEL_CONFIDENCE = (
    "Riegel fitted the model to world records, so it overestimates ability at longer distances for runners "
    "without specific endurance training. In 2,303 recreational runners it was well calibrated up to the half "
    "marathon but predicted the marathon at least 10 minutes too fast for half of them (Vickers and Vertosick "
    "2016, BMC Sports Sci Med Rehabil 8:26). That study gives no individual error band for the shorter races, "
    "so no range is shown for them. The input is your best training run, not a race: if none was a hard "
    "effort the predictions read slow, and moving time leaves out stops.")
CS_METHOD = ("Critical-speed model, time = (race distance - D') / CS (Monod and Scherrer 1965; Jones et al. 2010; "
             "Poole et al. 2016), from your saved critical-speed test.")
CS_CONFIDENCE = (
    "The model holds for efforts of about 2 to 30 minutes, so it gives the 5K and 10K only, and not the half "
    "marathon or marathon. No published error for an individual race prediction from critical speed is cited "
    "here, so no range is shown; the result is only as good as the all-out trials behind it.")
LONG_RUN_RULE = ("Heuristic, not a validated model: a common coaching rule of thumb is that your longest recent run "
                 "should be at least half the race distance before a half marathon or marathon time means much.")
ENDURANCE_CAVEAT = "Assumes specific endurance training for this distance (regular long runs)."
MARATHON_RANGE = ("Likely slower: half of the recreational runners studied ran the marathon at least 10 minutes "
                  "slower than this formula predicts (Vickers and Vertosick 2016).")


def riegel(t1_s: float, d1_m: float, d2_m: float, exponent: float = RIEGEL_EXPONENT) -> float:
    """Riegel's predicted time (s) for ``d2_m`` from a time ``t1_s`` over ``d1_m``."""
    if t1_s <= 0 or d1_m <= 0 or d2_m <= 0:
        raise ValueError("times and distances must be positive")
    return t1_s * (d2_m / d1_m) ** exponent


def cs_time(distance_m: float, cs_m_per_s: float, d_prime_m: float) -> float | None:
    """Time (s) to cover ``distance_m`` under the hyperbolic CS model; None when D <= D' (no prediction)."""
    if cs_m_per_s <= 0 or d_prime_m <= 0 or distance_m <= 0:
        raise ValueError("CS, D' and distance must be positive")
    if distance_m <= d_prime_m:
        return None
    return (distance_m - d_prime_m) / cs_m_per_s


def best_effort(runs: list[dict]) -> dict | None:
    """The run of >= 3 km with the fastest Riegel-equivalent time, or None.

    Each run is {distance_m, time_s, ...}. Ranking by t / d ** 1.06 is the same as ranking by the
    Riegel time at any one target distance, so the choice does not depend on the race.
    """
    ok = [r for r in runs if (r.get("distance_m") or 0) >= MIN_INPUT_M and (r.get("time_s") or 0) > 0]
    return min(ok, key=lambda r: r["time_s"] / r["distance_m"] ** RIEGEL_EXPONENT, default=None)


def _row(key, label, dist, model, status, time_s=None, range_text=None, notes=()):
    return {"race": key, "label": label, "distance_m": dist, "model": model, "status": status,
            "time_s": round(time_s, 1) if time_s is not None else None,
            "pace_s_per_km": round(time_s / dist * 1000, 1) if time_s is not None else None,
            "range_text": range_text, "notes": list(notes)}


def riegel_predictions(best: dict, longest_m: float) -> list[dict]:
    out = []
    for key, label, dist in RACES:
        t = riegel(best["time_s"], best["distance_m"], dist)
        notes = [ENDURANCE_CAVEAT] if key in LONG_RACES else []
        if not RIEGEL_MIN_S <= t <= RIEGEL_MAX_S:
            notes.append("Outside the 3.5 to 230 minute range Riegel fitted the model to.")
        if key in LONG_RACES and longest_m < LONG_RUN_FRACTION * dist:
            out.append(_row(key, label, dist, "riegel", "not_enough_long_run", notes=[
                f"Not enough long-run history: your longest run in the window is {longest_m / 1000:.1f} km, "
                f"under half of {dist / 1000:.1f} km (heuristic)."]))
            continue
        out.append(_row(key, label, dist, "riegel", "ok", t, MARATHON_RANGE if key == "marathon" else None, notes))
    return out


def cs_predictions(cs_m_per_s: float, d_prime_m: float) -> list[dict]:
    out = []
    for key, label, dist in RACES:
        if key in LONG_RACES:
            out.append(_row(key, label, dist, "critical_speed", "not_supported",
                            notes=["The critical-speed model covers efforts of about 2 to 30 minutes; it does not predict this race."]))
            continue
        t = cs_time(dist, cs_m_per_s, d_prime_m)
        if t is None or not CS_MIN_S <= t <= CS_MAX_S:
            out.append(_row(key, label, dist, "critical_speed", "out_of_range",
                            notes=["Your predicted time is outside the 2 to 30 minute range the critical-speed model holds for."]))
            continue
        out.append(_row(key, label, dist, "critical_speed", "ok", t))
    return out


def predict(runs: list[dict], cs: dict | None) -> dict:
    """Predictions from recent runs ({distance_m, time_s, ...}) and an optional {cs_m_per_s, d_prime_m}."""
    best = best_effort(runs)
    longest = max((r.get("distance_m") or 0 for r in runs), default=0)
    preds, missing = [], []
    if best:
        preds += riegel_predictions(best, longest)
    else:
        missing.append("No run of 3 km or more in the window, so there is no Riegel prediction.")
    if cs:
        preds += cs_predictions(cs["cs_m_per_s"], cs["d_prime_m"])
    else:
        missing.append("Save a critical-speed test (Run zones) to get 5K and 10K from critical speed.")
    return {"best_run": best, "longest_run_m": longest or None, "predictions": preds, "missing": missing,
            "riegel_method": RIEGEL_METHOD, "riegel_confidence": RIEGEL_CONFIDENCE,
            "cs_method": CS_METHOD, "cs_confidence": CS_CONFIDENCE, "long_run_rule": LONG_RUN_RULE}
