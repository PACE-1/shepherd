"""Open-water and wetsuit notes (#126): one plain record per swim, stored per profile.

A note has a date, optionally the intervals.icu activity it belongs to, the water
temperature (deg C), wetsuit yes/no, conditions, course, a sighting/navigation note and
free text. Plain data: no physiology is derived from it. One JSON file per profile
(``open_water_notes.json``), written atomically under the file's lock; an unreadable
file is never overwritten.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from atomic_io import update_json

FILE_NAME = "open_water_notes.json"
TEMP_MIN_C, TEMP_MAX_C = -2.0, 40.0  # rejects typos (sea water freezes near -2 deg C), not cold-water swims
LIMITS = {"activity_id": 64, "conditions": 200, "course": 200, "sighting": 500, "note": 1000}
FIELDS = ("date", "activity_id", "water_temp_c", "wetsuit", *[k for k in LIMITS if k != "activity_id"])


def read_notes(path: Path) -> list[dict]:
    """Stored notes, newest date first. A missing or corrupt file reads as none."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    notes = [n for n in data.get("notes", []) if isinstance(n, dict)] if isinstance(data, dict) else []
    return sorted(notes, key=lambda n: (str(n.get("date", "")), str(n.get("id", ""))), reverse=True)


def _update(path: Path, mutate) -> None:
    def apply(data):
        if not isinstance(data, dict):
            data = {}
        data["notes"] = mutate([n for n in data.get("notes", []) if isinstance(n, dict)])
        return data
    try:
        update_json(path, apply, default=dict, strict=True)
    except FileNotFoundError:
        update_json(path, apply, default=dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OSError("the open-water notes file could not be read, so it was left as it is") from None


def _clean(fields: dict) -> dict:
    """Validated note fields from ``fields`` (only the keys given). Raises ValueError on bad input."""
    out = {}
    for k, v in fields.items():
        if k not in FIELDS:
            raise ValueError(f"unknown field {k!r}")
        if k == "date":
            try:
                out[k] = date.fromisoformat(str(v)).isoformat()
            except (TypeError, ValueError):
                raise ValueError("date must be a date (YYYY-MM-DD)") from None
        elif k == "water_temp_c":
            if v is None or v == "":
                out[k] = None
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or not TEMP_MIN_C <= v <= TEMP_MAX_C:
                raise ValueError(f"water temperature must be between {TEMP_MIN_C:g} and {TEMP_MAX_C:g} deg C")
            else:
                out[k] = round(float(v), 1)
        elif k == "wetsuit":
            if v is not None and not isinstance(v, bool):
                raise ValueError("wetsuit must be true, false or empty")
            out[k] = v
        elif k == "activity_id":
            out[k] = (str(v).strip()[:LIMITS[k]] or None) if v is not None else None
        else:
            if v is not None and not isinstance(v, str):
                raise ValueError(f"{k} must be text")
            out[k] = (v or "").strip()[:LIMITS[k]]
    return out


def add_note(path: Path, fields: dict) -> dict:
    """Stores a new note and returns it. ``date`` is required."""
    clean = _clean(fields)
    if "date" not in clean:
        raise ValueError("date is required")
    note = {"id": uuid.uuid4().hex[:12], "date": clean["date"], "activity_id": None, "water_temp_c": None,
            "wetsuit": None, "conditions": "", "course": "", "sighting": "", "note": ""}
    note.update(clean)
    _update(path, lambda notes: [*notes, note])
    return note


def update_note(path: Path, note_id: str, fields: dict) -> dict:
    """Changes the given fields of a note. Raises KeyError for an unknown id, ValueError on bad input."""
    clean = _clean(fields)
    found: list[dict] = []

    def mutate(notes):
        for n in notes:
            if n.get("id") == note_id:
                n.update(clean)
                found.append(n)
        if not found:
            raise KeyError(note_id)
        return notes
    _update(path, mutate)
    return found[0]


def delete_note(path: Path, note_id: str) -> None:
    def mutate(notes):
        kept = [n for n in notes if n.get("id") != note_id]
        if len(kept) == len(notes):
            raise KeyError(note_id)
        return kept
    _update(path, mutate)
