"""Smoke route for the routes_*.py loader (see app._include_route_modules)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/_routes_loaded")
def routes_loaded():
    return {"ok": True}
