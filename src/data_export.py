"""Open-file exports of what Shepherd stores (#129): CSV tables for spreadsheets and a backup archive without secrets."""
from __future__ import annotations

import csv
import io

_COLUMNS = {
    "activities": ["id", "date", "name", "sport", "duration_sec", "tss", "avg_power", "avg_hr", "distance_km", "kilojoules", "calories", "elevation_gain"],
    "wellness": ["date", "ctl", "atl", "hrv", "rhr", "sleep_secs", "sleep_score", "eftp"],
    "checkins": None,  # every column of daily_log
}


def tables() -> tuple[str, ...]:
    return tuple(_COLUMNS)


def _safe(v):
    # A text cell that starts like a formula would run in Excel or Sheets; a leading quote keeps it text.
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def to_csv(table: str, rows: list[dict]) -> str:
    """Rows as CSV. Raw provider payloads (raw_json) are left out; only the named columns are written."""
    if table not in _COLUMNS:
        raise ValueError(f"unknown table {table!r}")
    cols = _COLUMNS[table] or sorted({k for r in rows for k in r})
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows({k: _safe(v) for k, v in r.items()} for r in rows)
    return out.getvalue()
