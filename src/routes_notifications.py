"""Notifications (#131): the in-app list, the settings, and a test send. Logic lives in notifications.py."""
from fastapi import APIRouter, HTTPException

import api_models
import notifications

router = APIRouter()


def _dir():
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    if not pm.active_id:
        raise HTTPException(status_code=409, detail="No profile is active.")
    return pm.active_dir


@router.get("/api/notifications", responses={200: {"model": api_models.NotificationList}})
def api_notifications():
    return notifications.listing(_dir())


@router.post("/api/notifications/read", responses={200: {"model": api_models.NotificationList}})
def api_notifications_read():
    return notifications.mark_all_read(_dir())


@router.get("/api/notifications/settings", responses={200: {"model": api_models.NotificationSettings}})
def api_notifications_settings():
    return notifications.public(notifications.load_settings(_dir()))


@router.put("/api/notifications/settings", responses={200: {"model": api_models.NotificationSettings}})
def api_notifications_save(body: dict):
    """``ntfy_url`` omitted keeps the stored URL; "" removes it. The URL is never sent back."""
    try:
        s = notifications.save_settings(_dir(), body.get("ntfy_url"), body.get("events"), body.get("readiness_time"))
    except notifications.NotificationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return notifications.public(s)


@router.post("/api/notifications/test", responses={200: {"model": api_models.NotificationTest}})
def api_notifications_test():
    """Send one test message to the stored URL (a sync route, so FastAPI runs it in a worker thread)."""
    url = notifications.load_settings(_dir())["ntfy_url"]
    if not url:
        return {"ok": False, "error": "Add an address first."}
    ok, why = notifications.post_ntfy(url, "Shepherd: test", "Notifications from Shepherd are working.")
    return {"ok": ok, "error": why}
