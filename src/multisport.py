"""Multi-sport data model (#109): sport mapping, per-sport and combined training load, per-sport thresholds.

Load method: the performance-management chart of Allen and Coggan, "Training and
Racing with a Power Meter" (CTL and ATL are exponentially weighted averages of daily
training stress with time constants of 42 and 7 days; TSB = CTL - ATL, both taken the
day before). The per-day update is x += (load - x) * (1 - exp(-1/tau)), the form
intervals.icu publishes. Daily stress is the ``tss`` column, i.e. intervals.icu's
``icu_training_load`` for each activity, which is on that sport's own scale (power TSS,
run and swim stress). The combined line sums them, which is the usual approximation;
the confidence statement ships in the API response.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

from atomic_io import write_json_atomic

SPORTS = ("cycling", "running", "swimming", "other")
CTL_DAYS, ATL_DAYS = 42, 7

_SPORT_OF = {
    **dict.fromkeys(("ride", "virtualride", "gravelride", "mountainbikeride", "ebikeride", "ebikemountainbikeride", "handcycle", "velomobile"), "cycling"),
    **dict.fromkeys(("run", "trailrun", "virtualrun", "walk", "hike"), "running"),
    **dict.fromkeys(("swim", "openwaterswim"), "swimming"),
}

# kind -> (sport, unit, low, high). Ranges reject typos, not elite values.
THRESHOLDS = {
    "run_threshold_pace": ("running", "s/km", 120, 900),
    "run_threshold_hr": ("running", "bpm", 100, 220),
    "swim_css": ("swimming", "s/100m", 40, 300),
}


def sport_of(activity_type: str | None) -> str:
    """Maps an intervals.icu activity type to one of SPORTS. Missing or unknown types are "other"."""
    key = (activity_type or "").replace(" ", "").replace("_", "").lower()
    return _SPORT_OF.get(key, "other")


def _series(daily: dict[date, float], start: date, end: date, tau: int) -> dict[date, float]:
    k = 1 - math.exp(-1 / tau)
    x, out, d = 0.0, {}, start
    while d <= end:
        x += (daily.get(d, 0.0) - x) * k
        out[d] = x
        d += timedelta(days=1)
    return out


def _line(daily: dict[date, float], start: date, end: date) -> dict:
    ctl, atl = _series(daily, start, end, CTL_DAYS), _series(daily, start, end, ATL_DAYS)
    yday = end - timedelta(days=1)
    return {
        "ctl": round(ctl[end], 1),
        "atl": round(atl[end], 1),
        "tsb": round(ctl[yday] - atl[yday], 1) if yday >= start else 0.0,
        "week_load": round(sum(v for d, v in daily.items() if end - timedelta(days=6) <= d <= end), 1),
    }


def load_by_sport(activities: list[dict], today: date, days: int = 180) -> dict:
    """Per-sport and combined CTL/ATL/TSB from ``activities`` rows (date, sport, tss).

    The series starts ``days`` back, so values are settled only once the history is
    longer than about 3 x 42 days; ``days_of_history`` says how much there is.
    """
    start = today - timedelta(days=days)
    per: dict[str, dict[date, float]] = {s: {} for s in SPORTS}
    first = None
    for a in activities:
        try:
            d = date.fromisoformat(str(a.get("date"))[:10])
        except ValueError:
            continue
        load = a.get("tss")
        if not isinstance(load, (int, float)) or load <= 0 or not start <= d <= today:
            continue
        s = sport_of(a.get("sport"))
        per[s][d] = per[s].get(d, 0.0) + float(load)
        first = d if first is None or d < first else first
    total: dict[date, float] = {}
    for m in per.values():
        for d, v in m.items():
            total[d] = total.get(d, 0.0) + v
    history = (today - first).days + 1 if first else 0
    return {
        "as_of": today.isoformat(),
        "days_of_history": history,
        "settled": history >= 3 * CTL_DAYS,
        "combined": _line(total, start, today),
        "sports": {s: _line(m, start, today) for s, m in per.items() if m},
        "method": "Allen and Coggan performance-management chart: CTL 42 days, ATL 7 days, TSB = CTL - ATL of the previous day.",
        "confidence": "Each sport's load is intervals.icu's own training load for it; the combined line adds them, so it is an approximation across sports.",
    }


# ── thresholds: one file per profile, each kind keeps its dated history ──────────────────────────
def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def read_thresholds(path: Path) -> dict:
    """{kind: {sport, unit, current, history: [{value, date, source}]}} for every kind, empty ones included."""
    stored = _read(path)
    out = {}
    for kind, (sport, unit, _lo, _hi) in THRESHOLDS.items():
        hist = stored.get(kind, [])
        out[kind] = {"sport": sport, "unit": unit, "current": hist[-1]["value"] if hist else None, "history": hist}
    return out


def set_threshold(path: Path, kind: str, value: float, on: date, source: str = "manual") -> dict:
    """Appends a dated value (the same day replaces). Raises ValueError for an unknown kind or out-of-range value."""
    if kind not in THRESHOLDS:
        raise ValueError(f"unknown threshold {kind!r}")
    _sport, unit, lo, hi = THRESHOLDS[kind]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise ValueError(f"{kind} must be between {lo} and {hi} {unit}")
    stored = _read(path)
    hist = [e for e in stored.get(kind, []) if e.get("date") != on.isoformat()]
    hist.append({"value": float(value), "date": on.isoformat(), "source": source})
    stored[kind] = sorted(hist, key=lambda e: e["date"])
    write_json_atomic(path, stored)
    return read_thresholds(path)[kind]
