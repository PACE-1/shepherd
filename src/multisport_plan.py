"""Companion sessions: run, swim and strength sessions planned next to the cycling plan
(MASTER_DECISIONS ADDENDUM 5, owner-approved 2026-10-18).

Pure: no I/O. training_planner wraps its plan builders (``_companion_overlay``); for a rider whose saved
sport targets (sport_balance) give a non-cycling sport a share, the cycling builder gets the cycling share
of the rider's weekly hours (``scaled_cycling_hours``) and ``overlay`` then adds ``CompanionSession`` rows
to ``PlannedWeek.companions``. Cycling sessions are never read for anything but their day, length and
hardness, and never changed.

Rules ``overlay`` keeps, each one a test in tests/test_multisport_plan.py:
  * Opt-in: nothing happens without targets giving running, swimming or "other" (strength) a share > 0
    and cycling a share > 0 (a 0 % cycling split is not supported: the planner builds a cycling plan).
    No default split, no invented hours.
  * Hours: a sport's week gets total hours x its share, scaled by how much of its own cycling share the
    week's cycling carries (a step-back or taper week shrinks companions in step; the split is the
    rider's), and all companions together never exceed the rider's hours left after the week's cycling.
  * Days: only today or later, only on available days (rest days and 0-hour dates excluded), within what
    the day's hours leave after its cycling, never on a race day, at most one companion per sport a day.
  * Time off: a plan time-off row blocks every sport; an injury episode blocks the sport it names
    (src/injury.py ``sport``; "all" blocks every sport, "cycling" none, "other" blocks strength).
  * Hard days: a hard companion never sits on or next to a hard bike day (training_planner._session_is_hit,
    or a race) or another hard companion. The week's hard-day budget is the cycling one: the planner's own
    hit_slots_for_volume (48 h between hard days, Seiler 2010) on the week's total volume, capped by the
    week's hit_allowance; hard companions get only what the bike sessions leave of it, none in a
    step-back week or an easy phase. At most one hard companion per sport a week. Bike sessions are
    never demoted.
  * Limiter (#124): the limiter sport gets first claim on hard slots and days, then on the longest free
    day for its longest session (a "long" template when its library has one); then sports by share. Its
    companions carry a one-line ``limiter`` tag saying so. No hours move: every sport keeps its share. A
    cycling limiter (or none) changes nothing, and the cycling plan is never changed by it.
  * Bricks (#123): for a rider with a running share, at most one brick a week: a running "brick" template
    placed on a key bike day (a hard bike session or the week's long ride, ``long_z2``) and not on or next
    to a hard companion; the run follows that day's ride and is linked to it (``workout["brick_of"]`` =
    ``bike_session_id``). The brick never takes a hard slot of its own; a hard brick template goes only on
    a hard bike day, so it adds no hard day. When no brick template is registered, ``PLACEHOLDER_BRICK``
    is used. The rider's note on how the run felt (``workout["brick_note"]``) keeps the brick as it is.
  * Strength (#127): a resistance session (kinds "strength" = A/B, and "maintenance") goes only on a day
    with no hard bike session, no hard companion and no race, never the day before a hard or key session
    (hard bike day, long ride, hard companion, brick) or a race; easy days first; at most
    ``STRENGTH_MAX_PER_WEEK`` a week together; maintenance first in a build or peak phase, A/B otherwise;
    a hard companion is never placed the day after one. Mobility (kind "mobility", session_type
    "mobility") takes what is left of the strength hours on any day that is not hard. A HEURISTIC after
    Wilson et al. 2012 (interference mostly with running and with frequent, long endurance work), not a
    measured optimum.
  * Taper (#125): in the plan's A-race taper weeks (phase "taper") each sport's companion minutes are its
    share x the planner's own ``TAPER_FRACS`` by position (the race week the last), imported, not copied.
    Other weeks follow the cycling week's volume (a B-race taper shrinks companions in step).
  * Kept: companions on past days, or done / missed / dismissed, stay as they are and count against the
    week's hours; pending future ones are planned again (deterministic, so an unchanged week is unchanged).

``brick_of``, ``brick_note`` and ``limiter`` live inside the companion's ``workout`` dict because
training_planner.CompanionSession (closed this wave) has no fields for them; the codec round-trips the
dict as it is.

Session content comes from templates (``SessionTemplate``, ``register``, ``templates_for``). Only three
PLACEHOLDER templates ship here (easy run, easy swim, general strength) so the engine runs end to end;
their duration ranges are structural placeholders, not prescriptions, and the real libraries replace
them. Companions carry no training-load estimate (no cross-sport number is invented). NOT VALIDATED:
nothing here has been checked against real recorded runs or swims (``NOT_VALIDATED`` is shown in the UI).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from multisport import sport_of

COMPANION_SPORTS = ("running", "swimming", "strength")
# The sport_balance / multisport sport a companion sport's hours and activities belong to.
BALANCE_SPORT = {"running": "running", "swimming": "swimming", "strength": "other"}
NOT_VALIDATED = "Not validated against real runs/swims yet."
# The planner's own easy phases: no hard companion in them.
EASY_PHASES = ("taper", "consolidation", "recon", "recovery_ramp")
STEP_MIN = 5            # companion durations are whole 5-minute steps (presentation, not physiology)
MATCH_TOLERANCE = 0.5   # ADDENDUM 5: same sport, same day, duration within +-50 %
KEPT_STATUSES = ("done", "missed", "dismissed")
BRICK_MAX_PER_WEEK = 1
# ACSM 2009 position stand (Med Sci Sports Exerc 41(3):687-708): novices train the whole body 2-3 days a
# week; 2 is the lower end, next to the endurance work. The day-placement rules are a heuristic.
STRENGTH_MAX_PER_WEEK = 2
BRICK_NOTE_MAX = 500
LONG_RIDE = "long_z2"   # the planner's long-ride session type: a key bike day
# Strength kinds (src/sessions_strength.py): "strength" (A/B) and "maintenance" are resistance sessions,
# at most STRENGTH_MAX_PER_WEEK together; "mobility" is easy stretching, any easy day, not counted in it.
BUILD_PHASES = ("build1", "build2", "peak")   # maintenance strength is preferred in these
MOBILITY = "mobility"
# The one-line tags a limiter-sport companion carries (#124): why it got its slot.
LIMITER_HARD = "Your limiter: first pick of the week's hard-session slots."
LIMITER_LONG = "Your limiter: first pick of the longest free day for its longest session."


# ── templates: the interface the session libraries implement ───────────────────────────────────
@dataclass(frozen=True)
class SessionTemplate:
    """One kind of companion session.

    id            unique; ``register`` replaces a template with the same id
    sport         running | swimming | strength
    kind          the library's own label (easy, long, tempo, intervals, endurance, css, strength,
                  brick, ...). "brick" is special: placed only on a day with a bike session.
    session_type  the companion's session_type (run_easy, run_long, run_tempo, run_intervals,
                  swim_endurance, swim_css, strength, brick_run)
    intent        one line shown to the rider
    minutes       (shortest, longest) session in minutes
    hard          counts against the week's hard-day budget and the spacing rule
    builder       builder(thresholds, minutes) -> workout dict in the workout_builder shape
                  ({"name", "description", "steps": [...]}, targets of kind pace_pct_threshold, css or
                  effort). ``thresholds`` is multisport.read_thresholds()'s dict. A builder that also
                  takes a ``phase`` keyword (or ``**kwargs``) is given the plan week's phase (base, build1,
                  build2, peak, taper, ...); others are called with the two arguments only.
    source        the published method the structure follows (empty for a placeholder)
    """
    id: str
    sport: str
    kind: str
    session_type: str
    intent: str
    minutes: tuple
    hard: bool
    builder: Callable[[dict, int], dict]
    source: str = ""


_REGISTRY: dict[str, SessionTemplate] = {}


def register(template: SessionTemplate) -> SessionTemplate:
    """Adds (or replaces, by id) a template. Raises ValueError for an unknown sport or a bad range."""
    if template.sport not in COMPANION_SPORTS:
        raise ValueError(f"sport must be one of {', '.join(COMPANION_SPORTS)}")
    lo, hi = template.minutes
    if not (isinstance(lo, int) and isinstance(hi, int) and 0 < lo <= hi):
        raise ValueError("minutes must be (shortest, longest) whole minutes, 0 < shortest <= longest")
    _REGISTRY[template.id] = template
    return template


def unregister(template_id: str) -> bool:
    """Removes a template by id (a library retiring the placeholder it replaces). True when it existed."""
    return _REGISTRY.pop(template_id, None) is not None


def templates_for(sport: str, kind: str | None = None,
                  library: Iterable[SessionTemplate] | None = None) -> list[SessionTemplate]:
    """The templates of ``sport`` (and ``kind``, when given), in registration order."""
    pool = _REGISTRY.values() if library is None else library
    return [t for t in pool if t.sport == sport and (kind is None or t.kind == kind)]


def _effort_workout(name: str, description: str, minutes: int, label: str) -> dict:
    return {"name": name, "description": description,
            "steps": [{"kind": "work", "duration_s": int(minutes) * 60,
                       "target": {"kind": "effort", "label": label}, "cadence_note": ""}]}


# PLACEHOLDERS (replaced next wave). Effort targets only, so no pace or CSS number is needed; the duration
# ranges are structural placeholders, not taken from a source.
register(SessionTemplate(
    id="placeholder-run-easy", sport="running", kind="easy", session_type="run_easy",
    intent="Easy aerobic run at a conversational effort.", minutes=(30, 60), hard=False,
    builder=lambda th, m: _effort_workout("Easy run", "Easy aerobic running; you can hold a conversation.",
                                          m, "easy, conversational")))
register(SessionTemplate(
    id="placeholder-swim-easy", sport="swimming", kind="endurance", session_type="swim_endurance",
    intent="Easy aerobic swim, continuous or with short rests.", minutes=(30, 60), hard=False,
    builder=lambda th, m: _effort_workout("Easy swim", "Easy aerobic swimming, relaxed technique.",
                                          m, "easy, relaxed")))
register(SessionTemplate(
    id="placeholder-strength-general", sport="strength", kind="strength", session_type="strength",
    intent="General strength: multi-joint exercises, 1-3 sets of 8-12 repetitions.", minutes=(30, 45),
    hard=False, source="ACSM position stand, Progression models in resistance training for healthy "
                        "adults, Med Sci Sports Exerc 2009;41(3):687-708 (novice: 1-3 sets, 8-12 reps).",
    builder=lambda th, m: _effort_workout(
        "General strength", "Multi-joint exercises, 1-3 sets of 8-12 repetitions at a load you could lift "
        "a few more times (ACSM 2009, novice).", m, "moderate")))

# PLACEHOLDER brick run, NOT registered: overlay uses it only when the registry holds no running "brick"
# template (a run library replaces it by registering one). Effort target only; the 10-20 minute range is a
# structural placeholder, not taken from a source.
PLACEHOLDER_BRICK = SessionTemplate(
    id="placeholder-run-brick", sport="running", kind="brick", session_type="brick_run",
    intent="Brick (placeholder): a short easy run straight after the ride.", minutes=(10, 20), hard=False,
    builder=lambda th, m: _effort_workout("Brick run", "Run straight off the bike at an easy, steady effort.",
                                          m, "easy, steady"))


def bike_session_id(s) -> str:
    """The id a brick links to: the app identifies a bike session by its day (and AM/PM half)."""
    half = getattr(s, "am_or_pm", None)
    return f"cycling-{s.day.isoformat()}" + (f"-{half}" if half else "")


def is_brick(c) -> bool:
    w = c.get("workout") if isinstance(c, dict) else getattr(c, "workout", None)
    return isinstance(w, dict) and bool(w.get("brick_of"))


# ── the split ──────────────────────────────────────────────────────────────────────────────────────
def _share(targets: dict | None, sport: str) -> float:
    v = (targets or {}).get(sport)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0.0


def overlay_on(targets: dict | None) -> bool:
    """Overlay planning is ON only for saved targets giving cycling and a non-cycling sport a share."""
    return _share(targets, "cycling") > 0 and any(_share(targets, BALANCE_SPORT[s]) > 0 for s in COMPANION_SPORTS)


def scaled_cycling_hours(hours_per_week: float, targets: dict | None) -> float:
    """The hours the cycling builder gets: the cycling share of the rider's hours (unchanged when off)."""
    if not overlay_on(targets):
        return hours_per_week
    return round(float(hours_per_week or 0) * _share(targets, "cycling") / 100.0, 2)


# ── overlay ────────────────────────────────────────────────────────────────────────────────────────
def _as_day(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _blocks(rows) -> list[tuple]:
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            lo, hi, sport = _as_day(r.get("start")), _as_day(r.get("end")), r.get("sport") or "all"
        elif isinstance(r, (tuple, list)) and len(r) == 2:
            lo, hi, sport = _as_day(r[0]), _as_day(r[1]), "all"
        else:
            continue
        if lo is not None:
            out.append((lo, hi, sport))          # hi None: open-ended
    return out


def _blocked(sport: str, d: date, blocks: list[tuple]) -> bool:
    return any(lo <= d and (hi is None or d <= hi) and s in ("all", BALANCE_SPORT[sport])
               for lo, hi, s in blocks)


def _kept(c, today: date) -> bool:
    return (c.day < today or c.status in KEPT_STATUSES or bool(c.dismissed_at)
            or (isinstance(c.workout, dict) and bool(c.workout.get("brick_note"))))


def _build(t: SessionTemplate, thresholds: dict, minutes: int, phase: str) -> dict:
    """Calls the template's builder, with ``phase=`` only when it takes that keyword (backward compatible)."""
    import inspect
    try:
        params = inspect.signature(t.builder).parameters.values()
    except (TypeError, ValueError):
        params = ()
    if any(p.name == "phase" or p.kind is p.VAR_KEYWORD for p in params):
        return t.builder(thresholds, minutes, phase=phase)
    return t.builder(thresholds, minutes)


def _is_resistance(c) -> bool:
    """A strength-sport companion that is a resistance session (not mobility)."""
    return c.sport == "strength" and c.session_type != MOBILITY


def _floor_step(m: float) -> int:
    return int(m // STEP_MIN) * STEP_MIN


def overlay(weeks: list, *, targets: dict | None, limiter: str | None, thresholds: dict | None,
            availability: dict, unavailable_periods, today: date, races=None, session_library=None) -> list:
    """Adds companion sessions to ``weeks`` (PlannedWeek list, already holding the cycling plan) in place
    and returns it. See the module docstring for every rule.

    availability          {"hours_per_week": rider's TOTAL hours, "weekday": {0..6: hours},
                           "date": {"YYYY-MM-DD": hours}} (a date entry overrides its weekday)
    unavailable_periods   [{"start", "end" (None = open), "sport": all|cycling|running|swimming|other}]
                           or (start, end) pairs, which block every sport
    races                 race dicts (or dates) with a "date": no companion that day, counted as hard
    session_library       templates to use instead of the registry
    """
    if not overlay_on(targets):
        return weeks
    from training_planner import TAPER_FRACS, CompanionSession, _session_is_hit, hit_slots_for_volume

    lib = list(_REGISTRY.values()) if session_library is None else list(session_library)
    if session_library is None and not templates_for("running", "brick", library=lib):
        lib.append(PLACEHOLDER_BRICK)
    total_min = float(availability.get("hours_per_week") or 0) * 60
    cyc_min = total_min * _share(targets, "cycling") / 100
    weekday_h = {int(k): float(v) for k, v in (availability.get("weekday") or {}).items()}
    date_h = {str(k): float(v) for k, v in (availability.get("date") or {}).items()}
    blocks = _blocks(unavailable_periods)
    sports = [s for s in COMPANION_SPORTS if _share(targets, BALANCE_SPORT[s]) > 0]
    sports.sort(key=lambda s: (BALANCE_SPORT[s] != limiter, -_share(targets, BALANCE_SPORT[s])))
    lim = next((s for s in sports if BALANCE_SPORT[s] == limiter), None)   # None: no limiter, or cycling

    race_days = {d for d in (_as_day(r.get("date") if isinstance(r, dict) else r) for r in races or []) if d}
    race_days |= {s.day for w in weeks for s in w.sessions if getattr(s, "is_race", False)}
    hard_days = set(race_days) | {s.day for w in weeks for s in w.sessions if _session_is_hit(s)}
    long_days = {s.day for w in weeks for s in w.sessions if s.session_type == LONG_RIDE}
    hard_comp: set[date] = set()       # hard companion days (a brick keeps clear of them)
    strength_days: set[date] = set()
    for w in weeks:
        w.companions = [c for c in (w.companions or []) if _kept(c, today)]
        live = [c for c in w.companions if c.status != "dismissed"]
        hard_comp |= {c.day for c in live if c.hard}
        strength_days |= {c.day for c in live if _is_resistance(c)}
        long_days |= {c.day for c in live if is_brick(c)}
    hard_days |= hard_comp
    # Key days: no strength session the day before one.
    key_days = hard_days | long_days

    # The A-race taper weeks take the planner's own fractions by position (training_planner._row_budget).
    taper_frac: dict[int, float] = {}
    block: list[int] = []
    for i, w in enumerate([*weeks, None]):
        if w is not None and w.phase == "taper":
            block.append(i)
            continue
        for k, j in enumerate(block):
            taper_frac[j] = TAPER_FRACS[max(0, len(TAPER_FRACS) - (len(block) - k))]
        block = []

    def fill(w, idx: int) -> None:
        bike_day: dict[date, int] = {}
        bike_sess: dict = {}
        for s in w.sessions:
            if s.session_type != "rest" and (s.duration_min or 0) > 0:
                bike_day[s.day] = bike_day.get(s.day, 0) + int(s.duration_min)
                bike_sess[s.day] = s                 # the day's last ride: a brick run follows it
        bike_week = sum(bike_day.values())
        bike_hard_days = {s.day for s in w.sessions if _session_is_hit(s)}
        key_bike = {d for d in bike_day if (d in bike_hard_days or d in long_days) and d not in race_days}
        comp_day: dict[date, int] = {}
        for c in w.companions:
            comp_day[c.day] = comp_day.get(c.day, 0) + int(c.duration_min or 0)

        if idx in taper_frac:
            factor = taper_frac[idx]
        else:
            factor = min(1.0, bike_week / cyc_min) if cyc_min > 0 else 0.0
        want = {s: total_min * _share(targets, BALANCE_SPORT[s]) / 100 * factor for s in sports}
        room, asked = max(0.0, total_min - bike_week), sum(want.values())
        if asked > room:
            want = {s: v * room / asked for s, v in want.items()}
        budget = {s: want[s] - sum(c.duration_min or 0 for c in w.companions if c.sport == s) for s in sports}

        def free(d: date) -> int:
            h = date_h.get(d.isoformat(), weekday_h.get(d.weekday(), 0.0))
            return int(h * 60) - bike_day.get(d, 0) - comp_day.get(d, 0)

        def strength_ok(d: date) -> bool:
            # #127 heuristic: not on a hard day (bike, companion or race), not the day before a key one.
            return d not in hard_days and (d + timedelta(days=1)) not in key_days

        def candidates(sport: str, t: SessionTemplate, longest: bool = False) -> list[date]:
            out = []
            d = max(w.start, today)
            while d <= w.end:
                if (d not in race_days and not _blocked(sport, d, blocks) and free(d) >= t.minutes[0]
                        and not any(c.day == d and c.sport == sport for c in w.companions)
                        and (t.kind != "brick" or d in bike_day)
                        and (not t.hard or t.kind == "brick"
                             or not ({d - timedelta(days=1), d, d + timedelta(days=1)} & hard_days))
                        and (not t.hard or (d - timedelta(days=1)) not in strength_days)
                        and (sport != "strength" or (d not in hard_days if t.kind == MOBILITY else strength_ok(d)))):
                    out.append(d)
                d += timedelta(days=1)
            n_on = lambda d: sum(1 for c in w.companions if c.day == d)  # noqa: E731
            if longest:
                return sorted(out, key=lambda d: (-free(d), n_on(d), d))
            if sport == "strength":
                return sorted(out, key=lambda d: (n_on(d), d in bike_day, d in key_bike, -free(d), d))
            return sorted(out, key=lambda d: (n_on(d), d in bike_day, -free(d), d))

        def place(sport: str, t: SessionTemplate, minutes: float, days=None, extra=None):
            for d in candidates(sport, t) if days is None else days:
                dur = _floor_step(min(minutes, t.minutes[1], free(d)))
                if dur < t.minutes[0]:
                    continue
                workout = _build(t, thresholds or {}, dur, w.phase)
                if extra:
                    workout = {**(workout or {}), **(extra(d) if callable(extra) else extra)}
                c = CompanionSession(
                    day=d, day_name=d.strftime("%a"), duration_min=dur,
                    session_type=MOBILITY if sport == "strength" and t.kind == MOBILITY else t.session_type,
                    tss_estimate=0.0, description=t.intent, id=f"{sport}-{d.isoformat()}", sport=sport,
                    template_id=t.id, hard=t.hard, workout=workout)
                w.companions.append(c)
                comp_day[d] = comp_day.get(d, 0) + dur
                budget[sport] -= dur
                if t.hard:
                    hard_days.add(d)
                    hard_comp.add(d)
                    key_days.add(d)
                if t.kind == "brick":
                    key_days.add(d)
                if sport == "strength" and t.kind != MOBILITY:
                    strength_days.add(d)
                return c
            return None

        # Hard slots: what the week's own budget leaves after its bike sessions (limiter first).
        bike_hard = sum(1 for s in w.sessions if _session_is_hit(s))
        cap = w.hit_allowance if (w.hit_allowance or 0) >= 0 else bike_hard
        slots = 0
        if not w.is_stepback and w.phase not in EASY_PHASES:
            slots = max(bike_hard, hit_slots_for_volume(bike_week + sum(want.values()), cap))
        free_slots = slots - bike_hard - sum(1 for c in w.companions if c.hard and c.status != "dismissed")
        for s in sports:
            hard = [t for t in templates_for(s, library=lib) if t.hard and t.kind != "brick"]
            if free_slots <= 0 or not hard:
                continue
            t = hard[w.week_num % len(hard)]
            if budget[s] >= t.minutes[0] and place(s, t, budget[s],
                                                   extra={"limiter": LIMITER_HARD} if s == lim else None):
                free_slots -= 1

        # One brick: a run straight after a key ride, clear of hard companions; no hard slot of its own.
        bricks = templates_for("running", "brick", library=lib)
        if "running" in sports and bricks and sum(1 for c in w.companions if is_brick(c)) < BRICK_MAX_PER_WEEK:
            t = bricks[w.week_num % len(bricks)]
            days = [d for d in candidates("running", t) if d in key_bike
                    and (not t.hard or d in bike_hard_days)
                    and not ({d - timedelta(days=1), d, d + timedelta(days=1)} & hard_comp)]
            days.sort(key=lambda d: (d not in long_days, -free(d), d))
            if budget["running"] >= t.minutes[0]:
                place("running", t, budget["running"], days=days,
                      extra=lambda d: {"brick_of": bike_session_id(bike_sess[d])})

        # The limiter's longest session takes the longest free day before any other sport's easy session.
        if lim is not None and lim != "strength":
            pool = [t for t in templates_for(lim, library=lib) if not t.hard and t.kind != "brick"]
            longs = [t for t in pool if t.kind == "long"] or sorted(pool, key=lambda t: -t.minutes[1])[:1]
            if longs:
                t = longs[w.week_num % len(longs)]
                if budget[lim] >= t.minutes[0]:
                    place(lim, t, budget[lim], days=candidates(lim, t, longest=True), extra={"limiter": LIMITER_LONG})

        def fill_easy(s: str, easy: list, cap: int | None = None) -> None:
            if not easy:
                return
            lo, hi = min(t.minutes[0] for t in easy), max(t.minutes[1] for t in easy)
            if budget[s] < lo:
                return
            n = max(1, math.ceil(budget[s] / hi))
            if cap is not None:
                n = min(n, cap)
            if n <= 0:
                return
            per = max(lo, min(hi, _floor_step(budget[s] / n)))
            for i in range(n):
                if budget[s] < lo:
                    break
                m = min(per, budget[s])
                fits = [t for t in easy if t.minutes[0] <= m] or easy   # a long template needs a long slot
                t = fits[(w.week_num + i) % len(fits)]
                if not place(s, t, m):
                    break

        # Easy sessions fill what is left of each sport's hours.
        for s in sports:
            easy = [t for t in templates_for(s, library=lib) if not t.hard and t.kind != "brick"]
            if s != "strength":
                fill_easy(s, easy)
                continue
            # Strength: up to STRENGTH_MAX_PER_WEEK resistance sessions (maintenance first in a build or
            # peak phase, A/B otherwise), then mobility with what is left.
            resist = [t for t in easy if t.kind != MOBILITY]
            pref = "maintenance" if w.phase in BUILD_PHASES else "strength"
            fill_easy(s, [t for t in resist if t.kind == pref] or resist,
                      STRENGTH_MAX_PER_WEEK - sum(1 for c in w.companions if _is_resistance(c)))
            fill_easy(s, [t for t in easy if t.kind == MOBILITY])
        w.companions.sort(key=lambda c: (c.day, COMPANION_SPORTS.index(c.sport) if c.sport in COMPANION_SPORTS else 9))

    for i, w in enumerate(weeks):
        fill(w, i)
    return weeks


# ── completion ─────────────────────────────────────────────────────────────────────────────────────
def _activity_minutes(a: dict) -> float:
    v = a.get("duration_sec")
    return float(v) / 60 if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0.0


def reconcile_week(week: dict, activities: list[dict], today: date) -> int:
    """Marks a stored plan week's companions (dicts) from activities-table rows (date, sport,
    duration_sec, id), in place; returns how many changed.

    A pending or missed companion is done when an activity of its sport (multisport.sport_of; strength is
    "other") on its day lasts within +-50 % of it; each activity completes one companion. A pending one
    whose day has passed is missed. When the week has ended, missed companions are dropped silently (their
    load is never moved into cycling). Cycling sessions are not read."""
    comps = week.get("companions")
    if not isinstance(comps, list) or not comps:
        return 0
    used = {m.get("activity_id") for c in comps if isinstance(c, dict)
            for m in (c.get("completion_matches") or []) if isinstance(m, dict)}
    changed = 0
    for c in comps:
        if not isinstance(c, dict) or c.get("status", "pending") not in ("pending", "missed") or c.get("dismissed_at"):
            continue
        day, planned = str(c.get("day", ""))[:10], float(c.get("duration_min") or 0)
        want = BALANCE_SPORT.get(c.get("sport"), c.get("sport"))
        hit = next((a for a in activities
                    if str(a.get("date", ""))[:10] == day and sport_of(a.get("sport")) == want
                    and a.get("id") not in used and planned > 0
                    and abs(_activity_minutes(a) - planned) <= MATCH_TOLERANCE * planned), None)
        if hit is not None:
            used.add(hit.get("id"))
            c["status"] = "done"
            c["completion_matches"] = [{"activity_id": hit.get("id"), "duration_min": round(_activity_minutes(hit))}]
            changed += 1
        elif day < today.isoformat() and c.get("status", "pending") == "pending":
            c["status"] = "missed"
            changed += 1
    end = _as_day(week.get("end"))
    if end is not None and end < today:
        kept = [c for c in comps if not (isinstance(c, dict) and c.get("status") == "missed")]
        if len(kept) != len(comps):
            changed += len(comps) - len(kept)
            if kept:
                week["companions"] = kept
            else:
                week.pop("companions", None)
    return changed


def _load_libraries() -> None:
    """Imports every src/sessions_*.py (the run, swim and strength libraries). Each registers its templates
    on import and may retire the placeholder it replaces. A library that fails to import is logged and
    skipped, so one broken library cannot stop plans from being built."""
    import importlib
    import logging
    from pathlib import Path
    for path in sorted(Path(__file__).resolve().parent.glob("sessions_*.py")):
        try:
            importlib.import_module(path.stem)
        except Exception:  # noqa: BLE001
            logging.getLogger("shepherd.plan").exception("session library %s failed to load", path.stem)


_load_libraries()
