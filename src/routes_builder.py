"""Workout builder routes (#110, cycling slice). Model + ZWO export live in
workout_builder (pure); this file is the I/O: preview numbers, save into the
rider's own workout folder, and push to the intervals.icu calendar.

A saved builder workout is a normal .zwo in the rider's extra workout folder
(so the Library lists it and the planner/exports treat it like any other),
plus ``<stem>.builder.json`` beside it holding the editable model.
"""
from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api_models
import workout_builder as wb
from atomic_io import write_text_atomic

router = APIRouter()
_log = logging.getLogger("shepherd.builder")

_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zwo$")


def _problems(errors):
    return {"error": "; ".join(e["message"] for e in errors) or "invalid workout", "errors": errors}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50].strip("-")
    return s or "workout"


def _user_dir() -> "Path | None":
    """Where the rider's own workouts live: their extra workout folder, else
    the active profile's own ``workouts`` folder (which the app adopts as the
    extra folder once it holds a .zwo -- see app._apply_profile_paths)."""
    import app as _app
    from profile_manager import ProfileManager
    if _app.EXTRA_WORKOUT_DIR is not None:
        return Path(_app.EXTRA_WORKOUT_DIR)
    pm = ProfileManager.get()
    return Path(pm.active_dir) / "workouts" if pm.active_id else None


def _sidecar(zwo: Path) -> Path:
    return zwo.with_suffix(".builder.json")


def _save(workout: dict, file: "str | None") -> "tuple[str, bool]":
    """Write the .zwo + model sidecar. Returns (file name, created). Raises
    LookupError(code) for a refusal the caller reports, OSError on disk trouble."""
    import app as _app
    d = _user_dir()
    if d is None:
        raise LookupError("no_active_profile")
    if file is not None:
        # Editing: only a file this builder wrote, never a library workout.
        if not _FILE_RE.match(file) or not _sidecar(d / file).is_file():
            raise LookupError("not_a_builder_workout")
        target, created = d / file, False
    else:
        d.mkdir(parents=True, exist_ok=True)
        base = _slug(workout["name"])
        target, n = d / f"builder_{base}.zwo", 1
        # ponytail: check-then-write, fine for one local user; O_EXCL if it ever serves several.
        while target.exists() or _sidecar(target).exists():
            n += 1
            target = d / f"builder_{base}-{n}.zwo"
        created = True
    write_text_atomic(target, wb.to_zwo(workout))
    try:
        write_text_atomic(_sidecar(target), json.dumps(workout, indent=2))
    except OSError:
        _log.warning("builder: saved %s but not its editable model", target.name, exc_info=True)
    if _app.EXTRA_WORKOUT_DIR is None:
        _app._apply_profile_paths()      # adopt the profile folder so the Library lists it
    return target.name, created


def _validated(body):
    workout = (body or {}).get("workout") if isinstance(body, dict) else None
    errors, warnings = wb.validate(workout)
    return workout, errors, warnings


@router.post("/api/builder/preview", responses={200: {"model": api_models.BuilderPreview}})
def builder_preview(body: dict):
    """Validate and compute duration / IF / TSS with the Library's own scanner."""
    workout, errors, warnings = _validated(body)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    import app as _app
    zwo = wb.to_zwo(workout)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "preview.zwo"
        p.write_text(zwo, encoding="utf-8")
        scan = _app._scan_zwo_for_library(p)
    if scan is None:
        warnings.append("Too short to work out IF and TSS (under 30 s).")
    return {"ok": True, "errors": [], "warnings": warnings,
            "duration_s": wb.total_seconds(workout),
            "intensity_factor": round(scan["if_val"], 3) if scan else None,
            "tss": round(scan["tss"], 1) if scan else None,
            "profile": wb.intensity_profile(zwo)}


def _save_response(workout, file):
    try:
        return _save(workout, file)
    except LookupError as e:
        return JSONResponse({"error": str(e)}, 409)
    except OSError as e:
        _log.warning("builder: save failed", exc_info=True)
        return JSONResponse({"error": f"Couldn't write to your workout folder: {e}"}, 500)


@router.post("/api/builder/save", responses={200: {"model": api_models.BuilderSaved}})
def builder_save(body: dict):
    workout, errors, _ = _validated(body)
    if errors:
        return JSONResponse(_problems(errors), 422)
    res = _save_response(workout, body.get("file"))
    if isinstance(res, JSONResponse):
        return res
    return {"ok": True, "file": res[0], "created": res[1]}


@router.post("/api/builder/send", responses={200: {"model": api_models.BuilderSaved}})
def builder_send(body: dict):
    """Save, then push to the intervals.icu calendar on ``date``. The save is
    committed first and the push result rides back in ``push``: a push
    failure (no permission, offline, bad date) never loses the workout."""
    workout, errors, _ = _validated(body)
    if errors:
        return JSONResponse(_problems(errors), 422)
    res = _save_response(workout, body.get("file"))
    if isinstance(res, JSONResponse):
        return res
    file, created = res
    import app as _app
    try:
        push = _app.api_calendar_push_workout({
            "source": "library", "zwo_file": file,
            "date": str(body.get("date") or ""), "name": workout["name"].strip()})
    except Exception as e:           # the saved workout must still be reported
        _log.exception("builder: calendar push failed")
        push = {"error": f"internal:{type(e).__name__}"}
    return {"ok": True, "file": file, "created": created, "push": push}


@router.get("/api/builder/workout", responses={200: {"model": api_models.BuilderLoaded}})
def builder_load(file: str):
    """The editable model of a workout this builder saved."""
    d = _user_dir()
    if d is None or not _FILE_RE.match(file) or not _sidecar(d / file).is_file():
        return JSONResponse({"error": "not_a_builder_workout"}, 404)
    try:
        return {"ok": True, "file": file, "workout": json.loads(_sidecar(d / file).read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return JSONResponse({"error": "unreadable"}, 404)
