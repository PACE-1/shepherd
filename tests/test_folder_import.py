"""#31 Phase 1: the folder importer.

The rider's own folder of .fit files, scanned through the upload endpoint's
import code. Duplicates of stored rides are skipped (start within 60 s, length
within 5 %), source files are never touched, a corrupt file does not stop the
scan, and only regular files directly in the folder are read unless the rider
asks for subfolders (symlinks never followed).

The FIT-reading tests use the e2e fixture web/e2e/fixtures/ride.fit (a 300 s
ride starting at unix time 1750000000), since fit_tool is what the repo reads
FIT files with.
"""
import json
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
import folder_import as fi
import ride_storage
import training

FIXTURE = Path(__file__).resolve().parent.parent / "web" / "e2e" / "fixtures" / "ride.fit"
FIX_START = datetime.fromtimestamp(1750000000)      # local wall time, as the importer reads it
FIX_LEN = 300


# ── the folder ──────────────────────────────────────────────────────────────

def test_the_folder_must_be_a_full_path_to_a_readable_folder(tmp_path):
    assert fi.validate_folder("") == ""
    assert fi.validate_folder(str(tmp_path)) == str(tmp_path)
    with pytest.raises(fi.FolderImportError, match="full path"):
        fi.validate_folder("relative/FIT")
    with pytest.raises(fi.FolderImportError, match="mounted volume"):
        fi.validate_folder(str(tmp_path / "missing"))
    (tmp_path / "a.fit").write_bytes(b"x")
    with pytest.raises(fi.FolderImportError, match="does not exist"):
        fi.validate_folder(str(tmp_path / "a.fit"))


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_an_unreadable_folder_is_refused(tmp_path):
    d = tmp_path / "locked"
    d.mkdir(mode=0o000)
    try:
        with pytest.raises(fi.FolderImportError, match="cannot read"):
            fi.validate_folder(str(d))
    finally:
        d.chmod(0o755)


def test_only_regular_fit_files_directly_in_the_folder(tmp_path):
    (tmp_path / "a.fit").write_bytes(b"a")
    (tmp_path / "B.FIT").write_bytes(b"b")
    (tmp_path / "notes.txt").write_bytes(b"n")
    (tmp_path / "._a.fit").write_bytes(b"mac resource fork")
    (tmp_path / "dir.fit").mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.fit").write_bytes(b"c")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.fit").write_bytes(b"s")
    (tmp_path / "link.fit").symlink_to(outside / "secret.fit")
    (tmp_path / "linkdir").symlink_to(outside, target_is_directory=True)

    names = sorted(p.name for p in fi.candidates(tmp_path, recursive=False))
    assert names == ["B.FIT", "a.fit"]
    deep = sorted(p.relative_to(tmp_path).as_posix() for p in fi.candidates(tmp_path, recursive=True))
    assert deep == ["B.FIT", "a.fit", "sub/c.fit"]      # no symlinked file, no symlinked folder


# ── duplicates ──────────────────────────────────────────────────────────────

T0 = datetime(2026, 10, 17, 8, 0, 0)
STORED = [(T0, [3600])]


def test_a_ride_starting_within_60_s_with_the_same_length_is_a_duplicate():
    assert fi.is_duplicate(T0 + timedelta(seconds=59), 3600, STORED)
    assert fi.is_duplicate(T0 - timedelta(seconds=60), 3600 + 170, STORED)      # 4.7 % longer


def test_near_misses_are_not_duplicates():
    assert not fi.is_duplicate(T0 + timedelta(seconds=61), 3600, STORED)        # started 61 s apart
    assert not fi.is_duplicate(T0, 3600 + 200, STORED)                           # 5.3 % longer
    assert not fi.is_duplicate(T0, 3600 - 200, STORED)


def test_either_stored_length_counts_elapsed_or_moving():
    """intervals.icu stores elapsed and moving time; a FIT's timer is close to moving."""
    assert fi.is_duplicate(T0, 3300, [(T0, [3900, 3290])])


# ── the scan, with fakes ────────────────────────────────────────────────────

def _fake_reader(starts):
    def read(p):
        if p.name.startswith("bad"):
            raise ValueError("could not read this FIT file")
        return starts[p.name], 3600
    return read


def test_the_scan_counts_caps_and_survives_a_corrupt_file(tmp_path, monkeypatch):
    folder = tmp_path / "fit"
    folder.mkdir()
    pd = tmp_path / "profile"
    pd.mkdir()
    names = ["a.fit", "b.fit", "bad.fit", "c.fit"]
    for i, n in enumerate(names):
        (folder / n).write_bytes(b"x" * (i + 1))
        os.utime(folder / n, (time.time() - 100 * i, time.time() - 100 * i))   # a newest
    starts = {n: T0 + timedelta(hours=i) for i, n in enumerate(names)}
    monkeypatch.setattr(fi, "_read_fit", _fake_reader(starts))
    monkeypatch.setattr(fi, "existing_rides", lambda: [(starts["b.fit"] + timedelta(seconds=30), [3600])])
    monkeypatch.setattr(fi, "MAX_FILES_PER_SCAN", 3)
    imported = []
    fi.save(pd, str(folder), None)

    res = fi.scan(pd, import_fn=lambda p: imported.append(p.name) or f"r-{p.name}")
    assert (res["imported"], res["duplicate"], res["failed"], res["remaining"]) == (1, 1, 1, 1)
    assert imported == ["a.fit"]
    assert res["failures"] == [{"file": "bad.fit", "reason": "could not read this FIT file"}]

    res = fi.scan(pd, import_fn=lambda p: imported.append(p.name) or f"r-{p.name}")
    # a and b were handled; the corrupt file is tried again; c was waiting
    assert (res["imported"], res["already_imported"], res["failed"], res["remaining"]) == (1, 2, 1, 0)
    assert imported == ["a.fit", "c.fit"]
    assert fi.load(pd)["last_scan"]["imported"] == 1


def test_a_profile_switch_stops_the_scan(tmp_path, monkeypatch):
    (tmp_path / "a.fit").write_bytes(b"a")
    pd = tmp_path / "p"
    pd.mkdir()
    fi.save(pd, str(tmp_path), None)
    monkeypatch.setattr(fi, "_read_fit", lambda p: (T0, 3600))
    monkeypatch.setattr(fi, "existing_rides", lambda: [])
    res = fi.scan(pd, import_fn=lambda p: pytest.fail("imported after the switch"), still_active=lambda: False)
    assert res["aborted"] is True and res["imported"] == 0


def test_a_folder_that_disappears_is_reported_not_raised(tmp_path):
    folder = tmp_path / "gone"
    folder.mkdir()
    fi.save(tmp_path, str(folder), None)
    folder.rmdir()
    res = fi.scan(tmp_path)
    assert "does not exist" in res["error"]


# ── the scan, for real: the upload endpoint's import code ───────────────────

@pytest.fixture
def c(monkeypatch):
    monkeypatch.setattr(training, "upload_fit_to_icu", lambda p, retry=1: {"ok": False, "status": 0, "detail": "no_credentials"})
    with TestClient(app_module.app) as client:
        yield client


def _icu_ride(start: datetime, seconds: int):
    d = ride_storage._icu_rides_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "i31.json").write_text(json.dumps({"ride_id": "icu_i31", "source": "icu", "external_id": "i31",
                                            "sport": "Ride", "started_at": start.isoformat(),
                                            "duration_s": seconds}))


def _folder(tmp_path):
    folder = tmp_path / "fit"
    folder.mkdir()
    shutil.copy(FIXTURE, folder / "ride.fit")
    (folder / "broken.fit").write_bytes(b"\x0e\x10not a fit file at all" * 4)
    return folder


def _fits():
    return sorted(ride_storage._fit_rides_dir().glob("*.fit"))


@pytest.fixture
def clean_rides():
    d = ride_storage._icu_rides_dir()
    before = set(_fits())
    yield
    (d / "i31.json").unlink(missing_ok=True)
    for f in set(_fits()) - before:
        f.unlink(missing_ok=True)
        f.with_name(f"{f.stem}.load.json").unlink(missing_ok=True)
    app_module.clear_cache()


def _run(c, folder):
    assert c.put("/api/folder-import", json={"folder": str(folder), "recursive": False}).status_code == 200
    assert c.post("/api/folder-import/scan").json()["running"] is True
    for _ in range(300):
        s = c.get("/api/folder-import").json()
        if not s["running"] and s["last_scan"]:
            return s["last_scan"]
        time.sleep(0.05)
    pytest.fail("scan did not finish")


def test_a_ride_intervals_icu_already_has_is_not_imported_again(c, tmp_path, clean_rides):
    folder = _folder(tmp_path)
    src = (folder / "ride.fit").read_bytes()
    mtime = (folder / "ride.fit").stat().st_mtime
    _icu_ride(FIX_START + timedelta(seconds=20), FIX_LEN + 5)
    before = _fits()

    scan = _run(c, folder)
    assert (scan["imported"], scan["duplicate"], scan["failed"]) == (0, 1, 1)
    assert scan["failures"][0]["file"] == "broken.fit"
    assert _fits() == before
    # the source folder is exactly as it was
    assert sorted(p.name for p in folder.iterdir()) == ["broken.fit", "ride.fit"]
    assert (folder / "ride.fit").read_bytes() == src and (folder / "ride.fit").stat().st_mtime == mtime


def test_a_near_miss_is_imported_through_the_upload_path_once(c, tmp_path, clean_rides):
    folder = _folder(tmp_path)
    _icu_ride(FIX_START + timedelta(seconds=90), FIX_LEN)        # a different ride 90 s later
    before = _fits()

    scan = _run(c, folder)
    assert (scan["imported"], scan["duplicate"], scan["failed"]) == (1, 0, 1)
    (new,) = set(_fits()) - set(before)
    assert new.read_bytes() == FIXTURE.read_bytes()
    assert (folder / "ride.fit").exists()

    again = _run(c, folder)
    assert (again["imported"], again["already_imported"]) == (0, 1)
    assert len(_fits()) == len(before) + 1


# ── contract ────────────────────────────────────────────────────────────────

def test_endpoints_validate_and_round_trip(c, tmp_path):
    s = c.get("/api/folder-import").json()
    assert s["max_files"] == 200 and s["running"] is False
    r = c.put("/api/folder-import", json={"folder": "not/absolute"})
    assert r.status_code == 400 and "full path" in r.json()["detail"]
    assert c.put("/api/folder-import", json={"folder": str(tmp_path / "nope")}).status_code == 400
    assert c.put("/api/folder-import", json={"recursive": "yes"}).status_code == 400
    s = c.put("/api/folder-import", json={"folder": str(tmp_path), "recursive": True}).json()
    assert s["folder"] == str(tmp_path) and s["recursive"] is True
    s = c.put("/api/folder-import", json={"folder": ""}).json()
    assert s["folder"] == ""
    assert c.post("/api/folder-import/scan").status_code == 409
