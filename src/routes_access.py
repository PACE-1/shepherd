"""Sign out everywhere (#152). Behind the access gate like every other route."""
from fastapi import APIRouter

import access

router = APIRouter()


@router.post("/api/logout-everywhere")
def logout_everywhere():
    access.revoke_all_sessions()
    return {"ok": True}
