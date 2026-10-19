"""#154 - one server process per data directory."""
import subprocess
import sys
import textwrap

import pytest

import datalock

SRC = __import__("pathlib").Path(datalock.__file__).parent


def _try_second_process(home):
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(SRC)!r})
        import datalock
        try:
            datalock.acquire({str(home)!r})
        except RuntimeError as e:
            print(e); sys.exit(3)
    """)
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)


def test_a_second_process_on_the_same_home_exits_with_a_message(tmp_path):
    datalock.acquire(tmp_path)
    try:
        r = _try_second_process(tmp_path)
        assert r.returncode == 3 and "already using the data folder" in r.stdout
        datalock.acquire(tmp_path)          # the first holder keeps it and may re-enter
    finally:
        datalock.release(tmp_path)


def test_the_lock_is_free_again_after_release(tmp_path):
    datalock.acquire(tmp_path)
    datalock.release(tmp_path)
    assert _try_second_process(tmp_path).returncode == 0


def test_another_home_is_not_blocked(tmp_path):
    datalock.acquire(tmp_path / "a")
    try:
        assert _try_second_process(tmp_path / "b").returncode == 0
    finally:
        datalock.release(tmp_path / "a")


def test_app_startup_refuses_a_held_home(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    monkeypatch.setenv("SHEPHERD_HOME", str(tmp_path))
    datalock.acquire(tmp_path)
    datalock.release(tmp_path)               # in-process re-entry would hide a real conflict
    import fcntl, os
    fd = os.open(tmp_path / ".lock", os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)   # "another process" = a separate open file
    try:
        with pytest.raises(RuntimeError, match="already using the data folder"):
            with TestClient(app_module.app):
                pass
    finally:
        os.close(fd)
