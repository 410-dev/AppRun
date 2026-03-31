#!/usr/bin/env python3
"""
apprun3-package — AppRun Format 3 패키징 도구
/usr/bin/apprun3-package

Usage:
    apprun3-package <bundle path> [-o <output path>] [--prefer speed|size|balanced]

Options:
    -o <path>               출력 경로 (기본값: <bundle name>.apprunx)
    --prefer speed          lz4  — 빠른 압축/해제, 큰 파일
    --prefer size           xz   — 느린 압축, 작은 파일
    --prefer balanced       zstd — 속도/크기 균형 (기본값)
"""

import sys
import os
import argparse
import subprocess
import shutil
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import libapprun


# ==============================================================================
# 상수
# ==============================================================================

PREFER_MAP = {
    "speed":    ("lz4",  ["-Xhc"]),         # lz4 high-compression
    "balanced": ("zstd", ["-Xcompression-level", "3"]),  # zstd level 3
    "size":     ("xz",   ["-Xbcj", "x86"]), # xz + x86 필터
}

DEFAULT_PREFER = "balanced"

# 패키징 시 제외할 항목
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".gitignore",
    ".DS_Store",
    "*.apprunx",
]


# ==============================================================================
# 유효성 검사
# ==============================================================================

def validate_bundle(bundle: str) -> list[str]:
    b      = Path(bundle)
    errors = []

    # 필수: AppRunMeta/id
    if not (b / "AppRunMeta" / "id").exists():
        errors.append("AppRunMeta/id 파일이 없습니다.")

    # 필수: entry point
    meta = libapprun.get_bundle_meta(bundle)
    has_entry = any([
        bool(meta.get("entry_point")),
        (b / "main.py").exists(),
        (b / "main.jar").exists(),
        (b / "main.sh").exists(),
        (b / "main").exists() and os.access(b / "main", os.X_OK),
    ])
    if not has_entry:
        errors.append("entry point 없음 (meta.json entry_point, main.py/jar/sh/main 중 하나 필요)")

    # meta.json 권장 키 검사
    recommended_keys = ["name", "version", "type"]
    for key in recommended_keys:
        if not meta.get(key):
            print(f"  경고: meta.json 에 '{key}' 가 없습니다. (권장)")

    # 권장: 아이콘
    if not (b / "AppRunMeta" / "DesktopLinks" / "Icon.png").exists():
        print("  경고: AppRunMeta/DesktopLinks/Icon.png 가 없습니다. (권장)")

    return errors

# ==============================================================================
# 패키징
# ==============================================================================

def package(bundle: str, output: str, prefer: str) -> int:
    b = Path(bundle)

    print(f"AppRun Format 3 패키징")
    print(f"  번들:  {b}")
    print(f"  출력:  {output}")
    print(f"  압축:  {prefer} ({PREFER_MAP[prefer][0]})")
    print()

    # --- 유효성 검사 ---
    print("번들 구조 검사 중...")
    errors = validate_bundle(bundle)
    if errors:
        print()
        print("오류가 발견되었습니다. 패키징을 중단합니다:")
        for e in errors:
            print(f"  오류: {e}")
        return 1
    print("  구조 검사 통과")
    print()

    # --- 기존 출력 파일 처리 ---
    out = Path(output)
    if out.exists():
        print(f"기존 파일 제거: {out}")
        out.unlink()

    # --- mksquashfs 호출 ---
    comp, comp_opts = PREFER_MAP[prefer]

    exclude_args = []
    for pattern in EXCLUDE_PATTERNS:
        exclude_args += ["-e", pattern]

    cmd = [
        libapprun.MKSQUASHFS,
        str(b),
        str(out),
        "-comp", comp,
        *comp_opts,
        "-noappend",
        "-progress",
        *exclude_args,
    ]

    print("패키징 중...")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("오류: mksquashfs 실패", file=sys.stderr)
        out.unlink(missing_ok=True)
        return 1

    # --- 결과 출력 ---
    print()
    _print_result(bundle, str(out))
    return 0


def _print_result(bundle: str, output: str) -> None:
    out = Path(output)
    app_id   = libapprun.get_bundle_id(output)
    meta     = libapprun.get_bundle_meta(output)

    original_size = _dir_size(bundle)
    packed_size   = out.stat().st_size
    ratio         = (1 - packed_size / original_size) * 100 if original_size > 0 else 0

    print("패키징 완료!")
    print(f"  ID:      {app_id}")
    if meta.get("name"):
        print(f"  이름:    {meta['name']}")
    if meta.get("version"):
        print(f"  버전:    {meta['version']}")
    print(f"  원본:    {_human_size(original_size)}")
    print(f"  패키지:  {_human_size(packed_size)}")
    print(f"  압축률:  {ratio:.1f}%")
    print(f"  출력:    {output}")


def _dir_size(path: str) -> int:
    total = 0
    for f in Path(path).rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ==============================================================================
# 인자 파싱
# ==============================================================================

def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="apprun3-package",
        description="AppRun Format 3 패키징 도구",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "bundle",
        help="패키징할 번들 디렉터리 경로"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="출력 .apprunx 경로 (기본값: <bundle name>.apprunx)"
    )
    parser.add_argument(
        "--prefer",
        choices=["speed", "size", "balanced"],
        default=DEFAULT_PREFER,
        help=(
            "압축 방식 선택\n"
            "  speed    — lz4,  빠른 속도, 큰 파일 (개발/테스트용)\n"
            "  balanced — zstd, 속도/크기 균형 (기본값)\n"
            "  size     — xz,   최고 압축률, 느린 속도 (배포용)"
        )
    )
    return parser.parse_args(argv)


# ==============================================================================
# 진입점
# ==============================================================================

def main():
    args = parse_args(sys.argv[1:])

    bundle = args.bundle

    # 번들 경로 확인
    if not Path(bundle).is_dir():
        print(f"오류: 디렉터리를 찾을 수 없습니다: {bundle}", file=sys.stderr)
        sys.exit(1)

    # 출력 경로 결정
    if args.output:
        output = args.output
    else:
        bundle_name = Path(bundle).name.rstrip("/")

        # .apprunxproj 라면 apprunx 로 단순 변환
        if bundle_name.endswith(".apprunxproj"):
            bundle_name = bundle_name[:-len(".apprunxproj")]

        output = f"{bundle_name}.apprunx"

    # 출력 경로가 .apprunx 로 끝나지 않으면 경고
    if not output.endswith(".apprunx"):
        print(f"경고: 출력 파일명이 .apprunx 로 끝나지 않습니다: {output}")

    sys.exit(package(bundle, output, args.prefer))


if __name__ == "__main__":
    main()
