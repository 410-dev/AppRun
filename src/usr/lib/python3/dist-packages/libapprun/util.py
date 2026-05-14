"""General-purpose helpers exported by libapprun."""

from __future__ import annotations

import hashlib
import subprocess


def get_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)

