"""Swim session library (sessions_swim.py): the templates with their set text for the rider's saved CSS,
and a plain-text download of one. No FIT / watch file is made for swims (sessions_swim.NO_FIT)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import api_models
import sessions_swim as ss
from routes_swim import _css

router = APIRouter()
NOT_VALIDATED = "Not validated against real recorded swims yet."


def _thresholds() -> dict:
    return {"swim_css": _css()}


@router.get("/api/swim/sessions", responses={200: {"model": api_models.SwimSessions}})
def swim_sessions():
    """Every swim template written out for the rider's CSS (effort labels and metres when none is saved)."""
    th = _thresholds()
    sessions = []
    for t in ss.library():
        m = ss.typical_minutes(t)
        w = t.builder(th, m)
        sessions.append({"id": t.id, "name": w["name"], "kind": t.kind, "session_type": t.session_type,
                         "intent": t.intent, "hard": t.hard, "minutes": m, "minutes_min": t.minutes[0],
                         "minutes_max": t.minutes[1], "lines": w["description"].split("\n"), "note": w["note"]})
    css = ss.css_of(th)
    return {"css_s_per_100m": css, "has_css": css is not None, "pool_m": ss.POOL_M, "source": ss.SOURCE,
            "not_validated": NOT_VALIDATED, "download_note": ss.NO_FIT, "sessions": sessions}


@router.get("/api/swim/sessions/{session_id}/text", response_class=PlainTextResponse)
def swim_session_text(session_id: str):
    """One session as a plain-text file (attachment)."""
    t = next((t for t in ss.library() if t.id == session_id), None)
    if t is None:
        raise HTTPException(status_code=404, detail="No such swim session")
    return PlainTextResponse(ss.session_text(t, _thresholds()),
                             headers={"Content-Disposition": f'attachment; filename="{t.id}.txt"'})
