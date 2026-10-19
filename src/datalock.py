"""One server process per data directory (#154).

The app keeps per-process caches and has one sync owner, so two processes on one
SHEPHERD_HOME (``--workers 2``, a second container on the same volume, a restart
policy overlapping the old container) corrupt each other. Take an exclusive,
non-blocking flock on ``$SHEPHERD_HOME/.lock`` at startup and hold it until exit.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

# ponytail: Linux/POSIX only (the only supported targets); flock on a network
# filesystem may not exclude across hosts.
_held: dict[Path, int] = {}


def acquire(home: Path) -> None:
    """Raise RuntimeError if another process holds ``home``. Idempotent in-process."""
    home = Path(home)
    if home in _held:
        return
    home.mkdir(parents=True, exist_ok=True)
    fd = os.open(home / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError(
            f"Another Shepherd process is already using the data folder {home}: "
            "refusing to start a second one (two writers corrupt it). Stop the other "
            "process or container, or point this one at a different SHEPHERD_HOME."
        ) from None
    _held[home] = fd


def release(home: Path) -> None:
    fd = _held.pop(Path(home), None)
    if fd is not None:
        os.close(fd)
