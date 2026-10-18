"""Injury and illness episodes, the return-to-training ramp after one, and the weekly ramp-rate warning (#113).

NOT MEDICAL ADVICE. Everything here is a conservative training heuristic. The rider is told so on every
response (``NOT_MEDICAL_ADVICE``).

Episodes. One JSON file per profile (``injury_episodes.json``): type injury|illness, start, optional end
(open-ended until the rider marks it resolved), optional sport and body area, a note. They reach the plan
through the planner's existing time-off mechanism, ``plan["unavailable_periods"]`` (the rows the Plan's
"Time off" form writes): ``sync_plan_periods`` writes one period per episode, tagged with ``episode_id``,
so the planner turns those days into rest exactly as it does for a holiday. An open episode covers the
rest of the plan and a year past today (a rebuild can lengthen the plan), i.e. the plan is paused until the
rider says they are back.

Return ramp. ``return_ramp`` tells the planner (``training_planner.regenerate_from_today``) that an episode
ended recently. The planner then reuses its own absence ramp, ``build_recovery_ramp``, unchanged: the first
week or two easy aerobic (Z2) only, then every ramp week still Z2, at 75/85/95 % of the decayed-CTL
maintenance load after up to 2 weeks off, 50..90 % after 3-4 weeks, 40..90 % after 5+, each week capped at
1.3 x the rolling chronic load. Sources and how far they carry it:
  * Detraining and reconditioning: Mujika I, Padilla S. Detraining: loss of training-induced physiological
    and performance adaptations, Parts I and II. Sports Med 2000;30(2):79-87 and 30(3):145-154. They
    describe how fitness is lost, not a return protocol, so the ramp's percentages are the planner's
    heuristic informed by them, not numbers taken from them.
  * Load progression: every step of those ramps is +10..+25 % a week, inside the range Nielsen RO et al.
    found no excess injury in (Excessive progression in weekly running distance and risk of running-related
    injuries. JOSPT 2014;44(10):739-747: novice runners progressing > 30 % a week had more distance-related
    injuries than those under 10 %; 10-30 % was not clearly different). Running data, not cycling.
  * Illness: no training with fever or "below the neck" symptoms (chest, aches, gut) and easy aerobic work
    only on return: the "neck check" (Eichner ER. Infection, immunity, and exercise. Phys Sportsmed
    1993;21(1):125-135) and the IOC consensus on load and illness (Schwellnus M et al. Br J Sports Med
    2016;50:1043-1052). The ramp therefore starts only once the rider marks the episode resolved, and holds
    intensity out for its whole length.
  * An injury, or an illness of 15 days or more, gets at least the planner's shortest ramp (the one for up to 2
    weeks off). A shorter illness gets none: the rider's own report of feeling well ends the pause, and the planner's
    short-break re-entry rule (SCIENCE.md 1b: keep the intensity, cut the volume) applies.
    That is a deliberate conservative choice, not a published number.
Confidence: low. These are conservative coaching heuristics, not a validated return-to-sport protocol.

Ramp-rate warning. The last 7 days' load against the weekly average of the 4 weeks before them (the
"uncoupled" acute:chronic ratio, which keeps the current week out of the baseline: Lolli L et al.
Mathematical coupling causes spurious correlation within the conventional acute-to-chronic workload ratio
calculations. Br J Sports Med 2019;53:921-922). Above 1.3 is past the "sweet spot" and 1.5 or more is the
"danger zone" of Gabbett TJ, The training-injury prevention paradox, Br J Sports Med 2016;50:273-280 (team
sports; also Hulin BT et al. Br J Sports Med 2016;50:231-236). The ratio's predictive value is disputed
(Impellizzeri FM et al. Acute:chronic workload ratio: conceptual issues and fundamental pitfalls. IJSPP
2020;15(6):907-913), so it is shown as a heuristic prompt, not a risk estimate. Weekly loads come from
``multisport.load_by_sport`` (combined and per sport).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from atomic_io import update_json
from multisport import SPORTS, load_by_sport

TYPES = ("injury", "illness")
EPISODE_SPORTS = ("all", *SPORTS)
FILE_NAME = "injury_episodes.json"
NOTE_MAX, AREA_MAX = 500, 60
OPEN_HORIZON_DAYS = 365  # how far ahead an open episode's time off reaches; rewritten on every change

NOT_MEDICAL_ADVICE = (
    "Not medical advice. This is a conservative training heuristic. See a clinician for an injury that is "
    "not settling, and do not train with a fever or chest symptoms (chest pain, breathlessness, palpitations).")

# Below this many days, an illness gets no return ramp (the planner's own short-break re-entry rule
# applies, SCIENCE.md 1b); at 15 days that rule hands over to the planner's recovery ramp.
SHORT_ILLNESS_DAYS = 15
RAMP_ELEVATED, RAMP_HIGH = 1.3, 1.5
RAMP_METHOD = ("Last 7 days' load divided by the weekly average of the 4 weeks before them (uncoupled "
               "acute:chronic ratio, Lolli et al. 2019). Above 1.3 is past the 'sweet spot' and 1.5 or more "
               "is the 'danger zone' of Gabbett 2016.")
RAMP_CONFIDENCE = ("Low: a heuristic from team-sport and running studies whose predictive value is disputed "
                   "(Impellizzeri et al. 2020). Small loads swing the ratio a lot.")
RETURN_METHOD = ("The planner's absence ramp: easy aerobic (Z2) riding only, rising from 75-95 % (short "
                 "episodes) or 40-90 % (5+ weeks) of the load your current fitness maintains, each week no "
                 "more than 1.3 x the rolling load. Conservative heuristic informed by Mujika and Padilla 2000 "
                 "(detraining) and Nielsen et al. 2014 (weekly progression), not a medical protocol.")


# ── episodes: one file per profile ─────────────────────────────────────────────────────────────────
def _day(v, what: str) -> date:
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a date (YYYY-MM-DD)") from None


def read_episodes(path: Path) -> list[dict]:
    """The stored episodes, newest start first. A missing or corrupt file reads as none."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    eps = [e for e in data.get("episodes", []) if isinstance(e, dict)] if isinstance(data, dict) else []
    return sorted(eps, key=lambda e: str(e.get("start", "")), reverse=True)


def _update(path: Path, mutate) -> list[dict]:
    def apply(data):
        if not isinstance(data, dict):
            data = {}
        data["episodes"] = mutate([e for e in data.get("episodes", []) if isinstance(e, dict)])
        return data
    # strict: an unreadable file is never overwritten with a fresh one (that would lose the history).
    try:
        update_json(path, apply, default=dict, strict=True)
    except FileNotFoundError:
        update_json(path, apply, default=dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OSError("the injury and illness file could not be read, so it was left as it is") from None
    return read_episodes(path)


def add_episode(path: Path, *, type: str, start, end=None, sport: str = "all", body_area: str = "",
                note: str = "") -> dict:
    """Stores a new episode and returns it. Raises ValueError on bad input."""
    if type not in TYPES:
        raise ValueError("type must be injury or illness")
    if sport not in EPISODE_SPORTS:
        raise ValueError(f"sport must be one of {', '.join(EPISODE_SPORTS)}")
    s = _day(start, "start")
    e = _day(end, "end") if end not in (None, "") else None
    if e is not None and e < s:
        raise ValueError("end must not be before start")
    ep = {"id": uuid.uuid4().hex[:12], "type": type, "start": s.isoformat(), "end": e.isoformat() if e else None,
          "sport": sport, "body_area": str(body_area or "").strip()[:AREA_MAX],
          "note": str(note or "").strip()[:NOTE_MAX]}
    _update(path, lambda eps: [*eps, ep])
    return ep


def resolve_episode(path: Path, episode_id: str, end) -> dict:
    """Sets an episode's last day. Raises KeyError for an unknown id, ValueError for a bad date."""
    found: list[dict] = []

    def mutate(eps):
        for ep in eps:
            if ep.get("id") == episode_id:
                last = _day(end, "end")
                if last < _day(ep.get("start"), "start"):
                    raise ValueError("end must not be before start")
                ep["end"] = last.isoformat()
                found.append(ep)
        if not found:
            raise KeyError(episode_id)
        return eps
    _update(path, mutate)
    return found[0]


def back_today_end(episode: dict, today: date) -> date:
    """'I'm back' today: the episode's last day is yesterday (or its first day, if it began today)."""
    return max(_day(episode.get("start"), "start"), today - timedelta(days=1))


def delete_episode(path: Path, episode_id: str) -> None:
    def mutate(eps):
        kept = [e for e in eps if e.get("id") != episode_id]
        if len(kept) == len(eps):
            raise KeyError(episode_id)
        return kept
    _update(path, mutate)


# ── the plan's time off ────────────────────────────────────────────────────────────────────────────
def _plan_end(plan: dict) -> date | None:
    ends = []
    for w in plan.get("weeks") or []:
        try:
            ends.append(date.fromisoformat(str(w.get("end"))))
        except (AttributeError, ValueError):
            continue
    return max(ends) if ends else None


def sync_plan_periods(plan: dict, episodes: list[dict], today: date) -> bool:
    """Rewrites the episode rows of ``plan["unavailable_periods"]`` from ``episodes``; other time off is kept
    as it is. Only episodes that affect cycling (sport "all" or "cycling") pause the plan, which is a cycling
    plan. An open episode runs to the plan's last day or OPEN_HORIZON_DAYS ahead, whichever is later.
    Returns True when the plan changed."""
    before = plan.get("unavailable_periods") or []
    kept = [p for p in before if not (isinstance(p, dict) and p.get("episode_id"))]
    horizon = max(today + timedelta(days=OPEN_HORIZON_DAYS), _plan_end(plan) or today)
    for ep in sorted(episodes, key=lambda e: str(e.get("start", ""))):
        if ep.get("sport", "all") not in ("all", "cycling"):
            continue
        start = str(ep.get("start"))
        end = ep.get("end") or max(horizon.isoformat(), start)
        kept.append({"start": start, "end": end, "type": ep.get("type", "injury"), "daily_tss": 0,
                     "reason": ep.get("body_area") or ep.get("type", ""), "episode_id": ep.get("id"),
                     "open": not ep.get("end")})
    if kept == before:
        return False
    plan["unavailable_periods"] = kept
    return True


def episode_days(periods: list | None) -> set[date]:
    """Every day covered by an episode's time-off row (rows without ``episode_id`` are ignored)."""
    out: set[date] = set()
    for p in periods or []:
        if not (isinstance(p, dict) and p.get("episode_id")):
            continue
        try:
            d, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        except (KeyError, TypeError, ValueError):
            continue
        while d <= end:
            out.add(d)
            d += timedelta(days=1)
    return out


def return_ramp(periods: list | None, today: date) -> dict | None:
    """What the planner's return ramp needs after the most recent finished episode, or None.

    None when there is no episode row (every plan without one is untouched), when an episode is still
    open or covers today, or when the latest one is still in the future. ``absence_days`` sizes the
    planner's ramp (at least 7, so any episode gets the shortest one); ``weeks_done`` is how many whole
    ramp weeks have passed since the rider came back, so a later rebuild continues the ramp rather than
    starting it again."""
    rows = []
    for p in periods or []:
        if not (isinstance(p, dict) and p.get("episode_id")):
            continue
        if p.get("open"):
            return None
        try:
            s, e = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if s <= today <= e:
            return None
        if e < today:
            rows.append((e, s, p))
    if not rows:
        return None
    end, start, p = max(rows, key=lambda r: r[0])
    days = (end - start).days + 1
    if p.get("type") == "illness" and days < SHORT_ILLNESS_DAYS:
        return None   # a short illness is a short break: the planner's re-entry rule (SCIENCE.md 1b) applies, with no forced ramp
    return {"episode_id": p["episode_id"], "type": p.get("type", "injury"), "start": start.isoformat(),
            "end": end.isoformat(), "episode_days": days, "absence_days": max(7, days),
            "weeks_done": ((today - end).days - 1) // 7}


# ── ramp-rate warning ───────────────────────────────────────────────────────────────────────────────
def _rate(week: float, prev: list[float]) -> dict:
    base = sum(prev) / len(prev)
    out = {"week_load": round(week, 1), "prev_4wk_avg": round(base, 1), "ratio": None, "change_pct": None}
    if base <= 0:
        return {**out, "level": "no_base"}
    ratio = week / base
    level = "high" if ratio >= RAMP_HIGH else "elevated" if ratio > RAMP_ELEVATED else "ok"
    return {**out, "ratio": round(ratio, 2), "change_pct": round((ratio - 1) * 100), "level": level}


def ramp_rate(activities: list[dict], today: date) -> dict:
    """This week's load (the 7 days to ``today``) against the 4 weeks before, combined and per sport."""
    lines = [load_by_sport(activities, today - timedelta(days=7 * k), days=7) for k in range(5)]
    combined = _rate(lines[0]["combined"]["week_load"], [ln["combined"]["week_load"] for ln in lines[1:]])
    sports = {}
    for s in SPORTS:
        loads = [ln["sports"].get(s, {}).get("week_load", 0.0) for ln in lines]
        if any(loads):
            sports[s] = _rate(loads[0], loads[1:])
    warnings = []
    for name, r in [("All sports", combined), *[(s.capitalize(), r) for s, r in sports.items()]]:
        if r["level"] in ("elevated", "high"):
            warnings.append(f"{name}: this week's load is {r['change_pct']}% above your 4-week average "
                            f"({r['week_load']:.0f} vs {r['prev_4wk_avg']:.0f}).")
    return {"as_of": today.isoformat(), "threshold": RAMP_ELEVATED, "high": RAMP_HIGH, "combined": combined,
            "sports": sports, "warn": bool(warnings), "warnings": warnings, "method": RAMP_METHOD,
            "confidence": RAMP_CONFIDENCE, "note": NOT_MEDICAL_ADVICE}
