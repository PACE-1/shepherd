"""GET /api/swim/sessions and the plain-text download (src/routes_swim_sessions.py)."""
import pytest
from fastapi.testclient import TestClient

import api_models


@pytest.fixture(autouse=True)
def _own_profile_files(tmp_path, monkeypatch):
    """The profile dir outlives a test; give each one its own thresholds file (a saved CSS must not leak)."""
    import app
    import routes_swim
    monkeypatch.setattr(routes_swim, "_profile_dir", lambda: tmp_path)
    monkeypatch.setattr(app, "_sport_thresholds_path", lambda: tmp_path / "sport_thresholds.json")


def _client():
    import app
    return TestClient(app.app)


def test_without_a_css_the_sessions_are_effort_labelled_metres_sets():
    r = _client().get("/api/swim/sessions")
    assert r.status_code == 200
    body = api_models.SwimSessions.model_validate(r.json())
    assert body.css_s_per_100m is None and not body.has_css and body.pool_m == 25
    assert [s.id for s in body.sessions] == ["swim-easy-technique", "swim-recovery", "swim-css-endurance",
                                             "swim-css-intervals", "swim-threshold-plus"]
    hard = next(s for s in body.sessions if s.id == "swim-css-intervals")
    assert hard.hard and hard.minutes_min <= hard.minutes <= hard.minutes_max
    assert any("x 100 m" in ln or "x 200 m" in ln for ln in hard.lines)
    assert "No swim CSS is saved" in hard.note and "Wakayoshi" in body.source
    assert "no FIT" in body.download_note and "Not validated" in body.not_validated


def test_with_a_saved_css_the_sets_carry_its_pace():
    c = _client()
    trials = [{"distance_m": 400, "time_s": 360}, {"distance_m": 200, "time_s": 170}]    # CSS 1:35
    assert c.post("/api/swim/css-test", json={"trials": trials, "save": True}).json()["saved"] is True
    body = c.get("/api/swim/sessions").json()
    assert body["css_s_per_100m"] == 95.0 and body["has_css"] is True
    text = " ".join(" ".join(s["lines"]) for s in body["sessions"] if s["hard"])
    assert "(1:35 per 100 m)" in text and "No swim CSS" not in " ".join(s["note"] for s in body["sessions"])


def test_download_is_a_plain_text_attachment_and_says_there_is_no_fit_file():
    c = _client()
    r = c.get("/api/swim/sessions/swim-css-intervals/text")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"] == 'attachment; filename="swim-css-intervals.txt"'
    assert "CSS intervals" in r.text and "no FIT" in r.text and "Your CSS: not saved" in r.text
    assert c.get("/api/swim/sessions/nope/text").status_code == 404
    assert c.get("/api/swim/sessions/placeholder-swim-easy/text").status_code == 404
