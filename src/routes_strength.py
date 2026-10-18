"""Strength and mobility session library (#127): the templates the plan places as companion sessions
(sessions_strength.py), with exercise lists, sets, reps or holds, effort words and cues. Read-only."""
from fastapi import APIRouter, HTTPException, Query

import api_models
import sessions_strength as ss

router = APIRouter()


@router.get("/api/strength/sessions", responses={200: {"model": api_models.StrengthSessions}})
def strength_sessions(stage: str = Query(ss.DEFAULT_STAGE, description="novice | progressing | experienced")):
    """Every strength / mobility template built at ``stage`` (sets, reps and effort change with it)."""
    if stage not in ss.STAGE:
        raise HTTPException(status_code=400, detail=f"stage must be one of {', '.join(ss.STAGE)}")
    return {
        "stage": stage,
        "stages": [{"id": s.id, "label": s.label, "sets": list(s.sets), "reps": list(s.reps), "rpe": list(s.rpe),
                    "effort": s.effort, "rest": s.rest, "pct_1rm": s.pct_1rm, "source": s.source,
                    "verify": s.verify} for s in ss.STAGES],
        "sessions": [ss.build_session(p.id, stage) for p in ss.PLANS],
        "disclaimer": ss.DISCLAIMER, "not_validated": ss.NOT_VALIDATED,
        "load_note": ss.LOAD_NOTE, "load_method": ss.LOAD_METHOD,
        "sources": [ss.ACSM_2009, ss.ACSM_2011, ss.FOSTER_2001],
    }
