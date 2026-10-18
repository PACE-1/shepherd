"""Races (#111): the rider's race list with A/B/C priorities, and how it reaches the plan.

One JSON file per profile (``races.json``). A race reuses the plan goal's event fields (``event_km``,
``event_climb_m``, ``event_type``) and adds what a race-day plan needs: a discipline, an expected duration,
a start time and an arrival time.

Disciplines (#125, #111 follow-on). ``cycling`` races are what they always were. ``triathlon`` (with a
``distance`` label: sprint | olympic | 70.3 | ironman | custom), ``running`` and ``swimming`` races are
LABELS: there are no distance-specific volumes, phase lengths or weekly-hours tables (no citable source is
available here). The plan toward one uses the rider's own hours and sport split, the cycling plan's taper
(the A race's, or the B race's, as for any race) and the companion overlay, whose sessions taper too
(multisport_plan). Their cycling-only fields (event type, distance, climbing) are not stored and never
reach the plan's goal, so the cycling planner never reads a run distance as a ride.

Migration. A rider who never opened the Races screen has no file. Their list is read from the plan's goal:
the goal event (an event plan's ``event_date`` + ``event_*`` fields) is the A race and ``goal.events`` the
B/C races. Nothing is written until the rider adds, edits or deletes a race; the first write stores that
list, with the change applied.

The plan. The planner keeps ONE A race per plan, its goal (``generate_plan`` refuses a second one). So:
  * the A race is the plan's goal event when the plan is an event plan. Its date and priority are the
    goal's: moving it means building a new plan. Its name, distance, climbing and type are copied into the
    goal block;
  * an A race on a plan that is not an event plan, or with no plan, is kept but is not in the plan (the
    rider is told to build an event plan for it, or to make it a B race);
  * B and C races are written to ``goal.events`` (the planner's existing intermediate-race list). The
    planner then tapers before them (training_planner._apply_secondary_event_tapers; see docs/SCIENCE.md
    "Races and tapers").
``sync_plan_goal`` mirrors the list into a plan dict; the client then rebuilds the plan with
/api/plan/regenerate, as the Plan's "Time off" form does.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from atomic_io import update_json

FILE_NAME = "races.json"
PRIORITIES = ("A", "B", "C")
DISCIPLINES = ("cycling", "triathlon", "running", "swimming")
TRI_DISTANCES = ("sprint", "olympic", "70.3", "ironman", "custom")   # labels only
# The planner's event types (training_planner.EVENT_TYPE_IF keys); a test keeps the two in step.
EVENT_TYPES = ("crit", "sportive", "century", "granfondo", "ultra")
NAME_MAX = 80
KM_MAX, CLIMB_MAX, HOURS_MAX = 1500.0, 30000.0, 48.0
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EVENT_GOAL_TYPES = ("event", "event_preparation")


# ── reading the list ────────────────────────────────────────────────────────────────────────────────
def _day(v, what: str = "date") -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a date (YYYY-MM-DD)") from None


def _num(v, what: str, hi: float) -> float:
    if v in (None, ""):
        return 0.0
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number") from None
    if not 0 <= x <= hi:
        raise ValueError(f"{what} must be between 0 and {hi:g}")
    return x


def goal_event_date(goal: dict | None) -> date | None:
    """The plan's A race date: an event plan's goal date, else None."""
    g = goal or {}
    if g.get("type") not in EVENT_GOAL_TYPES or not g.get("event_date"):
        return None
    try:
        return _day(g["event_date"])
    except ValueError:
        return None


def _plan_id(priority: str, d: str) -> str:
    return "plan-" + hashlib.sha1(f"{priority}:{d}".encode()).hexdigest()[:10]


def _race(**kw) -> dict:
    return {"id": kw.get("id") or uuid.uuid4().hex[:12], "name": kw.get("name", ""), "date": kw["date"],
            "priority": kw.get("priority", "B"), "discipline": kw.get("discipline") or "cycling",
            "distance": kw.get("distance"),
            "event_type": kw.get("event_type") or "granfondo", "event_km": float(kw.get("event_km") or 0),
            "event_climb_m": float(kw.get("event_climb_m") or 0),
            "expected_duration_h": kw.get("expected_duration_h"), "start_time": kw.get("start_time"),
            "arrive_time": kw.get("arrive_time")}


def from_goal(goal: dict | None) -> list[dict]:
    """The races a plan's goal block holds: its event as the A race, ``goal.events`` as B/C."""
    g = goal or {}
    out = []
    a = goal_event_date(g)
    if a:
        out.append(_race(id=_plan_id("A", a.isoformat()), name=g.get("event_name") or "", date=a.isoformat(),
                         priority="A", event_type=g.get("event_type"), event_km=g.get("event_km"),
                         event_climb_m=g.get("event_climb", g.get("event_climb_m"))))
    for e in g.get("events") or []:
        if not isinstance(e, dict):
            continue
        prio = str(e.get("priority") or "B").upper()
        try:
            d = _day(e.get("date")).isoformat()
        except ValueError:
            continue
        if prio not in ("B", "C") or (a and d == a.isoformat()):
            continue  # the A race is the goal's (an A entry in events mirrors it)
        climb = e.get("event_climb_m", e.get("event_climb"))
        out.append(_race(id=_plan_id(prio, d), name=e.get("name") or "", date=d, priority=prio,
                         event_type=e.get("event_type"), event_km=e.get("event_km") or e.get("km"),
                         event_climb_m=climb))
    return out


def _key(r: dict) -> tuple:
    return (r.get("priority"), r.get("date"))


def merge(stored: list[dict] | None, goal: dict | None) -> list[dict]:
    """The rider's list: the stored races (or none) plus any race the plan holds that the list lacks (one
    the Plan screen added, or the goal of a plan built since). Sorted by date."""
    races = [r for r in (stored or []) if isinstance(r, dict) and r.get("date")]
    have = {_key(r) for r in races}
    races += [r for r in from_goal(goal) if _key(r) not in have]
    return sorted(races, key=lambda r: (str(r["date"]), r.get("priority", "")))


def read_stored(path: Path) -> list[dict] | None:
    """The stored list, or None when the rider has none yet (or the file cannot be read)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("races"), list):
        return None
    return [r for r in data["races"] if isinstance(r, dict)]


def read_races(path: Path, goal: dict | None) -> list[dict]:
    return merge(read_stored(path), goal)


def in_plan(race: dict, goal: dict | None) -> bool:
    """Whether the plan's goal block holds this race (and so tapers for it)."""
    g = goal or {}
    if race.get("priority") == "A":
        a = goal_event_date(g)
        return bool(a and a.isoformat() == race.get("date"))
    return any(_key(r) == _key(race) for r in from_goal(g) if r["priority"] != "A")


# ── changing it ─────────────────────────────────────────────────────────────────────────────────────
def _clean(body: dict, old: dict | None = None) -> dict:
    """A validated race from a request body (fields not sent keep ``old``'s value). Raises ValueError."""
    b = {**(old or {}), **{k: v for k, v in (body or {}).items() if k != "id"}}
    prio = str(b.get("priority") or "B").upper()
    if prio not in PRIORITIES:
        raise ValueError("priority must be A, B or C")
    disc = str(b.get("discipline") or "cycling").lower()
    if disc not in DISCIPLINES:
        raise ValueError(f"discipline must be one of {', '.join(DISCIPLINES)}")
    dist = b.get("distance")
    if disc == "triathlon":
        dist = str(dist or "").lower()
        if dist not in TRI_DISTANCES:
            raise ValueError(f"a triathlon needs a distance: {', '.join(TRI_DISTANCES)}")
    else:
        dist = None
    if disc != "cycling":   # cycling-only fields: the planner would read them as a ride
        b = {**b, "event_type": None, "event_km": None, "event_climb_m": None}
    etype = str(b.get("event_type") or "granfondo").lower()
    if etype not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {', '.join(EVENT_TYPES)}")
    hours = b.get("expected_duration_h")
    hours = None if hours in (None, "") else _num(hours, "expected duration (hours)", HOURS_MAX) or None
    times = {}
    for k, what in (("start_time", "start time"), ("arrive_time", "arrival time")):
        v = b.get(k)
        if v in (None, ""):
            times[k] = None
        elif isinstance(v, str) and _TIME.match(v):
            times[k] = v
        else:
            raise ValueError(f"{what} must be HH:MM")
    if times["start_time"] and times["arrive_time"] and times["arrive_time"] > times["start_time"]:
        raise ValueError("arrival time must not be after the start time")
    return _race(id=(old or {}).get("id"), name=str(b.get("name") or "").strip()[:NAME_MAX],
                 date=_day(b.get("date")).isoformat(), priority=prio, discipline=disc, distance=dist,
                 event_type=etype,
                 event_km=_num(b.get("event_km"), "distance (km)", KM_MAX),
                 event_climb_m=_num(b.get("event_climb_m"), "climbing (m)", CLIMB_MAX),
                 expected_duration_h=hours, **times)


def _check(races: list[dict], race: dict, goal: dict | None, old: dict | None) -> None:
    """The rules a race must keep against the rest of the list and the plan. Raises ValueError."""
    if race["priority"] == "A" and any(r["priority"] == "A" and r["id"] != race["id"] for r in races):
        raise ValueError("there is already an A race: a plan builds toward one A race, so make this one B or C")
    a = goal_event_date(goal)
    if old is not None and old.get("priority") == "A" and a and old.get("date") == a.isoformat():
        if race["priority"] != "A" or race["date"] != old["date"]:
            raise ValueError("this A race is your plan's goal: to move it or change its priority, build a new "
                             "plan for it on the Plan screen")
    elif race["priority"] == "A" and a and race["date"] != a.isoformat():
        raise ValueError(f"your plan is built for its A race on {a.isoformat()}: add this race as B or C, or "
                         "build a new plan for it on the Plan screen")


def _update(path: Path, goal: dict | None, mutate) -> list[dict]:
    """Applies ``mutate`` to the rider's list (the migrated one on the first write) and stores it."""
    def apply(data):
        stored = data.get("races") if isinstance(data, dict) and isinstance(data.get("races"), list) else None
        return {"races": sorted(mutate(merge(stored, goal)), key=lambda r: (str(r["date"]), r.get("priority", "")))}
    # strict: an unreadable file is never replaced (that would lose the list).
    try:
        update_json(path, apply, default=dict, strict=True)
    except FileNotFoundError:
        update_json(path, apply, default=dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OSError("the races file could not be read, so it was left as it is") from None
    return read_races(path, goal)


def add_race(path: Path, goal: dict | None, body: dict, today: date) -> dict:
    race = _clean(body)
    if race["date"] < today.isoformat():
        raise ValueError("the race date is in the past")

    def mutate(races):
        _check(races, race, goal, None)
        if any(_key(r) == _key(race) for r in races):
            raise ValueError(f"there is already a {race['priority']} race on {race['date']}")
        return [*races, race]
    _update(path, goal, mutate)
    return race


def update_race(path: Path, goal: dict | None, race_id: str, body: dict) -> dict:
    """Raises KeyError for an unknown id, ValueError for a bad change."""
    out: list[dict] = []

    def mutate(races):
        old = next((r for r in races if r.get("id") == race_id), None)
        if old is None:
            raise KeyError(race_id)
        race = _clean(body, old)
        _check(races, race, goal, old)
        if any(_key(r) == _key(race) and r["id"] != race_id for r in races):
            raise ValueError(f"there is already a {race['priority']} race on {race['date']}")
        out.append(race)
        return [race if r is old else r for r in races]
    _update(path, goal, mutate)
    return out[0]


def delete_race(path: Path, goal: dict | None, race_id: str) -> None:
    def mutate(races):
        old = next((r for r in races if r.get("id") == race_id), None)
        if old is None:
            raise KeyError(race_id)
        a = goal_event_date(goal)
        if old.get("priority") == "A" and a and old.get("date") == a.isoformat():
            raise ValueError("this A race is your plan's goal: build a new plan to change it")
        return [r for r in races if r is not old]
    _update(path, goal, mutate)


# ── the plan ────────────────────────────────────────────────────────────────────────────────────────
def _event_dict(r: dict) -> dict:
    """A B/C race as goal.events stores it (training_planner._target_events_to_dicts' shape)."""
    return {"date": r["date"], "priority": r["priority"], "name": r.get("name", ""),
            "event_type": r.get("event_type") or "granfondo", "event_km": r.get("event_km") or 0,
            "event_climb_m": r.get("event_climb_m") or 0}


def sync_plan_goal(plan: dict, races: list[dict]) -> bool:
    """Mirrors the list into ``plan["goal"]``: B/C races become ``goal.events``; the A race's details are
    copied into an event plan's goal fields when it is that goal. Returns True when the plan changed."""
    goal = plan.get("goal")
    if not isinstance(goal, dict):
        return False
    before = json.dumps(goal, sort_keys=True, default=str)
    events = [_event_dict(r) for r in sorted(races, key=lambda r: r["date"]) if r.get("priority") in ("B", "C")]
    if events or goal.get("events"):
        goal["events"] = events
    a = goal_event_date(goal)
    for r in races:
        if r.get("priority") == "A" and a and r.get("date") == a.isoformat():
            if (r.get("discipline") or "cycling") != "cycling":
                goal["event_name"] = r.get("name", "")   # a label: the goal keeps its own ride fields
                continue
            goal.update({"event_name": r.get("name", ""), "event_km": r.get("event_km") or 0,
                         "event_climb": r.get("event_climb_m") or 0,
                         "event_type": r.get("event_type") or "granfondo"})
    return json.dumps(goal, sort_keys=True, default=str) != before


# ── race day ────────────────────────────────────────────────────────────────────────────────────────
def _hhmm(t: datetime) -> str:
    return t.strftime("%H:%M")


def timeline(race: dict, warmup_min: int, duration_h: float | None) -> list[dict]:
    """The day's timeline from the rider's start (and arrival) time: arrive, warm up, start, finish.
    Empty without a start time. ``duration_h`` (the rider's own estimate, else the projection) sets the
    finish; none is shown without one. ``warmup_min`` 0 leaves the warm-up row out."""
    if not race.get("start_time"):
        return []
    start = datetime.combine(_day(race["date"]), datetime.strptime(race["start_time"], "%H:%M").time())
    warm = start - timedelta(minutes=warmup_min)
    rows = []
    if race.get("arrive_time"):
        rows.append({"time": race["arrive_time"], "label": "Arrive"})
    if warmup_min:
        rows.append({"time": _hhmm(warm), "label": f"Warm up ({warmup_min} min)"})
    rows.append({"time": race["start_time"], "label": "Start"})
    if duration_h:
        rows.append({"time": _hhmm(start + timedelta(hours=duration_h)), "label": "Expected finish"})
    return rows
