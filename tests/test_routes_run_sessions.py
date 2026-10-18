"""Run workout library routes (#120): filters, the concrete workout for the rider's threshold pace, the
estimated rTSS, and the .fit (sport running, speed targets, repeat steps) and .txt downloads."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import multisport
import sessions_run as sr


@pytest.fixture(autouse=True)
def _own_thresholds(tmp_path, monkeypatch):
    """The profile dir outlives a test; give each one its own thresholds file (never the shared one)."""
    import routes_run
    p = tmp_path / "sport_thresholds.json"
    monkeypatch.setattr(routes_run, "_thresholds_path", lambda: p)
    return p


def _client():
    import app
    return TestClient(app.app)


def _decode(data: bytes):
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    recs = [r.message for r in FitFile.from_bytes(data).records]
    return (next(m for m in recs if isinstance(m, WorkoutMessage)),
            [m for m in recs if isinstance(m, WorkoutStepMessage)])


def test_library_lists_every_template_with_effort_targets_until_a_pace_is_saved(_own_thresholds):
    c = _client()
    r = c.get("/api/run/sessions").json()
    assert r["targets"] == "effort" and r["threshold_pace_s_per_km"] is None
    assert "not validated" in r["note"] and "Daniels" in r["method"]
    assert [s["id"] for s in r["sessions"]] == [t.id for t in sr.TEMPLATES]
    for s in r["sessions"]:
        assert s["min_minutes"] <= s["minutes"] <= s["max_minutes"] and s["rtss_estimate"] > 0 and s["profile"]
    multisport.set_threshold(_own_thresholds, "run_threshold_pace", 300, date(2026, 9, 1))
    r = c.get("/api/run/sessions").json()
    assert r["targets"] == "pace" and r["threshold_pace_s_per_km"] == 300.0
    easy = next(s for s in r["sessions"] if s["id"] == "run-easy")
    assert easy["workout"]["steps"][0]["target"]["fast_s_per_km"] == 342.0          # 114 % of 5:00/km


def test_filters_by_type_duration_and_load():
    c = _client()
    ids = lambda **q: [s["id"] for s in c.get("/api/run/sessions", params=q).json()["sessions"]]
    assert ids(type="threshold") == ["run-tempo", "run-cruise"]
    assert ids(type="I") == ["run-intervals", "run-hills"] and ids(type="long") == ["run-long"]
    assert ids(type="nope") == []
    short = c.get("/api/run/sessions", params={"max_minutes": 35}).json()["sessions"]
    assert {s["id"] for s in short} == {"run-easy", "run-recovery", "run-strides"}
    assert all(s["minutes"] <= 35 for s in short)
    assert "run-long" not in ids(max_minutes=59) and ids(min_minutes=61) == ["run-long", "run-cruise"]
    low = c.get("/api/run/sessions", params={"max_rtss": 40}).json()["sessions"]
    assert low and all(s["rtss_estimate"] <= 40 for s in low)


def test_one_session_at_a_chosen_length():
    c = _client()
    s = c.get("/api/run/sessions/run-tempo", params={"minutes": 45}).json()
    assert s["minutes"] == 45 and s["hard"] is True and s["daniels"] == "T"
    assert c.get("/api/run/sessions/run-tempo", params={"minutes": 200}).status_code == 400
    assert c.get("/api/run/sessions/nope").status_code == 404


def test_fit_download_is_a_structured_running_workout(_own_thresholds):
    from fit_tool.profile.profile_type import (
        Sport,
        WorkoutStepDuration,
        WorkoutStepTarget,
    )
    multisport.set_threshold(_own_thresholds, "run_threshold_pace", 300, date(2026, 9, 1))
    r = _client().get("/api/run/sessions/run-intervals/download", params={"minutes": 50})
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    assert 'filename="Interval_reps_50min.fit"' in r.headers["content-disposition"]
    wm, steps = _decode(r.content)
    assert wm.sport == Sport.RUNNING.value and wm.num_valid_steps == len(steps) == 5
    wu, on, off, rep, cd = steps
    assert [s.message_index for s in steps] == [0, 1, 2, 3, 4]
    assert on.target_type == WorkoutStepTarget.SPEED.value and on.duration_time == 240
    # Z5b = 90-96 % of 5:00/km = 4:30-4:48/km
    assert on.custom_target_speed_low == pytest.approx(1000 / 288, abs=0.002)
    assert on.custom_target_speed_high == pytest.approx(1000 / 270, abs=0.002)
    assert off.target_type == WorkoutStepTarget.OPEN.value                  # Z1 is open-ended
    assert rep.duration_type == WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT.value
    assert rep.duration_step == 1 and rep.target_repeat_steps == 3
    assert sum(s.duration_time or 0 for s in (wu, cd)) + 3 * (on.duration_time + off.duration_time) == 50 * 60


def test_fit_without_a_threshold_pace_uses_open_effort_steps():
    from fit_tool.profile.profile_type import WorkoutStepTarget
    r = _client().get("/api/run/sessions/run-easy/download", params={"minutes": 30})
    _, steps = _decode(r.content)
    assert [s.target_type for s in steps] == [WorkoutStepTarget.OPEN.value]
    assert steps[0].workout_step_name == "easy, conversat" and steps[0].duration_time == 1800


def test_text_download(_own_thresholds):
    c = _client()
    multisport.set_threshold(_own_thresholds, "run_threshold_pace", 300, date(2026, 9, 1))
    r = c.get("/api/run/sessions/run-recovery/download", params={"minutes": 30, "format": "txt"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Run 30 min: slower than 6:27/km (Z1 Recovery)" in r.text and "not validated" in r.text
    assert c.get("/api/run/sessions/run-easy/download", params={"format": "pdf"}).status_code == 422
