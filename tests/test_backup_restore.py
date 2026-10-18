"""#19 — consistent backup, verified restore, and no silent downgrade."""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import backup

SRC = Path(__file__).resolve().parent.parent / "src"


def _make_home(root: Path) -> Path:
    home = root / "home"
    prof = home / "profiles" / "default"
    for d in (prof / "plans", prof / "rides" / "icu", home / "logs", home / "cache"):
        d.mkdir(parents=True)
    (home / "profiles.json").write_text(json.dumps({"active": "default"}))
    (prof / "athlete.json").write_text(json.dumps({"ftp": 251}))
    (prof / ".env").write_text("ICU_ACCESS_TOKEN=secret\n")
    (prof / "plans" / "current_plan.json").write_text(json.dumps({"weeks": []}))
    (prof / "rides" / "2026-10-01T07-00-00.fit").write_bytes(b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT" + b"x" * 40)
    (prof / "rides" / "icu" / "123.json").write_text(json.dumps({"external_id": "123"}))
    (home / "logs" / "app.log").write_text("noise")
    (home / "cache" / "x.json").write_text("{}")
    (prof / "athlete.json.tmp").write_text("partial")
    (home / "update_check_cache.json").write_text("{}")
    return home


def _db_with_wal(home: Path):
    """A WAL database whose newest rows live only in the -wal file."""
    path = home / "profiles" / "default" / "health_tracker.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE wellness (date TEXT PRIMARY KEY, hrv REAL)")
    conn.execute("INSERT INTO wellness VALUES ('2026-10-01', 52.5)")
    conn.commit()
    assert (path.parent / "health_tracker.db-wal").stat().st_size > 0
    return conn, path          # keep open: the rows are in the WAL, not the main file


def _files(home: Path) -> dict:
    return {p.relative_to(home).as_posix(): p.read_bytes() for p in sorted(home.rglob("*"))
            if p.is_file() and p.suffix not in (".db",) and not p.name.endswith(("-wal", "-shm"))
            and p.name != backup.MARKER}


def test_round_trip_includes_wal_content_and_leaves_out_noise(tmp_path):
    home = _make_home(tmp_path)
    conn, dbpath = _db_with_wal(home)
    archive = tmp_path / "b.tar.gz"
    manifest = backup.create_backup(home, archive)
    conn.close()
    names = {f["path"] for f in manifest["files"]}
    assert "profiles/default/health_tracker.db" in names
    assert not any(n.startswith(("logs/", "cache/")) or n.endswith((".tmp", "-wal", "-shm"))
                   or n == "update_check_cache.json" for n in names)

    target = tmp_path / "restored"
    backup.restore_backup(archive, target)
    got = sqlite3.connect(target / "profiles" / "default" / "health_tracker.db")
    assert got.execute("SELECT hrv FROM wellness WHERE date='2026-10-01'").fetchone() == (52.5,)
    got.close()
    want = {k: v for k, v in _files(home).items()
            if not k.startswith(("logs/", "cache/")) and not k.endswith(".tmp") and k != "update_check_cache.json"}
    assert _files(target) == want
    assert backup.read_data_format(target) == backup.DATA_FORMAT
    assert (target / "profiles" / "default" / ".env").read_text() == "ICU_ACCESS_TOKEN=secret\n"


def test_verify_detects_a_changed_file(tmp_path):
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(archive) as src, tarfile.open(bad, "w:gz") as out:
        for m in src.getmembers():
            data = src.extractfile(m).read()
            if m.name.endswith("athlete.json"):
                data = b'{"ftp": 999}'
            m.size = len(data)
            out.addfile(m, io.BytesIO(data))
    with pytest.raises(backup.BackupError, match="checksum mismatch"):
        backup.verify_backup(bad)
    target = tmp_path / "t"
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad, target)
    assert not target.exists()


def test_restore_refuses_a_non_empty_home_unless_forced(tmp_path):
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    other = tmp_path / "other"
    other.mkdir()
    (other / "keep.txt").write_text("mine")
    with pytest.raises(backup.BackupError, match="not empty"):
        backup.restore_backup(archive, other)
    assert (other / "keep.txt").read_text() == "mine"
    backup.restore_backup(archive, other, force=True)
    assert not (other / "keep.txt").exists()
    assert (other / "profiles.json").is_file()
    assert sorted(x.name for x in other.iterdir() if x.name.startswith(".restore")) == []


def test_interrupted_restore_leaves_the_existing_home_untouched(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    target = tmp_path / "live"
    target.mkdir()
    (target / "keep.txt").write_text("mine")
    calls = {"n": 0}
    real = backup.shutil.copyfileobj

    def flaky(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(backup.shutil, "copyfileobj", flaky)
    with pytest.raises(OSError):
        backup.restore_backup(archive, target, force=True)
    assert (target / "keep.txt").read_text() == "mine"
    assert sorted(x.name for x in target.iterdir()) == ["keep.txt"]


def test_restore_into_a_mount_point_that_cannot_be_renamed(tmp_path, monkeypatch):
    """A Docker volume is a mount point: os.replace(home, ...) fails with EBUSY."""
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    mount = tmp_path / "data"
    mount.mkdir()
    real = os.replace

    def busy(src, dst, *a, **k):
        if Path(src) == mount or Path(dst) == mount:
            raise OSError(16, "Device or resource busy")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(backup.os, "replace", busy)
    backup.restore_backup(archive, mount)
    assert (mount / "profiles.json").is_file() and not list(mount.glob(".restore*"))


def test_failure_while_moving_in_rolls_the_old_data_back(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    live = tmp_path / "live"
    live.mkdir()
    (live / "a.txt").write_text("A")
    (live / "b.txt").write_text("B")
    real = os.replace
    state = {"new": 0}

    def flaky(src, dst, *a, **k):
        if ".restore-new-" in str(src):
            state["new"] += 1
            if state["new"] == 2:
                raise OSError("boom")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(backup.os, "replace", flaky)
    with pytest.raises(OSError):
        backup.restore_backup(archive, live, force=True)
    assert sorted(x.name for x in live.iterdir()) == ["a.txt", "b.txt"]
    assert (live / "a.txt").read_text() == "A"


def test_a_backup_from_a_newer_data_format_is_refused(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    archive = tmp_path / "b.tar.gz"
    backup.create_backup(home, archive)
    monkeypatch.setattr(backup, "DATA_FORMAT", 0)        # pretend this build is older
    with pytest.raises(backup.BackupError, match="data format"):
        backup.restore_backup(archive, tmp_path / "t")


def test_startup_guard_refuses_newer_data_and_stamps_new_data(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    backup.check_data_format(home)
    assert backup.read_data_format(home) == backup.DATA_FORMAT
    (home / backup.MARKER).write_text("99\n")
    with pytest.raises(backup.BackupError, match="newer data|could damage"):
        backup.check_data_format(home)


def test_app_refuses_to_start_on_newer_data(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    home = tmp_path / "h"
    home.mkdir()
    (home / backup.MARKER).write_text("99\n")
    monkeypatch.setenv("SHEPHERD_HOME", str(home))
    with pytest.raises(backup.BackupError):
        with TestClient(app_module.app):
            pass


def test_archive_with_a_path_traversal_entry_is_rejected(tmp_path):
    evil = tmp_path / "evil.tar.gz"
    manifest = json.dumps({"format": 1, "data_format": 1, "files": []}).encode()
    with tarfile.open(evil, "w:gz") as tar:
        for name, data in ((backup.MANIFEST, manifest), ("data/../../escape.txt", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(backup.BackupError, match="unexpected entry"):
        backup.verify_backup(evil)


def test_cli_create_verify_restore(tmp_path):
    home = _make_home(tmp_path)
    env = dict(os.environ, PYTHONPATH=str(SRC), HOME=str(tmp_path))
    run = lambda *a: subprocess.run([sys.executable, "-m", "backup", *a], env=env,
                                    capture_output=True, text=True, cwd=str(SRC))
    arch = str(tmp_path / "c.tar.gz")
    assert run("create", arch, "--home", str(home)).returncode == 0
    assert run("verify", arch).returncode == 0
    out = run("restore", arch, "--home", str(tmp_path / "new"))
    assert out.returncode == 0 and "restore: ok" in out.stdout
    again = run("restore", arch, "--home", str(tmp_path / "new"))
    assert again.returncode == 1 and "not empty" in again.stderr


def test_a_backup_without_secrets_leaves_out_credentials_but_keeps_the_rest(tmp_path):
    import tarfile
    import backup
    home = tmp_path / "home"
    prof = home / "profiles" / "default"
    prof.mkdir(parents=True)
    (prof / ".env").write_text("ICU_API_KEY=secret")
    (prof / "llm.json").write_text('{"api_key": "sk-secret"}')
    (prof / "garmin").mkdir()
    (prof / "garmin" / "garmin_tokens.json").write_text('{"di_token": "secret"}')
    (prof / "athlete.json").write_text("{}")
    m = backup.create_backup(home, tmp_path / "b.tar.gz", exclude_secrets=True)
    assert m["secrets_excluded"] is True
    assert [f["path"] for f in m["files"]] == ["profiles/default/athlete.json"]
    with tarfile.open(tmp_path / "b.tar.gz") as t:
        assert not any(n.endswith((".env", "llm.json", "garmin_tokens.json")) for n in t.getnames())
    assert {f["path"] for f in backup.create_backup(home, tmp_path / "c.tar.gz")["files"]} >= {"profiles/default/.env", "profiles/default/llm.json"}
