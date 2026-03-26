#!/usr/bin/env python3
"""
apprun3 — AppRun Format 3 실행기 및 유틸리티
/usr/bin/apprun3
"""
import shlex
import sys
import os
import subprocess
import time
import shutil
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import libapprun


UV_BIN      = "/usr/local/bin/uv"
PYTHON3_BIN = "/usr/bin/python3"


# ==============================================================================
# Flag 핸들러
# ==============================================================================

def handle_id(apprunx: str) -> int:
    print(libapprun.get_bundle_id(apprunx))
    return 0


def handle_is_format3(apprunx: str) -> int:
    print("true" if libapprun.is_squashfs(apprunx) else "false")
    return 0


def handle_info(apprunx: str, keys: list[str] | None = None) -> int:
    app_id = libapprun.get_bundle_id(apprunx)
    fmt    = libapprun.get_bundle_format(apprunx)
    meta   = libapprun.get_bundle_meta(apprunx)

    builtin = {
        "id":     app_id,
        "format": str(int(fmt)),
    }
    all_info = {**builtin, **meta}

    if keys:
        for key in keys:
            print(f"{key}: {all_info.get(key, '')}")
    else:
        for k, v in all_info.items():
            print(f"{k}: {v}")
    return 0


def handle_box_path(apprunx: str) -> int:
    print(libapprun.get_box_path(libapprun.get_bundle_id(apprunx)))
    return 0


def handle_extract_file(apprunx: str, inner_path: str, dest: str) -> int:
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = libapprun.peek_file_bytes(apprunx, inner_path)
    except FileNotFoundError:
        print(f"Error: '{inner_path}' 를 찾을 수 없습니다.", file=sys.stderr)
        return 1
    dest_path.write_bytes(data)
    return 0


# ==============================================================================
# Prepare 핸들러
# ==============================================================================

def handle_prepare(apprunx: str, register: bool) -> int:
    if not libapprun.is_squashfs(apprunx):
        print("Error: --prepare 는 Format 3 (.apprunx) 만 지원합니다.", file=sys.stderr)
        print("Format 1/2 는 apprun-prepare 를 사용하세요.", file=sys.stderr)
        return 1

    app_id = libapprun.get_bundle_id(apprunx)
    print(app_id)
    box    = libapprun.ensure_box(app_id)

    mount_path = libapprun.get_mount_path(app_id)
    mount_path.mkdir(parents=True, exist_ok=True)

    if not libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.mount(apprunx, str(mount_path))
        except RuntimeError as e:
            print(f"Error: 마운트 실패: {e}", file=sys.stderr)
            return 1

    bundle = str(mount_path)

    if not _validate_entry(bundle):
        libapprun.notify("[AppRun] 준비 실패", f"entry point 없음: {app_id}")
        print("Error: 실행 가능한 entry point 없음", file=sys.stderr)
        return 9

    if (Path(bundle) / "main.py").exists():
        result = _prepare_python(bundle, app_id, box)
        if result != 0:
            return result

    if register:
        _register_desktop(bundle, app_id)

    return 0


def _validate_entry(bundle: str) -> bool:
    b = Path(bundle)
    meta = libapprun.get_bundle_meta(bundle)
    return any([
        bool(meta.get("entry_point")),
        (b / "main.py").exists(),
        (b / "main.jar").exists(),
        (b / "main.sh").exists(),
        (b / "main").exists() and os.access(b / "main", os.X_OK),
    ])


def _prepare_python(bundle: str, app_id: str, box: Path) -> int:
    venv_py       = box / "pyvenv" / "bin" / "python3"
    checksum_file = box / "requirements.txt.sha256"
    req_file      = Path(bundle) / "requirements.txt"

    if not venv_py.exists():
        result = subprocess.run([UV_BIN, "venv", str(box / "pyvenv")])
        if result.returncode != 0:
            print("Error: venv 생성 실패", file=sys.stderr)
            return 1

    if not req_file.exists():
        return 0

    new_checksum = libapprun.get_checksum(str(req_file))
    old_checksum = checksum_file.read_text().strip() if checksum_file.exists() else ""

    if old_checksum == new_checksum:
        return 0

    is_first = old_checksum == ""
    if is_first:
        libapprun.notify("[AppRun] 의존성 설치 중", f"{app_id} 패키지를 설치합니다.")
    else:
        libapprun.notify("[AppRun] 의존성 업데이트 중", f"{app_id} 패키지가 변경되었습니다.")
        shutil.rmtree(box / "pyvenv", ignore_errors=True)
        subprocess.run([UV_BIN, "venv", str(box / "pyvenv")], check=True)

    install = subprocess.run([
        UV_BIN, "pip", "install",
        "--python", str(venv_py),
        "-r", str(req_file)
    ])
    if install.returncode != 0:
        print("Error: 패키지 설치 실패", file=sys.stderr)
        libapprun.notify("[AppRun] 설치 실패", f"{app_id} 패키지 설치 실패")
        return 1

    checksum_file.write_text(new_checksum)
    libapprun.notify("[AppRun] 준비 완료", f"{app_id} 준비 완료")
    return 0


# ==============================================================================
# 실행 핸들러
# ==============================================================================

def _wrap_terminal(cmd: list[str], meta: dict) -> list[str]:
    if not meta.get("launch_in_terminal", False):
        return cmd

    # (터미널 실행파일, 구분자, 명령어를 문자열로 합쳐야 하는지 여부)
    terminals = [
        ("ptyxis",         ["-x"],  True ),  # ptyxis -x "python3 main.py"
        ("alacritty",      ["-e"],  False),  # alacritty -e python3 main.py
        ("gnome-terminal", ["--"],  False),  # gnome-terminal -- python3 main.py
        ("konsole",        ["-e"],  False),
        ("xfce4-terminal", ["-e"],  False),
        ("xterm",          ["-e"],  False),
    ]

    for term, separator, join_cmd in terminals:
        if shutil.which(term):
            if join_cmd:
                return [term] + separator + [shlex.join(cmd)]
            else:
                return [term] + separator + cmd

    libapprun.show_gui_alert(
        "AppRun 오류",
        "터미널 에뮬레이터를 찾을 수 없습니다.\n"
        "ptyxis, alacritty, gnome-terminal, konsole, xfce4-terminal, xterm 중 하나를 설치해주세요.",
        "error"
    )
    sys.exit(1)

# handle_run 초반, 마운트 확인 전에 추가
def _heal_refcount(app_id: str) -> None:
    """
    비정상 종료로 refcount 가 틀어진 경우 복구.
    마운트가 안 됐는데 refcount > 0 이면 리셋.
    """
    mount_path = libapprun.get_mount_path(app_id)
    libapprun._ensure_refcount(app_id)
    if not libapprun.is_mounted(str(mount_path)):
        libapprun.get_refcount_path(app_id).write_text("0")

def handle_run(apprunx: str, extra_args: list[str]) -> int:
    app_id     = libapprun.get_bundle_id(apprunx)
    mount_path = libapprun.get_mount_path(app_id)

    _heal_refcount(app_id)

    if libapprun.is_locked(app_id):
        libapprun.show_gui_alert("AppRun", f"{app_id} 준비 중입니다. 잠시 후 다시 시도해주세요.", "warning")
        return 1

    if not libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.mount(apprunx, str(mount_path))
        except RuntimeError as e:
            libapprun.show_gui_alert("AppRun 오류", f"마운트 실패: {e}", "error")
            return 1

    # 참조 카운트 증가
    libapprun.increment_refcount(app_id)

    bundle = str(mount_path)

    prepare_code = handle_prepare(apprunx, register=False)
    if prepare_code != 0:
        return prepare_code

    meta = libapprun.get_bundle_meta(bundle)

    cmd = _build_cmd(bundle, app_id, meta)
    if cmd is None:
        print(f"Error: entry point 없음: {bundle}", file=sys.stderr)
        return 10

    cmd = _wrap_root(cmd, meta)
    cmd = _wrap_terminal(cmd, meta)
    cmd = _wrap_screen(cmd, meta, app_id)

    start  = time.time()
    result = None
    try:
        result = subprocess.run(cmd + extra_args)
    finally:
        # 프로세스 종료 시 항상 실행 (크래시, 강제종료 포함)
        count = libapprun.decrement_refcount(app_id)
        if count == 0:
            try:
                libapprun.unmount(str(mount_path))
            except Exception:
                pass  # 언마운트 실패해도 앱 종료에는 영향 없음

    duration = time.time() - start

    # result 가 None 이면 실행 자체가 실패한 것
    if result is None:
        return 1

    _detect_crash(meta, result.returncode, duration)
    return result.returncode

def _build_cmd(bundle: str, app_id: str, meta: dict) -> list[str] | None:
    b = Path(bundle)

    # meta.json 의 entry_point 우선
    entry_point = meta.get("entry_point", "").strip()
    if entry_point:
        return entry_point.replace("{APPDIR}", bundle).split()

    # fallback: main.* 파일 기반
    if (b / "main.py").exists():
        _setup_pythonpath(bundle)
        venv_py = libapprun.get_box_path(app_id) / "pyvenv" / "bin" / "python3"
        return [str(venv_py), str(b / "main.py")]

    if (b / "main.jar").exists():
        return ["java", "-jar", str(b / "main.jar")]

    if (b / "main.sh").exists():
        return ["bash", str(b / "main.sh")]

    main_bin = b / "main"
    if main_bin.exists() and os.access(main_bin, os.X_OK):
        return [str(main_bin)]

    return None


def _setup_pythonpath(bundle: str) -> None:
    libs_file = None
    for candidate in ["AppRunMeta/libs", "libs"]:
        p = Path(bundle) / candidate
        if p.exists():
            libs_file = p
            break
    if not libs_file:
        return
    result = subprocess.run(
        [PYTHON3_BIN, "/usr/bin/dictionary.py",
         "--dict-collection=apprun-python",
         f"--string={libs_file.read_text()}"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        existing = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = f"{result.stdout.strip()}:{existing}"


def _wrap_root(cmd: list[str], meta: dict) -> list[str]:
    if meta.get("enforce_root_launch", False):
        if meta.get("keep_environment", False):
            return ["sudo", "-E"] + cmd
        return ["sudo"] + cmd
    return cmd


def _wrap_screen(cmd: list[str], meta: dict, app_id: str) -> list[str]:
    mode = meta.get("launch_in_screen", "")
    if not mode:
        return cmd

    if shutil.which("screen"):
        session = f"apprun_{app_id}_{os.getpid()}"
        return ["screen", "-D", "-m", "-S", session] + cmd

    if mode == "enforced":
        libapprun.show_gui_alert(
            "AppRun 오류",
            "'screen' 이 필요하지만 설치되지 않았습니다.",
            "error"
        )
        sys.exit(127)
    else:
        libapprun.show_gui_alert(
            "AppRun 안내",
            "'screen' 을 권장하지만 설치되지 않아 일반 모드로 실행합니다.",
            "warning"
        )
    return cmd


def _detect_crash(meta: dict, exit_code: int, duration: float) -> None:
    if meta.get("type", "") != "Application":
        return
    if exit_code != 0:
        libapprun.show_gui_alert(
            "AppRun — 앱 크래시",
            f"앱이 비정상 종료되었습니다. (exit code {exit_code})",
            "error"
        )
    elif duration < 1.0:
        libapprun.show_gui_alert(
            "AppRun — 비정상 종료",
            "앱이 너무 빨리 종료되었습니다. 크래시가 발생했을 수 있습니다.",
            "warning"
        )

def _register_desktop(bundle: str, app_id: str) -> None:
    """
    ~/.local/share/applications/<app_id>.desktop 생성
    ~/.local/share/icons/<app_id>.png 아이콘 복사
    """
    meta         = libapprun.get_bundle_meta(bundle)
    desktop_dir  = Path.home() / ".local/share/applications"
    icons_dir    = Path.home() / ".local/share/icons"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    # 아이콘 복사
    icon_src  = Path(bundle) / "AppRunMeta" / "DesktopLinks" / "Icon.png"
    icon_dest = icons_dir / f"{app_id}.png"
    if icon_src.exists():
        import shutil
        shutil.copy2(str(icon_src), str(icon_dest))

    # .desktop 생성
    name        = meta.get("name", app_id)
    description = meta.get("description", "")
    app_type    = meta.get("type", "Application")

    # apprunx 원본 경로는 box 에 저장해둠
    apprunx_ref = libapprun.get_box_path(app_id) / "source.path"
    apprunx_path = apprunx_ref.read_text().strip() if apprunx_ref.exists() else ""

    desktop_content = f"""[Desktop Entry]
Name={name}
Comment={description}
Exec=apprun3 {apprunx_path}
Icon={app_id}
Type={app_type}
Categories=Application;
StartupWMClass={app_id}
"""
    desktop_file = desktop_dir / f"{app_id}.desktop"
    desktop_file.write_text(desktop_content)
    desktop_file.chmod(0o755)

# ==============================================================================
# 인자 파싱
# ==============================================================================

def parse_args(argv: list[str]):
    flags     = {}
    remaining = argv[:]
    i = 0

    while i < len(remaining):
        arg = remaining[i]
        if not arg.startswith("--"):
            break

        if arg == "--id":
            flags["id"] = True
        elif arg == "--is-format3":
            flags["is_format3"] = True
        elif arg == "--info":
            flags["info"] = []
        elif arg.startswith("--info="):
            flags["info"] = arg[len("--info="):].split(",")
        elif arg == "--box-path":
            flags["box_path"] = True
        elif arg == "--prepare":
            flags["prepare"] = True
        elif arg.startswith("--extract-file-from="):
            flags["extract_file_from"] = arg[len("--extract-file-from="):]
        elif arg.startswith("--extract-file-to="):
            flags["extract_file_to"] = arg[len("--extract-file-to="):]
        elif arg == "--register":
            flags["register"] = True
        else:
            print(f"Error: 알 수 없는 옵션 '{arg}'", file=sys.stderr)
            sys.exit(2)

        remaining.pop(i)

    # --extract-file-from/to 쌍 검사
    has_from = "extract_file_from" in flags
    has_to   = "extract_file_to"   in flags
    if has_from != has_to:
        print("Error: --extract-file-from 과 --extract-file-to 는 함께 사용해야 합니다.", file=sys.stderr)
        sys.exit(2)

    if not remaining:
        print("Usage: apprun3 [--flags] <apprunx> [args...]", file=sys.stderr)
        sys.exit(2)

    return flags, remaining[0], remaining[1:]


# ==============================================================================
# 진입점
# ==============================================================================

def main():
    flags, apprunx, extra_args = parse_args(sys.argv[1:])

    if not Path(apprunx).exists():
        print(f"Error: 파일을 찾을 수 없습니다: {apprunx}", file=sys.stderr)
        sys.exit(1)

    if flags:
        if "id"          in flags: sys.exit(handle_id(apprunx))
        if "is_format3"  in flags: sys.exit(handle_is_format3(apprunx))
        if "info"        in flags: sys.exit(handle_info(apprunx, flags["info"] or None))
        if "box_path"    in flags: sys.exit(handle_box_path(apprunx))
        if "prepare"     in flags: sys.exit(handle_prepare(apprunx, register=False))
        if "register"    in flags: sys.exit(handle_prepare(apprunx, register=True))
        if "extract_file_from" in flags:
            sys.exit(handle_extract_file(
                apprunx,
                flags["extract_file_from"],
                flags["extract_file_to"]
            ))

    sys.exit(handle_run(apprunx, extra_args))


if __name__ == "__main__":
    main()
