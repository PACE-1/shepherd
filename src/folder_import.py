"""Folder import (#31 Phase 1): bring rides in from a folder of .fit files.

The route that does not depend on the intervals.icu API. The rider names one
folder per profile; a scan imports the .fit files in it that Shepherd does not
already have, through the same code the FIT upload endpoint uses
(app._import_fit_locked), so an imported file is stored, parsed, given its load
and relayed to intervals.icu exactly like an uploaded one.

Rules:
  * Source files are only ever opened for reading: never moved, renamed,
    changed or deleted.
  * Only regular files whose names end in .fit. Symlinks are skipped, and a
    recursive scan does not follow symlinked folders.
  * A file is a duplicate when a stored ride (from intervals.icu or an earlier
    import) started within START_TOLERANCE_S of it and its length is within
    DURATION_TOLERANCE.
  * At most MAX_FILES_PER_SCAN new files per scan; the rest wait for the next.
  * A file that cannot be read is counted as failed; the scan carries on.

Storage: ``<profile>/folder_import.json`` holds the folder, the recursive flag,
the last scan's counts and the files already handled (by path, size and mtime).
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from atomic_io import update_json

log = logging.getLogger("shepherd.folder_import")

MAX_FILES_PER_SCAN = 200
START_TOLERANCE_S = 60
DURATION_TOLERANCE = 0.05
MAX_FILE_BYTES = 50 * 1024 * 1024      # the upload endpoint's limit
_FILE = "folder_import.json"

_running: set = set()                   # profile ids with a scan in progress
_running_lock = threading.Lock()


class FolderImportError(ValueError):
    """Bad input; the message is safe to show."""


def _path(pd: Path) -> Path:
    return Path(pd) / _FILE


def load(pd: Path) -> dict:
    try:
        raw = json.loads(_path(pd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    return {
        "folder": raw.get("folder") if isinstance(raw.get("folder"), str) else "",
        "recursive": bool(raw.get("recursive", False)),
        "last_scan": raw.get("last_scan") if isinstance(raw.get("last_scan"), dict) else None,
        "handled": raw.get("handled") if isinstance(raw.get("handled"), dict) else {},
    }


def public(pd: Path, pid: str) -> dict:
    s = load(pd)
    return {"folder": s["folder"], "recursive": s["recursive"], "running": pid in _running,
            "max_files": MAX_FILES_PER_SCAN, "last_scan": s["last_scan"]}


def validate_folder(text: str) -> str:
    """The folder as stored ("" clears it), or FolderImportError."""
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) > 1024 or "\x00" in text:
        raise FolderImportError("That path could not be read.")
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise FolderImportError("Enter the full path to the folder, for example /home/you/FIT.")
    if not p.is_dir():
        raise FolderImportError("That folder does not exist on the machine Shepherd runs on. "
                                "In Docker, it must be a path inside a mounted volume.")
    if not os.access(p, os.R_OK | os.X_OK):
        raise FolderImportError("Shepherd cannot read that folder. Check its permissions.")
    return str(p)


def save(pd: Path, folder: Optional[str], recursive: Optional[bool]) -> dict:
    new_folder = None if folder is None else validate_folder(folder)

    def mutate(st: dict) -> None:
        if new_folder is not None:
            if new_folder != st.get("folder"):
                st["last_scan"] = None
            st["folder"] = new_folder
        if recursive is not None:
            st["recursive"] = bool(recursive)
    update_json(_path(pd), mutate, default=dict)
    return load(pd)


# ── what a scan looks at ────────────────────────────────────────────────────

def _is_fit_file(p: Path) -> bool:
    if not p.name.lower().endswith(".fit") or p.name.startswith("."):
        return False
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)      # lstat: a symlink is not a regular file
    except OSError:
        return False


def candidates(folder: Path, recursive: bool) -> list[Path]:
    """Regular .fit files in ``folder`` (and below it if ``recursive``), newest first."""
    out: list[Path] = []
    if recursive:
        for root, _dirs, files in os.walk(folder, followlinks=False):
            out.extend(p for p in (Path(root) / f for f in files) if _is_fit_file(p))
    else:
        with os.scandir(folder) as it:
            out.extend(Path(e.path) for e in it if _is_fit_file(Path(e.path)))

    def mtime(p: Path) -> float:
        try:
            return os.lstat(p).st_mtime
        except OSError:
            return 0.0
    return sorted(out, key=mtime, reverse=True)


def _key(folder: Path, p: Path) -> str:
    st = os.lstat(p)
    return f"{p.relative_to(folder).as_posix()}|{st.st_size}|{int(st.st_mtime)}"


def _local(text) -> Optional[datetime]:
    """An ISO timestamp as local wall time (the convention load_all_rides' dedupe uses)."""
    try:
        dt = datetime.fromisoformat(str(text or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def existing_rides() -> list[tuple[datetime, list[int]]]:
    """(start, known lengths in seconds) for every stored ride with a known length."""
    import ride_storage
    out = []
    for r in ride_storage.load_all_rides():
        start = _local(r.get("started_at"))
        lengths = [int(v) for v in (r.get("duration_s"), r.get("moving_s")) if v]
        if start is not None and lengths:
            out.append((start, lengths))
    return out


def is_duplicate(start: datetime, duration_s: int, rides: list[tuple[datetime, list[int]]]) -> bool:
    """Same ride: started within START_TOLERANCE_S and a length within DURATION_TOLERANCE."""
    for s, lengths in rides:
        if abs((start - s).total_seconds()) > START_TOLERANCE_S:
            continue
        if any(abs(duration_s - d) <= DURATION_TOLERANCE * max(duration_s, d) for d in lengths):
            return True
    return False


def _read_fit(p: Path) -> tuple[datetime, int]:
    """Start (local wall time) and length of a FIT file, or ValueError."""
    if os.lstat(p).st_size > MAX_FILE_BYTES:
        raise ValueError("larger than 50 MB")
    from fit_activity import parse_record_streams
    info = parse_record_streams(p)
    ms = (info or {}).get("start_time_ms")
    dur = int((info or {}).get("duration_s") or 0)
    if not ms or dur <= 0:
        raise ValueError("could not read this FIT file")
    return datetime.fromtimestamp(float(ms) / 1000.0), dur


def import_via_upload_path(p: Path) -> str:
    """Import one file through the upload endpoint's own code. Returns the ride id."""
    import asyncio

    import app as _app
    from fastapi import HTTPException
    from starlette.datastructures import UploadFile
    with open(p, "rb") as fh:                         # read-only: the source is never changed
        try:
            res = asyncio.run(_app._import_fit_locked(UploadFile(file=fh, filename=p.name)))
        except HTTPException as e:
            raise ValueError(str(e.detail)) from None
    return str(res["ride_id"])


# ── the scan ────────────────────────────────────────────────────────────────

def scan(pd: Path, import_fn: Callable[[Path], str] = import_via_upload_path,
         still_active: Callable[[], bool] = lambda: True) -> dict:
    """One scan of the profile's folder. Never raises; problems land in ``error``/``failures``."""
    cfg = load(pd)
    res = {"started_at": datetime.now().isoformat(timespec="seconds"), "finished_at": "",
           "imported": 0, "duplicate": 0, "failed": 0, "already_imported": 0, "remaining": 0,
           "aborted": False, "error": "", "failures": []}
    handled: dict = {}
    try:
        if not cfg["folder"]:
            raise FolderImportError("No folder is set.")
        folder = Path(validate_folder(cfg["folder"]))
        files = candidates(folder, cfg["recursive"])
        known = cfg["handled"]
        fresh = []
        for f in files:
            try:
                k = _key(folder, f)
            except (OSError, ValueError):
                continue
            if k in known:
                res["already_imported"] += 1
            else:
                fresh.append((k, f))
        res["remaining"] = max(0, len(fresh) - MAX_FILES_PER_SCAN)
        rides = existing_rides() if fresh else []
        for k, f in fresh[:MAX_FILES_PER_SCAN]:
            if not still_active():
                res["aborted"] = True
                break
            try:
                start, dur = _read_fit(f)
                if is_duplicate(start, dur, rides):
                    res["duplicate"] += 1
                    handled[k] = "duplicate"
                    continue
                handled[k] = import_fn(f)
                rides.append((start, [dur]))
                res["imported"] += 1
            except Exception as e:  # noqa: BLE001 - one bad file never stops the scan
                res["failed"] += 1
                if len(res["failures"]) < 20:
                    res["failures"].append({"file": f.name, "reason": str(e)[:160] or e.__class__.__name__})
    except (FolderImportError, OSError) as e:
        res["error"] = str(e) if isinstance(e, FolderImportError) else "The folder could not be read."
    res["finished_at"] = datetime.now().isoformat(timespec="seconds")

    def mutate(st: dict) -> None:
        if st.get("folder") != cfg["folder"]:
            return                                      # folder changed mid-scan: keep the new one clean
        # ponytail: one entry per file ever handled; prune by folder listing if folders get huge
        st.setdefault("handled", {}).update(handled)
        st["last_scan"] = res
    update_json(_path(pd), mutate, default=dict)
    if res["imported"]:
        try:
            import app as _app
            _app.clear_cache()
        except Exception:  # noqa: BLE001
            log.debug("cache clear after folder import failed", exc_info=True)
    log.info("EVENT=folder_import imported=%d duplicate=%d failed=%d remaining=%d",
             res["imported"], res["duplicate"], res["failed"], res["remaining"])
    return res


def start_scan(pd: Path, pid: str, import_fn: Callable[[Path], str] = import_via_upload_path) -> bool:
    """Run a scan in a worker thread. False when one is already running for this profile."""
    with _running_lock:
        if pid in _running:
            return False
        _running.add(pid)

    def still_active() -> bool:
        try:
            from profile_manager import ProfileManager
            return ProfileManager.get().active_id == pid
        except Exception:  # noqa: BLE001
            return False

    def run() -> None:
        try:
            scan(pd, import_fn, still_active)
        except Exception:  # noqa: BLE001
            log.exception("folder import scan failed")
        finally:
            with _running_lock:
                _running.discard(pid)
    threading.Thread(target=run, name="folder-import", daemon=True).start()
    return True


def scan_in_background() -> None:
    """Sync-loop hook: scan the active profile's folder if one is set. Never raises."""
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager.get()
        if pm.active_id and load(pm.active_dir)["folder"]:
            start_scan(pm.active_dir, pm.active_id)
    except Exception:  # noqa: BLE001 - never break the sync loop
        log.debug("folder import from sync skipped", exc_info=True)
