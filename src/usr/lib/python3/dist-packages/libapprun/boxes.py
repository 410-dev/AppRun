"""AppRun Box path and lock-file helpers."""

from __future__ import annotations

from pathlib import Path

from apprun_validation import validate_app_id

from .constants import BOXES_ROOT
from .mounts import get_portable_data_root


def get_box_root() -> Path:
    return BOXES_ROOT


def get_box_path(app_id: str) -> Path:
    app_id = validate_app_id(app_id)
    return BOXES_ROOT / app_id


def get_portable_box_path(apprunx: str, app_id: str) -> Path:
    return get_portable_data_root(apprunx, app_id) / "box"


def ensure_box(app_id: str) -> Path:
    box = get_box_path(app_id)
    box.mkdir(parents=True, exist_ok=True)
    return box


def ensure_box_path(box: Path) -> Path:
    box.mkdir(parents=True, exist_ok=True)
    return box


def is_locked(app_id: str) -> bool:
    return (get_box_path(app_id) / ".lock").exists()


def is_locked_path(box: Path) -> bool:
    return (box / ".lock").exists()


def lock(app_id: str) -> None:
    ensure_box(app_id)
    (get_box_path(app_id) / ".lock").touch()


def unlock(app_id: str) -> None:
    (get_box_path(app_id) / ".lock").unlink(missing_ok=True)

