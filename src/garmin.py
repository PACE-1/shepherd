"""Garmin Connect as the source of health data and activity files.

The rider signs in once with their Garmin email and password (and the MFA code
Garmin sends, when the account has MFA). Only the tokens python-garminconnect
issues are stored, in ``<profile>/garmin/garmin_tokens.json`` (0600 inside a
0700 directory, written by the library); the password is never written. The
tokens refresh themselves; when Garmin stops accepting them the rider signs in
again.

What a sync pulls, per day: sleep time and score, overnight HRV, resting HR,
plus body battery, stress, steps and the morning training readiness score.
Sleep, HRV and resting HR land in the same fields intervals.icu fills, and
Garmin's value wins: ``overlay_health`` applies it to every intervals.icu
wellness fetch, so the stores and the live reads agree. Activities are
downloaded as their original FIT and go through the same import as a FIT the
rider uploads (``fit_importer``, set by app.py); the ride list already prefers
the intervals.icu copy of a ride both sources have.

Unofficial: python-garminconnect uses the endpoints Garmin's own app uses, so a
change on Garmin's side can break it. Nothing here is needed for the app to run.
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import clock
from atomic_io import update_json

log = logging.getLogger("shepherd.garmin")

TOKEN_FILE = "garmin_tokens.json"
STATE_FILE = "state.json"
FIRST_SYNC_DAYS = 30        # history pulled the first time
RESYNC_DAYS = 3             # later passes re-read the last days (late watch syncs)
SYNC_INTERVAL_S = 3600
MFA_TTL_S = 600
MAX_FIT_BYTES = 50 * 1024 * 1024
# ponytail: keyword match on Garmin's typeKey; a per-sport choice in Settings if riders ask
_TRAINING_TYPES = ("cycl", "biking", "bike", "ride", "run", "swim", "multi_sport", "triathlon")

# Set by app.py at startup: imports one FIT already written to the rides folder
# (parse, load sidecar). Returns False when the file is not a usable activity.
fit_importer: Optional[Callable[[Path], bool]] = None

_pending_mfa: dict[str, tuple[object, float]] = {}   # profile dir -> (Garmin, started)
_sync_lock = threading.Lock()
_stop = threading.Event()


class GarminError(Exception):
    """A failure the rider can act on; the message is safe to show."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def available() -> bool:
    try:
        import garminconnect  # noqa: F401
        return True
    except ImportError:
        return False


def _profile_dir() -> Path:
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    if pm.active_id is None:
        raise GarminError("No active profile.", 400)
    return Path(pm.active_dir)


def _dir(profile_dir: Path) -> Path:
    return Path(profile_dir) / "garmin"


def connected(profile_dir: "Path | None" = None) -> bool:
    try:
        profile_dir = profile_dir or _profile_dir()
    except GarminError:
        return False
    return (_dir(profile_dir) / TOKEN_FILE).exists()


def _load_state(profile_dir: Path) -> dict:
    try:
        d = json.loads((_dir(profile_dir) / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _update_state(profile_dir: Path, **changes) -> dict:
    _dir(profile_dir).mkdir(parents=True, exist_ok=True)

    def mutate(d):
        d = d if isinstance(d, dict) else {}
        d.update(changes)
        return d
    return update_json(_dir(profile_dir) / STATE_FILE, mutate)


def status(profile_dir: "Path | None" = None) -> dict:
    profile_dir = profile_dir or _profile_dir()
    st = _load_state(profile_dir)
    pending = _pending_mfa.get(str(profile_dir))
    return {
        "available": available(),
        "connected": connected(profile_dir),
        "needs_login": bool(st.get("needs_login")),
        "mfa_pending": bool(pending and time.monotonic() - pending[1] < MFA_TTL_S),
        "name": st.get("name", ""),
        "relay_to_icu": bool(st.get("relay_to_icu")),
        "last_sync_at": st.get("last_sync_at"),
        "last_error": st.get("last_error"),
        "health_days": int(st.get("health_days") or 0),            # last pass
        "activities_imported": int(st.get("activities_imported") or 0),
    }


def _errors():
    import garminconnect as gc
    return gc.GarminConnectAuthenticationError, gc.GarminConnectTooManyRequestsError


def _translate(e: Exception) -> GarminError:
    auth, too_many = _errors()
    if isinstance(e, too_many):
        return GarminError("Garmin is limiting sign-ins. Wait a few minutes and try again.", 429)
    if isinstance(e, auth):
        return GarminError("Garmin did not accept that email and password.", 400)
    return GarminError(f"Couldn't reach Garmin Connect: {e}", 502)


def _finish_login(profile_dir: Path, g) -> dict:
    """Store the tokens of a completed login and remember who signed in."""
    _dir(profile_dir).mkdir(parents=True, exist_ok=True)
    g.client.dump(str(_dir(profile_dir)))
    name = getattr(g, "full_name", "") or getattr(g, "display_name", "") or ""
    _update_state(profile_dir, needs_login=False, last_error=None, name=name)
    return status(profile_dir)


def login(email: str, password: str) -> dict:
    """Start a sign-in. Returns the status; ``mfa_pending`` asks for ``submit_mfa``."""
    if not available():
        raise GarminError("The garminconnect package is not installed.", 501)
    email, password = (email or "").strip(), password or ""
    if not email or not password:
        raise GarminError("Enter your Garmin email and password.", 400)
    from garminconnect import Garmin
    profile_dir = _profile_dir()
    g = Garmin(email, password, return_on_mfa=True)
    try:
        needs, _ = g.login()
    except Exception as e:
        raise _translate(e) from e
    if needs == "needs_mfa":
        _pending_mfa[str(profile_dir)] = (g, time.monotonic())
        return status(profile_dir)
    # return_on_mfa returns before the profile is read: dump, then resume from the
    # tokens, which loads it (and proves they work).
    _dir(profile_dir).mkdir(parents=True, exist_ok=True)
    g.client.dump(str(_dir(profile_dir)))
    return _finish_login(profile_dir, _client(profile_dir))


def submit_mfa(code: str) -> dict:
    profile_dir = _profile_dir()
    pending = _pending_mfa.get(str(profile_dir))
    if not pending or time.monotonic() - pending[1] >= MFA_TTL_S:
        _pending_mfa.pop(str(profile_dir), None)
        raise GarminError("The sign-in expired. Start again.", 400)
    code = (code or "").strip()
    if not code:
        raise GarminError("Enter the code Garmin sent you.", 400)
    g = pending[0]
    try:
        g.resume_login(None, code)
    except Exception as e:
        # A wrong code keeps the pending sign-in, so the rider can retry it.
        raise GarminError(f"Garmin did not accept that code: {e}", 400) from e
    _pending_mfa.pop(str(profile_dir), None)
    return _finish_login(profile_dir, g)


def disconnect() -> dict:
    """Forget the tokens. Data already synced stays."""
    profile_dir = _profile_dir()
    _pending_mfa.pop(str(profile_dir), None)
    try:
        (_dir(profile_dir) / TOKEN_FILE).unlink()
    except FileNotFoundError:
        pass
    _update_state(profile_dir, needs_login=False, name="", last_error=None)
    return status(profile_dir)


def set_relay(on: bool) -> dict:
    profile_dir = _profile_dir()
    _update_state(profile_dir, relay_to_icu=bool(on))
    return status(profile_dir)


def _client(profile_dir: Path):
    """A signed-in client from the stored tokens (refreshed when due)."""
    from garminconnect import Garmin
    g = Garmin()
    try:
        g.login(tokenstore=str(_dir(profile_dir)))
    except Exception as e:
        auth, _ = _errors()
        if isinstance(e, auth):
            _update_state(profile_dir, needs_login=True,
                          last_error="Garmin no longer accepts the saved sign-in. Sign in again.")
            raise GarminError("Garmin no longer accepts the saved sign-in. Sign in again.", 400) from e
        raise _translate(e) from e
    return g


# ── health ────────────────────────────────────────────────────────────────

def _call(fn, *args):
    """One endpoint; a day Garmin has nothing for is None, not a failed sync."""
    try:
        return fn(*args)
    except Exception as e:
        auth, too_many = _errors()
        if isinstance(e, (auth, too_many)):
            raise
        log.debug("garmin %s(%s) failed: %s", getattr(fn, "__name__", fn), args, e)
        return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def health_for_day(g, day: str) -> dict:
    """The day's values under intervals.icu's wellness field names, plus extras."""
    sleep = _call(g.get_sleep_data, day) or {}
    dto = sleep.get("dailySleepDTO") or {}
    hrv = (_call(g.get_hrv_data, day) or {}).get("hrvSummary") or {}
    summary = _call(g.get_user_summary, day) or {}
    readiness = _call(g.get_morning_training_readiness, day) or {}
    return {
        "hrv": _num(hrv.get("lastNightAvg")),
        "restingHR": _num(summary.get("restingHeartRate")) or _num(sleep.get("restingHeartRate")),
        "sleepSecs": _num(dto.get("sleepTimeSeconds")),
        "sleepScore": _num(((dto.get("sleepScores") or {}).get("overall") or {}).get("value")),
        "bodyBatteryHigh": _num(summary.get("bodyBatteryHighestValue")),
        "bodyBatteryLow": _num(summary.get("bodyBatteryLowestValue")),
        "stressAvg": _num(summary.get("averageStressLevel")),
        "steps": _num(summary.get("totalSteps")),
        "trainingReadiness": _num(readiness.get("score")) if isinstance(readiness, dict) else None,
    }


_ICU_KEYS = ("hrv", "restingHR", "sleepSecs", "sleepScore")


def _store_health(day: str, values: dict) -> bool:
    """Write one day into the per-day wellness file and the SQLite row."""
    import db
    import ride_storage
    found = {k: v for k, v in values.items() if v is not None}
    if not found:
        return False
    record = {"id": day, **{k: found[k] for k in _ICU_KEYS if k in found}}
    record["garmin"] = {**found, "synced_at": clock.now(timezone.utc).isoformat()}
    ride_storage.persist_wellness(record)
    conn = db.get_db()
    conn.execute(
        """INSERT INTO wellness (date, hrv, rhr, sleep_secs, sleep_score)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               hrv         = COALESCE(excluded.hrv, wellness.hrv),
               rhr         = COALESCE(excluded.rhr, wellness.rhr),
               sleep_secs  = COALESCE(excluded.sleep_secs, wellness.sleep_secs),
               sleep_score = COALESCE(excluded.sleep_score, wellness.sleep_score)""",
        (day, found.get("hrv"), found.get("restingHR"), found.get("sleepSecs"), found.get("sleepScore")),
    )
    conn.commit()
    return True


def overlay_health(records: list) -> list:
    """Garmin's stored values over intervals.icu wellness records, in place.

    Called on every intervals.icu wellness fetch, so a sync that stores what
    intervals.icu says, and every live reader, sees Garmin's numbers.
    """
    if not records or not connected():
        return records
    try:
        import ride_storage
        wdir = ride_storage._wellness_dir()
    except Exception:
        return records
    for rec in records:
        day = rec.get("id") if isinstance(rec, dict) else None
        if not isinstance(day, str) or len(day) != 10:
            continue
        try:
            stored = json.loads((wdir / f"{day}.json").read_text(encoding="utf-8")).get("garmin") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for k in _ICU_KEYS:
            if stored.get(k) is not None:
                rec[k] = stored[k]
    return records


# ── activities ────────────────────────────────────────────────────────────

def _is_training(activity: dict) -> bool:
    key = str((activity.get("activityType") or {}).get("typeKey") or "").lower()
    return any(t in key for t in _TRAINING_TYPES)


def _fit_from_zip(data: bytes) -> bytes:
    """The FIT inside Garmin's "original" download (a zip), size-bounded."""
    if data[8:12] == b".FIT":
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.filename.lower().endswith(".fit"):
                if info.file_size > MAX_FIT_BYTES:
                    raise ValueError("FIT larger than 50 MB")
                return z.read(info)
    raise ValueError("no FIT file in the download")


def _start_utc(activity: dict) -> "datetime | None":
    raw = activity.get("startTimeGMT")
    try:
        return datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _has_icu_twin(activity: dict) -> bool:
    import ride_storage
    mine = {"started_at": str(activity.get("startTimeLocal") or "").replace(" ", "T")}
    return any(ride_storage._same_ride_start(mine, r) for r in ride_storage.load_icu_rides())


def _download_fit(g, activity: dict) -> "bytes | None":
    """The activity's FIT, or None when it is already imported or has none."""
    import ride_storage
    aid = activity.get("activityId")
    if not isinstance(aid, int) or (ride_storage._fit_rides_dir() / f"garmin-{aid}.fit").exists():
        return None
    raw = g.download_activity(str(aid), dl_fmt=g.ActivityDownloadFormat.ORIGINAL)
    try:
        return _fit_from_zip(raw)
    except (ValueError, zipfile.BadZipFile) as e:
        log.info("EVENT=garmin_activity_skipped id=%s reason=%s", aid, e)
        return None


def _import_activity(activity: dict, data: bytes) -> bool:
    """Write one downloaded FIT into the rides folder and import it."""
    import ride_storage
    fit_path = ride_storage._fit_rides_dir() / f"garmin-{activity['activityId']}.fit"
    tmp = fit_path.with_name(fit_path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, fit_path)
    start = _start_utc(activity)
    if start is not None:
        # The listing sorts a FIT without a sidecar by mtime: make that the start.
        os.utime(fit_path, (start.timestamp(), start.timestamp()))
    if fit_importer is not None and not fit_importer(fit_path):
        fit_path.unlink(missing_ok=True)
        return False
    return True


def _relay(activity: dict) -> None:
    """Send an imported Garmin FIT on to intervals.icu, unless it already has the ride."""
    import ride_storage
    if _has_icu_twin(activity):
        return
    fit_path = ride_storage._fit_rides_dir() / f"garmin-{activity['activityId']}.fit"
    try:
        from training import upload_fit_to_icu
        res = upload_fit_to_icu(fit_path, 1)
        log.info("EVENT=garmin_icu_relay id=%s ok=%s status=%s",
                 activity["activityId"], res.get("ok"), res.get("status"))
    except Exception as e:
        log.warning("EVENT=garmin_icu_relay_failed id=%s err=%s", activity["activityId"], e)


# ── sync ──────────────────────────────────────────────────────────────────

def sync(days: "int | None" = None) -> dict:
    """Pull health days and new activities for the active profile."""
    import db
    profile_dir = _profile_dir()
    if not connected(profile_dir):
        raise GarminError("Garmin is not connected.", 400)
    if not _sync_lock.acquire(blocking=False):
        return {"health_days": 0, "activities_imported": 0, "skipped": "busy"}
    try:
        snapshot = db.snapshot_sync_identity()
        st = _load_state(profile_dir)
        if days is None:
            days = RESYNC_DAYS if st.get("last_sync_at") else FIRST_SYNC_DAYS
        today = clock.today()
        start = today - timedelta(days=days - 1)
        health = imported = 0
        try:
            g = _client(profile_dir)
            for i in range(days):
                if _stop.is_set():
                    break
                day = (start + timedelta(days=i)).isoformat()
                values = health_for_day(g, day)
                with db.sync_write_gate(snapshot):
                    health += _store_health(day, values)
            activities = g.get_activities_by_date(start.isoformat(), today.isoformat())
            relay = bool(st.get("relay_to_icu"))
            for a in activities or []:
                if _stop.is_set():
                    break
                if not isinstance(a, dict) or not _is_training(a):
                    continue
                data = _download_fit(g, a)
                if data is None:
                    continue
                with db.sync_write_gate(snapshot):
                    ok = _import_activity(a, data)
                if ok:
                    imported += 1
                    if relay:
                        _relay(a)
            g.client.dump(str(_dir(profile_dir)))   # keep refreshed tokens
        except db.SyncAborted:
            log.info("garmin sync aborted: profile switched")
            return {"health_days": health, "activities_imported": imported, "skipped": "profile_switched"}
        except Exception as e:
            err = e if isinstance(e, GarminError) else _translate(e)
            _update_state(profile_dir, last_error=str(err))
            raise err from e
        _update_state(
            profile_dir, last_sync_at=clock.now(timezone.utc).isoformat(), last_error=None,
            health_days=health,
            activities_imported=int(st.get("activities_imported") or 0) + imported,
        )
        log.info("EVENT=garmin_sync_done health_days=%d activities=%d", health, imported)
        return {"health_days": health, "activities_imported": imported}
    finally:
        _sync_lock.release()


def _loop() -> None:
    # First pass a minute after start, so booting stays quick.
    delay = 60.0
    while not _stop.wait(delay):
        delay = SYNC_INTERVAL_S
        try:
            if connected() and not status().get("needs_login"):
                sync()
        except Exception as e:
            log.warning("background garmin sync failed: %s", e)


def start_background() -> None:
    import jobs
    _stop.clear()
    jobs.start_thread(_loop, name="garmin-sync", cancel=_stop.set)
