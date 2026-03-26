#!/usr/bin/env python3
"""
apprunx-thumbnailer — Nautilus 썸네일 생성기
/usr/bin/apprunx-thumbnailer

Nautilus 가 호출하는 방식:
    apprunx-thumbnailer %i %o %s
    %i = 입력 .apprunx 경로
    %o = 출력 PNG 경로 (Nautilus 가 지정)
    %s = 요청 크기 (px)
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import libapprun

DEFAULT_ICON = "/usr/share/apprun/default-icon.png"
BADGE_ICON   = "/usr/share/apprun/badge.png"


def main():
    if len(sys.argv) < 4:
        print("Usage: apprunx-thumbnailer <input> <output> <size>", file=sys.stderr)
        sys.exit(1)

    apprunx = sys.argv[1]
    output  = sys.argv[2]
    size    = sys.argv[3]

    # convert 확인
    if not _check_deps():
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix=f"apprun-thumb-{os.getpid()}-") as tmpdir:
        icon_path = _extract_icon(apprunx, tmpdir)
        _compose(icon_path, output, size)


def _check_deps() -> bool:
    import shutil
    if not shutil.which("convert"):
        print("Error: imagemagick (convert) 가 필요합니다.", file=sys.stderr)
        return False
    return True


def _extract_icon(apprunx: str, tmpdir: str) -> str:
    """
    아이콘 추출 시도.
    실패하면 기본 아이콘 경로 반환.
    """
    dest = str(Path(tmpdir) / "icon.png")
    try:
        data = libapprun.peek_file_bytes(apprunx, "AppRunMeta/DesktopLinks/Icon.png")
        Path(dest).write_bytes(data)
        return dest
    except FileNotFoundError:
        return DEFAULT_ICON


def _compose(icon_path: str, output: str, size: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    badge_size = str(int(int(size) / 3))

    # 공통 전처리: 투명 배경을 흰색으로 flatten
    base_args = [
        "convert",
        "-background", "none",
        "-alpha", "on",
        icon_path,
        "-resize", f"{size}x{size}",
    ]

    if Path(BADGE_ICON).exists():
        subprocess.run([
            *base_args,
            "(", BADGE_ICON,
                "-background", "white",
                "-flatten",
                "-resize", f"{badge_size}x{badge_size}",
            ")",
            "-gravity", "SouthEast",
            "-composite",
            output
        ], check=True)
    else:
        subprocess.run([
            *base_args,
            output
        ], check=True)


if __name__ == "__main__":
    main()
