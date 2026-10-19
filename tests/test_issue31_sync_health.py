"""#31 Phase 0: tell only the riders the evidence points at.

One in-app notice per episode, and only when intervals.icu visibly is not
passing rides on: it lists activities without their data, or rides the rider
imported have nothing on intervals.icu. A rider who simply has not ridden has
neither, and is never told.
"""
import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import app as app_module
import db
import notifications as n

TODAY = date(2026, 10, 18)
NOON = datetime(2026, 10, 18, 12, 0)


@pytest.fixture(autouse=True)
def inline_spawn(monkeypatch):
    sent = []
    monkeypatch.setattr(n, "_spawn", lambda fn: fn())
    monkeypatch.setattr(n, "post_ntfy", lambda url, title, body: (sent.append((title, body)) or (True, "")))
    return sent


def _health(pd, withheld=(), local=(), today=TODAY):
    return n.check_sync_health(pd, today, list(withheld), list(local), NOON)


def test_a_rider_who_has_not_ridden_is_never_told(tmp_path):
    for _ in range(5):
        assert _health(tmp_path) is False
    assert n.listing(tmp_path)["items"] == []


def test_one_odd_activity_is_not_evidence(tmp_path):
    assert _health(tmp_path, withheld=["2026-10-16"], local=["2026-10-15"]) is False
    assert n.listing(tmp_path)["items"] == []


def test_withheld_activities_send_one_notice_per_episode(tmp_path, inline_spawn):
    n.save_settings(tmp_path, "https://ntfy.example.com/t")
    assert _health(tmp_path, withheld=["2026-10-15", "2026-10-17"]) is True
    assert _health(tmp_path, withheld=["2026-10-15", "2026-10-17", "2026-10-18"]) is False   # same episode
    assert _health(tmp_path, withheld=["2026-10-15", "2026-10-17"], today=date(2026, 10, 19)) is False
    (item,) = n.listing(tmp_path)["items"]
    assert item["event"] == "sync_health"
    assert "intervals.icu listed 2 of your activities without their data" in item["body"]
    assert "Folder import" in item["body"] and "Garmin" not in item["body"]
    assert len(inline_spawn) == 1


def test_the_episode_ends_when_the_evidence_is_gone_and_can_start_again(tmp_path):
    assert _health(tmp_path, withheld=["2026-10-15", "2026-10-17"]) is True
    assert _health(tmp_path, today=date(2026, 10, 19)) is False             # cleared
    assert _health(tmp_path, local=["2026-10-19", "2026-10-20"], today=date(2026, 10, 21)) is True
    assert "2 days with rides you imported have nothing on intervals.icu" in n.listing(tmp_path)["items"][0]["body"]


def test_old_evidence_and_todays_imports_do_not_count(tmp_path):
    # Outside the 14-day window; and an import from today may simply not have
    # reached intervals.icu yet.
    assert _health(tmp_path, withheld=["2026-09-01", "2026-09-02"], local=["2026-10-18", "2026-10-18"]) is False


def test_the_sync_failure_switch_governs_the_notice(tmp_path):
    n.save_settings(tmp_path, events={"sync_failure": False})
    assert _health(tmp_path, withheld=["2026-10-15", "2026-10-17"]) is False
    assert n.listing(tmp_path)["items"] == []


# ── the evidence, read from the real stores ─────────────────────────────────

@pytest.fixture
def c():
    with TestClient(app_module.app) as client:
        yield client


def test_withheld_days_reads_stubs_from_the_sync_and_data_less_rows(c, monkeypatch):
    monkeypatch.setattr(db, "last_stub_days", ["2026-10-14"])
    conn = db.get_db()
    rows = [("w31a", "2026-10-15", "Ride", 3600, None, None, None, json.dumps({"type": "Ride"})),
            ("w31b", "2026-10-16", "Ride", 3600, 55.0, None, 140.0, json.dumps({"type": "Ride"})),   # has data
            ("w31c", "2026-10-16", "Ride", 3600, None, None, None, json.dumps({"icu_intensity": 70}))]
    conn.executemany("INSERT OR REPLACE INTO activities (id, date, sport, duration_sec, tss, avg_power, avg_hr, raw_json) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    try:
        assert sorted(n._withheld_days("2026-10-04")) == ["2026-10-14", "2026-10-15"]
    finally:
        conn.execute("DELETE FROM activities WHERE id LIKE 'w31%'")
        conn.commit()


def test_sync_activities_records_the_stub_days(c, monkeypatch):
    stub = {"id": "s31", "source": "STRAVA", "start_date_local": "2026-10-17T08:00:00",
            "name": None, "type": None, "elapsed_time": None, "moving_time": None}
    monkeypatch.setattr(db, "fetch_activities", lambda days=90: [stub])
    monkeypatch.setattr(db, "_refresh_hr_from_activities", lambda snap: None)
    # sync_activities rewrites this module list in place; give it a throwaway so later tests in the worker do not see the stub day.
    monkeypatch.setattr(db, "last_stub_days", [])
    db.sync_activities(days=7)
    assert db.last_stub_days == ["2026-10-17"]


def test_on_sync_pass_never_raises_on_an_empty_profile(c):
    from profile_manager import ProfileManager
    pd = ProfileManager.get().active_dir
    n.on_sync_pass()
    assert not any(i["event"] == "sync_health" for i in n.listing(pd)["items"])
