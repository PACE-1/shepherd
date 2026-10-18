"""Gear tracking (#115): bikes, shoes and components with distance and hours, and the rider's service threshold.

One JSON file per profile (``gear.json``): the items, the service history, and the ride-to-gear overrides.

Counting rules (all of this is bookkeeping, no physiology):
  * An item adds up the distance and moving time of the activities assigned to it from its counter start:
    the later of ``started_on`` and the last "service done" date. A ride on the service day itself counts as
    before the service. Hours are ``activities.duration_sec`` / 3600.
  * A component with a parent bike counts the activities assigned to that bike; any other item counts the
    activities assigned to itself.
  * "Service done" appends to the item's history and restarts the counter after that day. Nothing is erased.
  * Thresholds (``service_every_km`` / ``service_every_hours``) are typed by the rider. There are no defaults.
    An item is due when either counter reaches its threshold. "Due soon" from 90 % is a display convention
    (``DUE_SOON``), not a published figure.

Which gear a ride has: a manual choice (stored under ``assignments``; ``NONE`` means "no gear") wins. Without
one, the ride's intervals.icu gear is used when its name matches an item's ``icu_name`` (case-insensitive).
ponytail: auto-assign is best-effort. This code reads ``gear.name`` from the activity payload that sync stores in
``activities.raw_json`` (intervals.icu's activity object has a ``gear`` object; its exact shape could not be
checked against the API docs from here, and no fixture in this repo carries it). A payload without
``gear.name`` simply maps nothing. Upgrade path: match on ``gear.id`` once a real payload confirms it.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

from atomic_io import update_json

FILE_NAME = "gear.json"
KINDS = ("bike", "shoes", "component")
NONE = "none"          # assignment value: this ride has no gear, do not auto-assign
DUE_SOON = 0.9         # UI convention: "due soon" from 90 % of the threshold
NAME_MAX, NOTE_MAX = 80, 200

METHOD = ("Distance and hours add up from the rides assigned to the item since it was started or last serviced. "
          "Thresholds are the ones you typed; \"due soon\" from 90 % is only a display convention.")


# ── storage ────────────────────────────────────────────────────────────────────────────────────────
def _shape(data: Any) -> dict:
    data = data if isinstance(data, dict) else {}
    items = [i for i in data.get("items", []) if isinstance(i, dict) and i.get("id")]
    asg = data.get("assignments") if isinstance(data.get("assignments"), dict) else {}
    return {"items": items, "assignments": {str(k): str(v) for k, v in asg.items()}}


def read(path: Path) -> dict:
    """The stored gear. A missing or corrupt file reads as empty."""
    try:
        return _shape(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return _shape({})


def _update(path: Path, mutate) -> Any:
    """Read-modify-write under the file lock. An unreadable file is never overwritten with a fresh one."""
    out: list = []

    def apply(data):
        state = _shape(data)
        out.append(mutate(state))
        return state
    try:
        update_json(path, apply, default=dict, strict=True)
    except FileNotFoundError:
        out.clear()
        update_json(path, apply, default=dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OSError("the gear file could not be read, so it was left as it is") from None
    return out[-1]


# ── validation ─────────────────────────────────────────────────────────────────────────────────────
def _day(v, what: str) -> Optional[str]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise ValueError(f"{what} must be a date (YYYY-MM-DD)") from None


def _threshold(v, what: str) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number") from None
    if not 0 < n < 1_000_000:
        raise ValueError(f"{what} must be more than 0")
    return n


def _clean(state: dict, fields: dict, current: Optional[dict] = None) -> dict:
    """The item fields as stored, from the rider's input merged over ``current``. Raises ValueError."""
    f = {**(current or {}), **fields}
    name = str(f.get("name") or "").strip()
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"name must be 1 to {NAME_MAX} characters")
    kind = f.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    parent = f.get("parent_id") or None
    if parent:
        p = next((i for i in state["items"] if i["id"] == parent), None)
        if kind != "component" or p is None or p.get("kind") != "bike" or parent == f.get("id"):
            raise ValueError("only a component can have a parent, and the parent must be one of your bikes")
    icu = str(f.get("icu_name") or "").strip()[:NAME_MAX] or None
    if icu and kind == "component":
        raise ValueError("intervals.icu gear is a bike or shoes, not a component")
    if icu and any(i["id"] != f.get("id") and str(i.get("icu_name") or "").lower() == icu.lower() for i in state["items"]):
        raise ValueError("another item already uses that intervals.icu gear name")
    return {"name": name, "kind": kind, "parent_id": parent, "retired": bool(f.get("retired")),
            "service_every_km": _threshold(f.get("service_every_km"), "service every (km)"),
            "service_every_hours": _threshold(f.get("service_every_hours"), "service every (hours)"),
            "started_on": _day(f.get("started_on"), "started on"), "icu_name": icu}


def add_item(path: Path, **fields) -> dict:
    def run(state):
        item = {"id": uuid.uuid4().hex[:12], **_clean(state, fields), "services": []}
        state["items"].append(item)
        return item
    return _update(path, run)


def edit_item(path: Path, item_id: str, **fields) -> dict:
    """Changes the given fields. KeyError for an unknown id, ValueError for bad input."""
    def run(state):
        item = _find(state, item_id)
        item.update(_clean(state, fields, item))
        return item
    return _update(path, run)


def delete_item(path: Path, item_id: str) -> None:
    """Removes an item, its history and the ride choices that point at it. ValueError while it has components."""
    def run(state):
        _find(state, item_id)
        if any(i.get("parent_id") == item_id for i in state["items"]):
            raise ValueError("remove or move this bike's components first")
        state["items"] = [i for i in state["items"] if i["id"] != item_id]
        state["assignments"] = {a: g for a, g in state["assignments"].items() if g != item_id}
    _update(path, run)


def service_done(path: Path, item_id: str, on: date, note: str = "") -> dict:
    """Restarts the item's counter after ``on`` and keeps the history. KeyError for an unknown id."""
    def run(state):
        item = _find(state, item_id)
        item.setdefault("services", []).append({"date": on.isoformat(), "note": str(note or "").strip()[:NOTE_MAX]})
        return item
    return _update(path, run)


def assign(path: Path, activity_id: str, gear_id: Optional[str]) -> None:
    """``gear_id`` an item id: that gear. ``NONE``: no gear. None: forget the choice (back to automatic)."""
    def run(state):
        if gear_id is None:
            state["assignments"].pop(str(activity_id), None)
            return
        if gear_id != NONE:
            _find(state, gear_id)
        state["assignments"][str(activity_id)] = gear_id
    _update(path, run)


def _find(state: dict, item_id: str) -> dict:
    for i in state["items"]:
        if i["id"] == item_id:
            return i
    raise KeyError(item_id)


# ── counting ───────────────────────────────────────────────────────────────────────────────────────
def _icu_gear_name(row: dict) -> Optional[str]:
    n = row.get("icu_gear")
    return n.strip() if isinstance(n, str) and n.strip() else None


def gear_of(row: dict, assignments: dict, by_icu: dict) -> tuple[Optional[str], str]:
    """(gear id or None, source) for one activity row. source: manual | auto | none."""
    aid = str(row["id"])
    if aid in assignments:
        g = assignments[aid]
        return (None if g == NONE else g), "manual"
    name = _icu_gear_name(row)
    if name and name.lower() in by_icu:
        return by_icu[name.lower()], "auto"
    return None, "none"


def _by_icu(items: list[dict]) -> dict:
    out: dict = {}
    for i in items:
        if i.get("icu_name"):
            out.setdefault(str(i["icu_name"]).lower(), i["id"])
    return out


def counter_start(item: dict) -> tuple[Optional[str], Optional[str]]:
    """(started_on, last service day): the counter covers rides after the service day and from started_on."""
    last = max((s["date"] for s in item.get("services") or [] if s.get("date")), default=None)
    return item.get("started_on"), last


def item_status(item: dict, rows: list[dict], state: dict) -> dict:
    by_icu = _by_icu(state["items"])
    started, last = counter_start(item)
    own = item["id"] if not item.get("parent_id") else item["parent_id"]
    km = hours = 0.0
    for r in rows:
        d = str(r.get("date") or "")[:10]
        if (started and d < started) or (last and d <= last):
            continue
        if gear_of(r, state["assignments"], by_icu)[0] != own:
            continue
        km += float(r.get("distance_km") or 0)
        hours += float(r.get("duration_sec") or 0) / 3600
    cap_km, cap_h = item.get("service_every_km"), item.get("service_every_hours")
    km_pct = km / cap_km if cap_km else None
    h_pct = hours / cap_h if cap_h else None
    worst = max((p for p in (km_pct, h_pct) if p is not None), default=None)
    if item.get("retired"):
        st = "retired"
    elif worst is None:
        st = "no_threshold"
    else:
        st = "due" if worst >= 1 else "due_soon" if worst >= DUE_SOON else "ok"
    return {"id": item["id"], "name": item["name"], "kind": item["kind"], "parent_id": item.get("parent_id"),
            "retired": bool(item.get("retired")), "started_on": started, "icu_name": item.get("icu_name"),
            "service_every_km": cap_km, "service_every_hours": cap_h,
            "km": round(km, 1), "hours": round(hours, 2),
            "km_pct": None if km_pct is None else round(km_pct, 3),
            "hours_pct": None if h_pct is None else round(h_pct, 3),
            "state": st, "last_service": last, "services": sorted(item.get("services") or [], key=lambda s: s["date"], reverse=True)}


def suggestions(rows: list[dict], state: dict) -> list[dict]:
    """intervals.icu gear names on rides that no item uses yet, with how many rides carry each."""
    by_icu = _by_icu(state["items"])
    seen: dict = {}
    for r in rows:
        n = _icu_gear_name(r)
        if n and n.lower() not in by_icu:
            s = seen.setdefault(n.lower(), {"icu_name": n, "rides": 0})
            s["rides"] += 1
    return sorted(seen.values(), key=lambda s: -s["rides"])


def overview(state: dict, rows: list[dict], recent: list[dict]) -> dict:
    by_icu = _by_icu(state["items"])
    return {
        "items": [item_status(i, rows, state) for i in state["items"]],
        "suggestions": suggestions(rows, state),
        "recent": [{"id": str(r["id"]), "date": str(r.get("date") or "")[:10], "name": r.get("name"),
                    "sport": r.get("sport"), "distance_km": r.get("distance_km"),
                    "gear_id": (g := gear_of(r, state["assignments"], by_icu))[0], "source": g[1]} for r in recent],
        "method": METHOD,
    }
