"""Multi-sport data model (#109): sport mapping, per-sport thresholds, per-sport load.

Cycling stays where it was: FTP is the existing ``ftp`` row in ``athlete_metrics``
and the ``ATHLETE_FTP_W`` setting, untouched. Run and swim thresholds are rows in
the same table, so they get dated history and a test date for free and nothing
in an existing profile or database needs migrating.

Load. intervals.icu supplies a training load per activity (``icu_training_load``,
stored in ``activities.tss``) but its wellness record carries CTL/ATL only for
the athlete as a whole, not per sport. So per-sport CTL/ATL/TSB are derived here
from the per-activity load with the same EWMA the rest of the app uses
(`ride_storage.compute_local_ctl`: tau 42 and 7 days). Because the EWMA is
linear, the combined series is exactly the sum of the per-sport ones. The
combined numbers from intervals.icu (`fitness.state`) remain the headline;
`combined` here is the local sum, returned beside them so one can be checked
against the other.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import clock

SPORTS = ("ride", "run", "swim", "other")

# intervals.icu activity types. Anything unlisted is "other" (strength, hike,
# yoga, ...): it still counts toward combined load, it just has no thresholds.
_ICU_TYPES = {
    "ride": ("Ride", "VirtualRide", "EBikeRide", "GravelRide", "MountainBikeRide",
             "EMountainBikeRide", "Handcycle", "Velomobile"),
    "run": ("Run", "TrailRun", "VirtualRun"),
    "swim": ("Swim", "OpenWaterSwim"),
}
_SPORT_BY_TYPE = {t: s for s, types in _ICU_TYPES.items() for t in types}


def sport_of(activity_type: Optional[str]) -> str:
    """'ride' | 'run' | 'swim' | 'other' for an intervals.icu activity type."""
    return _SPORT_BY_TYPE.get(activity_type or "", "other")


# threshold key -> (athlete_metrics metric, unit, lowest, highest accepted)
THRESHOLDS = {
    "ftp":           ("ftp",                 "W",        50,  700),
    "run_pace":      ("run_threshold_pace",  "s/km",     120, 900),
    "run_lthr":      ("run_lthr",            "bpm",      80,  230),
    "swim_css":      ("swim_css",            "s/100m",   40,  300),
}
SPORT_THRESHOLDS = {"ride": ("ftp",), "run": ("run_pace", "run_lthr"), "swim": ("swim_css",)}

CTL_TAU = 42
ATL_TAU = 7


def set_threshold(key: str, value: float, on: Optional[date] = None, source: str = "manual") -> None:
    """Record a threshold test result for `on` (default today). One value per
    day per threshold; a later write the same day replaces the earlier."""
    import db
    if key not in THRESHOLDS:
        raise ValueError(f"unknown threshold {key!r}")
    metric, unit, lo, hi = THRESHOLDS[key]
    value = float(value)
    if not lo <= value <= hi:
        raise ValueError(f"{key} {value:g} {unit} is outside {lo}-{hi}")
    db.log_metric((on or clock.today()).isoformat(), metric, value, source=source)


def threshold_history(key: str, days: int = 3650) -> list[dict]:
    """[{date, value, source}] oldest first."""
    import db
    return [{"date": r["date"], "value": r["value"], "source": r["source"]}
            for r in db.query_metric_history(THRESHOLDS[key][0], days=days)]


def thresholds() -> dict:
    """{sport: {key: {value, unit, tested_on} | None}} for ride, run and swim:
    the latest value of each threshold and the date it was recorded."""
    out: dict = {}
    for sport, keys in SPORT_THRESHOLDS.items():
        out[sport] = {}
        for k in keys:
            hist = threshold_history(k)
            out[sport][k] = ({"value": hist[-1]["value"], "unit": THRESHOLDS[k][1],
                              "tested_on": hist[-1]["date"]} if hist else None)
    return out


def _daily_load(days: int) -> dict[str, dict[str, float]]:
    """{iso day: {sport: load}} from the synced activities, `days` back."""
    import db
    oldest = (clock.today() - timedelta(days=days)).isoformat()
    rows = db.get_db().execute(
        "SELECT date, sport, tss FROM activities WHERE date >= ? AND tss IS NOT NULL",
        (oldest,)).fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        day = out.setdefault(r["date"], {})
        s = sport_of(r["sport"])
        day[s] = day.get(s, 0.0) + float(r["tss"])
    return out


def load_state(days: int = 90) -> dict:
    """Per-sport and combined CTL/ATL/TSB as of today, from the last `days` of
    synced activities (the sync window; a rider with a longer history than that
    reads low until the window fills). {sport|"combined": {ctl, atl, tsb}}."""
    daily = _daily_load(days)
    ctl = {s: 0.0 for s in SPORTS}
    atl = {s: 0.0 for s in SPORTS}
    d, today = clock.today() - timedelta(days=days), clock.today()
    while d <= today:
        day = daily.get(d.isoformat(), {})
        for s in SPORTS:
            x = day.get(s, 0.0)
            ctl[s] += (x - ctl[s]) / CTL_TAU
            atl[s] += (x - atl[s]) / ATL_TAU
        d += timedelta(days=1)

    def _row(c: float, a: float) -> dict:
        return {"ctl": round(c, 1), "atl": round(a, 1), "tsb": round(c - a, 1)}

    out = {s: _row(ctl[s], atl[s]) for s in SPORTS}
    out["combined"] = _row(sum(ctl.values()), sum(atl.values()))
    return out
