#!/usr/bin/env python3
"""
apprun3 — AppRun Format 3 실행기 및 유틸리티
/usr/bin/apprun3
"""
import hashlib
import pwd
import shlex
import sys
import os
import re
import subprocess
import time
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import libapprun


# ==============================================================================
# 상수
# ==============================================================================

UV_BIN          = "/usr/local/bin/uv"
PYTHON3_BIN     = "/usr/bin/python3"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")


# ==============================================================================
# 공통 유틸
# ==============================================================================

def get_real_user() -> str:
    """sudo 환경이든 아니든 실제 사용자를 반환."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        return sudo_user
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid:
        return pwd.getpwuid(int(sudo_uid)).pw_name
    return pwd.getpwuid(os.getuid()).pw_name


def _has_gui() -> bool:
    """DISPLAY 또는 WAYLAND_DISPLAY 가 설정돼 있으면 GUI 환경으로 판단."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _pkexec_available() -> bool:
    return bool(shutil.which("pkexec"))


def _sudo_cmd() -> list[str]:
    """
    root 가 아닐 때 권한 상승 명령을 반환.
    - GUI 환경 + pkexec 있음  →  ["pkexec"]  (인증 팝업)
    - 그 외 (SSH 등)          →  ["sudo"]    (터미널 패스워드 프롬프트)
    """
    if os.geteuid() == 0:
        return []
    if _has_gui() and _pkexec_available():
        return ["pkexec"]
    return ["sudo"]


def _can_escalate() -> bool:
    """root 이거나 권한 상승 수단(pkexec/sudo)이 있으면 True."""
    return (
        os.geteuid() == 0
        or (_has_gui() and _pkexec_available())
        or bool(shutil.which("sudo"))
    )


# ==============================================================================
# Flag 핸들러
# ==============================================================================

def handle_id(apprunx: str) -> int:
    print(libapprun.get_bundle_id(apprunx))
    return 0


def handle_info(apprunx: str, keys: list[str] | None = None) -> int:
    app_id = libapprun.get_bundle_id(apprunx)
    meta   = libapprun.get_bundle_meta(apprunx)

    all_info = {"id": app_id, "format": "3"}
    all_info.update(meta)
    
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

def handle_prepare(apprunx: str, mount_path: Path, register: bool, unmount: bool = True) -> int:

    app_id = libapprun.get_bundle_id(apprunx)
    box    = libapprun.ensure_box(app_id)

    mount_path.mkdir(parents=True, exist_ok=True)

    def termination_unmount(mnt: str):
        if unmount:
            try:
                libapprun.unmount(mnt)
            except Exception as ex:
                print(f"Warning: 마운트 해제 실패: {ex}", file=sys.stderr)

    if not libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.mount(apprunx, str(mount_path))
        except RuntimeError as e:
            print(f"Error: 마운트 실패: {e}", file=sys.stderr)
            termination_unmount(str(mount_path))
            return 1

    bundle = str(mount_path)

    if not _validate_entry(bundle):
        libapprun.notify("[AppRun] 준비 실패", f"entry point 없음: {app_id}")
        print("Error: 실행 가능한 entry point 없음", file=sys.stderr)
        termination_unmount(str(mount_path))
        return 9

    if (Path(bundle) / "main.py").exists():
        result = _prepare_python(bundle, app_id, box)
        if result != 0:
            shutil.rmtree(box / "pyvenv", ignore_errors=True)
            termination_unmount(str(mount_path))
            return result

    if register:
        _register_desktop(bundle, app_id)

    termination_unmount(str(mount_path))
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


def _run_cmd_gui_term_prefer(gui_cmds: list[str]) -> bool:
    terminal = _find_terminal()

    if terminal:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".exitcode", delete=False) as f:
            exitcode_file = f.name

        try:
            shell_cmd = (
                " ".join(gui_cmds) + "; "
                "success=$?; "
                f"echo $success > {exitcode_file}; "
                "if [ $success -eq 0 ]; then "
                "  echo ''; echo '✅ 설치 완료. 3초 후 창이 닫힙니다'; sleep 3; "
                "else "
                "  echo ''; echo '❌ 설치 실패. 창을 닫으려면 아무 키나 누르세요'; read -n 1; "
                "fi"
            )
            proc = subprocess.run(terminal + ["bash", "-c", shell_cmd])

            try:
                actual_code = int(Path(exitcode_file).read_text().strip())
            except (ValueError, FileNotFoundError):
                actual_code = proc.returncode if proc.returncode != 0 else 1

            return actual_code == 0
        finally:
            Path(exitcode_file).unlink(missing_ok=True)
    else:
        libapprun.notify(
            "[AppRun] 의존성 설치중",
            f"[AppRun] 터미널 에뮬레이터를 찾을 수 없습니다. "
            f"명령을 백그라운드에서 실행합니다: {' '.join(gui_cmds)}",
        )
        proc = subprocess.run(gui_cmds)
        return proc.returncode == 0


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

    if old_checksum == "":
        libapprun.notify("[AppRun] 의존성 설치 중", f"{app_id} 패키지를 설치합니다.")
    else:
        libapprun.notify("[AppRun] 의존성 업데이트 중", f"{app_id} 패키지가 변경되었습니다.")
        shutil.rmtree(box / "pyvenv", ignore_errors=True)
        subprocess.run([UV_BIN, "venv", str(box / "pyvenv")], check=True)

    success = _run_cmd_gui_term_prefer([
        UV_BIN, "pip", "install",
        "--python", str(venv_py),
        "-r", str(req_file),
    ])

    if not success:
        print("Error: 패키지 설치 실패", file=sys.stderr)
        libapprun.notify("[AppRun] 설치 실패", f"{app_id} 패키지 설치 실패")
        return 1

    checksum_file.write_text(new_checksum)
    libapprun.notify("[AppRun] 준비 완료", f"{app_id} 준비 완료")
    return 0


def _find_terminal() -> list[str] | None:
    """
    사용 가능한 터미널 에뮬레이터를 찾아 반환
    반환 형식: [실행파일, <명령 실행 플래그>]
    """
    candidates = [
        ("ptyxis",              "--"),
        ("alacritty",           "-e"),
        ("x-terminal-emulator", "-e"),
        ("gnome-terminal",      "--"),
        ("xfce4-terminal",      "-e"),
        ("konsole",             "-e"),
        ("xterm",               "-e"),
        ("lxterminal",          "-e"),
        ("mate-terminal",       "-e"),
    ]
    for binary, flag in candidates:
        if shutil.which(binary):
            return [binary, flag]
    return None


def _pkg_names_only(requirements: list[str]) -> list[str]:
    """버전 조건을 제거하고 패키지 이름만 반환. (apt install 용)"""
    return [libapprun._parse_pkg_requirement(r)[0] for r in requirements]


def _install_packages_gui(pkg_names: list[str]) -> bool:
    if not _pkexec_available():
        libapprun.show_gui_alert(
            "AppRun — 패키지 설치 오류",
            "pkexec 를 찾을 수 없습니다. polkit 이 설치되어 있는지 확인하세요.",
            level="error",
        )
        return False
    return _run_cmd_gui_term_prefer(["pkexec", "apt", "install", "-y"] + pkg_names)


def _install_packages_cli(pkg_names: list[str], auto: bool = False) -> bool:
    """
    CLI 환경에서 패키지 설치.
    auto=True 이면 묻지 않고 즉시 설치.
    """
    if not auto:
        print(f"\n[AppRun] 다음 패키지가 필요합니다: {', '.join(pkg_names)}")
        try:
            answer = input("지금 설치하시겠습니까? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            return False

    apt_cmd = ["sudo", "apt-get", "install", "-y"] + pkg_names
    print(f"[AppRun] 실행: {' '.join(apt_cmd)}")
    return subprocess.run(apt_cmd).returncode == 0


def ensure_base_packages(path: str) -> bool:
    """
    누락된 패키지 확인 → 환경에 따라 설치 시도.
    반환값: True = 모두 충족, False = 설치 거부 또는 실패
    """
    missing = libapprun.list_missing_base_packages(path)
    if not missing:
        return True

    pkg_names = _pkg_names_only(missing)

    if _has_gui():
        if not _confirm_install_gui(missing):
            libapprun.show_gui_alert(
                "AppRun — 실행 취소",
                "필수 패키지가 설치되지 않아 실행을 중단합니다.",
                level="warning",
            )
            return False
        try:
            success = _install_packages_gui(pkg_names)
        except Exception as e:
            print(f"Error during package installation: {e}", file=sys.stderr)
            success = False

        if not success:
            libapprun.show_gui_alert(
                "AppRun — 설치 실패",
                "패키지 설치에 실패했습니다. 로그를 확인하세요.",
                level="error",
            )
        return success
    else:
        auto = os.environ.get("AUTO_INSTALL_BASEPKG", "0") == "1"
        if auto:
            print(f"[AppRun] AUTO_INSTALL_BASEPKG=1 — 자동 설치: {', '.join(pkg_names)}")
        success = _install_packages_cli(pkg_names, auto=auto)
        if not success:
            print("[AppRun] 패키지 설치가 취소되었거나 실패했습니다. 실행을 중단합니다.")
        return success


def _confirm_install_gui(missing: list[str]) -> bool:
    """
    zenity / kdialog 로 설치 확인 다이얼로그 표시.
    둘 다 없으면 True (설치 진행) 로 fallback.
    """
    pkg_list = "\n".join(f"  • {p}" for p in missing)
    message  = f"이 앱을 실행하려면 다음 패키지가 필요합니다:\n\n{pkg_list}\n\n지금 설치하시겠습니까?"

    if shutil.which("zenity"):
        result = subprocess.run([
            "zenity", "--question",
            f"--text={message}",
            "--title=AppRun — 필수 패키지 설치",
            "--width=420",
            "--ok-label=설치",
            "--cancel-label=취소",
        ])
        return result.returncode == 0

    if shutil.which("kdialog"):
        result = subprocess.run([
            "kdialog", "--yesno", message,
            "--title", "AppRun — 필수 패키지 설치",
        ])
        return result.returncode == 0

    return True  # 다이얼로그 도구 없음 → 진행


# ==============================================================================
# 실행 핸들러
# ==============================================================================

def _get_mountpath(apprunx: str) -> tuple[str, Path]:
    app_id     = libapprun.get_bundle_id(apprunx)
    mount_path = libapprun.get_mount_path(app_id)
    return app_id, mount_path


# 심볼릭 링크 임시 디렉토리 추적
_tmp_symlink_dir: str | None = None


def handle_run(apprunx: str, extra_args: list[str]) -> int:
    global _tmp_symlink_dir
    _tmp_symlink_dir = None

    app_id, mount_path = _get_mountpath(apprunx)

    if not ensure_base_packages(apprunx):
        return 1

    if libapprun.is_locked(app_id):
        libapprun.show_gui_alert("AppRun", f"{app_id} 준비 중입니다. 잠시 후 다시 시도해주세요.", "warning")
        return 1

    if libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.unmount(str(mount_path))
        except Exception as e:
            libapprun.show_gui_alert("AppRun 오류", f"기존 이미지 언마운트 실패: {e}", "error")
            return 1

    try:
        libapprun.mount(apprunx, str(mount_path))
    except RuntimeError as e:
        libapprun.show_gui_alert("AppRun 오류", f"마운트 실패: {e}", "error")
        return 1

    bundle      = str(mount_path)
    prepare_code = handle_prepare(apprunx, mount_path, register=False, unmount=False)
    if prepare_code != 0:
        return prepare_code

    meta = libapprun.get_bundle_meta(bundle)
    cmd  = _build_cmd(bundle, app_id, meta)
    if cmd is None:
        print(f"Error: entry point 없음: {bundle}", file=sys.stderr)
        return 10

    cmd = _wrap_root(cmd, meta)
    cmd = _wrap_terminal(cmd, meta)
    cmd = _wrap_screen(cmd, meta, app_id)

    # box 에 마운트 포인트 다이제스트 파일로 apprunx 위치 저장
    rundir             = libapprun.get_box_path(app_id) / ".run"
    mountpoint_digest  = hashlib.sha256(str(mount_path).encode()).hexdigest()
    try:
        rundir.mkdir(parents=True, exist_ok=True)
        rundir.joinpath(mountpoint_digest).write_text(os.path.abspath(apprunx))
    except Exception as e:
        print(f"Warning: 런디렉토리에 마운트 정보 저장 실패: {e}", file=sys.stderr)

    start  = time.time()
    result = None
    try:
        result = subprocess.run(cmd + extra_args)
    except KeyboardInterrupt:
        print("실행이 취소되었습니다.", file=sys.stderr)
    finally:
        try:
            libapprun.unmount(str(mount_path))
        except Exception as e:
            print(f"마운트 해제 실패: {e}", file=sys.stderr)

        digest_file = rundir.joinpath(mountpoint_digest)
        if digest_file.exists():
            try:
                digest_file.unlink()
            except Exception as e:
                print(f"Warning: 런디렉토리 파일 삭제 실패: {e}", file=sys.stderr)
        else:
            print(f"Warning: 런디렉토리 파일이 존재하지 않습니다: {digest_file}", file=sys.stderr)

        if _tmp_symlink_dir and os.path.isdir(_tmp_symlink_dir):
            try:
                shutil.rmtree(_tmp_symlink_dir)
            except Exception:
                pass
            _tmp_symlink_dir = None

    if result is None:
        return 1

    _detect_crash(meta, result.returncode, time.time() - start)
    return result.returncode


def _get_proc_title(app_id: str, meta: dict) -> str:
    if meta.get("name"):
        name = meta["name"].replace(" ", "")
        return re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return app_id.split(".")[-1].replace(" ", "-")


def _build_cmd(bundle: str, app_id: str, meta: dict) -> list[str] | None:
    global _tmp_symlink_dir

    b          = Path(bundle)
    proc_title = _get_proc_title(app_id, meta)

    def make_symlink(executable: str) -> str:
        global _tmp_symlink_dir
        _tmp_symlink_dir = tempfile.mkdtemp(prefix="apprun_")
        fake_bin = os.path.join(_tmp_symlink_dir, proc_title[:15])
        os.symlink(executable, fake_bin)
        return fake_bin

    entry_point = meta.get("entry_point", "").strip()
    if entry_point:
        parts  = entry_point.replace("{APPDIR}", bundle).split()
        linked = make_symlink(parts[0])
        return [linked] + parts[1:]

    if (b / "main.py").exists():
        _setup_pythonpath(bundle)
        venv_py = str(libapprun.get_box_path(app_id) / "pyvenv" / "bin" / "python3")
        return [make_symlink(venv_py), str(b / "main.py")]

    if (b / "main.jar").exists():
        return [make_symlink("/usr/bin/java"), "-jar", str(b / "main.jar")]

    if (b / "main.sh").exists():
        return [make_symlink("/bin/bash"), str(b / "main.sh")]

    main_bin = str(b / "main")
    if os.access(main_bin, os.X_OK):
        return [make_symlink(main_bin)]

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
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        existing = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = f"{result.stdout.strip()}:{existing}"


def _wrap_root(cmd: list[str], meta: dict) -> list[str]:
    if not meta.get("enforce_root_launch", False):
        return cmd
    return (["sudo", "-E"] if meta.get("keep_environment", False) else ["sudo"]) + cmd


def _wrap_terminal(cmd: list[str], meta: dict) -> list[str]:
    if not meta.get("launch_in_terminal", False):
        return cmd

    terminals = [
        ("ptyxis",         ["--"],  False),
        ("alacritty",      ["-e"],  False),
        ("gnome-terminal", ["--"],  False),
        ("konsole",        ["-e"],  False),
        ("xfce4-terminal", ["-e"],  False),
        ("xterm",          ["-e"],  False),
    ]
    for term, separator, join_cmd in terminals:
        if shutil.which(term):
            return [term] + separator + ([shlex.join(cmd)] if join_cmd else cmd)

    libapprun.show_gui_alert(
        "AppRun 오류",
        "터미널 에뮬레이터를 찾을 수 없습니다.\n"
        "ptyxis, alacritty, gnome-terminal, konsole, xfce4-terminal, xterm 중 하나를 설치해주세요.",
        "error",
    )
    sys.exit(1)


def _wrap_screen(cmd: list[str], meta: dict, app_id: str) -> list[str]:
    mode = meta.get("launch_in_screen", "")
    if not mode:
        return cmd

    if shutil.which("screen"):
        session = f"apprun_{app_id}_{os.getpid()}"
        return ["screen", "-D", "-m", "-S", session] + cmd

    if mode == "enforced":
        libapprun.show_gui_alert("AppRun 오류", "'screen' 이 필요하지만 설치되지 않았습니다.", "error")
        sys.exit(127)

    libapprun.show_gui_alert(
        "AppRun 안내",
        "'screen' 을 권장하지만 설치되지 않아 일반 모드로 실행합니다.",
        "warning",
    )
    return cmd


def _detect_crash(meta: dict, exit_code: int, duration: float) -> None:
    if meta.get("type", "") != "Application":
        return
    if exit_code != 0:
        libapprun.show_gui_alert(
            "AppRun — 앱 크래시",
            f"앱이 비정상 종료되었습니다. (exit code {exit_code})",
            "error",
        )
    elif duration < 1.0:
        libapprun.show_gui_alert(
            "AppRun — 비정상 종료",
            "앱이 너무 빨리 종료되었습니다. 크래시가 발생했을 수 있습니다.",
            "warning",
        )


def _register_desktop(bundle: str, app_id: str) -> None:
    """
    ~/.local/share/applications/<app_id>.desktop 생성
    ~/.local/share/icons/<app_id>.png 아이콘 복사
    """
    meta        = libapprun.get_bundle_meta(bundle)
    desktop_dir = Path.home() / ".local/share/applications"
    icons_dir   = Path.home() / ".local/share/icons"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    icon_src  = Path(bundle) / "AppRunMeta" / "DesktopLinks" / "Icon.png"
    icon_dest = icons_dir / f"{app_id}.png"
    if icon_src.exists():
        shutil.copy2(str(icon_src), str(icon_dest))

    apprunx_ref  = libapprun.get_box_path(app_id) / "source.path"
    apprunx_path = apprunx_ref.read_text().strip() if apprunx_ref.exists() else ""

    desktop_content = (
        f"[Desktop Entry]\n"
        f"Name={meta.get('name', app_id)}\n"
        f"Comment={meta.get('description', '')}\n"
        f"Exec=apprun3 {apprunx_path}\n"
        f"Icon={app_id}\n"
        f"Type={meta.get('type', 'Application')}\n"
        f"Categories=Application;\n"
        f"StartupWMClass={app_id}\n"
    )
    desktop_file = desktop_dir / f"{app_id}.desktop"
    desktop_file.write_text(desktop_content)
    desktop_file.chmod(0o755)


# ==============================================================================
# 서비스 단순 설치 핸들러
# ==============================================================================
def handle_install_services(apprunx: str, enable: bool, start: bool) -> int:
    """번들 내 services/ 폴더의 .service 파일들을 /etc/systemd/system/ 에 설치."""
    try:
        file_list = libapprun.list_files(apprunx)
    except Exception as e:
        print(f"Error: 번들 파일 목록을 읽을 수 없습니다: {e}", file=sys.stderr)
        return 1

    service_files = [
        f for f in file_list
        if f.startswith("services/") and f.endswith(".service")
    ]
    if not service_files:
        print("Error: 번들 내에 services/*.service 파일이 없습니다.", file=sys.stderr)
        return 1

    if not _can_escalate():
        print("Error: 서비스 설치에는 root 권한이 필요합니다.", file=sys.stderr)
        return 1

    actions   = (["enable"] if enable else []) + (["start"] if start else [])
    installed: list[str] = []

    if os.geteuid() == 0:
        for svc_path in service_files:
            svc_name = Path(svc_path).name
            try:
                data = libapprun.peek_file_bytes(apprunx, svc_path)
            except FileNotFoundError:
                print(f"Warning: '{svc_path}' 를 읽을 수 없습니다. 건너뜁니다.", file=sys.stderr)
                continue
            (SYSTEMD_UNIT_DIR / svc_name).write_bytes(data)
            installed.append(svc_name)
            print(f"  설치됨: {svc_name}")

        if not installed:
            print("Error: 설치할 서비스 파일이 없습니다.", file=sys.stderr)
            return 1

        _systemctl_daemon_reload()
        if actions:
            result = _systemctl_batch(actions, installed)
            if result != 0:
                return result
    else:
        tmp_map: list[tuple[str, Path]] = []  # (tmp_path, dest)
        try:
            for svc_path in service_files:
                svc_name = Path(svc_path).name
                try:
                    data = libapprun.peek_file_bytes(apprunx, svc_path)
                except FileNotFoundError:
                    print(f"Warning: '{svc_path}' 를 읽을 수 없습니다. 건너뜁니다.", file=sys.stderr)
                    continue
                tmp  = _prepare_temp_file(data)
                dest = SYSTEMD_UNIT_DIR / svc_name
                tmp_map.append((tmp, dest))
                installed.append(svc_name)
                print(f"  설치됨: {svc_name}")

            if not installed:
                print("Error: 설치할 서비스 파일이 없습니다.", file=sys.stderr)
                return 1

            script_parts: list[str] = []
            for tmp, dest in tmp_map:
                script_parts += [f"mv {tmp} {dest}", f"chmod 644 {dest}"]
            script_parts.append("systemctl daemon-reload")
            for action in actions:
                script_parts.append(f"systemctl {action} {' '.join(installed)}")

            if not _run_privileged("; ".join(script_parts)):
                return 1
        finally:
            for tmp, _ in tmp_map:
                Path(tmp).unlink(missing_ok=True)

    print(f"\n{len(installed)}개 서비스 파일 설치 완료.")
    if not actions:
        print("서비스를 활성화하려면: sudo systemctl enable --now <서비스명>")
    return 0

# ==============================================================================
# 서비스 생성 후 설치 핸들러
# ==============================================================================

def _sanitize_service_name(app_id: str) -> str:
    """app_id 의 특수문자를 '-' 로 치환하여 서비스 이름으로 사용."""
    return re.sub(r"[^.A-Za-z0-9_\-]", "-", app_id)


def _get_user_systemd_env(username: str) -> dict[str, str] | None:
    """
    SSH 등 비대화형 환경에서도 systemctl --user 가 동작하도록
    필요한 환경변수를 추론하여 반환. 실패 시 None 반환.
    """
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        print(f"Error: 사용자 '{username}'를 찾을 수 없습니다.", file=sys.stderr)
        return None

    env         = os.environ.copy()
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{pw.pw_uid}"

    if not Path(xdg_runtime).is_dir():
        print(
            f"Error: XDG_RUNTIME_DIR '{xdg_runtime}' 가 존재하지 않습니다.\n"
            f"  loginctl enable-linger {username} 을 실행했는지 확인하세요.",
            file=sys.stderr,
        )
        return None
    env["XDG_RUNTIME_DIR"] = xdg_runtime

    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        socket_path = Path(xdg_runtime) / "bus"
        if socket_path.exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={socket_path}"
        else:
            print(
                "Error: D-Bus session bus 소켓을 찾을 수 없습니다.\n"
                f"  loginctl enable-linger {username} 을 실행했는지 확인하세요.",
                file=sys.stderr,
            )
            return None

    return env


def _ensure_linger(username: str) -> bool:
    """
    loginctl enable-linger 가 비활성화 상태면 자동으로 활성화 시도.
    로그아웃 후에도 user 서비스가 계속 실행되기 위해 필요.
    """
    proc = subprocess.run(
        ["loginctl", "show-user", username, "--property=Linger"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and "Linger=yes" in proc.stdout:
        return True

    print(f"  linger 활성화 중 ({username})...", file=sys.stderr)

    cmd = ([] if os.geteuid() == 0 else ["sudo"]) + ["loginctl", "enable-linger", username]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(
            f"Warning: linger 활성화 실패 — 로그아웃 시 서비스가 중단될 수 있습니다.\n"
            f"  수동 실행: sudo loginctl enable-linger {username}",
            file=sys.stderr,
        )
        return False

    return True

def _prepare_temp_file(data: bytes) -> str:
    """data 를 임시파일에 기록하고 경로 반환. 권한 상승 불필요."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        return f.name




def handle_install_as_service(
    apprunx: str,
    spec: str,
    enable: bool,
    start: bool,
    user: str | None,
) -> int:
    """
    --install-as-service=<type>,<after>+<after>...,<before>+<before>...
    지정된 설정으로 .service 파일을 생성하고 systemd 에 설치.
    - 지정 user == 현재 실제 user  →  ~/.config/systemd/user/ (권한 불필요)
    - 지정 user != 현재 실제 user  →  /etc/systemd/system/   (root 필요)
    """
    app_id        = libapprun.get_bundle_id(apprunx)
    apprunx_abs   = str(Path(apprunx).resolve())
    real_user     = get_real_user()
    resolved_user = real_user if user is None else user
    user_mode     = (resolved_user == real_user)

    user_env: dict | None = None
    if user_mode:
        user_env = _get_user_systemd_env(resolved_user)
        if user_env is None:
            return 1
        _ensure_linger(resolved_user)

    # ── spec 파싱 ──────────────────────────────────────────────────────────
    parts = spec.split(",")
    if not parts[0].strip():
        print("Error: 서비스 타입이 지정되지 않았습니다.", file=sys.stderr)
        print("사용법: --install-as-service=<type>[,<after>][,<before>]", file=sys.stderr)
        return 1

    svc_type    = parts[0].strip()
    valid_types = ("simple", "oneshot", "forking", "notify", "idle")
    if svc_type not in valid_types:
        print(f"Error: 알 수 없는 서비스 타입 '{svc_type}'.", file=sys.stderr)
        print(f"지원 타입: {', '.join(valid_types)}", file=sys.stderr)
        return 1

    after_units  = " ".join(parts[1].strip().split("+")) if len(parts) >= 2 and parts[1].strip() else ""
    before_units = " ".join(parts[2].strip().split("+")) if len(parts) >= 3 and parts[2].strip() else ""

    # ── 설치 경로 결정 ─────────────────────────────────────────────────────
    if user_mode:
        dest_dir = Path(f"~{resolved_user}").expanduser() / ".config" / "systemd" / "user"
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not _can_escalate():
            print("Error: 서비스 설치에는 root 권한이 필요합니다.", file=sys.stderr)
            return 1
        dest_dir = SYSTEMD_UNIT_DIR

    svc_name = _sanitize_service_name(app_id)
    dest     = dest_dir / f"{svc_name}.service"

    # ── .service 파일 생성 ─────────────────────────────────────────────────
    meta        = libapprun.get_bundle_meta(apprunx)
    description = meta.get("description", meta.get("name", app_id))

    unit_lines = ["[Unit]", f"Description={description}"]
    if after_units:
        unit_lines.append(f"After={after_units}")
    if before_units:
        unit_lines.append(f"Before={before_units}")

    service_lines = [
        "",
        "[Service]",
        f"Type={svc_type}",
        "Environment=PYTHONUNBUFFERED=1",
        f"ExecStart=/usr/bin/apprun3 {apprunx_abs}",
    ]
    if not user_mode:
        service_lines.append(f"User={resolved_user}")
    if svc_type == "oneshot":
        service_lines.append("RemainAfterExit=yes")

    wanted_by     = "default.target" if user_mode else "multi-user.target"
    install_lines = ["", "[Install]", f"WantedBy={wanted_by}"]
    unit_bytes    = ("\n".join(unit_lines + service_lines + install_lines) + "\n").encode("utf-8")

    actions = (["enable"] if enable else []) + (["start"] if start else [])

    # ── 파일 쓰기 + daemon-reload + enable/start ───────────────────────────
    if user_mode:
        dest.write_bytes(unit_bytes)
        _systemctl_daemon_reload(user_mode=True, env=user_env)
        if actions:
            result = _systemctl_batch(actions, [svc_name], user_mode=True, env=user_env)
            if result != 0:
                return result
    elif os.geteuid() == 0:
        dest.write_bytes(unit_bytes)
        _systemctl_daemon_reload()
        if actions:
            result = _systemctl_batch(actions, [svc_name])
            if result != 0:
                return result
    else:
        tmp = _prepare_temp_file(unit_bytes)
        try:
            script_parts = [
                f"mv {tmp} {dest}",
                f"chmod 644 {dest}",
                "systemctl daemon-reload",
            ] + [f"systemctl {a} {svc_name}" for a in actions]

            if not _run_privileged("; ".join(script_parts)):
                return 1
        finally:
            Path(tmp).unlink(missing_ok=True)

    # ── 완료 출력 ──────────────────────────────────────────────────────────
    print(f"서비스 설치 완료 ({'user' if user_mode else 'system'}): {svc_name}.service")
    print(f"  타입:   {svc_type}")
    if after_units:
        print(f"  After:  {after_units}")
    if before_units:
        print(f"  Before: {before_units}")
    print(f"  경로:   {dest}")

    if not enable or not start:
        flag = " --user" if user_mode else ""
        print(f"\n활성화: systemctl{flag} enable --now {svc_name}.service")
    return 0

# ==============================================================================
# 서비스 단순 제거 핸들러
# ==============================================================================

def handle_uninstall_services(apprunx: str) -> int:
    """번들 내 services/ 폴더에 해당하는 시스템 서비스를 중지·비활성화·삭제."""
    try:
        file_list = libapprun.list_files(apprunx)
    except Exception as e:
        print(f"Error: 번들 파일 목록을 읽을 수 없습니다: {e}", file=sys.stderr)
        return 1

    service_files = [
        Path(f).name for f in file_list
        if f.startswith("services/") and f.endswith(".service")
    ]
    if not service_files:
        print("Error: 번들 내에 services/*.service 파일이 없습니다.", file=sys.stderr)
        return 1

    if not _can_escalate():
        print("Error: 서비스 제거에는 root 권한이 필요합니다.", file=sys.stderr)
        return 1

    removed = []
    for svc_name in service_files:
        dest = SYSTEMD_UNIT_DIR / svc_name
        if not dest.exists():
            print(f"  건너뜀 (미설치): {svc_name}")
            continue

        _systemctl_stop_disable(svc_name)
        _remove_unit_file(dest)
        removed.append(svc_name)
        print(f"  제거됨: {svc_name}")

    _systemctl_daemon_reload()
    print(f"\n{len(removed)}개 서비스 파일 제거 완료.")
    return 0


# ==============================================================================
# 생성된 서비스 제거 핸들러
# ==============================================================================
def handle_uninstall_as_service(apprunx: str, user: str | None) -> int:
    """--install-as-service 로 생성된 서비스를 중지·비활성화·삭제."""
    app_id        = libapprun.get_bundle_id(apprunx)
    real_user     = get_real_user()
    resolved_user = real_user if user is None else user
    user_mode     = (resolved_user == real_user)

    svc_name = f"{_sanitize_service_name(app_id)}.service"

    if user_mode:
        dest = (
            Path(f"~{resolved_user}").expanduser()
            / ".config" / "systemd" / "user"
            / svc_name
        )
    else:
        dest = SYSTEMD_UNIT_DIR / svc_name

    if not dest.exists():
        print(f"Error: 서비스 파일이 존재하지 않습니다: {dest}", file=sys.stderr)
        return 1

    if user_mode:
        user_env = _get_user_systemd_env(resolved_user)
        if user_env is None:
            return 1
        _systemctl_stop_disable(svc_name, user_mode=True, env=user_env)
        dest.unlink()
        _systemctl_daemon_reload(user_mode=True, env=user_env)
    else:
        if not _can_escalate():
            print("Error: 서비스 제거에는 root 권한이 필요합니다.", file=sys.stderr)
            return 1
        if not _run_privileged(
                f"systemctl stop {svc_name}; "
                f"systemctl disable {svc_name}; "
                f"rm -f {dest}; "
                f"systemctl daemon-reload"
        ):
            return 1

    mode_label = "user" if user_mode else "system"
    print(f"서비스 제거 완료 ({mode_label}): {svc_name}")
    return 0


# ==============================================================================
# systemd 헬퍼
# ==============================================================================

def _run_privileged(script: str) -> bool:
    """
    여러 명령을 하나의 bash -c 로 묶어 권한 상승을 1회만 수행.
    성공 시 True 반환.
    """
    proc = subprocess.run(
        _sudo_cmd() + ["bash", "-c", script],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"Error: 명령 실행 실패:\n{proc.stderr}", file=sys.stderr)
    return proc.returncode == 0


def _write_system_file(dest: Path, data: bytes) -> bool:
    """
    시스템 경로에 파일을 씀.
    root 이면 직접, 아니면 tempfile → _run_privileged(mv) 로 1회 인증.
    """
    if os.geteuid() == 0:
        dest.write_bytes(data)
        return True

    # 현재 사용자 권한으로 tempfile 에 먼저 기록
    with tempfile.NamedTemporaryFile(delete=False) as f:
        tmp_path = f.name
        f.write(data)

    try:
        return _run_privileged(f"mv {tmp_path} {dest} && chmod 644 {dest}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _systemctl_daemon_reload(user_mode: bool = False, env: dict | None = None) -> None:
    if user_mode:
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True, env=env)
    else:
        subprocess.run(_sudo_cmd() + ["systemctl", "daemon-reload"],
                       capture_output=True)


def _systemctl_batch(
    actions: list[str],
    svc_names: list[str],
    user_mode: bool = False,
    env: dict | None = None,
) -> int:
    """
    여러 systemctl 명령을 실행.
    - user 모드 : --user 플래그, 권한 상승 없음.
    - system 모드: 모든 액션을 한 번의 _run_privileged 로 처리 (인증 1회).
    """
    if not svc_names:
        return 0

    if user_mode:
        for action in actions:
            proc = subprocess.run(
                ["systemctl", "--user", action, *svc_names],
                capture_output=True, text=True, env=env,
            )
            if proc.returncode != 0:
                print(f"Error: systemctl --user {action} 실패: {proc.stderr}", file=sys.stderr)
                return proc.returncode
        return 0

    script = "; ".join(
        f"systemctl {action} {' '.join(svc_names)}"
        for action in actions
    )
    return 0 if _run_privileged(script) else 1


def _systemctl_stop_disable(
    svc_name: str,
    user_mode: bool = False,
    env: dict | None = None,
) -> None:
    if user_mode:
        for action in ("stop", "disable"):
            subprocess.run(["systemctl", "--user", action, svc_name],
                           capture_output=True, env=env)
    else:
        # stop + disable 을 한 번에 → 인증 1회
        _run_privileged(f"systemctl stop {svc_name}; systemctl disable {svc_name}")


def _remove_unit_file(path: Path) -> None:
    if os.geteuid() == 0:
        path.unlink(missing_ok=True)
    else:
        _run_privileged(f"rm -f {path}")

# ==============================================================================
# 도움말
# ==============================================================================

HELP_TEXT = """\
apprun3 — AppRun Format 3 실행기 및 유틸리티

사용법:
    apprun3 [--flags] <apprunx> [앱 인자...]

flags 없이 실행하면 번들을 실행합니다.
flags 가 있으면 해당 작업을 수행하고 종료합니다.

정보 조회:
    --id                        번들 ID 출력
    --is-format3                Format 3 여부 출력 (true/false)
    --info                      전체 메타데이터 출력
    --info=key1,key2,...        지정한 키만 출력
    --box-path                  Box 디렉터리 경로 출력

준비 및 등록:
    --prepare                   실행 환경 준비 (마운트, venv, 의존성 설치)
    --register                  --prepare 수행 후 .desktop 파일 등록

파일 추출:
    --extract-file-from=<내부경로> --extract-file-to=<대상경로>
                                번들 내 파일을 지정 경로로 추출
                                (두 옵션은 반드시 함께 사용)

서비스 관리:
    --install-services          번들 내 services/*.service 파일을
                                /etc/systemd/system/ 에 설치
                                --enable: [추가 옵션] 설치 과정에서 자동으로 활성화
                                --start : [추가 옵션] 설치 과정에서 자동으로 시작 (자동으로 활성화 트리거)

    --uninstall-services        번들 내 services/*.service 에 해당하는
                                시스템 서비스를 중지·비활성화·삭제

    --install-as-service=<type>,<after>,<before>
                                지정 설정으로 systemd 서비스를 생성하여 설치
                                  type  : [필수] simple, oneshot, forking, notify, idle
                                  after : [선택] After= 유닛 (+ 로 구분)
                                  before: [선택] Before= 유닛 (+ 로 구분)
                                예: --install-as-service=oneshot,network.target,multi-user.target                                  
                                --enable: [추가 옵션] 설치 과정에서 자동으로 활성화
                                --start : [추가 옵션] 설치 과정에서 자동으로 시작 (자동으로 활성화 트리거)

    --uninstall-as-service      --install-as-service 로 생성된 서비스를
                                중지·비활성화·삭제

기타:
    --help, -h                  이 도움말 출력

예시:
    apprun3 my-app.apprunx                          번들 실행
    apprun3 my-app.apprunx --verbose --port 8080    앱에 인자 전달
    apprun3 --id my-app.apprunx                     번들 ID 확인
    apprun3 --info=name,version my-app.apprunx      이름과 버전 확인
    apprun3 --prepare my-app.apprunx                실행 환경만 준비
    apprun3 --register my-app.apprunx               데스크톱 등록
    apprun3 --install-as-service=oneshot,plymouth-quit-wait.service+systemd-user-sessions.service,network.target my-app.apprunx
"""


def handle_help() -> int:
    print(HELP_TEXT, end="")
    return 0


# ==============================================================================
# 인자 파싱
# ==============================================================================

def parse_args(argv: list[str]):
    flags     = {}
    remaining = argv[:]
    i = 0

    while i < len(remaining):
        arg = remaining[i]
        if not arg.startswith("--") and arg != "-h":
            break

        if arg in ("--help", "-h"):
            flags["help"] = True
        elif arg == "--id":
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
        elif arg == "--install-services":
            flags["install_services"] = True
        elif arg == "--start":
            flags["service_install_and_enable"] = True
            flags["service_install_and_start"]  = True
        elif arg == "--enable":
            flags["service_install_and_enable"] = True
        elif arg.startswith("--install-as-service="):
            flags["install_as_service"] = arg[len("--install-as-service="):]
        elif arg.startswith("--user=") and ("install_as_service" in flags or "uninstall_as_service" in flags):
            flags["service_install_user"] = arg[len("--user="):]
        elif arg == "--uninstall-services":
            flags["uninstall_services"] = True
        elif arg == "--uninstall-as-service":
            flags["uninstall_as_service"] = True
        else:
            print(f"Error: 알 수 없는 옵션 '{arg}'", file=sys.stderr)
            sys.exit(2)

        remaining.pop(i)

    if "help" in flags:
        return flags, None, []

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

    if flags.get("help"):
        sys.exit(handle_help())

    if not Path(apprunx).exists():
        print(f"Error: 파일을 찾을 수 없습니다: {apprunx}", file=sys.stderr)
        sys.exit(1)

    if flags:
        if "id"          in flags: sys.exit(handle_id(apprunx))
        if "info"        in flags: sys.exit(handle_info(apprunx, flags["info"] or None))
        if "box_path"    in flags: sys.exit(handle_box_path(apprunx))
        if "prepare"     in flags: sys.exit(handle_prepare(apprunx, _get_mountpath(apprunx)[1], register=False))
        if "register"    in flags: sys.exit(handle_prepare(apprunx, _get_mountpath(apprunx)[1], register=True))
        if "extract_file_from" in flags:
            sys.exit(handle_extract_file(apprunx, flags["extract_file_from"], flags["extract_file_to"]))
        if "install_services"   in flags:
            sys.exit(handle_install_services(apprunx, flags.get("service_install_and_enable", False), flags.get("service_install_and_start", False)))
        if "install_as_service" in flags:
            sys.exit(handle_install_as_service(apprunx, flags["install_as_service"], flags.get("service_install_and_enable", False), flags.get("service_install_and_start", False), flags.get("service_install_user")))
        if "uninstall_services"   in flags: sys.exit(handle_uninstall_services(apprunx))
        if "uninstall_as_service" in flags: sys.exit(handle_uninstall_as_service(apprunx, flags.get("service_install_user")))

    sys.exit(handle_run(apprunx, extra_args))


if __name__ == "__main__":
    main()