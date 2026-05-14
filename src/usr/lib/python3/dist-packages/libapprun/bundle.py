"""Bundle metadata and SquashFS access helpers."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from apprun_i18n import tr
from apprun_validation import sanitize_identifier, validate_app_id

from .constants import UNSQUASHFS


def get_bundle_id(path: str) -> str:
    """
    Return a validated bundle ID.

    ``path`` may be a Format 3 squashfs file or an already-mounted bundle
    directory.  If no ID file is present, a host-derived fallback ID is
    generated from the filename.
    """
    try:
        val = peek_file(path, "AppRunMeta/id").strip()
        if val:
            return validate_app_id(val)
    except Exception:
        pass

    id_file = Path(path) / "AppRunMeta" / "id"
    if id_file.exists():
        val = id_file.read_text().strip()
        if val:
            return validate_app_id(val)

    name = Path(path).name.removesuffix(".apprunx")
    suffix = "application" if path.endswith(".apprunx") else "unknowntype"
    return sanitize_identifier(f"{name}_{suffix}")


def get_bundle_meta(path: str) -> dict:
    """Read and parse ``AppRunMeta/meta.json`` from a bundle path."""
    try:
        if os.path.isdir(path):
            raw = (Path(path) / "AppRunMeta" / "meta.json").read_text()
        elif os.path.isfile(path):
            raw = peek_file(path, "AppRunMeta/meta.json")
        else:
            raise FileNotFoundError(f"{path} not found in {path}")
    except Exception as exc:
        print(tr("error.meta_read_failed", path=path, error=exc))
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_meta_value(path: str, key: str, default=None):
    """Return one value from bundle metadata."""
    return get_bundle_meta(path).get(key, default)


def peek_file(apprunx: str, inner_path: str) -> str:
    """Read a text file from a squashfs bundle without mounting it."""
    result = subprocess.run(
        [UNSQUASHFS, "-cat", apprunx, inner_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"{inner_path} not found in {apprunx}")
    return result.stdout


def peek_file_bytes(apprunx: str, inner_path: str) -> bytes:
    """Read bytes from a squashfs bundle without mounting it."""
    result = subprocess.run(
        [UNSQUASHFS, "-cat", apprunx, inner_path],
        capture_output=True,
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"{inner_path} not found in {apprunx}")
    return result.stdout


def list_files(apprunx: str) -> list[str]:
    """List bundle paths using ``unsquashfs -l`` output."""
    result = subprocess.run(
        [UNSQUASHFS, "-l", apprunx],
        capture_output=True,
        text=True,
    )
    return [
        line.replace("squashfs-root/", "", 1).strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("squashfs-root/")
    ]

