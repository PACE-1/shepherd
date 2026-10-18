"""Compare two rides, or two efforts (time ranges) of rides, side by side (#116).

Input is the normalized ride record the ride-detail endpoint returns with
``?include=samples`` (``samples`` = t_s, power_w, hr_bpm, possibly averaged
into buckets of a few seconds for long rides). Samples are expanded back to
one value per second so both sides share elapsed time from their own start.

A whole ride keeps the ride's own summary (duration, distance, NP, IF, TSS,
average HR). An effort is summarised from its samples: NP is the 30-s rolling
4th-power mean (``ride_storage.normalized_power``), IF = NP / FTP at the ride,
TSS from ``ride_storage.compute_power_tss``; distance is not in the samples, so
it is left empty. Best efforts use ``power_curve._extract_efforts_from_streams``
on the same per-second series; durations shorter than ten sample buckets are
left out because bucket averaging flattens short peaks.
"""
from __future__ import annotations

import math

from ride_storage import compute_power_tss, normalized_power

MAX_POINTS = 600


def _per_second(samples: dict, key: str) -> list:
    """The ``key`` stream as one value per second of elapsed time."""
    t = list(samples.get("t_s") or [])
    v = list(samples.get(key) or [])
    out: list = []
    for i, x in enumerate(v[:len(t)]):
        gap = (t[i + 1] - t[i]) if i + 1 < len(t) else ((t[i] - t[i - 1]) if i else 1)
        out.extend([x] * max(1, int(round(gap or 1))))
    return out


def sample_interval_s(samples: dict) -> int:
    t = list(samples.get("t_s") or [])
    return max(1, round((t[-1] - t[0]) / (len(t) - 1))) if len(t) > 1 else 1


def _mean(xs: list, positive_only: bool = False):
    vals = [float(x) for x in xs if x is not None and (x > 0 or not positive_only)]
    return sum(vals) / len(vals) if vals else None


def side(rec: dict, start_s: int | None, end_s: int | None, ftp: float | None) -> dict:
    """One side of the comparison: its summary and per-second power/HR."""
    samples = rec.get("samples") or {}
    power = [float(p or 0) for p in _per_second(samples, "power_w")]
    hr = _per_second(samples, "hr_bpm")
    whole = start_s is None and end_s is None
    lo = max(0, int(start_s or 0))
    hi = min(len(power), int(end_s)) if end_s is not None else len(power)
    power, hr = power[lo:hi], hr[lo:hi]
    if whole:
        summary = {k: rec.get(k) for k in ("duration_s", "distance_km", "np_w", "if_pct", "tss", "avg_hr", "avg_power_w")}
    else:
        np_w = normalized_power(power) if power else 0.0
        avg_hr = _mean(hr, positive_only=True)
        avg_p = _mean(power)
        summary = {
            "duration_s": len(power),
            "distance_km": None,
            "np_w": round(np_w) if np_w > 0 else None,
            "if_pct": round(100 * np_w / ftp, 1) if ftp and np_w > 0 else None,
            "tss": compute_power_tss(power, int(ftp)) if ftp and power else None,
            "avg_hr": round(avg_hr) if avg_hr else None,
            "avg_power_w": round(avg_p) if avg_p else None,
        }
    return {"ride_id": rec.get("ride_id"), "name": rec.get("name") or "Ride", "started_at": rec.get("started_at"),
            "whole": whole, "start_s": lo, "end_s": lo + len(power), "summary": summary,
            "_power": power, "_hr": hr, "_interval": sample_interval_s(samples)}


def _binned(xs: list, bin_s: int, positive_only: bool) -> list:
    out = []
    for i in range(0, len(xs), bin_s):
        m = _mean(xs[i:i + bin_s], positive_only)
        out.append(round(m) if m is not None else None)
    return out


def compare(a: dict, b: dict) -> dict:
    """Combine two ``side`` results: overlaid curves on one elapsed-time grid,
    summary differences (b - a) and best-effort differences."""
    from power_curve import _extract_efforts_from_streams
    longest = max(len(a["_power"]), len(b["_power"]), 1)
    bin_s = max(5, math.ceil(longest / MAX_POINTS))
    min_dur = 10 * max(a["_interval"], b["_interval"])
    ea = {e["secs"]: e["watts"] for e in _extract_efforts_from_streams({"watts": a["_power"]})}
    eb = {e["secs"]: e["watts"] for e in _extract_efforts_from_streams({"watts": b["_power"]})}
    best = [{"duration_s": d, "a_w": ea[d], "b_w": eb[d], "delta_w": eb[d] - ea[d]}
            for d in sorted(set(ea) & set(eb)) if d >= min_dur and ea[d] > 0 and eb[d] > 0]
    delta = {}
    for k in ("duration_s", "distance_km", "np_w", "if_pct", "tss", "avg_hr", "avg_power_w"):
        x, y = a["summary"].get(k), b["summary"].get(k)
        delta[k] = round(y - x, 1) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None
    out = {"bin_s": bin_s, "best_efforts": best, "delta": delta, "min_best_effort_s": min_dur}
    for name, s in (("a", a), ("b", b)):
        out[name] = {k: v for k, v in s.items() if not k.startswith("_")}
        out[name]["power_w"] = _binned(s["_power"], bin_s, False)
        out[name]["hr_bpm"] = _binned(s["_hr"], bin_s, True)
    return out
