"""Analytics: weight trend and W/kg (#114), power-duration model (#114), ride comparison (#116)."""
import json
from datetime import timedelta

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

import api_models
import clock
import cp_model
import db
import ride_compare
import weight_trend as wt

router = APIRouter()

WARMUP_DAYS = 60  # readings before the window start the trend, so its first days are not just one reading


def _synced_weights(days: int) -> list[dict]:
    from ride_storage import wellness_value
    oldest = (clock.today() - timedelta(days=days)).isoformat()
    out = []
    for d, raw in db.get_db().execute("SELECT date, raw_json FROM wellness WHERE date >= ?", (oldest,)).fetchall():
        try:
            v = wellness_value("weight", (json.loads(raw or "{}") or {}).get("weight"))
        except (ValueError, TypeError, AttributeError):
            continue
        if v is not None:
            out.append({"date": d, "value": v, "source": "intervals.icu"})
    return out


def _ftp_rows() -> list[dict]:
    """Every FTP on record: values saved in Settings, then the applied FTP ledger (wins on the same date)."""
    from profile_manager import ProfileManager
    rows = [{"date": r["date"], "ftp": r["value"]} for r in db.query_metric_history("ftp", days=36500)]
    rows += [{"date": e.get("date"), "ftp": e.get("ftp")} for e in ProfileManager.get().ftp_test_history if e.get("applied")]
    return rows


@router.get("/api/analytics/weight-trend", responses={200: {"model": api_models.WeightTrend}})
def weight_trend(days: int = Query(365, ge=7, le=3650)):
    """Body weight (typed in and synced) with a 7-day exponential trend, and W/kg from FTP over the trend weight."""
    span = days + WARMUP_DAYS
    readings = wt.merge_readings(db.query_metric_history("weight", days=span), _synced_weights(span))
    trend = wt.ewma_trend(readings)
    start = (clock.today() - timedelta(days=days)).isoformat()
    wkg = [r for r in wt.wkg_history(trend, _ftp_rows()) if r["date"] >= start]
    return {
        "method": wt.METHOD,
        "tau_days": wt.TAU_DAYS,
        "points": [r for r in trend if r["date"] >= start],
        "latest_trend_kg": trend[-1]["trend_kg"] if trend else None,
        "change_28d_kg": wt.change_over(trend, 28, clock.today()),
        "wkg": wkg,
        "latest_w_per_kg": wkg[-1]["w_per_kg"] if wkg else None,
    }


@router.get("/api/analytics/power-model", responses={200: {"model": api_models.PowerModel}})
def power_model(window_days: int = Query(90, ge=28, le=365)):
    """Critical power and W' fitted to your best 3-20 min efforts, with a 95% interval, plus monthly history."""
    import power_curve
    from profile_manager import ProfileManager
    curve = power_curve.aggregate_power_curve(window_days=window_days)
    fit = cp_model.fit_cp({p["duration_s"]: p["watts"] for p in curve["rider_curve"]})
    ftp, weight = power_curve._profile_ftp_weight()
    try:
        max_hr = int(ProfileManager.get().max_hr) or None
    except Exception:
        max_hr = None
    span = 365 + WARMUP_DAYS
    trend = wt.ewma_trend(wt.merge_readings(db.query_metric_history("weight", days=span), _synced_weights(span)))
    hist = cp_model.history(power_curve._load_cached_rides(), clock.today(),
                            {"ftp": ftp, "weight_kg": weight, "max_hr": max_hr}, months=12, window_days=window_days,
                            weight_at=lambda day: wt._at([(r["date"], r["trend_kg"]) for r in trend], day))
    return {
        "window_days": window_days,
        "n_rides": curve["n_rides"],
        "method": cp_model.METHOD,
        "caveat": cp_model.CAVEAT,
        "fit": fit,
        "pmax_w": curve["pmax_w"],
        "weight_kg": weight,
        "cp_w_per_kg": round(fit["cp_w"] / weight, 2) if fit["cp_w"] and weight else None,
        "history": hist,
    }


def _load_ride(ride_id: str):
    import app as _app  # the ride-detail loader (ICU, FIT and legacy rides), loaded lazily: app imports this module
    rec = _app.api_ride_full_detail(ride_id, include="samples")
    return None if isinstance(rec, JSONResponse) else rec


@router.get("/api/analytics/compare", responses={200: {"model": api_models.RideCompare}})
def compare(a: str = Query(...), b: str = Query(...),
            a_start: int | None = Query(None, ge=0), a_end: int | None = Query(None, ge=1),
            b_start: int | None = Query(None, ge=0), b_end: int | None = Query(None, ge=1)):
    """Two rides, or two efforts (start/end seconds), side by side: summaries, overlaid power and HR, best-effort differences."""
    from profile_manager import ProfileManager
    sides = []
    for rid, lo, hi in ((a, a_start, a_end), (b, b_start, b_end)):
        if lo is not None and hi is not None and hi <= lo:
            return JSONResponse({"error": "An effort must end after it starts."}, 400)
        rec = _load_ride(rid)
        if rec is None:
            return JSONResponse({"error": f"Ride {rid} not found"}, 404)
        s = ride_compare.side(rec, lo, hi, rec.get("ftp_at_ride") or ProfileManager.get().ftp)
        if not any(s["_power"]) and not any(h for h in s["_hr"] if h):
            return JSONResponse({"error": f"{s['name']} has no power or heart-rate samples to compare."}, 422)
        sides.append(s)
    return ride_compare.compare(*sides)
