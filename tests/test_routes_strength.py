"""GET /api/strength/sessions (#127)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import app
    return TestClient(app.app)


def test_lists_all_templates_with_exercise_lists_and_notes(client):
    r = client.get("/api/strength/sessions")
    assert r.status_code == 200
    d = r.json()
    assert d["stage"] == "novice" and [s["id"] for s in d["stages"]] == ["novice", "progressing", "experienced"]
    assert {s["kind"] for s in d["sessions"]} == {"strength", "maintenance", "mobility"}
    assert len(d["sessions"]) == 4
    for s in d["sessions"]:
        assert s["exercises"] and s["load_note"] == "arbitrary units (session-RPE), not comparable with TSS"
        assert "Stop if anything hurts" in s["disclaimer"]
    assert "Foster" in " ".join(d["sources"]) and "687-708" in " ".join(d["sources"])


def test_stage_changes_sets_and_reps(client):
    nov = client.get("/api/strength/sessions?stage=novice").json()["sessions"][0]["exercises"][0]
    exp = client.get("/api/strength/sessions?stage=experienced").json()["sessions"][0]["exercises"][0]
    assert nov["reps"] == [8, 12] and exp["reps"] == [4, 6] and exp["sets"][1] > nov["sets"][0]


def test_bad_stage_is_400(client):
    assert client.get("/api/strength/sessions?stage=elite").status_code == 400
