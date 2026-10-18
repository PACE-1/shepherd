"""Notifications: daily readiness, a missed planned session, a failing sync (#131).

Two channels. Every notice lands in an in-app list (the bell). If the rider
set an ntfy-compatible URL (ntfy.sh or self-hosted), the same notice is also
POSTed there: plain-text body, ``Title`` header. No SDK, no web-push.

Storage, per profile directory:
  ``notifications.json``        settings, mode 0600 (the URL may hold a topic secret)
  ``notifications_state.json``  the list, the (event, day) dedupe keys, the sync-failure latch

The URL is write-only: ``public()`` returns ``has_url``, never the URL, and no
message or log line built here contains it.

Hooks (called from the sync loop, never raise): ``on_sync_pass`` after a good
pass, ``on_sync_failure`` after a failed one.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

import httpx

from atomic_io import file_lock, update_json, write_text_atomic

log = logging.getLogger("shepherd.notifications")

EVENTS = ("readiness", "missed", "sync_failure")
POST_TIMEOUT_S = 5
MAX_ITEMS = 100
KEEP_DAYS = 60            # dedupe keys older than this are dropped
_DEFAULT = {"ntfy_url": "", "events": {e: True for e in EVENTS}, "readiness_time": ""}


class NotificationError(ValueError):
    """Bad input; the message is safe to show (it never contains the URL)."""


def _settings_path(pd: Path) -> Path:
    return Path(pd) / "notifications.json"


def _state_path(pd: Path) -> Path:
    return Path(pd) / "notifications_state.json"


# ── settings ────────────────────────────────────────────────────────────────

def load_settings(pd: Path) -> dict:
    try:
        raw = json.loads(_settings_path(pd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    ev = raw.get("events") if isinstance(raw.get("events"), dict) else {}
    return {
        "ntfy_url": raw.get("ntfy_url") if isinstance(raw.get("ntfy_url"), str) else "",
        "events": {e: bool(ev.get(e, True)) for e in EVENTS},
        "readiness_time": raw.get("readiness_time") if isinstance(raw.get("readiness_time"), str) else "",
    }


def public(s: dict) -> dict:
    """What the interface may see: everything except the URL."""
    return {"has_url": bool(s.get("ntfy_url")), "events": dict(s["events"]),
            "readiness_time": s.get("readiness_time", "")}


def validate_url(url: str) -> str:
    """The URL as stored, or NotificationError. http(s) only, with a host.

    Credentials typed into the URL (``user:pass@host``) are kept as typed, since
    that is how a self-hosted ntfy with basic auth is addressed; nothing is added.
    """
    url = (url or "").strip()
    if not url or len(url) > 2000 or any(c.isspace() or ord(c) < 32 for c in url):
        raise NotificationError("Enter a full http:// or https:// address, with no spaces.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        raise NotificationError("That address could not be read.") from None
    if parts.scheme not in ("http", "https") or not host:
        raise NotificationError("The address must start with http:// or https:// and name a host.")
    return url


def validate_time(text: str) -> str:
    text = (text or "").strip()
    if text and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
        raise NotificationError("Time must be HH:MM (24-hour) or empty for the first sync of the day.")
    return text


def save_settings(pd: Path, ntfy_url: Optional[str] = None, events: Optional[dict] = None,
                  readiness_time: Optional[str] = None) -> dict:
    """Validate, merge and store. ``ntfy_url`` None keeps the stored URL, "" clears it."""
    new_url = None if ntfy_url is None else (validate_url(ntfy_url) if ntfy_url.strip() else "")
    new_time = None if readiness_time is None else validate_time(readiness_time)
    if events is not None and (not isinstance(events, dict) or set(events) - set(EVENTS)):
        raise NotificationError("Unknown notification type.")
    with file_lock(_settings_path(pd)):
        s = load_settings(pd)
        if new_url is not None:
            s["ntfy_url"] = new_url
        if new_time is not None:
            s["readiness_time"] = new_time
        for k, v in (events or {}).items():
            s["events"][k] = bool(v)
        write_text_atomic(_settings_path(pd), json.dumps(s, indent=2), mode=0o600)
    return s


# ── delivery ────────────────────────────────────────────────────────────────

def post_ntfy(url: str, title: str, body: str) -> tuple[bool, str]:
    """POST one notice. Never raises; the reason never contains the URL."""
    try:
        from http_util import _icu_verify
        r = httpx.post(url, content=body.encode("utf-8"), timeout=POST_TIMEOUT_S, follow_redirects=False,
                       headers={"Title": title.encode("ascii", "replace").decode(),
                                "Content-Type": "text/plain; charset=utf-8"},
                       verify=_icu_verify())
        if r.status_code >= 400:
            return False, f"The server answered {r.status_code}."
        return True, ""
    except Exception as e:  # noqa: BLE001 - delivery is best-effort; exception text can hold the URL
        return False, f"Could not reach the server ({e.__class__.__name__})."


def _spawn(fn: Callable[[], None]) -> None:
    """Run ``fn`` off the calling thread (tests replace this to run inline)."""
    threading.Thread(target=fn, name="ntfy-post", daemon=True).start()


def notify(pd: Path, event: str, day: str, title: str, body: str, now: Optional[datetime] = None) -> bool:
    """Record one notice and send it, once per (event, day). False when off or already sent."""
    s = load_settings(pd)
    if not s["events"].get(event):
        return False
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    key = f"{event}:{day}"
    created = []

    def claim(st: dict) -> Optional[bool]:
        sent = st.setdefault("sent", {})
        if key in sent:
            return False        # skip the write
        cutoff = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
        st["sent"] = sent = {k: d for k, d in sent.items() if d >= cutoff}
        sent[key] = day
        st["seq"] = seq = int(st.get("seq", 0)) + 1
        items = st.setdefault("items", [])
        items.insert(0, {"id": seq, "event": event, "day": day, "title": title, "body": body,
                         "ts": stamp, "read": False})
        del items[MAX_ITEMS:]
        created.append(True)
        return None

    update_json(_state_path(pd), claim, default=dict)
    if not created:
        return False
    if s["ntfy_url"]:
        url = s["ntfy_url"]

        def send() -> None:
            ok, why = post_ntfy(url, title, body)
            if not ok:
                log.info("EVENT=ntfy_failed event=%s reason=%s", event, why)
        _spawn(send)
    return True


# ── the list ────────────────────────────────────────────────────────────────

def listing(pd: Path) -> dict:
    try:
        st = json.loads(_state_path(pd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    items = st.get("items") if isinstance(st, dict) and isinstance(st.get("items"), list) else []
    return {"items": items, "unread": sum(1 for i in items if not i.get("read"))}


def mark_all_read(pd: Path) -> dict:
    def mutate(st: dict) -> Optional[bool]:
        if not any(not i.get("read") for i in st.get("items", [])):
            return False
        for i in st["items"]:
            i["read"] = True
        return None
    update_json(_state_path(pd), mutate, default=dict)
    return listing(pd)


# ── the three events ────────────────────────────────────────────────────────

def _set_failing(pd: Path, failing: bool) -> bool:
    """Set the sync-failure latch; True when this call flipped it."""
    flipped = []

    def mutate(st: dict) -> Optional[bool]:
        if bool(st.get("sync_failing")) == failing:
            return False
        st["sync_failing"] = failing
        flipped.append(True)
        return None
    update_json(_state_path(pd), mutate, default=dict)
    return bool(flipped)


def check_sync_failure(pd: Path, today: date, error: str, now: Optional[datetime] = None) -> bool:
    """Once per failure episode (until a pass succeeds), and at most once a day."""
    if not _set_failing(pd, True):
        return False
    msg = (error or "").strip().splitlines()[0][:160] if (error or "").strip() else "unknown error"
    return notify(pd, "sync_failure", today.isoformat(), "Shepherd: intervals.icu sync failed",
                  f"The background sync is failing ({msg}). Your data may be out of date. "
                  "Check the connection in Settings.", now)


def check_readiness(pd: Path, today: date, now: datetime, get_readiness: Callable[[str], Optional[dict]],
                    get_planned: Callable[[str], Optional[dict]]) -> bool:
    """Today's readiness, once, from ``readiness_time`` on (empty: the first pass of the day)."""
    s = load_settings(pd)
    if not s["events"]["readiness"]:
        return False
    day = today.isoformat()
    if f"readiness:{day}" in _sent(pd):
        return False
    if s["readiness_time"] and now.strftime("%H:%M") < s["readiness_time"]:
        return False
    r = get_readiness(day)
    if not r or r.get("score") is None:
        return False            # not enough wellness yet: try again next pass
    text = f"Readiness {r['score']:.1f} of 10. {r.get('advice', '')}".strip()
    p = get_planned(day)
    if p:
        text += f" Planned today: {p['name']}, {p['minutes']} min."
    return notify(pd, "readiness", day, f"Shepherd: readiness {r['score']:.1f}/10", text, now)


def check_missed(pd: Path, today: date, now: datetime, get_planned: Callable[[str], Optional[dict]],
                 had_activity: Callable[[str], bool]) -> bool:
    """Yesterday had a planned session and no activity: say so, once."""
    yday = (today - timedelta(days=1)).isoformat()
    if not load_settings(pd)["events"]["missed"] or f"missed:{yday}" in _sent(pd):
        return False
    p = get_planned(yday)
    if not p or had_activity(yday):
        return False
    return notify(pd, "missed", yday, "Shepherd: missed session",
                  f"Yesterday's {p['name']} ({p['minutes']} min) has no activity. "
                  "Open the plan to move it or let it go.", now)


def _sent(pd: Path) -> dict:
    try:
        st = json.loads(_state_path(pd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return st.get("sent", {}) if isinstance(st, dict) else {}


# ── real data sources (lazy imports keep this module pure for tests) ────────

def _planned(pd: Path, day: str) -> Optional[dict]:
    """The plan's session on ``day`` that is still owed, or None (no plan, rest day, done, dismissed, moved)."""
    try:
        plan = json.loads((Path(pd) / "plans" / "current_plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for w in plan.get("weeks") or []:
        for s in w.get("sessions") or []:
            if s.get("day") != day:
                continue
            st = str(s.get("status") or "pending")
            if (s.get("session_type") or "rest") == "rest" or st in ("done", "done_partial", "dismissed") \
                    or st.startswith("moved"):
                return None
            name = str(s.get("zwo_name") or s.get("session_type")).replace("_", " ")
            return {"name": name, "minutes": int(round(float(s.get("duration_min") or 0)))}
    return None


def _had_activity(day: str) -> bool:
    import db
    row = db.get_db().execute("SELECT 1 FROM activities WHERE substr(date, 1, 10) = ? LIMIT 1", (day,)).fetchone()
    return row is not None


def _readiness(pid: str, day: str) -> Optional[dict]:
    import readiness_composite
    return readiness_composite.compute_readiness_composite(pid, day)


def _active():
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    return (pm.active_dir, pm.active_id) if pm.active_id else (None, None)


def on_sync_pass() -> None:
    """After a good sync pass: end any failure episode, then the daily readiness and missed-session checks."""
    try:
        import clock
        pd, pid = _active()
        if pd is None:
            return
        now = clock.now()
        _set_failing(pd, False)
        check_readiness(pd, now.date(), now, lambda d: _readiness(pid, d), lambda d: _planned(pd, d))
        check_missed(pd, now.date(), now, lambda d: _planned(pd, d), _had_activity)
    except Exception:  # noqa: BLE001 - never break the sync loop
        log.debug("notifications: sync-pass check failed", exc_info=True)


def on_sync_failure(error: str) -> None:
    """After a failed sync pass."""
    try:
        import clock
        pd, _pid = _active()
        if pd is None:
            return
        now = clock.now()
        check_sync_failure(pd, now.date(), error, now)
    except Exception:  # noqa: BLE001 - never break the sync loop
        log.debug("notifications: sync-failure check failed", exc_info=True)
