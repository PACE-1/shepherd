"""Weekly sport balance (#124, actuals): hours and load by sport per week and month, the rider's target split
and limiter, and the gap. The planner does not read any of it (see sport_balance)."""
from fastapi import APIRouter, HTTPException, Query

import api_models
import clock
import db
import sport_balance as sb

router = APIRouter()


def _path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / sb.FILE_NAME


def _targets_out(stored: dict) -> dict:
    return {**stored, "has_targets": stored["targets"] is not None, "limiter_note": sb.LIMITER_NOTE}


@router.get("/api/balance", responses={200: {"model": api_models.Balance}})
def get_balance(weeks: int = Query(12, ge=1, le=104)):
    today = clock.today()
    stored = sb.read_targets(_path())
    acts = db.query_activities(days=(today - sb.window_start(today, weeks)).days)
    return {**sb.balance(acts, today, weeks, stored["targets"]), **_targets_out(stored)}


@router.put("/api/balance/targets", responses={200: {"model": api_models.BalanceTargets}})
def put_balance_targets(body: dict):
    """Both keys are required: ``targets`` ({sport: percent} summing to 100, or null/{} to clear) and
    ``limiter`` (cycling, running, swimming or null)."""
    if "targets" not in body or "limiter" not in body:
        raise HTTPException(status_code=400, detail="send both targets and limiter (null to clear)")
    try:
        return _targets_out(sb.save_targets(_path(), body["targets"], body["limiter"]))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
