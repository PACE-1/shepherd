"""Body-weight trend and W/kg history (#114). Pure functions; no I/O.

Method: exponentially weighted moving average for unevenly spaced readings
(exponential smoothing, Brown 1956; the irregular-interval form in Eckner,
"Algorithms for Unevenly Spaced Time Series", 2019). With a time constant of
TAU_DAYS, each reading moves the trend by ``1 - exp(-gap_days / TAU_DAYS)``
of the distance to it, so a reading after a long gap counts for more than one
the next morning, and daily readings behave like a 7-day exponential average.
The first reading starts the trend.

W/kg for a date is the FTP in force on that date divided by the trend weight on
that date, so a single heavy or light morning does not move it.
"""
from __future__ import annotations

import math
from datetime import date

TAU_DAYS = 7.0
METHOD = ("Exponentially weighted moving average, time constant 7 days, for "
          "unevenly spaced readings (Brown 1956; Eckner 2019).")
# The range the profile's weight field accepts (app.SETUP_LIMITS["weight"]).
WEIGHT_RANGE_KG = (30.0, 200.0)


def merge_readings(manual: list[dict], synced: list[dict]) -> list[dict]:
    """One reading per date, sorted. ``manual`` (typed in or saved in
    Settings) wins over ``synced`` (intervals.icu wellness) on the same date.
    Each input row is {date, value, source?}; out-of-range values are dropped."""
    lo, hi = WEIGHT_RANGE_KG
    by_date: dict[str, dict] = {}
    for rows, default_src in ((synced, "intervals.icu"), (manual, "manual")):
        for r in rows:
            try:
                d = date.fromisoformat(str(r["date"])[:10]).isoformat()
                v = float(r["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (lo <= v <= hi):
                continue
            by_date[d] = {"date": d, "weight_kg": v, "source": r.get("source") or default_src}
    return [by_date[d] for d in sorted(by_date)]


def ewma_trend(readings: list[dict], tau_days: float = TAU_DAYS) -> list[dict]:
    """Add ``trend_kg`` to each reading (sorted by date, one per date)."""
    out: list[dict] = []
    trend = prev = None
    for r in readings:
        d = date.fromisoformat(r["date"])
        if trend is None:
            trend = r["weight_kg"]
        else:
            a = 1.0 - math.exp(-(d - prev).days / tau_days)
            trend += a * (r["weight_kg"] - trend)
        prev = d
        out.append({**r, "trend_kg": round(trend, 2)})
    return out


def _at(rows: list[tuple[str, float]], day: str):
    """Value of the last row on or before ``day`` (rows sorted by date)."""
    v = None
    for d, x in rows:
        if d > day:
            break
        v = x
    return v


def wkg_history(trend: list[dict], ftp_rows: list[dict]) -> list[dict]:
    """W/kg on every date with an FTP change or a weight reading, once both an
    FTP and a weight are known. ``ftp_rows`` are {date, ftp}; a later entry on
    the same date wins."""
    ftp_by_date: dict[str, float] = {}
    for r in ftp_rows:
        try:
            d = date.fromisoformat(str(r["date"])[:10]).isoformat()
            f = float(r["ftp"])
        except (KeyError, TypeError, ValueError):
            continue
        if f > 0:
            ftp_by_date[d] = f
    ftps = sorted(ftp_by_date.items())
    weights = [(r["date"], r["trend_kg"]) for r in trend]
    out = []
    for d in sorted(set(ftp_by_date) | {w[0] for w in weights}):
        f, w = _at(ftps, d), _at(weights, d)
        if f and w:
            out.append({"date": d, "ftp_w": round(f), "weight_kg": w, "w_per_kg": round(f / w, 2)})
    return out


def change_over(trend: list[dict], days: int, today: date) -> float | None:
    """Trend change over the last ``days`` days, or None without a reading
    at or before the start of that span."""
    if not trend:
        return None
    start = date.fromordinal(today.toordinal() - days).isoformat()
    then = _at([(r["date"], r["trend_kg"]) for r in trend], start)
    return None if then is None else round(trend[-1]["trend_kg"] - then, 2)
