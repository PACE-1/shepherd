"""Weekly sport balance (#124, actuals half): hours and load by sport per ISO week and calendar month,
against a target split the rider types in.

Actuals only. Hours are ``duration_sec`` / 3600; load is the ``tss`` column, i.e. intervals.icu's own
training load for each activity, the same number multisport.load_by_sport uses (it is on each sport's own
scale, so load shares across sports are indicative, not exact). Sports come from multisport.sport_of.

There is no default split: until the rider saves targets (percent of weekly hours per sport, summing to
100) there is nothing to compare against. The planner's companion overlay (multisport_plan) gives a run or
swim limiter first pick of hard-session slots and of the longest free day; a cycling limiter changes nothing.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from atomic_io import write_json_atomic
from multisport import SPORTS, _read, sport_of

FILE_NAME = "balance_targets.json"
LIMITER_SPORTS = ("cycling", "running", "swimming")
LIMITER_NOTE = ("The plan gives a run or swim limiter first pick of the hard-session slots and of the longest "
                "free day, within your own split (no hours move). A cycling limiter changes nothing.")
METHOD = ("Hours come from each activity's duration; load is intervals.icu's training load for it, which is "
          "on that sport's own scale, so shares of load across sports are indicative.")


def week_start(d: date) -> date:
    """The Monday of ``d``'s ISO week."""
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def window(today: date, weeks: int) -> tuple[list[tuple[date, date]], list[tuple[date, date]]]:
    """(weeks, months) as inclusive (start, end) pairs, oldest first; the last of each holds ``today``.

    Weeks are ISO weeks (Monday to Sunday). Months are calendar months, as many as cover ``weeks`` weeks.
    """
    w0 = week_start(today) - timedelta(weeks=weeks - 1)
    wk = [(w0 + timedelta(weeks=i), w0 + timedelta(weeks=i, days=6)) for i in range(weeks)]
    n_months = max(1, math.ceil(weeks * 7 / 30))
    m0 = _add_months(month_start(today), -(n_months - 1))
    mo = [(s, _add_months(s, 1) - timedelta(days=1)) for s in (_add_months(m0, i) for i in range(n_months))]
    return wk, mo


def window_start(today: date, weeks: int) -> date:
    """The earliest date any bucket of ``window`` covers: query activities from here."""
    wk, mo = window(today, weeks)
    return min(wk[0][0], mo[0][0])


def _share(part: dict[str, float], total: float) -> dict[str, Optional[float]]:
    return {s: (round(100 * part[s] / total, 1) if total > 0 else None) for s in SPORTS}


def _bucket(key: str, label: str, start: date, end: date, hours: dict[str, float], load: dict[str, float],
            targets: Optional[dict[str, float]]) -> dict:
    th, tl = sum(hours.values()), sum(load.values())
    hs = _share(hours, th)
    gap = {s: round(hs[s] - targets[s], 1) for s in SPORTS} if targets and th > 0 else None
    return {
        "key": key, "label": label, "start": start.isoformat(), "end": end.isoformat(),
        "hours": {s: round(hours[s], 2) for s in SPORTS}, "load": {s: round(load[s], 1) for s in SPORTS},
        "total_hours": round(th, 2), "total_load": round(tl, 1),
        "hours_share": hs, "load_share": _share(load, tl), "gap_pp": gap,
    }


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0.0


def balance(activities: list[dict], today: date, weeks: int = 12, targets: Optional[dict[str, float]] = None) -> dict:
    """Hours and load by sport for each of the last ``weeks`` ISO weeks and the calendar months around them.

    ``activities`` are activities-table rows (date, sport, duration_sec, tss). Rows dated after ``today`` or
    before the window are ignored. ``targets`` (all four sports, percent) adds ``gap_pp`` = actual share of
    hours minus target, in percentage points; without targets it is None.
    """
    wk, mo = window(today, weeks)
    first = min(wk[0][0], mo[0][0])
    zero = lambda: ({x: 0.0 for x in SPORTS}, {x: 0.0 for x in SPORTS})  # noqa: E731
    acc = {"w": {s: zero() for s, _ in wk}, "m": {s: zero() for s, _ in mo}}
    for a in activities:
        try:
            d = date.fromisoformat(str(a.get("date"))[:10])
        except ValueError:
            continue
        if not first <= d <= today:
            continue
        hours, load, s = _num(a.get("duration_sec")) / 3600, _num(a.get("tss")), sport_of(a.get("sport"))
        for kind, start in (("w", week_start(d)), ("m", month_start(d))):
            if start in acc[kind]:
                acc[kind][start][0][s] += hours
                acc[kind][start][1][s] += load
    weeks_out = [_bucket(f"{s.isocalendar()[0]}-W{s.isocalendar()[1]:02d}", f"Week of {s.isoformat()}", s, e,
                         *acc["w"][s], targets) for s, e in wk]
    months_out = [_bucket(s.strftime("%Y-%m"), s.strftime("%B %Y"), s, e, *acc["m"][s], targets) for s, e in mo]
    present = [s for s in SPORTS if any(b["hours"][s] > 0 for b in weeks_out)]
    return {
        "as_of": today.isoformat(), "weeks": weeks_out, "months": months_out,
        "sports_present": present, "single_sport": present[0] if len(present) == 1 else None,
        "has_history": bool(present), "method": METHOD,
    }


# ── targets and the limiter: one JSON file per profile ───────────────────────────────────────────
def read_targets(path: Path) -> dict:
    """{targets: {sport: percent} | None, limiter: sport | None}. Nothing stored means no targets."""
    stored = _read(path)
    t = stored.get("targets")
    ok = isinstance(t, dict) and all(isinstance(t.get(s), (int, float)) for s in SPORTS)
    lim = stored.get("limiter")
    return {"targets": {s: float(t[s]) for s in SPORTS} if ok else None,
            "limiter": lim if lim in LIMITER_SPORTS else None}


def save_targets(path: Path, targets: Optional[dict], limiter: Optional[str]) -> dict:
    """Stores the split and the limiter. ``targets`` None or {} clears the split; otherwise every value is a
    percent of weekly hours between 0 and 100 and they sum to 100 (a sport left out counts as 0).
    Raises ValueError otherwise."""
    if limiter is not None and limiter not in LIMITER_SPORTS:
        raise ValueError(f"limiter must be one of {', '.join(LIMITER_SPORTS)} or empty")
    clean: Optional[dict[str, float]] = None
    if targets:
        if not isinstance(targets, dict):
            raise ValueError("targets must be an object of sport -> percent")
        unknown = set(targets) - set(SPORTS)
        if unknown:
            raise ValueError(f"unknown sport {sorted(unknown)[0]!r}")
        clean = {}
        for s in SPORTS:
            v = targets.get(s, 0)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100:
                raise ValueError(f"{s} must be a percent between 0 and 100")
            clean[s] = float(v)
        if abs(sum(clean.values()) - 100) > 0.05:
            raise ValueError(f"targets must add up to 100 percent (they add up to {round(sum(clean.values()), 1):g})")
    write_json_atomic(path, {"targets": clean, "limiter": limiter})
    return read_targets(path)
