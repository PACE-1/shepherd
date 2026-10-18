"""Fueling guidance (#112): carbohydrate during a session and across the day. Pure functions; no I/O.

Sources (docs/SCIENCE.md section 1d):
- [J] Jeukendrup AE. A step towards personalized sports nutrition: carbohydrate intake during exercise.
  Sports Med 2014;44 Suppl 1:S25-33.
- [A] Thomas DT, Erdman KA, Burke LM. American College of Sports Medicine Joint Position Statement
  (ACSM / Academy of Nutrition and Dietetics / Dietitians of Canada). Nutrition and athletic
  performance. Med Sci Sports Exerc 2016;48(3):543-568.
- [E] Ettema G, Loras HW. Efficiency in cycling: a review. Eur J Appl Physiol 2009;106(1):1-14
  (gross efficiency about 20 to 25%; used only for the approximate ride-energy figure).

Confidence: these are general, population-level guidelines. Gut tolerance, intensity, heat and the
rider's own practice move the right number; they are not medical advice. No calorie target is
computed: that would need a resting-energy equation and activity factors this app does not have.
"""
from __future__ import annotations

NOT_MEDICAL_ADVICE = ("General sports-nutrition guidance from published position statements. Individual "
                      "tolerance varies, so practise race fueling in training. Not medical advice.")
HOURLY_METHOD = ("Carbohydrate during exercise by duration: none needed under 45 min, small amounts or a "
                 "mouth rinse at 45 to 75 min, 30 to 60 g/h for 1 to 2.5 h, up to 90 g/h beyond 2.5 h "
                 "from multiple transportable carbohydrates (glucose plus fructose). Jeukendrup 2014; "
                 "ACSM/AND/DC 2016.")
DAILY_METHOD = ("Daily carbohydrate in g per kg body mass by the day's training: light 3 to 5, moderate "
                "(about 1 h) 5 to 7, high (1 to 3 h) 6 to 10, very high (4 to 5 h or more) 8 to 12. "
                "ACSM/AND/DC 2016.")
ENERGY_METHOD = ("Approximate: ride energy in kcal from the mechanical work in kJ, assuming about 24% "
                 "gross efficiency (trained cyclists are about 20 to 25%, Ettema and Loras 2009), which "
                 "makes kcal burned roughly equal to kJ of work.")

# Duration cut points in minutes. 45 and 75 bound [A]'s "45 to 75 min" band; 150 is [J]/[A]'s 2.5 h.
# The 60 to 75 min overlap between [A]'s "45 to 75 min" and "1 to 2.5 h" bands goes to the shorter band.
SHORT_MIN, MEDIUM_MIN, LONG_MIN = 45, 75, 150
# [A] gives "very high" as 4 to 5 h or more a day; the 3 to 4 h gap in its table is counted as "high".
VERY_HIGH_MIN = 240
LIGHT_TYPES = {"rest", "recovery"}     # [A]'s "light: low-intensity or skill-based activities"

# (band, g/h low, g/h high, note). [J] Fig. 1 and [A] "acute fuelling strategies".
_HOURLY = {
    "none": (0, 0, "Not needed for sessions under 45 minutes."),
    "small": (0, 0, "Small amounts, or a carbohydrate mouth rinse. No hourly target."),
    "moderate": (30, 60, "30 to 60 g per hour."),
    # [J] and [A] give "up to 90 g/h"; the range starts at 60, where the 1 to 2.5 h band ends ([J]: 2 to 3 h,
    # up to 60 g/h). Above 60 g/h it needs glucose plus fructose ("multiple transportable carbohydrates").
    "high": (60, 90, "Up to 90 g per hour, from a glucose plus fructose mix. Build up to it in training."),
}

# g per kg body mass per day, [A] Table 2 ("daily needs for fuel and recovery").
_DAILY = {"light": (3, 5), "moderate": (5, 7), "high": (6, 10), "very_high": (8, 12)}


def hourly_band(duration_min: float) -> str:
    d = max(0.0, float(duration_min or 0))
    if d < SHORT_MIN:
        return "none"
    if d < MEDIUM_MIN:
        return "small"
    if d <= LONG_MIN:
        return "moderate"
    return "high"


def during_session(duration_min: float) -> dict:
    """Carbohydrate during one session: the per-hour range and the total over its duration."""
    band = hourly_band(duration_min)
    lo, hi, note = _HOURLY[band]
    h = max(0.0, float(duration_min or 0)) / 60
    return {"band": band, "low_g_per_h": lo, "high_g_per_h": hi,
            "low_g": round(lo * h), "high_g": round(hi * h), "note": note}


def day_load(duration_min: float, session_type: str = "") -> str:
    """[A]'s training-load category for a day with this much planned training."""
    d = max(0.0, float(duration_min or 0))
    if (session_type or "").lower() in LIGHT_TYPES or d < SHORT_MIN:
        return "light"
    if d < MEDIUM_MIN:
        return "moderate"
    if d < VERY_HIGH_MIN:
        return "high"
    return "very_high"


def daily_carbs(weight_kg: float, duration_min: float, session_type: str = "") -> dict:
    """The day's carbohydrate range in g/kg and in grams for this rider."""
    load = day_load(duration_min, session_type)
    lo, hi = _DAILY[load]
    w = float(weight_kg)
    return {"load": load, "low_g_per_kg": lo, "high_g_per_kg": hi, "low_g": round(lo * w), "high_g": round(hi * w)}


GROSS_EFFICIENCY = 0.24
KJ_PER_KCAL = 4.184


def ride_kcal(work_kj: float) -> float:
    """Approximate energy burned from mechanical work (ENERGY_METHOD): kJ / (0.24 x 4.184), about kJ x 1.0."""
    return round(max(0.0, float(work_kj or 0)) / (GROSS_EFFICIENCY * KJ_PER_KCAL))
