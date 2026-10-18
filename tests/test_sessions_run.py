"""Run session library (#120): every template builds a valid run workout with and without a saved threshold
pace, its pace targets are exactly the cited Friel zone bounds, it stays inside its own duration range, the
rTSS estimate follows run_metrics.rtss, and the companion engine places the templates."""
from datetime import date, timedelta

import pytest

import multisport_plan as mp
import run_metrics as rm
import sessions_run as sr
import training_planner as tp
import workout_builder as wb

PACE = {"run_threshold_pace": {"current": 300.0, "history": []}}     # 5:00/km
NO_PACE = {"run_threshold_pace": {"current": None, "history": []}}
# Shepherd's mapping of Daniels' categories onto Friel's zones (sessions_run docstring).
DANIELS_ZONES = {"E": {"1", "2"}, "T": {"1", "2", "4"}, "I": {"1", "2", "5b"}, "R": {"1", "2", "5c"}}


def _blocks(w):
    for s in w["steps"]:
        if s["kind"] == "repeat":
            yield s["on"]
            yield s["off"]
        else:
            yield s


def _all_minutes(t):
    return range(t.minutes[0], t.minutes[1] + 1)


def test_the_library_covers_the_brief_and_retires_the_placeholder():
    kinds = {t.kind for t in sr.TEMPLATES}
    assert kinds == {"easy", "long", "recovery", "strides", "tempo", "cruise", "intervals", "hills"}
    ids = [t.id for t in mp.templates_for("running")]
    assert "placeholder-run-easy" not in ids and ids == [t.id for t in sr.TEMPLATES]
    for t in sr.TEMPLATES:
        assert t.stimulus in ("recovery", "aerobic", "threshold", "vo2max", "speed") and t.daniels in "ETIR"
        assert t.session_type in ("run_easy", "run_long", "run_tempo", "run_intervals") and "Daniels" in t.source
    assert {t.kind for t in sr.TEMPLATES if t.hard} == {"tempo", "cruise", "intervals", "hills"}


@pytest.mark.parametrize("th", [PACE, NO_PACE, {}], ids=["pace", "no-pace", "empty"])
@pytest.mark.parametrize("t", sr.TEMPLATES, ids=lambda t: t.id)
def test_every_template_builds_a_valid_run_workout_of_exactly_its_length(t, th):
    for m in _all_minutes(t):
        w = t.builder(th, m)
        errors, _ = wb.validate(w, wb.RUN_TARGETS)
        assert errors == [], (m, errors)
        assert wb.total_seconds(w) == m * 60
        kinds = {b["target"]["kind"] for b in _blocks(w)}
        assert kinds <= ({"pace_pct_threshold", "effort"} if th is PACE else {"effort"})


@pytest.mark.parametrize("t", sr.TEMPLATES, ids=lambda t: t.id)
def test_pace_targets_are_the_cited_friel_zone_bounds(t):
    friel = {z: (slow, fast) for z, _n, slow, fast in rm.FRIEL_PACE}
    for m in _all_minutes(t):
        for b in _blocks(t.builder(PACE, m)):
            tg = b["target"]
            assert tg["zone"] in DANIELS_ZONES[t.daniels]
            if tg["kind"] == "effort":
                continue
            slow, fast = friel[tg["zone"]]
            assert (tg["hi"], tg["lo"]) == (slow, fast)
            for pct, s in ((fast, tg["fast_s_per_km"]), (slow, tg["slow_s_per_km"])):
                assert s == (None if pct is None else round(300 * pct / 100, 1))


def test_daniels_structures():
    def main(t, m=None):
        w = t.builder(PACE, m or t.minutes[0])
        return [s for s in w["steps"] if s["kind"] not in ("warmup", "cooldown")], w
    by = {t.kind: t for t in sr.TEMPLATES}
    (tempo,), _ = main(by["tempo"])
    assert tempo["duration_s"] == 20 * 60 and tempo["target"]["zone"] == "4"           # ~20 min continuous T
    for m in _all_minutes(by["cruise"]):
        (rep,), _ = main(by["cruise"], m)
        assert 5 * 60 <= rep["on"]["duration_s"] <= 15 * 60 and rep["off"]["duration_s"] * 5 == rep["on"]["duration_s"]
    for kind in ("intervals", "hills"):
        for m in _all_minutes(by[kind]):
            (rep,), _ = main(by[kind], m)
            assert 3 * 60 <= rep["on"]["duration_s"] <= 5 * 60 and rep["off"]["duration_s"] == rep["on"]["duration_s"]
    (_easy, strides), _ = main(by["strides"])
    assert 20 <= strides["on"]["duration_s"] <= 30
    assert by["long"].minutes[1] == sr.LONG_RUN_CAP_MIN == 150                          # Daniels' 2.5 h cap
    _, hill = main(by["hills"])
    assert all(b["target"]["kind"] == "effort" for b in _blocks(hill) if b["target"]["zone"] == "5b")
    # Hard work sits between at least 10 minutes of easy warm-up and cool-down.
    for t in sr.TEMPLATES:
        if t.hard:
            for m in _all_minutes(t):
                w = t.builder(PACE, m)
                assert w["steps"][0]["duration_s"] >= 600 and w["steps"][-1]["duration_s"] >= 600


def test_rtss_estimate_follows_run_metrics():
    one_hour_t = {"name": "x", "description": "", "steps": [
        {"kind": "work", "duration_s": 3600, "target": sr.target("4", 300.0), "cadence_note": ""}]}
    pct = (105 + 99) / 2
    assert sr.rtss_estimate(one_hour_t) == rm.rtss(3600, 100 / pct, 1.0) == round((100 / pct) ** 2 * 100, 1)
    easy = next(t for t in sr.TEMPLATES if t.kind == "easy")
    # The estimate needs no threshold: IF is threshold pace / pace.
    assert sr.rtss_estimate(easy.builder(PACE, 45)) == sr.rtss_estimate(easy.builder({}, 45)) == 50.8
    assert sr.zone_pct("1") == 129 and sr.zone_pct("5c") == 90       # open zones read at their one bound
    prof = sr.profile(easy.builder({}, 45))
    assert prof[0]["x"] == 0 and prof[-1]["x"] == 45 and prof[0]["y"] == round(10000 / 121.5, 1)


def test_cycling_validation_still_rejects_run_targets_and_run_validation_checks_them():
    w = {"name": "x", "steps": [{"kind": "work", "duration_s": 600, "target": sr.target("2", 300.0)}]}
    assert wb.validate(w)[0][0]["path"] == "steps[0].target.kind"
    assert wb.validate(w, wb.RUN_TARGETS)[0] == []
    bad = [{"kind": "pace_pct_threshold", "lo": None, "hi": None}, {"kind": "pace_pct_threshold", "lo": 120, "hi": 110},
           {"kind": "pace_pct_threshold", "lo": 20, "hi": 110}, {"kind": "pace_pct_threshold", "lo": "x"},
           {"kind": "effort", "label": ""}, {"kind": "power", "lo": 50, "hi": 60}]
    for tg in bad:
        w["steps"][0]["target"] = tg
        assert wb.validate(w, wb.RUN_TARGETS)[0], tg


def _week(start, hard=()):
    def s(d, st, m):
        return tp.PlannedSession(day=d, day_name=d.strftime("%a"), session_type=st, duration_min=m,
                                 tss_estimate=m * 0.6, description="")
    sessions = [s(start, "rest", 0)] + [s(start + timedelta(days=k), "vo2max" if k in hard else "z2", 60)
                                        for k in range(1, 7)]
    return tp.PlannedWeek(week_num=1, start=start, end=start + timedelta(days=6), phase="build1", tss_target=400,
                          is_stepback=False, sessions=sessions, hit_allowance=3)


@pytest.mark.parametrize("th", [PACE, NO_PACE], ids=["pace", "no-pace"])
def test_the_engine_places_library_templates(th):
    monday = date(2026, 9, 14)
    w = _week(monday, hard=(2,))
    mp.overlay([w], targets={"cycling": 60.0, "running": 40.0}, limiter="running", thresholds=th,
               availability={"hours_per_week": 10.0, "weekday": {0: 0, 1: 2, 2: 2, 3: 2, 4: 2, 5: 4, 6: 4}, "date": {}},
               unavailable_periods=[], today=monday)
    ours = {t.id: t for t in sr.TEMPLATES}
    assert w.companions and all(c.template_id in ours for c in w.companions)
    assert any(c.hard for c in w.companions), "the library's hard templates get the free hard slot"
    for c in w.companions:
        t = ours[c.template_id]
        assert t.minutes[0] <= c.duration_min <= t.minutes[1]
        assert wb.validate(c.workout, wb.RUN_TARGETS)[0] == [] and wb.total_seconds(c.workout) == c.duration_min * 60
