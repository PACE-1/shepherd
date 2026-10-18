"""Fueling guidance (#112): reference values from Jeukendrup 2014 and the ACSM/AND/DC 2016 statement,
including the boundaries between duration bands."""
import pytest

import fueling


@pytest.mark.parametrize("minutes,band,lo,hi", [
    (0, "none", 0, 0), (30, "none", 0, 0), (44, "none", 0, 0),          # < 45 min: not needed
    (45, "small", 0, 0), (60, "small", 0, 0), (74, "small", 0, 0),       # 45-75 min: mouth rinse
    (75, "moderate", 30, 60), (120, "moderate", 30, 60), (150, "moderate", 30, 60),  # 1-2.5 h: 30-60 g/h
    (151, "high", 60, 90), (240, "high", 60, 90), (360, "high", 60, 90),  # > 2.5 h: up to 90 g/h
])
def test_hourly_bands_follow_the_cited_durations(minutes, band, lo, hi):
    d = fueling.during_session(minutes)
    assert (d["band"], d["low_g_per_h"], d["high_g_per_h"]) == (band, lo, hi)


def test_session_totals_scale_with_duration():
    assert fueling.during_session(120)["low_g"] == 60 and fueling.during_session(120)["high_g"] == 120
    four_h = fueling.during_session(240)
    assert (four_h["low_g"], four_h["high_g"]) == (240, 360)
    assert fueling.during_session(30)["high_g"] == 0
    assert "multiple" in fueling.HOURLY_METHOD and "glucose plus fructose" in fueling.during_session(200)["note"]


@pytest.mark.parametrize("minutes,stype,load,lo,hi", [
    (0, "rest", "light", 3, 5), (60, "recovery", "light", 3, 5), (44, "endurance", "light", 3, 5),
    (45, "endurance", "moderate", 5, 7), (74, "threshold", "moderate", 5, 7),
    (75, "endurance", "high", 6, 10), (180, "long_z2", "high", 6, 10), (239, "long_z2", "high", 6, 10),
    (240, "long_z2", "very_high", 8, 12), (300, "long_z2", "very_high", 8, 12),
])
def test_daily_ranges_are_the_acsm_g_per_kg_bands(minutes, stype, load, lo, hi):
    d = fueling.daily_carbs(70, minutes, stype)
    assert (d["load"], d["low_g_per_kg"], d["high_g_per_kg"]) == (load, lo, hi)
    assert (d["low_g"], d["high_g"]) == (lo * 70, hi * 70)


def test_daily_grams_use_the_riders_weight():
    assert fueling.daily_carbs(62.5, 120, "endurance") == {
        "load": "high", "low_g_per_kg": 6, "high_g_per_kg": 10, "low_g": 375, "high_g": 625}


def test_ride_energy_is_about_one_kcal_per_kj_of_work():
    # 1000 kJ / (0.24 x 4.184) = 995.9 kcal
    assert fueling.ride_kcal(1000) == 996
    assert fueling.ride_kcal(0) == 0 and fueling.ride_kcal(None) == 0
    assert "Approximate" in fueling.ENERGY_METHOD


def test_confidence_is_stated():
    assert "Not medical advice" in fueling.NOT_MEDICAL_ADVICE
    assert "Individual" in fueling.NOT_MEDICAL_ADVICE
