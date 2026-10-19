"""Restore a backup from the UI (#129): upload, verify and stage it; it is applied at the next start.

Replacing files under a running database is not safe, so the upload only stages a verified
archive (``backup.stage_restore``) and ``backup.apply_pending`` swaps it in at startup, before
anything opens the data.
"""
import tarfile

from fastapi import APIRouter, File, HTTPException, UploadFile

import api_models
import backup
from user_home import shepherd_home

router = APIRouter()

_MAX_BACKUP_BYTES = 4 * 1024 ** 3
_CHUNK = 1024 * 1024
_BAD_ARCHIVE = (backup.BackupError, tarfile.TarError, OSError, EOFError, ValueError, KeyError)


def _summary(manifest: dict) -> dict:
    return {"pending": True, "files": len(manifest.get("files", [])), "data_format": manifest.get("data_format"),
            "app_version": manifest.get("app_version") or "", "created_at": manifest.get("created_at") or "",
            "secrets_excluded": bool(manifest.get("secrets_excluded"))}


@router.get("/api/import/backup", responses={200: {"model": api_models.BackupStaged}})
def api_backup_pending():
    """The staged restore waiting for a restart, or ``{"pending": false}``."""
    staged = shepherd_home() / backup.PENDING
    if not staged.is_file():
        return {"pending": False}
    try:
        return _summary(backup.verify_backup(staged))
    except _BAD_ARCHIVE:
        return {"pending": False}


@router.post("/api/import/backup", responses={200: {"model": api_models.BackupStaged}})
async def api_backup_stage(file: UploadFile = File(...)):
    """Check a backup archive and stage it. Nothing changes until Shepherd restarts."""
    home = shepherd_home()
    part = home / (backup.PENDING + ".part")
    size = 0
    try:
        with part.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > _MAX_BACKUP_BYTES:
                    raise HTTPException(status_code=413, detail="Backup too large (>4 GB).")
                out.write(chunk)
        try:
            return _summary(backup.stage_restore(home, part))
        except _BAD_ARCHIVE as e:
            raise HTTPException(status_code=400, detail=f"That file is not a usable Shepherd backup: {e}")
    finally:
        part.unlink(missing_ok=True)


@router.delete("/api/import/backup", responses={200: {"model": api_models.BackupStaged}})
def api_backup_cancel():
    (shepherd_home() / backup.PENDING).unlink(missing_ok=True)
    return {"pending": False}
