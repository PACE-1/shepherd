"""Folder import (#31 Phase 1): the rider's FIT folder and the Scan now button. Logic lives in folder_import.py."""
from fastapi import APIRouter, HTTPException

import api_models
import folder_import

router = APIRouter()


def _active():
    from profile_manager import ProfileManager
    pm = ProfileManager.get()
    if not pm.active_id:
        raise HTTPException(status_code=409, detail="No profile is active.")
    return pm.active_dir, pm.active_id


@router.get("/api/folder-import", responses={200: {"model": api_models.FolderImportState}})
def folder_import_state():
    pd, pid = _active()
    return folder_import.public(pd, pid)


@router.put("/api/folder-import", responses={200: {"model": api_models.FolderImportState}})
def folder_import_save(body: dict):
    """``folder`` "" removes it; omitted keeps it. The folder must exist and be readable on the server."""
    pd, pid = _active()
    folder = body.get("folder")
    recursive = body.get("recursive")
    if (folder is not None and not isinstance(folder, str)) or (recursive is not None and not isinstance(recursive, bool)):
        raise HTTPException(status_code=400, detail="folder must be text and recursive true or false.")
    try:
        folder_import.save(pd, folder, recursive)
    except folder_import.FolderImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return folder_import.public(pd, pid)


@router.post("/api/folder-import/scan", responses={200: {"model": api_models.FolderImportStarted}})
def folder_import_scan():
    """Start a scan in a worker thread; poll GET /api/folder-import for ``running`` and ``last_scan``."""
    pd, pid = _active()
    if not folder_import.load(pd)["folder"]:
        raise HTTPException(status_code=409, detail="Set a folder first.")
    started = folder_import.start_scan(pd, pid)
    return {"started": started, "running": True}
