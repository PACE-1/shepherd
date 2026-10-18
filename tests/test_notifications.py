"""Notifications (#131): dedupe, the write-only URL, URL validation, and a POST that fails quietly."""
import json
import os
import stat
from datetime import date, datetime
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
import notifications as n

SECRET = "https://ntfy.example.com/topic-s3cret-xyz"
TODAY = date(2026, 10, 18)
NOON = datetime(2026, 10, 18, 12, 0)
READY = lambda d: {"score": 7.24, "advice": "Normal day."}          # noqa: E731
PLANNED = lambda d: {"name": "sweetspot", "minutes": 60}              # noqa: E731


@pytest.fixture(autouse=True)
def inline_spawn(monkeypatch):
    sent = []
    monkeypatch.setattr(n, "_spawn", lambda fn: fn())
    monkeypatch.setattr(n, "post_ntfy", lambda url, title, body: (sent.append((url, title, body)) or (True, "")))
    return sent


def test_readiness_is_sent_once_a_day_and_survives_a_restart(tmp_path, inline_spawn):
    n.save_settings(tmp_path, SECRET)
    assert n.check_readiness(tmp_path, TODAY, NOON, READY, PLANNED) is True
    assert n.check_readiness(tmp_path, TODAY, NOON, READY, PLANNED) is False   # same process
    # a "restart" re-reads everything from disk: nothing is held in memory
    assert n.check_readiness(tmp_path, TODAY, NOON, READY, PLANNED) is False
    assert len(inline_spawn) == 1
    url, title, body = inline_spawn[0]
    assert url == SECRET and title == "Shepherd: readiness 7.2/10"
    assert "Readiness 7.2 of 10. Normal day." in body and "sweetspot, 60 min" in body
    tomorrow = date(2026, 10, 19)
    assert n.check_readiness(tmp_path, tomorrow, datetime(2026, 10, 19, 8), READY, PLANNED) is True
    assert [i["day"] for i in n.listing(tmp_path)["items"]] == ["2026-10-19", "2026-10-18"]


def test_readiness_waits_for_the_set_time_and_for_data(tmp_path):
    n.save_settings(tmp_path, readiness_time="07:30")
    assert n.check_readiness(tmp_path, TODAY, datetime(2026, 10, 18, 7, 0), READY, PLANNED) is False
    assert n.check_readiness(tmp_path, TODAY, datetime(2026, 10, 18, 7, 31), lambda d: {"score": None}, PLANNED) is False
    assert n.check_readiness(tmp_path, TODAY, datetime(2026, 10, 18, 7, 31), READY, PLANNED) is True


def test_missed_session_needs_a_plan_and_no_activity_and_is_sent_once(tmp_path):
    assert n.check_missed(tmp_path, TODAY, NOON, lambda d: None, lambda d: False) is False       # rest day
    assert n.check_missed(tmp_path, TODAY, NOON, PLANNED, lambda d: True) is False               # rode
    assert n.check_missed(tmp_path, TODAY, NOON, PLANNED, lambda d: False) is True
    assert n.check_missed(tmp_path, TODAY, NOON, PLANNED, lambda d: False) is False
    (item,) = n.listing(tmp_path)["items"]
    assert item["event"] == "missed" and item["day"] == "2026-10-17"


def test_sync_failure_is_once_per_episode_and_rearms_after_a_good_pass(tmp_path):
    assert n.check_sync_failure(tmp_path, TODAY, "HTTP 500\nbody", NOON) is True
    assert n.check_sync_failure(tmp_path, TODAY, "HTTP 500", NOON) is False
    n._set_failing(tmp_path, False)                    # a good pass ends the episode
    nxt = date(2026, 10, 19)
    assert n.check_sync_failure(tmp_path, nxt, "again", NOON) is True
    assert n.listing(tmp_path)["items"][1]["body"].count("HTTP 500") == 1
    assert "body" not in n.listing(tmp_path)["items"][1]["body"]    # first line of the error only


def test_a_switched_off_event_sends_and_records_nothing(tmp_path, inline_spawn):
    n.save_settings(tmp_path, SECRET, events={"sync_failure": False})
    assert n.check_sync_failure(tmp_path, TODAY, "x", NOON) is False
    assert n.listing(tmp_path)["items"] == [] and inline_spawn == []


def test_without_a_url_the_list_still_fills(tmp_path, inline_spawn):
    assert n.check_readiness(tmp_path, TODAY, NOON, READY, PLANNED) is True
    assert inline_spawn == [] and n.listing(tmp_path)["unread"] == 1
    assert n.mark_all_read(tmp_path)["unread"] == 0


def test_the_url_is_stored_privately_and_never_returned(tmp_path):
    s = n.save_settings(tmp_path, SECRET)
    assert stat.S_IMODE(os.stat(tmp_path / "notifications.json").st_mode) == 0o600
    pub = n.public(s)
    assert pub["has_url"] is True and "s3cret" not in json.dumps(pub)
    assert n.save_settings(tmp_path, None, events={"missed": False})["ntfy_url"] == SECRET   # omitted keeps it
    assert n.public(n.save_settings(tmp_path, ""))["has_url"] is False                       # "" clears it


@pytest.mark.parametrize("url", ["", "ftp://x/y", "file:///etc/passwd", "javascript:alert(1)", "https://",
                                 "https://secret-host.example/a b/c", "http://secret-host.example:99999/x", "ntfy.sh/topic", "https://secret-host.example/\nX: y"])
def test_bad_urls_are_refused_and_never_echoed(tmp_path, url):
    with pytest.raises(n.NotificationError) as e:
        n.validate_url(url)
    assert len(url) < 12 or url not in str(e.value)
    if url:
        with pytest.raises(n.NotificationError):
            n.save_settings(tmp_path, url)
        assert n.load_settings(tmp_path)["ntfy_url"] == ""


def test_good_urls_and_times():
    assert n.validate_url(" http://192.168.1.5:2586/mytopic ") == "http://192.168.1.5:2586/mytopic"
    assert n.validate_url("https://user:pw@ntfy.example.com/t") == "https://user:pw@ntfy.example.com/t"
    assert n.validate_time("") == "" and n.validate_time("07:05") == "07:05"
    for bad in ("7:05", "24:00", "07:60", "noon"):
        with pytest.raises(n.NotificationError):
            n.validate_time(bad)
    with pytest.raises(n.NotificationError):
        n.save_settings(".", events={"bogus": True})


@pytest.mark.parametrize("fail", [httpx.ConnectTimeout(SECRET), httpx.ConnectError(SECRET), RuntimeError(SECRET), ValueError(SECRET)])
def test_a_failing_post_never_raises_and_never_leaks_the_url(monkeypatch, fail):
    monkeypatch.undo()
    with mock.patch("httpx.post", side_effect=fail):
        ok, why = n.post_ntfy(SECRET, "t", "b")
    assert ok is False and "s3cret" not in why


def test_post_sends_plain_text_with_a_title_and_short_timeout(monkeypatch):
    monkeypatch.undo()
    with mock.patch("httpx.post", return_value=mock.Mock(status_code=200)) as p:
        assert n.post_ntfy(SECRET, "Shepherd: hi", "body é") == (True, "")
    assert p.call_args.args == (SECRET,)
    kw = p.call_args.kwargs
    assert kw["content"] == "body é".encode() and kw["headers"]["Title"] == "Shepherd: hi"
    assert kw["timeout"] <= 10 and kw["follow_redirects"] is False
    with mock.patch("httpx.post", return_value=mock.Mock(status_code=403)):
        assert n.post_ntfy(SECRET, "t", "b") == (False, "The server answered 403.")


def test_a_delivery_failure_still_leaves_the_notice_in_the_list(tmp_path, monkeypatch):
    monkeypatch.setattr(n, "post_ntfy", lambda *a: (False, "nope"))
    n.save_settings(tmp_path, SECRET)
    assert n.check_readiness(tmp_path, TODAY, NOON, READY, PLANNED) is True
    assert n.listing(tmp_path)["unread"] == 1


def test_the_post_runs_off_the_calling_thread(tmp_path, monkeypatch):
    monkeypatch.undo()
    import threading
    seen = {}
    done = threading.Event()

    def fake(url, title, body):
        seen["thread"] = threading.current_thread()
        done.set()
        return True, ""
    monkeypatch.setattr(n, "post_ntfy", fake)
    n.save_settings(tmp_path, SECRET)
    n.notify(tmp_path, "readiness", "2026-10-18", "t", "b")
    assert done.wait(5) and seen["thread"] is not threading.current_thread()


def test_planned_reads_the_stored_plan_and_skips_done_rest_and_moved(tmp_path):
    sess = [{"day": "2026-10-17", "session_type": "sweetspot", "duration_min": 60, "zwo_name": "Sweet Spot 3x15"},
            {"day": "2026-10-18", "session_type": "rest"},
            {"day": "2026-10-19", "session_type": "z2", "duration_min": 90, "status": "done"},
            {"day": "2026-10-20", "session_type": "z2", "duration_min": 90, "status": "moved_from:2026-10-20"}]
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "current_plan.json").write_text(json.dumps({"weeks": [{"sessions": sess}]}))
    assert n._planned(tmp_path, "2026-10-17") == {"name": "Sweet Spot 3x15", "minutes": 60}
    assert [n._planned(tmp_path, d) for d in ("2026-10-18", "2026-10-19", "2026-10-20", "2026-11-01")] == [None] * 4
    assert n._planned(tmp_path / "nowhere", "2026-10-17") is None


# ── contract: the HTTP surface ──────────────────────────────────────────────

@pytest.fixture
def c():
    with TestClient(app_module.app) as client:
        yield client


def test_endpoints_round_trip_without_echoing_the_url(c, monkeypatch):
    s = c.get("/api/notifications/settings").json()
    assert s == {"has_url": False, "events": {"readiness": True, "missed": True, "sync_failure": True}, "readiness_time": ""}
    r = c.put("/api/notifications/settings", json={"ntfy_url": SECRET, "events": {"missed": False}, "readiness_time": "07:30"})
    assert r.status_code == 200 and r.json()["has_url"] is True and r.json()["events"]["missed"] is False
    assert "s3cret" not in r.text and "s3cret" not in c.get("/api/notifications/settings").text
    assert c.put("/api/notifications/settings", json={"events": {"missed": True}}).json()["has_url"] is True
    assert c.put("/api/notifications/settings", json={"ntfy_url": "ftp://x"}).status_code == 400
    assert c.put("/api/notifications/settings", json={"readiness_time": "9am"}).status_code == 400
    monkeypatch.setattr(n, "post_ntfy", lambda url, t, b: (url == SECRET, ""))
    assert c.post("/api/notifications/test").json() == {"ok": True, "error": ""}
    assert c.put("/api/notifications/settings", json={"ntfy_url": ""}).json()["has_url"] is False
    assert c.post("/api/notifications/test").json()["ok"] is False


def test_list_and_mark_read_endpoints(c):
    from profile_manager import ProfileManager
    pd = ProfileManager.get().active_dir
    n.notify(pd, "missed", "2026-10-17", "Shepherd: missed session", "Yesterday's z2 has no activity.")
    got = c.get("/api/notifications").json()
    assert got["unread"] >= 1 and got["items"][0]["event"] == "missed"
    assert c.post("/api/notifications/read").json()["unread"] == 0


def test_the_sync_hooks_use_the_active_profile_and_never_raise(c):
    from profile_manager import ProfileManager
    pd = ProfileManager.get().active_dir
    n._set_failing(pd, False)
    n.on_sync_failure("HTTP 500: upstream down")
    n.on_sync_failure("HTTP 500: upstream down")
    assert [i["event"] for i in n.listing(pd)["items"]].count("sync_failure") == 1
    n.on_sync_pass()                                    # real readiness/plan/db reads on an empty profile
    assert n._sent(pd) and not json.loads((pd / "notifications_state.json").read_text())["sync_failing"]
    with mock.patch.object(n, "_active", side_effect=RuntimeError("boom")):
        n.on_sync_pass()
        n.on_sync_failure("x")
