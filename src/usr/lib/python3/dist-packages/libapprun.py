"""
libapprun.py — AppRun Format 3 공용 라이브러리
/usr/lib/python3/dist-packages/libapprun.py
"""

import os
import json
import hashlib
import subprocess
import shutil
from pathlib import Path
from enum import IntEnum


# ==============================================================================
# 상수
# ==============================================================================

BOXES_ROOT = Path.home() / ".local/apprun/boxes"
MOUNT_ROOT = Path.home() / ".local/apprun/mounts"
SQUASHFUSE = "/usr/bin/squashfuse"
FUSERMOUNT = "/usr/bin/fusermount"
UNSQUASHFS = "/usr/bin/unsquashfs"
MKSQUASHFS = "/usr/bin/mksquashfs"


class BundleFormat(IntEnum):
    UNKNOWN  = 0
    FORMAT_1 = 1
    FORMAT_2 = 2
    FORMAT_3 = 3


# ==============================================================================
# Bundle
# ==============================================================================

def get_bundle_format(path: str) -> BundleFormat:
    p = Path(path)
    if p.is_file() and p.suffix == ".apprunx":
        return BundleFormat.FORMAT_3
    if p.is_dir():
        if (p / "AppRunMeta" / "id").exists():
            return BundleFormat.FORMAT_2
        if (p / "id").exists():
            return BundleFormat.FORMAT_1
    return BundleFormat.UNKNOWN


def is_squashfs(path: str) -> bool:
    return get_bundle_format(path) == BundleFormat.FORMAT_3


def get_bundle_id(path: str) -> str:
    """
    번들 ID 추출.
    FORMAT_3: unsquashfs -cat 으로 마운트 없이 읽음
    FORMAT_3 (마운트된 경로): 디렉터리로 접근
    FORMAT_2: AppRunMeta/id
    FORMAT_1: id
    """
    fmt = get_bundle_format(path)
    val = ""
    try:
        if fmt == BundleFormat.FORMAT_3:
            val = peek_file(path, "AppRunMeta/id").strip()
        if fmt == BundleFormat.FORMAT_2:
            val = (Path(path) / "AppRunMeta" / "id").read_text().strip()
        if fmt == BundleFormat.FORMAT_1:
            val = (Path(path) / "id").read_text().strip()

        # 빈 값인지 체크
        if val:
            return val
    except Exception:
        pass
    # 마운트된 Format 3 디렉터리인 경우
    id_file = Path(path) / "AppRunMeta" / "id"
    if id_file.exists():
        val = id_file.read_text().strip()
        if val:
            return val
    # fallback
    name = Path(path).name.removesuffix(".apprunx")
    suffix = "application" if path.endswith(".apprunx") else "unknowntype"
    return f"{name}_{suffix}"


def get_bundle_meta(path: str) -> dict:
    """
    meta.json 파싱. Format 3 전용.
    path 는 .apprunx 파일 또는 마운트된 디렉터리 둘 다 허용.
    """
    raw = ""
    try:
        p = Path(path)
        if p.is_file() and p.suffix == ".apprunx":
            # 마운트 없이 읽기
            raw = peek_file(path, "AppRunMeta/meta.json")
        elif p.is_dir():
            # 마운트된 경로 또는 Format 2 디렉터리
            meta_file = p / "AppRunMeta" / "meta.json"
            if meta_file.exists():
                raw = meta_file.read_text()
    except Exception:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def get_meta_value(path: str, key: str, default=None):
    """meta.json 에서 특정 키 하나만 꺼내는 헬퍼."""
    return get_bundle_meta(path).get(key, default)


# ==============================================================================
# Squashfs
# ==============================================================================

def peek_file(apprunx: str, inner_path: str) -> str:
    """마운트 없이 특정 파일 내용 읽기 (텍스트)."""
    result = subprocess.run(
        [UNSQUASHFS, "-cat", apprunx, inner_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"{inner_path} not found in {apprunx}")
    return result.stdout


def peek_file_bytes(apprunx: str, inner_path: str) -> bytes:
    """마운트 없이 특정 파일 내용 읽기 (바이너리)."""
    result = subprocess.run(
        [UNSQUASHFS, "-cat", apprunx, inner_path],
        capture_output=True
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"{inner_path} not found in {apprunx}")
    return result.stdout


def list_files(apprunx: str) -> list[str]:
    result = subprocess.run(
        [UNSQUASHFS, "-l", apprunx],
        capture_output=True, text=True
    )
    return [
        l.replace("squashfs-root/", "", 1).strip()
        for l in result.stdout.splitlines()
        if l.strip().startswith("squashfs-root/")
    ]


def mount(apprunx: str, mountpoint: str) -> None:
    mp = Path(mountpoint)
    mp.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [SQUASHFUSE, apprunx, str(mp)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"mount failed: {result.stderr}")


def unmount(mountpoint: str) -> None:
    subprocess.run([FUSERMOUNT, "-u", mountpoint], check=True)


def is_mounted(mountpoint: str) -> bool:
    mp = str(Path(mountpoint).resolve())
    with open("/proc/mounts") as f:
        return any(mp in line for line in f)


def get_mount_path(app_id: str) -> Path:
    return MOUNT_ROOT / app_id


# ==============================================================================
# Box
# ==============================================================================

def get_box_root() -> Path:
    return BOXES_ROOT


def get_box_path(app_id: str) -> Path:
    return BOXES_ROOT / app_id


def ensure_box(app_id: str) -> Path:
    box = get_box_path(app_id)
    box.mkdir(parents=True, exist_ok=True)
    return box


def is_locked(app_id: str) -> bool:
    return (get_box_path(app_id) / ".lock").exists()


def lock(app_id: str) -> None:
    ensure_box(app_id)
    (get_box_path(app_id) / ".lock").touch()


def unlock(app_id: str) -> None:
    (get_box_path(app_id) / ".lock").unlink(missing_ok=True)


# ==============================================================================
# Util
# ==============================================================================

def get_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def notify(title: str, message: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, message])


def show_gui_alert(title: str, message: str, level: str = "info") -> None:
    print(f"[AppRun] {title}: {message}")
    zenity_flag  = {"info": "--info", "warning": "--warning", "error": "--error"}.get(level, "--info")
    kdialog_flag = {"info": "--msgbox", "warning": "--sorry",  "error": "--error"}.get(level, "--msgbox")
    if shutil.which("zenity"):
        subprocess.run(["zenity", zenity_flag, f"--text={message}", f"--title={title}", "--width=400"])
    elif shutil.which("kdialog"):
        subprocess.run(["kdialog", kdialog_flag, message, "--title", title])


def run_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)

def get_refcount_path(app_id: str) -> Path:
    return get_box_path(app_id) / ".refcount"

def increment_refcount(app_id: str) -> int:
    path = get_refcount_path(app_id)
    _ensure_refcount(app_id)
    count = int(path.read_text().strip()) if path.exists() else 0
    count += 1
    path.write_text(str(count))
    return count

def decrement_refcount(app_id: str) -> int:
    path = get_refcount_path(app_id)
    _ensure_refcount(app_id)
    count = int(path.read_text().strip()) if path.exists() else 0
    count = max(0, count - 1)
    path.write_text(str(count))
    return count

def get_refcount(app_id: str) -> int:
    path = get_refcount_path(app_id)
    _ensure_refcount(app_id)
    return int(path.read_text().strip()) if path.exists() else 0

def _ensure_refcount(app_id: str) -> Path:
    path = get_refcount_path(app_id)
    # Ensure parent directories as well
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("0")
    return path
