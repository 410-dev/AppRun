#!/usr/bin/env python3
"""
apprun3-package — AppRun Format 3 패키징 도구
/usr/bin/apprun3-package

Usage:
    apprun3-package <bundle path> [-o <output path>] [--prefer speed|size|balanced] [--force]

Options:
    -o <path>               출력 경로 (기본값: <bundle name>.apprunx)
    --prefer speed          lz4  — 빠른 압축/해제, 큰 파일
    --prefer size           xz   — 느린 압축, 작은 파일
    --prefer balanced       zstd — 속도/크기 균형 (기본값)
    --force                 기존 출력 파일을 덮어쓰기
"""

import sys
import os
import argparse
import subprocess
import shutil
from pathlib import Path

LOCAL_DIST_PACKAGES = Path(__file__).resolve().parents[1] / "lib/python3/dist-packages"
sys.path.insert(0, "/usr/lib/python3/dist-packages")
if LOCAL_DIST_PACKAGES.exists():
    sys.path.insert(0, str(LOCAL_DIST_PACKAGES))
import libapprun
from apprun_validation import ValidationError, validate_app_id
from apprun_i18n import tr


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
        errors.append(tr("package.error.id_missing"))
    else:
        try:
            validate_app_id((b / "AppRunMeta" / "id").read_text().strip())
        except (OSError, ValidationError) as exc:
            errors.append(str(exc))

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
        errors.append(tr("package.error.entry_missing"))

    # meta.json 권장 키 검사
    recommended_keys = ["name", "version", "type"]
    for key in recommended_keys:
        if not meta.get(key):
            print(tr("package.warning.meta_missing", key=key))

    if "python_version" in meta and not isinstance(meta["python_version"], str):
        errors.append(tr("package.error.python_version_type"))

    # 권장: 아이콘
    if not (b / "AppRunMeta" / "DesktopLinks" / "Icon.png").exists():
        print(tr("package.warning.icon_missing"))

    return errors

# ==============================================================================
# 패키징
# ==============================================================================

def package(bundle: str, output: str, prefer: str, force: bool = False) -> int:
    b = Path(bundle)

    print(tr("package.title"))
    print(tr("package.bundle", value=b))
    print(tr("package.output", value=output))
    print(tr("package.compression", prefer=prefer, algorithm=PREFER_MAP[prefer][0]))
    print()

    # --- 유효성 검사 ---
    print(tr("package.checking"))
    errors = validate_bundle(bundle)
    if errors:
        print()
        print(tr("package.errors_found"))
        for e in errors:
            print(tr("package.error_item", error=e))
        return 1
    print(tr("package.check_passed"))
    print()

    # --- 기존 출력 파일 처리 ---
    out = Path(output)
    if out.exists():
        if not force:
            print(tr("package.error_output_exists", path=out), file=sys.stderr)
            return 1
        print(tr("package.removing_existing", path=out))
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

    print(tr("package.packaging"))
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(tr("package.error_mksquashfs"), file=sys.stderr)
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

    print(tr("package.complete"))
    print(tr("package.id", value=app_id))
    if meta.get("name"):
        print(tr("package.name", value=meta["name"]))
    if meta.get("version"):
        print(tr("package.version", value=meta["version"]))
    print(tr("package.source_size", value=_human_size(original_size)))
    print(tr("package.package_size", value=_human_size(packed_size)))
    print(tr("package.ratio", value=ratio))
    print(tr("package.output", value=output))


def _dir_size(path: str) -> int:
    total = 0
    for f in Path(path).rglob("*"):
        if f.is_file() and not f.is_symlink():
            total += f.stat().st_size
    return total


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _configure_argparse_i18n() -> None:
    def translate(text: str) -> str:
        mapping = {
            "usage: ": tr("argparse.usage_prefix"),
            "positional arguments": tr("argparse.positional_arguments"),
            "options": tr("argparse.options"),
            "show this help message and exit": tr("argparse.help"),
        }
        return mapping.get(text, text)

    argparse._ = translate


# ==============================================================================
# 인자 파싱
# ==============================================================================

def parse_args(argv: list[str]):
    _configure_argparse_i18n()
    parser = argparse.ArgumentParser(
        prog="apprun3-package",
        description=tr("package.description"),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "bundle",
        help=tr("package.arg.bundle")
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help=tr("package.arg.output")
    )
    parser.add_argument(
        "--prefer",
        choices=["speed", "size", "balanced"],
        default=DEFAULT_PREFER,
        help=tr("package.arg.prefer")
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=tr("package.arg.force")
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
        print(tr("package.error_directory_missing", path=bundle), file=sys.stderr)
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
        print(tr("package.warning_extension", path=output))

    sys.exit(package(bundle, output, args.prefer, force=args.force))


if __name__ == "__main__":
    main()
