"""Workout builder model (#110): validation, ZWO export and its round trip
through the library's own parsers, and the IF/TSS the Library would show."""
from __future__ import annotations

import copy
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import hr_targets  # noqa: E402
import workout_builder as wb  # noqa: E402
from structure_fidelity import parse_zwo_text  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def P(lo, hi=None):
    return {"kind": "power", "lo": lo, "hi": lo if hi is None else hi}


def block(d, t, note=""):
    return {"duration_s": d, "target": t, "cadence_note": note}


# Same structure as the shipped library file sweet_spot_10x1min-1min_90pct_33min.zwo.
SWEET_SPOT = {
    "name": "Sweet spot 10x1",
    "description": "",
    "steps": [
        {"kind": "warmup", **block(480, P(50, 75))},
        {"kind": "repeat", "count": 10, "on": block(60, P(90)), "off": block(60, P(50))},
        {"kind": "cooldown", **block(300, P(25, 50))},
    ],
}


def _errs(w):
    return wb.validate(w)[0]


def test_valid_workout_has_no_errors():
    assert _errs(SWEET_SPOT) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda w: w.update(name="  "), "name"),
    (lambda w: w.update(steps=[]), "at least one"),
    (lambda w: w["steps"][0].update(duration_s=0), "positive"),
    (lambda w: w["steps"][0].update(duration_s=-5), "positive"),
    (lambda w: w["steps"][0].update(duration_s=90.5), "whole number"),
    (lambda w: w["steps"][0].update(duration_s=7 * 3600), "at most 6 hours"),
    (lambda w: w["steps"][0].update(target=P(80, 60)), "above its high"),
    (lambda w: w["steps"][0].update(target=P(5, 50)), "between 10 and 300"),
    (lambda w: w["steps"][0].update(target=P(50, 400)), "between 10 and 300"),
    (lambda w: w["steps"][0].update(target={"kind": "hr", "lo": 40, "hi": 80}), "between 50 and 105"),
    (lambda w: w["steps"][0].update(target={"kind": "pace", "lo": 1, "hi": 2}), "not supported yet"),
    (lambda w: w["steps"][0].update(target=None), "target is required"),
    (lambda w: w["steps"][1].update(count=0), "Repeats"),
    (lambda w: w["steps"][1].update(count=100), "Repeats"),
    (lambda w: w["steps"][1].update(count=1.5), "Repeats"),
    (lambda w: w["steps"][1]["on"].update(duration_s=0), "positive"),
    (lambda w: w["steps"][0].update(kind="sprint"), "Unknown step"),
    (lambda w: w["steps"][0].update(cadence_note="x" * 500), "Cadence note"),
    (lambda w: w["steps"][0].update(duration_s=True), "positive"),
])
def test_validation_rejects(mutate, needle):
    w = copy.deepcopy(SWEET_SPOT)
    mutate(w)
    msgs = " | ".join(e["message"] for e in _errs(w))
    assert needle in msgs, msgs
    with pytest.raises(ValueError):
        wb.to_zwo(w)


def test_max_steps_and_total_length():
    w = copy.deepcopy(SWEET_SPOT)
    w["steps"] = [{"kind": "work", **block(60, P(70))} for _ in range(wb.MAX_STEPS + 1)]
    assert any("At most" in e["message"] for e in _errs(w))
    w["steps"] = [{"kind": "work", **block(6 * 3600, P(70))}] * 3      # 18 h
    assert any("at most 12 hours" in e["message"] for e in _errs(w))
    w["steps"] = [{"kind": "repeat", "count": 99, "on": block(3600, P(70)), "off": block(3600, P(50))}]
    assert any("at most 12 hours" in e["message"] for e in _errs(w))


def test_hr_target_on_short_step_warns_but_is_valid():
    w = copy.deepcopy(SWEET_SPOT)
    w["steps"][0]["target"] = {"kind": "hr", "lo": 70, "hi": 80}
    w["steps"][0]["duration_s"] = 60
    errors, warnings = wb.validate(w)
    assert errors == [] and len(warnings) == 1


def test_non_dict_inputs_do_not_raise():
    for bad in (None, [], "x", {"name": "a", "steps": "nope"}, {"name": "a", "steps": [1]}):
        assert wb.validate(bad)[0]


# ── ZWO round trip through the repo's own parser ─────────────────────────────

def test_zwo_round_trip_through_existing_parser():
    segs = parse_zwo_text(wb.to_zwo(SWEET_SPOT))
    assert wb.total_seconds(SWEET_SPOT) == 480 + 10 * 120 + 300 == sum(s["dur_s"] for s in segs)
    assert segs[0] == {"kind": "warmup", "start_s": 0, "dur_s": 480, "lo": 0.5, "hi": 0.75}
    assert [s["kind"] for s in segs[1:5]] == ["interval_on", "interval_off"] * 2
    assert (segs[1]["lo"], segs[2]["lo"]) == (0.9, 0.5)
    # a cool-down ramps DOWN: starts at the high end
    assert (segs[-1]["kind"], segs[-1]["lo"], segs[-1]["hi"]) == ("cooldown", 0.5, 0.25)


def test_range_on_steady_step_is_exported_at_its_midpoint():
    w = {"name": "SS", "steps": [{"kind": "work", **block(600, P(88, 94))}]}
    seg = parse_zwo_text(wb.to_zwo(w))[0]
    assert (seg["kind"], seg["lo"], seg["hi"]) == ("steady", 0.91, 0.91)


def test_zwo_is_well_formed_and_escapes_text():
    w = copy.deepcopy(SWEET_SPOT)
    w["name"] = 'Tom & "Jerry" <3'
    w["steps"][0]["cadence_note"] = "spin <90 rpm> & easy"
    root = ET.fromstring(wb.to_zwo(w))
    assert root.findtext("name") == 'Tom & "Jerry" <3'
    assert root.find("workout/Warmup/textevent").get("message") == "spin <90 rpm> & easy"
    assert root.findtext("sportType") == "bike"


def test_intensity_profile_follows_the_segments():
    pts = wb.intensity_profile(wb.to_zwo(SWEET_SPOT))
    assert pts[0] == {"x": 0.0, "y": 50.0} and pts[1] == {"x": 8.0, "y": 75.0}
    assert pts[-1] == {"x": 33.0, "y": 25.0}


# ── heart-rate targets: inverse of hr_targets' own table ─────────────────────

@pytest.mark.parametrize("lthr,ftp", [(68, 55), (83, 75), (94, 90), (105, 105)])
def test_hr_anchor_values_are_hr_targets_zone_tops(lthr, ftp):
    assert wb.hr_to_ftp_pct(lthr) == pytest.approx(ftp)
    # and the forward map lands each top in the zone it came from
    assert hr_targets.zone_of_pct(ftp) in (1, 2, 3, 4)


def test_hr_mapping_is_monotone_flat_below_z1_and_clamped_above():
    assert wb.hr_to_ftp_pct(50) == wb.hr_to_ftp_pct(60) == 55
    vals = [wb.hr_to_ftp_pct(x) for x in range(50, 106)]
    assert vals == sorted(vals)
    assert wb.hr_to_ftp_pct(120) == 105


def test_hr_step_exports_mapped_power_and_hr_targets_agree_on_the_zone():
    w = {"name": "HR tempo", "steps": [{"kind": "work", **block(1200, {"kind": "hr", "lo": 84, "hi": 94})}]}
    seg = parse_zwo_text(wb.to_zwo(w))[0]
    pct = seg["lo"] * 100
    assert 75 < pct < 90                                    # Z3 band
    got = hr_targets.power_target_to_hr(pct, pct, 1200, lthr=170, max_hr=190)
    assert got["kind"] == "hr" and got["zone"] == 3


# ── IF / TSS equal what the Library shows for the same structure ─────────────

def test_if_and_tss_match_the_library_scanner_on_a_known_workout(tmp_path):
    import app as app_module
    lib = REPO / "src" / "workouts" / "sweet_spot_10x1min-1min_90pct_33min.zwo"
    mine = tmp_path / "mine.zwo"
    mine.write_text(wb.to_zwo(SWEET_SPOT), encoding="utf-8")
    a = app_module._scan_zwo_for_library(lib)
    b = app_module._scan_zwo_for_library(mine)
    assert b["total_sec"] == a["total_sec"] == 33 * 60
    assert b["if_val"] == pytest.approx(a["if_val"], abs=1e-9)
    assert b["tss"] == pytest.approx(a["tss"], abs=1e-9)
    # and that is the formula: TSS = hours * IF^2 * 100
    assert b["tss"] == pytest.approx(b["total_sec"] / 3600 * b["if_val"] ** 2 * 100)
