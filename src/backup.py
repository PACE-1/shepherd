"""Consistent backup and restore of the Shepherd data directory (#19).

    python -m backup create  <archive.tar.gz> [--home DIR]
    python -m backup verify  <archive.tar.gz>
    python -m backup restore <archive.tar.gz> [--home DIR] [--force]

What a backup holds: everything under the data home (profile registry, each
profile's athlete.json, .env credentials, plans with their rotating backups,
imported FIT rides, intervals.icu ride and wellness envelopes, generated
workouts, settings) plus a consistent copy of every SQLite database.

SQLite: ``Connection.backup()`` reads a point-in-time snapshot through the
database engine, so committed WAL content is included and the ``-wal`` /
``-shm`` files are not copied. Everything else is copied as is; the app writes
user JSON atomically (atomic_io), so each file is whole. The archive is
therefore consistent per file and per database; for cross-file consistency stop
the app first (``docker stop``), or accept that a plan and the ride written a
millisecond apart may be one step out of sync.

Excluded on purpose: logs, caches, temp files (``*.tmp``, ``*.part``) and the
update-check cache. They are rebuilt and can be large or stale.

Restore refuses to overwrite a non-empty home without ``--force``, verifies
every checksum before touching the target, refuses an archive written by a newer
DATA FORMAT than this build understands, and stages into a sibling directory so
an interrupted restore never leaves a half-written home.

``DATA_FORMAT`` is the schema version of the data layout, deliberately separate
from the product version: the fork's release numbers do not have to follow
upstream's, and a lower product number must not read as a downgrade.
"""
from __future__ import annotations
import envcompat  # noqa: F401  (old DOMESTIQUE_* names -> SHEPHERD_*, before anything reads them)

import argparse
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DATA_FORMAT = 1
MARKER = ".data_format"
MANIFEST = "manifest.json"
PENDING = ".restore-pending.tar.gz"   # a verified archive staged from the UI, applied at the next start
_EXCLUDED_DIRS = {"logs", "cache", "__pycache__"}
_EXCLUDED_NAMES = {"update_check_cache.json"}
_SECRET_NAMES = {".env", "llm.json", "nutrition_sparkyfitness.json"}  # intervals.icu credentials, the AI provider and SparkyFitness keys
_EXCLUDED_SUFFIXES = (".tmp", ".part", "-wal", "-shm", ".lock")
_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
_KEEP_IN_PLACE = {".lock", PENDING, PENDING + ".part"}   # the data-folder lock and staged upload are not data


class BackupError(RuntimeError):
    pass


def _app_version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "unknown"


def _excluded(rel: Path) -> bool:
    if any(part in _EXCLUDED_DIRS for part in rel.parts[:-1]):
        return True
    return rel.name in _EXCLUDED_NAMES or rel.name.endswith(_EXCLUDED_SUFFIXES)


def _is_sqlite(path: Path) -> bool:
    if not path.name.endswith(_SQLITE_SUFFIXES):
        return False
    try:
        with path.open("rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _snapshot_sqlite(src: Path, dest: Path) -> None:
    """A consistent copy of ``src`` (WAL content included) at ``dest``."""
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_data_format(home: Path) -> int | None:
    try:
        return int((home / MARKER).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def check_data_format(home: Path) -> None:
    """Startup guard: refuse to run against data written by a newer layout, and
    stamp the marker on first use. Raises BackupError when the data is newer."""
    found = read_data_format(home)
    if found is not None and found > DATA_FORMAT:
        raise BackupError(
            f"the data in {home} uses format {found}; this build understands up to "
            f"{DATA_FORMAT}. Running it could damage newer data. Use a newer build, "
            "or restore a backup made by this one.")
    if found is None and home.is_dir():
        from atomic_io import write_text_atomic
        write_text_atomic(home / MARKER, f"{DATA_FORMAT}\n")


def create_backup(home: Path, archive: Path, *, exclude_secrets: bool = False) -> dict:
    home, archive = Path(home), Path(archive)
    if not home.is_dir():
        raise BackupError(f"data home not found: {home}")
    files: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="shepherd-backup-") as tmp:
        staging = Path(tmp)
        for path in sorted(home.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(home)
            if _excluded(rel) or rel.name == MARKER or (exclude_secrets and rel.name in _SECRET_NAMES):
                continue
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if _is_sqlite(path):
                _snapshot_sqlite(path, dest)
            else:
                shutil.copy2(path, dest)
            files.append({"path": rel.as_posix(), "size": dest.stat().st_size, "sha256": _sha256(dest)})
        manifest = {
            "format": 1,
            "data_format": read_data_format(home) or DATA_FORMAT,
            "app_version": _app_version(),
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "secrets_excluded": exclude_secrets,
            "files": files,
            "excluded": sorted(_EXCLUDED_DIRS) + sorted(_EXCLUDED_NAMES) + list(_EXCLUDED_SUFFIXES),
        }
        archive.parent.mkdir(parents=True, exist_ok=True)
        part = archive.with_name(archive.name + ".part")
        with tarfile.open(part, "w:gz") as tar:
            blob = json.dumps(manifest, indent=2).encode()
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
            for f in files:
                tar.add(staging / f["path"], arcname="data/" + f["path"], recursive=False)
        os.replace(part, archive)
    return manifest


def _read_manifest(tar: tarfile.TarFile) -> dict:
    try:
        member = tar.getmember(MANIFEST)
    except KeyError:
        raise BackupError("not a Shepherd backup (no manifest)")
    f = tar.extractfile(member)
    return json.loads(f.read().decode()) if f else {}


def _safe_member(name: str) -> bool:
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts


def verify_backup(archive: Path) -> dict:
    """Check the manifest and every file's checksum without extracting."""
    with tarfile.open(archive, "r:gz") as tar:
        manifest = _read_manifest(tar)
        listed = {f["path"]: f for f in manifest.get("files", [])}
        seen = set()
        for member in tar.getmembers():
            if member.name == MANIFEST:
                continue
            if not member.isfile() or not _safe_member(member.name) or not member.name.startswith("data/"):
                raise BackupError(f"unexpected entry in backup: {member.name}")
            rel = member.name[len("data/"):]
            entry = listed.get(rel)
            if entry is None:
                raise BackupError(f"file not in manifest: {rel}")
            h = hashlib.sha256()
            f = tar.extractfile(member)
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
            if h.hexdigest() != entry["sha256"]:
                raise BackupError(f"checksum mismatch: {rel}")
            seen.add(rel)
        missing = set(listed) - seen
        if missing:
            raise BackupError(f"files missing from backup: {sorted(missing)[:3]}")
    return manifest


def _extract(archive: Path, manifest: dict, stage: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == MANIFEST:
                continue
            dest = stage / member.name[len("data/"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as out:
                shutil.copyfileobj(tar.extractfile(member), out)
    (stage / MARKER).write_text(f"{manifest.get('data_format', DATA_FORMAT)}\n", encoding="utf-8")


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except OSError:
            pass


def _check_format(manifest: dict) -> None:
    if int(manifest.get("data_format", 1)) > DATA_FORMAT:
        raise BackupError(
            f"this backup uses data format {manifest['data_format']}; this build understands up to "
            f"{DATA_FORMAT}. Restoring it here could corrupt it.")


def _carry_over_secrets(old: Path, home: Path) -> None:
    """Copy the credential files of the replaced home back into the restored one (where its profile exists)."""
    for p in old.rglob("*"):
        if p.is_file() and p.name in _SECRET_NAMES:
            dest = home / p.relative_to(old)
            if dest.parent.is_dir() and not dest.exists():
                shutil.copy2(p, dest)


def stage_restore(home: Path, upload: Path) -> dict:
    """Verify ``upload`` and stage it for the next start (a running app cannot be restored in place)."""
    manifest = verify_backup(upload)
    _check_format(manifest)
    os.replace(upload, Path(home) / PENDING)
    return manifest


def apply_pending(home: Path) -> dict | None:
    """Startup, before anything opens the data: apply a staged restore. The staged file is removed either way."""
    pending = Path(home) / PENDING
    if not pending.is_file():
        return None
    try:
        return restore_backup(pending, home, force=True, keep_secrets=True)
    finally:
        pending.unlink(missing_ok=True)


def restore_backup(archive: Path, home: Path, *, force: bool = False, keep_secrets: bool = False) -> dict:
    """Restore ``archive`` into ``home``. A Docker volume is a mount point and
    cannot be renamed, so an existing home is never renamed: its entries are
    moved aside, the new ones moved in, and the old ones restored if anything
    fails part-way."""
    home = Path(home)
    manifest = verify_backup(archive)                  # nothing is touched until this passes
    _check_format(manifest)
    if home.exists() and not home.is_dir():
        raise BackupError(f"{home} exists and is not a directory")
    if not home.exists():
        home.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=home.name + ".restore-", dir=str(home.parent)))
        try:
            _extract(archive, manifest, stage)
            os.replace(stage, home)
        except BaseException:
            _remove(stage)
            raise
        return manifest
    existing = [p for p in home.iterdir() if p.name not in _KEEP_IN_PLACE]
    if existing and not force:
        raise BackupError(f"{home} is not empty; pass --force to replace its contents")
    stage = Path(tempfile.mkdtemp(prefix=".restore-new-", dir=str(home)))
    old = home / ".restore-old"
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        _extract(archive, manifest, stage)
        if existing:
            old.mkdir()
            for p in existing:
                os.replace(p, old / p.name)
                moved_old.append(p.name)
        for p in list(stage.iterdir()):
            os.replace(p, home / p.name)
            moved_new.append(p.name)
        if keep_secrets and manifest.get("secrets_excluded") and existing:
            _carry_over_secrets(old, home)   # a backup without keys must not wipe the ones in use
    except BaseException:
        for name in moved_new:
            _remove(home / name)
        for name in moved_old:
            os.replace(old / name, home / name)
        _remove(stage)
        _remove(old)
        raise
    _remove(stage)
    _remove(old)
    return manifest


def main(argv: list[str] | None = None) -> int:
    from user_home import shepherd_home
    ap = argparse.ArgumentParser(prog="backup", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("create", "verify", "restore"):
        p = sub.add_parser(name)
        p.add_argument("archive", type=Path)
        if name != "verify":
            p.add_argument("--home", type=Path, default=None, help="data directory (default: SHEPHERD_HOME or ~/.shepherd)")
        if name == "restore":
            p.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "verify":
            m = verify_backup(args.archive)
        else:
            home = args.home or shepherd_home()
            m = (create_backup(home, args.archive) if args.cmd == "create"
                 else restore_backup(args.archive, home, force=args.force))
    except (BackupError, tarfile.TarError, sqlite3.Error, OSError) as e:
        print(f"backup: {e}", file=sys.stderr)
        return 1
    print(f"{args.cmd}: ok ({len(m['files'])} files, data format {m['data_format']}, app {m['app_version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
