"""Race predictor endpoint (#121). The models and their sources live in race_predictor.

Inputs: runs from the activities table (distance and moving time; no streams are stored
for runs) in the last eight weeks, and the critical-speed test last saved from Run zones.
"""
from __future__ import annotations

import json

from fastapi import APIRouter

import api_models
import db
import multisport
import race_predictor as rp
import routes_run

router = APIRouter()

WINDOW_DAYS = 56  # eight weeks


def _saved_cs() -> dict | None:
    try:
        cs = json.loads(routes_run._cs_path().read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(cs, dict):
        return None
    vals = (cs.get("cs_m_per_s"), cs.get("d_prime_m"))
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in vals):
        return None
    return {"cs_m_per_s": float(vals[0]), "d_prime_m": float(vals[1]), "date": cs.get("date") if isinstance(cs.get("date"), str) else None}


def _recent_runs() -> list[dict]:
    runs = []
    for a in db.query_activities(days=WINDOW_DAYS):
        kind = (a.get("sport") or "").replace(" ", "").replace("_", "").lower()
        if multisport.sport_of(a.get("sport")) != "running" or kind in routes_run._WALKS:
            continue
        km, dur = a.get("distance_km") or 0, a.get("duration_sec") or 0
        if km > 0 and dur > 0:
            runs.append({"id": str(a["id"]), "date": a.get("date"), "name": a.get("name") or "",
                         "distance_m": round(km * 1000, 1), "time_s": float(dur), "pace_s_per_km": round(dur / km, 1)})
    return runs


@router.get("/api/run/predict", responses={200: {"model": api_models.RacePredictor}})
def run_predict():
    """5K, 10K, half marathon and marathon from the best recent run (Riegel) and the saved critical speed."""
    cs = _saved_cs()
    return {"window_days": WINDOW_DAYS, "critical_speed": cs, **rp.predict(_recent_runs(), cs)}
