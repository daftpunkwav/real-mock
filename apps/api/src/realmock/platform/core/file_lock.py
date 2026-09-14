"""Cross-process file lock (no third-party dependencies).

Windows uses ``msvcrt.locking``; POSIX uses ``fcntl.flock``.
Used for cross-process serialization of local JSON files such as ``system_learning.json``.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class FileLockTimeout(TimeoutError):
    """Timeout obtaining file lock."""


@contextmanager
def file_lock(
    lock_path: Path,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Acquire an exclusive lock on ``lock_path``; release it on exit.

    The lock file is created as needed; it is not deleted (to avoid race conditions).
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Open with binary reading and writing to ensure that the locking API of each platform is available
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    # Lock 1 byte; the file may be empty, write a placeholder first
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                        os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise FileLockTimeout(f"Timeout for acquiring file lock: {lock_path}") from None
                time.sleep(poll_interval)
        yield
    finally:
        if locked:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
