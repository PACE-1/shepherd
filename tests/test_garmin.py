"""Garmin Connect: sign-in with and without MFA, token storage, health sync
into both wellness stores (Garmin wins), the overlay on intervals.icu fetches,
activity import and the endpoints. A fake client stands in for Garmin."""
import io
import json
import os
import stat
import time
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

import garminconnect
import pytest
from fastapi.testclient import TestClient

import app as app_module
import clock
import db
import garmin
import ride_storage
import training

FIT = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT" + b"\x00" * 40


def _zip(name="123_ACTIVITY.fit", data=FIT):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, data)
    return buf.getvalue()


class FakeClient:
    def dump(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        p = Path(path) / garmin.TOKEN_FILE
        p.write_text(json.dumps({"di_token": "tok"}))
        os.chmod(p, 0o600)


class FakeGarmin:
    """What garmin.py uses of garminconnect.Garmin."""
    ActivityDownloadFormat = garminconnect.Garmin.ActivityDownloadFormat
    mfa = False
    reject_tokens = False
    error = None
    activities: list = []
    downloads: list = []

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.email, self.password = email, password
        self.client = FakeClient()
        self.full_name = "Test Rider"

    def login(self, tokenstore=None):
        if FakeGarmin.error:
            raise FakeGarmin.error
        if tokenstore:
            if FakeGarmin.reject_tokens or not (Path(tokenstore) / garmin.TOKEN_FILE).exists():
                raise garminconnect.GarminConnectAuthenticationError("rejected")
            return None, None
        return ("needs_mfa", None) if FakeGarmin.mfa else (None, None)

    def resume_login(self, state, code):
        if code != "123456":
            raise garminconnect.GarminConnectConnectionError("bad code")
        return None, None

    def get_sleep_data(self, day):
        return {"dailySleepDTO": {"sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 81}}},
                "restingHeartRate": 49}

    def get_hrv_data(self, day):
        return {"hrvSummary": {"lastNightAvg": 62}}

    def get_user_summary(self, day):
        return {"restingHeartRate": 47, "bodyBatteryHighestValue": 90, "bodyBatteryLowestValue": 20,
                "averageStressLevel": 28, "totalSteps": 9000}

    def get_morning_training_readiness(self, day):
        return {"score": 74}

    def get_activities_by_date(self, start, end):
        return FakeGarmin.activities

    def download_activity(self, aid, dl_fmt=None):
        FakeGarmin.downloads.append(aid)
        return _zip()


@pytest.fixture
def env(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    (profile / "wellness").mkdir(parents=True)
    (profile / "rides").mkdir()
    monkeypatch.setattr(garmin, "_profile_dir", lambda: profile)
    monkeypatch.setattr(ride_storage, "_wellness_dir", lambda: profile / "wellness")
    monkeypatch.setattr(ride_storage, "_fit_rides_dir", lambda: profile / "rides")
    monkeypatch.setattr(ride_storage, "load_icu_rides", lambda: [])
    monkeypatch.setattr(garminconnect, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin, "fit_importer", lambda p: True)
    monkeypatch.setattr(garmin, "_pending_mfa", {})
    FakeGarmin.mfa = FakeGarmin.reject_tokens = False
    FakeGarmin.error = None
    FakeGarmin.activities, FakeGarmin.downloads = [], []
    old_db = db.DB_PATH
    db.set_db_path(tmp_path / "test.db")
    db.init_db()
    yield profile
    db.set_db_path(old_db)


def test_health_for_day_maps_garmin_fields_to_the_wellness_names():
    v = garmin.health_for_day(FakeGarmin(), "2026-10-17")
    assert v == {"hrv": 62, "restingHR": 47, "sleepSecs": 27000, "sleepScore": 81,
                 "bodyBatteryHigh": 90, "bodyBatteryLow": 20, "stressAvg": 28,
                 "steps": 9000, "trainingReadiness": 74}


def test_missing_and_zero_values_are_no_reading():
    g = FakeGarmin()
    g.get_hrv_data = lambda d: None
    g.get_user_summary = lambda d: {"restingHeartRate": 0}
    g.get_sleep_data = mock.Mock(side_effect=garminconnect.GarminConnectConnectionError("404"))
    v = garmin.health_for_day(g, "2026-10-17")
    assert v["hrv"] is None and v["restingHR"] is None and v["sleepSecs"] is None


def test_login_without_mfa_stores_tokens_never_the_password(env):
    st = garmin.login("me@example.com", "hunter2")
    assert st["connected"] and st["name"] == "Test Rider" and not st["mfa_pending"]
    tok = env / "garmin" / garmin.TOKEN_FILE
    assert stat.S_IMODE(os.stat(tok).st_mode) == 0o600
    for f in (env / "garmin").iterdir():
        assert "hunter2" not in f.read_text()


def test_login_with_mfa_waits_for_the_code_and_a_wrong_code_can_be_retried(env):
    FakeGarmin.mfa = True
    st = garmin.login("me@example.com", "pw")
    assert st["mfa_pending"] and not st["connected"]
    with pytest.raises(garmin.GarminError) as e:
        garmin.submit_mfa("000000")
    assert e.value.status == 400
    assert garmin.status()["mfa_pending"]
    st = garmin.submit_mfa("123456")
    assert st["connected"] and not st["mfa_pending"]


def test_an_expired_mfa_sign_in_must_start_again(env):
    FakeGarmin.mfa = True
    garmin.login("me@example.com", "pw")
    g, _ = garmin._pending_mfa[str(env)]
    garmin._pending_mfa[str(env)] = (g, time.monotonic() - garmin.MFA_TTL_S - 1)
    with pytest.raises(garmin.GarminError, match="expired"):
        garmin.submit_mfa("123456")


@pytest.mark.parametrize("err,status", [
    (garminconnect.GarminConnectAuthenticationError("401"), 400),
    (garminconnect.GarminConnectTooManyRequestsError("429"), 429),
    (garminconnect.GarminConnectConnectionError("down"), 502),
])
def test_login_failures_become_readable_errors(env, err, status):
    FakeGarmin.error = err
    with pytest.raises(garmin.GarminError) as e:
        garmin.login("me@example.com", "pw")
    assert e.value.status == status
    assert not garmin.connected()


def test_sync_stores_health_in_both_stores_and_garmin_wins(env, monkeypatch):
    garmin.login("me@example.com", "pw")
    day = clock.today().isoformat()
    # intervals.icu already stored a different reading for today.
    ride_storage.persist_wellness({"id": day, "hrv": 40, "restingHR": 60, "ctl": 50})
    res = garmin.sync(days=2)
    assert res["health_days"] == 2
    rec = json.loads((env / "wellness" / f"{day}.json").read_text())
    assert (rec["hrv"], rec["restingHR"], rec["sleepSecs"], rec["ctl"]) == (62, 47, 27000, 50)
    assert rec["garmin"]["bodyBatteryHigh"] == 90
    row = db.get_db().execute("SELECT hrv, rhr, sleep_secs, sleep_score FROM wellness WHERE date=?", (day,)).fetchone()
    assert tuple(row) == (62, 47, 27000, 81)

    # The next intervals.icu fetch carries its own numbers: the overlay puts Garmin's back.
    monkeypatch.setattr(training, "_require_credentials", lambda: None)
    monkeypatch.setattr(training, "_get", lambda *a, **k: [{"id": day, "hrv": 40, "restingHR": 60, "ctl": 51}])
    monkeypatch.setattr(training.config, "ICU_ATHLETE_ID", "i1", raising=False)
    fetched = training.fetch_wellness(days=2)
    assert fetched[0]["hrv"] == 62 and fetched[0]["restingHR"] == 47 and fetched[0]["ctl"] == 51
    # ...and storing that fetch keeps the Garmin values and the Garmin block.
    ride_storage.persist_wellness(fetched[0])
    rec = json.loads((env / "wellness" / f"{day}.json").read_text())
    assert rec["hrv"] == 62 and rec["garmin"]["steps"] == 9000


def test_overlay_is_a_no_op_when_garmin_is_not_connected(env):
    recs = [{"id": "2026-10-17", "hrv": 40}]
    assert garmin.overlay_health(recs) == [{"id": "2026-10-17", "hrv": 40}]


def test_sync_imports_training_activities_once_and_drops_unreadable_files(env, monkeypatch):
    garmin.login("me@example.com", "pw")
    start = (clock.today() - timedelta(days=1)).isoformat()
    FakeGarmin.activities = [
        {"activityId": 1, "activityType": {"typeKey": "road_biking"}, "startTimeGMT": f"{start} 06:00:00"},
        {"activityId": 2, "activityType": {"typeKey": "walking"}},
        {"activityId": 3, "activityType": {"typeKey": "treadmill_running"}},
        {"activityId": 4, "activityType": {"typeKey": "indoor_cycling"}},
    ]
    monkeypatch.setattr(garmin, "fit_importer", lambda p: p.name != "garmin-4.fit")
    assert garmin.sync(days=2)["activities_imported"] == 2
    assert sorted(FakeGarmin.downloads) == ["1", "3", "4"]
    assert sorted(p.name for p in (env / "rides").glob("*.fit")) == ["garmin-1.fit", "garmin-3.fit"]
    assert (env / "rides" / "garmin-1.fit").read_bytes() == FIT
    FakeGarmin.downloads = []
    assert garmin.sync(days=2)["activities_imported"] == 0
    assert FakeGarmin.downloads == ["4"]          # only the rejected one is tried again
    assert garmin.status()["activities_imported"] == 2


def test_relay_to_intervals_icu_only_when_on_and_icu_lacks_the_ride(env, monkeypatch):
    garmin.login("me@example.com", "pw")
    FakeGarmin.activities = [
        {"activityId": 1, "activityType": {"typeKey": "cycling"}, "startTimeLocal": "2026-10-17 07:00:00"},
        {"activityId": 2, "activityType": {"typeKey": "cycling"}, "startTimeLocal": "2026-10-17 18:00:00"},
    ]
    monkeypatch.setattr(ride_storage, "load_icu_rides", lambda: [{"started_at": "2026-10-17T07:00:30"}])
    up = mock.Mock(return_value={"ok": True, "status": 201})
    monkeypatch.setattr(training, "upload_fit_to_icu", up)
    garmin.sync(days=1)
    up.assert_not_called()
    for p in (env / "rides").glob("*.fit"):
        p.unlink()
    garmin.set_relay(True)
    garmin.sync(days=1)
    assert [c.args[0].name for c in up.call_args_list] == ["garmin-2.fit"]


def test_rejected_tokens_mark_the_connection_as_needing_a_new_sign_in(env):
    garmin.login("me@example.com", "pw")
    FakeGarmin.reject_tokens = True
    with pytest.raises(garmin.GarminError, match="Sign in again"):
        garmin.sync(days=1)
    st = garmin.status()
    assert st["needs_login"] and st["connected"]


def test_fit_from_zip():
    assert garmin._fit_from_zip(_zip()) == FIT
    assert garmin._fit_from_zip(FIT) == FIT
    with pytest.raises(ValueError):
        garmin._fit_from_zip(_zip(name="notes.txt"))


def test_disconnect_forgets_the_tokens_but_keeps_the_data(env):
    garmin.login("me@example.com", "pw")
    garmin.sync(days=1)
    st = garmin.disconnect()
    assert not st["connected"]
    assert list((env / "wellness").glob("*.json"))


@pytest.fixture
def c(env):
    with TestClient(app_module.app) as client:
        yield client


def test_endpoints(c, env):
    assert c.get("/api/garmin").json()["connected"] is False
    assert c.post("/api/garmin/login", json={"email": "", "password": ""}).status_code == 400
    assert c.post("/api/garmin/sync").status_code == 400
    assert c.post("/api/garmin/settings", json={"relay_to_icu": "yes"}).status_code == 400
    r = c.post("/api/garmin/login", json={"email": "me@example.com", "password": "pw"})
    assert r.status_code == 200 and r.json()["connected"] is True and "pw" not in r.text.replace("mfa_pending", "")
    assert c.post("/api/garmin/settings", json={"relay_to_icu": True}).json()["relay_to_icu"] is True
    assert c.post("/api/garmin/sync").json()["health_days"] >= 1
    assert c.delete("/api/garmin").json()["connected"] is False
