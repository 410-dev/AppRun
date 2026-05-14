"""
Small no-symlink file-write helpers for privileged AppRun paths.

These helpers do not make arbitrary user home writes fully race-proof, but they
remove the highest-risk final-path symlink overwrite primitive and avoid chmod
or chown following symlinks after data is written.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def ensure_directory_no_symlink(path: Path, mode: int = 0o755, uid: int | None = None, gid: int | None = None) -> None:
    """Create a directory and reject symlink components at the final path."""
    path.mkdir(parents=True, exist_ok=True)
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        st_part = current.lstat()
        if stat.S_ISLNK(st_part.st_mode):
            raise OSError(f"refusing symlink directory component: {current}")
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise OSError(f"refusing unsafe directory path: {path}")
    if uid is not None or gid is not None:
        os.chown(path, -1 if uid is None else uid, -1 if gid is None else gid, follow_symlinks=False)
    os.chmod(path, mode, follow_symlinks=False)


def write_file_no_symlink(
    path: Path,
    content: bytes,
    *,
    mode: int = 0o644,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    """Write bytes to ``path`` while refusing a final symlink target."""
    ensure_directory_no_symlink(path.parent, uid=uid, gid=gid)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        os.write(fd, content)
        os.fchmod(fd, mode)
        if uid is not None or gid is not None:
            os.fchown(fd, -1 if uid is None else uid, -1 if gid is None else gid)
    finally:
        os.close(fd)
