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

LOCAL_DIST_PACKAGES = Path(__file__).resolve().parents[1] / "lib/python3/dist-packages"
sys.path.insert(0, "/usr/lib/python3/dist-packages")
if LOCAL_DIST_PACKAGES.exists():
    sys.path.insert(0, str(LOCAL_DIST_PACKAGES))
import libapprun
from apprun_i18n import tr


# ==============================================================================
# 상수
# ==============================================================================

UV_BIN          = "/usr/local/bin/uv"
PYTHON3_BIN     = "/usr/bin/python3"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")
SYSTEMD_GLOBAL_USER_UNIT_DIR = Path("/etc/systemd/user")
SERVICE_STORE_ROOT = Path("/usr/share/services.apprd")
SYSTEM_SERVICE_STORE_DIR = SERVICE_STORE_ROOT / "system"
GLOBAL_USER_SERVICE_STORE_DIR = SERVICE_STORE_ROOT / "global"
GLOBAL_GUI_STARTUP_DIR = Path("/etc/xdg/autostart")
GLOBAL_GUI_STARTUP_STORE_DIR = SERVICE_STORE_ROOT / "gui-startup" / "global"
PORTABLE_TARGETS = {"mount", "box"}
INHERIT_TARGETS = {"venv", "data", "full"}


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
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if pkexec_uid:
        return pwd.getpwuid(int(pkexec_uid)).pw_name
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


def _current_cli_command() -> str:
    argv0 = sys.argv[0]
    if os.sep in argv0:
        return str(Path(argv0).resolve())
    return shutil.which(argv0) or argv0


def _argv_with_absolute_bundle(apprunx: str) -> list[str]:
    args: list[str] = []
    replaced = False
    for arg in sys.argv[1:]:
        if not replaced and arg == apprunx:
            args.append(str(Path(apprunx).resolve()))
            replaced = True
        else:
            args.append(arg)
    return args


def _reexec_privileged(apprunx: str) -> int:
    """현재 CLI 호출을 root 권한으로 한 번 다시 실행."""
    if not _can_escalate():
        print(tr("error.root_required_service_install"), file=sys.stderr)
        return 1

    cmd = _sudo_cmd() + [_current_cli_command(), *_argv_with_absolute_bundle(apprunx)]
    proc = subprocess.run(cmd)
    return proc.returncode


def _parse_option_list(value: str, valid: set[str], option_name: str) -> list[str]:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = [item for item in items if item not in valid]
    if invalid:
        print(
            tr("error.invalid_option_value", option=option_name, values=", ".join(invalid)),
            file=sys.stderr,
        )
        sys.exit(2)
    return items


def _meta_option_list(meta: dict, key: str, valid: set[str]) -> list[str]:
    raw = meta.get(key, [])
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        print(tr("warning.meta_array_required", key=key), file=sys.stderr)
        return []

    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            print(tr("warning.meta_item_string_required", key=key, item=item), file=sys.stderr)
            continue
        normalized = item.strip().lower()
        if normalized not in valid:
            print(tr("warning.meta_value_ignored", key=key, item=item), file=sys.stderr)
            continue
        values.append(normalized)
    return values


def _normalize_inherit_modes(values: list[str]) -> set[str]:
    modes = set(values)
    if "full" in modes:
        modes.update({"venv", "data"})
        modes.discard("full")
    return modes


def _resolve_runtime_paths(apprunx: str, flags: dict) -> tuple[str, Path, Path, set[str], set[str]]:
    app_id = libapprun.get_bundle_id(apprunx)
    meta = libapprun.get_bundle_meta(apprunx)

    portable_targets = set(flags.get("portable", []))
    portable_targets.update(_meta_option_list(meta, "EnforcePortable", PORTABLE_TARGETS))

    inherit_values = list(flags.get("inherit", []))
    inherit_values.extend(_meta_option_list(meta, "EnforceInherit", INHERIT_TARGETS))
    inherit_targets = _normalize_inherit_modes(inherit_values)
    if inherit_targets:
        portable_targets.add("box")

    if "mount" in portable_targets:
        mount_path = libapprun.get_portable_mount_path(apprunx, app_id)
    else:
        mount_path = libapprun.get_mount_path(app_id)

    if "box" in portable_targets:
        box_path = libapprun.get_portable_box_path(apprunx, app_id)
    else:
        box_path = libapprun.get_box_path(app_id)

    return app_id, mount_path, box_path, portable_targets, inherit_targets


def _copy_path(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
    elif src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _copy_box_data(src_box: Path, dest_box: Path) -> None:
    for item in src_box.iterdir():
        if item.name in {"pyvenv", ".lock", ".run"}:
            continue
        _copy_path(item, dest_box / item.name)


def _inherit_box(app_id: str, dest_box: Path, inherit_targets: set[str]) -> None:
    if not inherit_targets:
        return

    src_box = libapprun.get_box_path(app_id)
    if src_box.resolve() == dest_box.resolve() or not src_box.exists():
        return

    dest_box.mkdir(parents=True, exist_ok=True)
    if "data" in inherit_targets:
        _copy_box_data(src_box, dest_box)
    if "venv" in inherit_targets:
        _copy_path(src_box / "pyvenv", dest_box / "pyvenv")


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


def handle_box_path(box: Path) -> int:
    print(box)
    return 0


def handle_extract_file(apprunx: str, inner_path: str, dest: str) -> int:
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = libapprun.peek_file_bytes(apprunx, inner_path)
    except FileNotFoundError:
        print(tr("error.inner_file_not_found", path=inner_path), file=sys.stderr)
        return 1
    dest_path.write_bytes(data)
    return 0


# ==============================================================================
# Prepare 핸들러
# ==============================================================================

def handle_prepare(apprunx: str, mount_path: Path, box: Path, register: bool, unmount: bool = True) -> int:

    app_id = libapprun.get_bundle_id(apprunx)
    box    = libapprun.ensure_box_path(box)
    try:
        (box / "source.path").write_text(str(Path(apprunx).resolve()))
    except Exception as e:
        print(tr("warning.source_path_write_failed", error=e), file=sys.stderr)

    mount_path.mkdir(parents=True, exist_ok=True)

    def termination_unmount(mnt: str):
        if unmount:
            try:
                libapprun.unmount(mnt)
            except Exception as ex:
                print(tr("warning.unmount_failed", error=ex), file=sys.stderr)

    if not libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.mount(apprunx, str(mount_path))
        except RuntimeError as e:
            print(tr("error.mount_failed", error=e), file=sys.stderr)
            termination_unmount(str(mount_path))
            return 1

    bundle = str(mount_path)

    if not _validate_entry(bundle):
        libapprun.notify(
            tr("notify.prepare_failed_title"),
            tr("notify.prepare_failed_entry_missing", app_id=app_id),
        )
        print(tr("error.entry_missing"), file=sys.stderr)
        termination_unmount(str(mount_path))
        return 9

    if (Path(bundle) / "main.py").exists():
        result = _prepare_python(bundle, app_id, box)
        if result != 0:
            shutil.rmtree(box / "pyvenv", ignore_errors=True)
            termination_unmount(str(mount_path))
            return result

    if register:
        _register_desktop(bundle, app_id, box)

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
                f"  echo ''; echo {shlex.quote(tr('terminal.install_success'))}; sleep 3; "
                "else "
                f"  echo ''; echo {shlex.quote(tr('terminal.install_failed'))}; read -n 1; "
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
            tr("notify.installing_deps_title"),
            tr("notify.no_terminal_background", cmd=" ".join(gui_cmds)),
        )
        proc = subprocess.run(gui_cmds)
        return proc.returncode == 0


def _uv_venv_cmd(venv_dir: Path, python_version: str) -> list[str]:
    cmd = [UV_BIN, "venv"]
    if python_version:
        cmd += ["--python", python_version]
    cmd.append(str(venv_dir))
    return cmd


def _create_python_venv(venv_dir: Path, python_version: str) -> bool:
    result = subprocess.run(_uv_venv_cmd(venv_dir, python_version))
    if result.returncode != 0:
        version_desc = f" (Python {python_version})" if python_version else ""
        print(tr("error.venv_create_failed", version_desc=version_desc), file=sys.stderr)
        return False
    return True


def _prepare_python(bundle: str, app_id: str, box: Path) -> int:
    venv_dir            = box / "pyvenv"
    venv_py             = venv_dir / "bin" / "python3"
    checksum_file       = box / "requirements.txt.sha256"
    python_version_file = box / "python_version"
    req_file            = Path(bundle) / "requirements.txt"
    meta                = libapprun.get_bundle_meta(bundle)
    python_version      = meta.get("python_version", "")

    if python_version is None:
        python_version = ""
    elif not isinstance(python_version, str):
        print(tr("error.python_version_type"), file=sys.stderr)
        return 1
    python_version = python_version.strip()

    stored_python_version = (
        python_version_file.read_text().strip()
        if python_version_file.exists()
        else ""
    )
    python_version_changed = venv_py.exists() and python_version != stored_python_version

    if python_version_changed:
        shutil.rmtree(venv_dir, ignore_errors=True)
        checksum_file.unlink(missing_ok=True)

    venv_created = False
    if not venv_py.exists():
        if not _create_python_venv(venv_dir, python_version):
            return 1
        venv_created = True

    python_version_file.write_text(python_version)

    if not req_file.exists():
        return 0

    new_checksum = libapprun.get_checksum(str(req_file))
    old_checksum = checksum_file.read_text().strip() if checksum_file.exists() else ""
    if venv_created:
        old_checksum = ""

    if old_checksum == new_checksum and not venv_created:
        return 0

    if old_checksum == "":
        libapprun.notify(
            tr("notify.installing_packages_title"),
            tr("notify.installing_packages_body", app_id=app_id),
        )
    else:
        libapprun.notify(
            tr("notify.updating_packages_title"),
            tr("notify.updating_packages_body", app_id=app_id),
        )
        shutil.rmtree(venv_dir, ignore_errors=True)
        if not _create_python_venv(venv_dir, python_version):
            return 1
        python_version_file.write_text(python_version)

    success = _run_cmd_gui_term_prefer([
        UV_BIN, "pip", "install",
        "--python", str(venv_py),
        "-r", str(req_file),
    ])

    if not success:
        print(tr("error.package_install_failed"), file=sys.stderr)
        libapprun.notify(tr("app.install_failed_title"), tr("notify.install_failed_body", app_id=app_id))
        return 1

    checksum_file.write_text(new_checksum)
    libapprun.notify(tr("notify.prepare_complete_title"), tr("notify.prepare_complete_body", app_id=app_id))
    return 0




def _find_terminal() -> list[str] | None:
    """
    사용 가능한 터미널 에뮬레이터를 찾아 반환
    반환 형식: [실행파일, <명령 실행 플래그>]
    """

    if os.geteuid() == 0:
        # root 권한은 terminal 에서 처리하는 것으로 기본 간주하며,
        # DBUS_SESSION_BUS_ADDRESS, DBUS_STARTER_ADDRESS, DBUS_STARTER_BUS_TYPE 가 모두 있고,
        # DISPLAY 가 있으면 현재 root 로 로그인 한것이니 터미널을 사용을 시도함
        if libapprun.can_use_dbus_and_gui():
            pass
        else:
            return None

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
            tr("app.install_packages_error_title"),
            tr("error.pkexec_missing"),
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
        print(tr("cli.required_packages", packages=", ".join(pkg_names)))
        try:
            answer = input(tr("cli.install_now_prompt")).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            return False

    apt_cmd = ["sudo", "apt-get", "install", "-y"] + pkg_names
    print(tr("cli.running_command", cmd=" ".join(apt_cmd)))
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
                tr("app.launch_cancelled_title"),
                tr("alert.required_packages_missing"),
                level="warning",
            )
            return False
        try:
            success = _install_packages_gui(pkg_names)
        except Exception as e:
            print(tr("error.package_install_exception", error=e), file=sys.stderr)
            success = False

        if not success:
            libapprun.show_gui_alert(
                tr("app.install_failed_title"),
                tr("alert.package_install_failed"),
                level="error",
            )
        return success
    else:
        auto = os.environ.get("AUTO_INSTALL_BASEPKG", "0") == "1"
        if auto:
            print(tr("cli.auto_install_basepkg", packages=", ".join(pkg_names)))
        success = _install_packages_cli(pkg_names, auto=auto)
        if not success:
            print(tr("cli.package_install_cancelled"))
        return success


def _confirm_install_gui(missing: list[str]) -> bool:
    """
    zenity / kdialog 로 설치 확인 다이얼로그 표시.
    둘 다 없으면 True (설치 진행) 로 fallback.
    """
    pkg_list = "\n".join(f"  • {p}" for p in missing)
    message  = tr("dialog.required_packages", packages=pkg_list)

    if shutil.which("zenity"):
        result = subprocess.run([
            "zenity", "--question",
            f"--text={message}",
            f"--title={tr('app.install_packages_title')}",
            "--width=420",
            f"--ok-label={tr('dialog.install')}",
            f"--cancel-label={tr('dialog.cancel')}",
        ])
        return result.returncode == 0

    if shutil.which("kdialog"):
        result = subprocess.run([
            "kdialog", "--yesno", message,
            "--title", tr("app.install_packages_title"),
        ])
        return result.returncode == 0

    return True  # 다이얼로그 도구 없음 → 진행


# ==============================================================================
# 실행 핸들러
# ==============================================================================

# 심볼릭 링크 임시 디렉토리 추적
_tmp_symlink_dir: str | None = None


def handle_run(apprunx: str, extra_args: list[str], flags: dict) -> int:
    global _tmp_symlink_dir
    _tmp_symlink_dir = None

    app_id, mount_path, box, _portable_targets, inherit_targets = _resolve_runtime_paths(apprunx, flags)
    libapprun.ensure_box_path(box)
    _inherit_box(app_id, box, inherit_targets)

    if not ensure_base_packages(apprunx):
        return 1

    if libapprun.is_locked_path(box):
        libapprun.show_gui_alert(tr("app.title"), tr("alert.app_preparing", app_id=app_id), "warning")
        return 1

    if libapprun.is_mounted(str(mount_path)):
        try:
            libapprun.unmount(str(mount_path))
        except Exception as e:
            libapprun.show_gui_alert(tr("app.error_title"), tr("alert.old_unmount_failed", error=e), "error")
            return 1

    try:
        libapprun.mount(apprunx, str(mount_path))
    except RuntimeError as e:
        libapprun.show_gui_alert(tr("app.error_title"), tr("error.mount_failed", error=e), "error")
        return 1

    bundle      = str(mount_path)
    prepare_code = handle_prepare(apprunx, mount_path, box, register=False, unmount=False)
    if prepare_code != 0:
        return prepare_code

    meta = libapprun.get_bundle_meta(bundle)
    cmd  = _build_cmd(bundle, app_id, meta, box)
    if cmd is None:
        print(tr("error.entry_missing_path", path=bundle), file=sys.stderr)
        return 10

    cmd = _wrap_root(cmd, meta)
    cmd = _wrap_terminal(cmd, meta)
    cmd = _wrap_screen(cmd, meta, app_id)

    # box 에 마운트 포인트 다이제스트 파일로 apprunx 위치 저장
    rundir             = box / ".run"
    mountpoint_digest  = hashlib.sha256(str(mount_path).encode()).hexdigest()
    try:
        rundir.mkdir(parents=True, exist_ok=True)
        rundir.joinpath(mountpoint_digest).write_text(os.path.abspath(apprunx))
    except Exception as e:
        print(tr("warning.run_dir_write_failed", error=e), file=sys.stderr)

    start  = time.time()
    result = None
    try:
        result = subprocess.run(cmd + extra_args)
    except KeyboardInterrupt:
        print(tr("error.run_cancelled"), file=sys.stderr)
    finally:
        try:
            libapprun.unmount(str(mount_path))
        except Exception as e:
            print(tr("error.run_unmount_failed", error=e), file=sys.stderr)

        digest_file = rundir.joinpath(mountpoint_digest)
        if digest_file.exists():
            try:
                digest_file.unlink()
            except Exception as e:
                print(tr("warning.run_dir_delete_failed", error=e), file=sys.stderr)
        else:
            print(tr("warning.run_dir_missing", path=digest_file), file=sys.stderr)

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


def _build_cmd(bundle: str, app_id: str, meta: dict, box: Path) -> list[str] | None:
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
        venv_py = str(box / "pyvenv" / "bin" / "python3")
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

    if not libapprun.can_use_dbus_and_gui():
        print(tr("error.terminal_gui_missing"), file=sys.stderr)
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
        tr("app.error_title"),
        tr("alert.terminal_missing"),
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
        libapprun.show_gui_alert(tr("app.error_title"), tr("alert.screen_required"), "error")
        sys.exit(127)

    libapprun.show_gui_alert(
        tr("app.info_title"),
        tr("alert.screen_recommended"),
        "warning",
    )
    return cmd


def _detect_crash(meta: dict, exit_code: int, duration: float) -> None:
    if meta.get("type", "") != "Application":
        return
    if exit_code != 0:
        libapprun.show_gui_alert(
            tr("app.crash_title"),
            tr("alert.app_crashed", exit_code=exit_code),
            "error",
        )
    elif duration < 1.0:
        libapprun.show_gui_alert(
            tr("app.abnormal_exit_title"),
            tr("alert.app_exited_too_fast"),
            "warning",
        )


def _register_desktop(bundle: str, app_id: str, box: Path) -> None:
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

    apprunx_ref  = box / "source.path"
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
    """번들 내 services/ 폴더의 .service 파일들을 system store 에 복사 후 systemd 에 링크."""
    try:
        file_list = libapprun.list_files(apprunx)
    except Exception as e:
        print(tr("error.bundle_file_list_failed", error=e), file=sys.stderr)
        return 1

    service_files = [
        f for f in file_list
        if f.startswith("services/") and f.endswith(".service")
    ]
    if not service_files:
        print(tr("error.no_service_files"), file=sys.stderr)
        return 1

    if os.geteuid() != 0:
        return _reexec_privileged(apprunx)

    actions   = (["enable"] if enable else []) + (["start"] if start else [])
    installed: list[str] = []

    if os.geteuid() == 0:
        SYSTEM_SERVICE_STORE_DIR.mkdir(parents=True, exist_ok=True)
        SYSTEMD_UNIT_DIR.mkdir(parents=True, exist_ok=True)
        for svc_path in service_files:
            svc_name = Path(svc_path).name
            try:
                data = libapprun.peek_file_bytes(apprunx, svc_path)
            except FileNotFoundError:
                print(tr("warning.service_read_failed", path=svc_path), file=sys.stderr)
                continue
            stored_unit = SYSTEM_SERVICE_STORE_DIR / svc_name
            dest = SYSTEMD_UNIT_DIR / svc_name
            stored_unit.write_bytes(data)
            stored_unit.chmod(0o644)
            _replace_symlink(dest, stored_unit)
            installed.append(svc_name)
            print(tr("service.installed_item", dest=dest, stored=stored_unit))

        if not installed:
            print(tr("error.no_installable_services"), file=sys.stderr)
            return 1

        _systemctl_daemon_reload()
        if actions:
            result = _systemctl_batch(actions, installed)
            if result != 0:
                return result
    else:
        tmp_map: list[tuple[str, Path, Path]] = []  # (tmp_path, stored_unit, dest)
        try:
            for svc_path in service_files:
                svc_name = Path(svc_path).name
                try:
                    data = libapprun.peek_file_bytes(apprunx, svc_path)
                except FileNotFoundError:
                    print(tr("warning.service_read_failed", path=svc_path), file=sys.stderr)
                    continue
                tmp = _prepare_temp_file(data)
                stored_unit = SYSTEM_SERVICE_STORE_DIR / svc_name
                dest = SYSTEMD_UNIT_DIR / svc_name
                tmp_map.append((tmp, stored_unit, dest))
                installed.append(svc_name)
                print(tr("service.installed_item", dest=dest, stored=stored_unit))

            if not installed:
                print(tr("error.no_installable_services"), file=sys.stderr)
                return 1

            script_parts: list[str] = [
                f"mkdir -p {shlex.quote(str(SYSTEM_SERVICE_STORE_DIR))} {shlex.quote(str(SYSTEMD_UNIT_DIR))}"
            ]
            for tmp, stored_unit, dest in tmp_map:
                script_parts += [
                    f"mv {shlex.quote(tmp)} {shlex.quote(str(stored_unit))}",
                    f"chmod 644 {shlex.quote(str(stored_unit))}",
                    f"ln -sfn {shlex.quote(str(stored_unit))} {shlex.quote(str(dest))}",
                ]
            script_parts.append("systemctl daemon-reload")
            for action in actions:
                script_parts.append(f"systemctl {action} {' '.join(installed)}")

            if not _run_privileged("; ".join(script_parts)):
                return 1
        finally:
            for tmp, _, _ in tmp_map:
                Path(tmp).unlink(missing_ok=True)

    print(tr("service.install_complete_count", count=len(installed)))
    if not actions:
        print(tr("service.enable_hint"))
    return 0

# ==============================================================================
# 서비스 생성 후 설치 핸들러
# ==============================================================================

def _sanitize_service_name(app_id: str) -> str:
    """app_id 의 특수문자를 '-' 로 치환하여 서비스 이름으로 사용."""
    return re.sub(r"[^.A-Za-z0-9_\-]", "-", app_id)


def _parse_generated_service_spec(
    spec: str | None,
    usage_flag: str,
    default_type: str | None = None,
) -> tuple[str, str, str] | None:
    """
    <type>,<after>+<after>,<before>+<before> 형식의 생성 서비스 설정을 파싱.
    반환값은 (service_type, after_units, before_units).
    """
    if spec is None and default_type is not None:
        spec = default_type

    parts = (spec or "").split(",")
    if not parts[0].strip():
        print(tr("error.service_type_missing"), file=sys.stderr)
        print(tr("usage.generated_service", flag=usage_flag), file=sys.stderr)
        return None

    svc_type    = parts[0].strip()
    valid_types = ("simple", "oneshot", "forking", "notify", "idle")
    if svc_type not in valid_types:
        print(tr("error.unknown_service_type", type=svc_type), file=sys.stderr)
        print(tr("service.supported_types", types=", ".join(valid_types)), file=sys.stderr)
        return None

    after_units  = " ".join(parts[1].strip().split("+")) if len(parts) >= 2 and parts[1].strip() else ""
    before_units = " ".join(parts[2].strip().split("+")) if len(parts) >= 3 and parts[2].strip() else ""
    return svc_type, after_units, before_units


def _get_user_systemd_env(username: str) -> dict[str, str] | None:
    """
    SSH 등 비대화형 환경에서도 systemctl --user 가 동작하도록
    필요한 환경변수를 추론하여 반환. 실패 시 None 반환.
    """
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        print(tr("error.user_not_found", user=username), file=sys.stderr)
        return None

    env         = os.environ.copy()
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{pw.pw_uid}"

    if not Path(xdg_runtime).is_dir():
        print(
            tr("error.xdg_runtime_missing", path=xdg_runtime, user=username),
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
                tr("error.dbus_socket_missing", user=username),
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

    print(tr("service.enabling_linger", user=username), file=sys.stderr)

    cmd = _sudo_cmd() + ["loginctl", "enable-linger", username]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(
            tr("warning.linger_failed", user=username),
            file=sys.stderr,
        )
        return False

    return True

def _prepare_temp_file(data: bytes) -> str:
    """data 를 임시파일에 기록하고 경로 반환. 권한 상승 불필요."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        return f.name


def _prepare_temp_copy(src: str) -> str:
    """src 를 임시파일에 복사하고 경로 반환. 권한 상승 불필요."""
    fd, tmp_path = tempfile.mkstemp()
    os.close(fd)
    shutil.copy2(src, tmp_path)
    return tmp_path


def _user_service_store_dir(username: str) -> Path:
    return Path(f"~{username}").expanduser() / ".local" / "share" / "services.apprd"


def _stored_service_paths(store_dir: Path, svc_name: str) -> tuple[Path, Path]:
    return store_dir / f"{svc_name}.apprunx", store_dir / f"{svc_name}.service"


def _user_gui_startup_store_dir(username: str) -> Path:
    return Path(f"~{username}").expanduser() / ".local" / "share" / "services.apprd" / "gui-startup"


def _user_gui_startup_dir(username: str) -> Path:
    return Path(f"~{username}").expanduser() / ".config" / "autostart"


def _stored_gui_startup_paths(store_dir: Path, desktop_name: str) -> tuple[Path, Path]:
    return store_dir / f"{desktop_name}.apprunx", store_dir / f"{desktop_name}.desktop"


def _chown_to_user(path: Path, username: str) -> None:
    """root 로 user 홈 내부에 만든 파일/디렉터리 소유권을 대상 user 로 맞춤."""
    if os.geteuid() != 0:
        return

    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return

    home = Path(pw.pw_dir)
    chain: list[Path] = []
    current = path
    while current != home and current.parent != current:
        chain.append(current)
        current = current.parent

    if current != home:
        chain = [path]

    for item in reversed(chain):
        if item.exists() or item.is_symlink():
            try:
                os.chown(item, pw.pw_uid, pw.pw_gid, follow_symlinks=False)
            except OSError:
                pass


def _desktop_value(value: object) -> str:
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def _desktop_exec_quote_arg(value: str | Path) -> str:
    """
    Quote one argument for a Desktop Entry Exec line.
    Desktop Exec is not a shell command, but quoted args preserve whitespace and
    literal quote/backslash characters for the desktop launcher tokenizer.
    """
    text = str(value)
    if text and not re.search(r'[\s"\\]', text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _format_desktop_exec(args: list[str | Path]) -> str:
    return " ".join(_desktop_exec_quote_arg(arg) for arg in args)


def _gui_startup_exec_args(
    stored_bundle: Path,
    apprun_args: list[str] | None = None,
    run_args: list[str] | None = None,
) -> list[str | Path]:
    return [
        "/usr/bin/apprun3",
        *(apprun_args or []),
        stored_bundle,
        *(run_args or []),
    ]


def _build_gui_startup_desktop(
    apprunx: str,
    stored_bundle: Path,
    app_id: str,
    apprun_args: list[str] | None = None,
    run_args: list[str] | None = None,
) -> bytes:
    meta = libapprun.get_bundle_meta(apprunx)
    name = _desktop_value(meta.get("name", app_id)) or app_id
    comment = _desktop_value(meta.get("description", ""))
    exec_args = _gui_startup_exec_args(stored_bundle, apprun_args, run_args)

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={name}",
        f"Comment={comment}",
        f"Exec={_format_desktop_exec(exec_args)}",
        f"Icon={_desktop_value(app_id)}",
        "Terminal=false",
        "Hidden=false",
        "X-GNOME-Autostart-enabled=true",
        f"StartupWMClass={_desktop_value(app_id)}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _replace_symlink(link_path: Path, target_path: Path) -> None:
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    link_path.symlink_to(target_path)


def _quote_paths(paths: list[Path]) -> str:
    return " ".join(shlex.quote(str(path)) for path in paths)


def _remove_paths(paths: list[Path], use_privilege: bool = False) -> None:
    existing = [path for path in paths if path.exists() or path.is_symlink()]
    if not existing:
        return
    if os.geteuid() == 0 or not use_privilege:
        for path in existing:
            path.unlink(missing_ok=True)
    else:
        _run_privileged(f"rm -f {_quote_paths(existing)}")


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
    - 지정 user == 현재 실제 user  →  ~/.local/share/services.apprd 에 복사 후 user systemd 에 링크
    - 지정 user != 현재 실제 user  →  /usr/share/services.apprd/system 에 복사 후 systemd 에 링크
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
    parsed = _parse_generated_service_spec(spec, "--install-as-service")
    if parsed is None:
        return 1
    svc_type, after_units, before_units = parsed

    if not user_mode and os.geteuid() != 0:
        return _reexec_privileged(apprunx)

    # ── 설치 경로 결정 ─────────────────────────────────────────────────────
    if user_mode:
        store_dir = _user_service_store_dir(resolved_user)
        dest_dir  = Path(f"~{resolved_user}").expanduser() / ".config" / "systemd" / "user"
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not _can_escalate():
            print(tr("error.root_required_service_install"), file=sys.stderr)
            return 1
        store_dir = SYSTEM_SERVICE_STORE_DIR
        dest_dir  = SYSTEMD_UNIT_DIR

    svc_name = _sanitize_service_name(app_id)
    stored_bundle, stored_unit = _stored_service_paths(store_dir, svc_name)
    dest = dest_dir / f"{svc_name}.service"

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
        f"ExecStart=/usr/bin/apprun3 {stored_bundle}",
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
        store_dir.mkdir(parents=True, exist_ok=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(apprunx_abs, stored_bundle)
        stored_unit.write_bytes(unit_bytes)
        stored_bundle.chmod(0o644)
        stored_unit.chmod(0o644)
        _replace_symlink(dest, stored_unit)
        _systemctl_daemon_reload(user_mode=True, env=user_env)
        if actions:
            result = _systemctl_batch(actions, [svc_name], user_mode=True, env=user_env)
            if result != 0:
                return result
    elif os.geteuid() == 0:
        store_dir.mkdir(parents=True, exist_ok=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(apprunx_abs, stored_bundle)
        stored_unit.write_bytes(unit_bytes)
        stored_bundle.chmod(0o644)
        stored_unit.chmod(0o644)
        _replace_symlink(dest, stored_unit)
        _systemctl_daemon_reload()
        if actions:
            result = _systemctl_batch(actions, [svc_name])
            if result != 0:
                return result
    else:
        tmp_unit = _prepare_temp_file(unit_bytes)
        tmp_bundle = _prepare_temp_copy(apprunx_abs)
        try:
            script_parts = [
                f"mkdir -p {shlex.quote(str(store_dir))} {shlex.quote(str(dest_dir))}",
                f"mv {shlex.quote(tmp_bundle)} {shlex.quote(str(stored_bundle))}",
                f"mv {shlex.quote(tmp_unit)} {shlex.quote(str(stored_unit))}",
                f"chmod 644 {shlex.quote(str(stored_bundle))} {shlex.quote(str(stored_unit))}",
                f"ln -sfn {shlex.quote(str(stored_unit))} {shlex.quote(str(dest))}",
                "systemctl daemon-reload",
            ] + [f"systemctl {a} {svc_name}" for a in actions]

            if not _run_privileged("; ".join(script_parts)):
                return 1
        finally:
            Path(tmp_unit).unlink(missing_ok=True)
            Path(tmp_bundle).unlink(missing_ok=True)

    # ── 완료 출력 ──────────────────────────────────────────────────────────
    print(tr("service.install_complete", mode="user" if user_mode else "system", name=svc_name))
    print(tr("label.type", value=svc_type))
    if after_units:
        print(tr("label.after", value=after_units))
    if before_units:
        print(tr("label.before", value=before_units))
    print(tr("label.bundle", value=stored_bundle))
    print(tr("label.unit", value=f"{dest} -> {stored_unit}"))

    if not enable or not start:
        flag = " --user" if user_mode else ""
        print(tr("service.enable_command", flag=flag, name=svc_name))
    return 0


def handle_install_as_global_user_service(
    apprunx: str,
    spec: str | None,
    enable: bool,
    start: bool,
) -> int:
    """
    systemd global user unit 을 /usr/share/services.apprd/global 에 생성 후 /etc/systemd/user 에 링크.
    --enable 이 지정되면 systemctl --global enable 로 모든 사용자에게 기본 활성화.
    """
    parsed = _parse_generated_service_spec(
        spec,
        "--install-as-global-user-service",
        default_type="simple",
    )
    if parsed is None:
        return 1
    svc_type, after_units, before_units = parsed

    if os.geteuid() != 0:
        return _reexec_privileged(apprunx)

    app_id      = libapprun.get_bundle_id(apprunx)
    apprunx_abs = str(Path(apprunx).resolve())
    svc_name    = _sanitize_service_name(app_id)
    store_dir   = GLOBAL_USER_SERVICE_STORE_DIR
    stored_bundle, stored_unit = _stored_service_paths(store_dir, svc_name)
    dest        = SYSTEMD_GLOBAL_USER_UNIT_DIR / f"{svc_name}.service"

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
        f"ExecStart=/usr/bin/apprun3 {stored_bundle}",
    ]
    if svc_type == "oneshot":
        service_lines.append("RemainAfterExit=yes")

    install_lines = ["", "[Install]", "WantedBy=default.target"]
    unit_bytes    = ("\n".join(unit_lines + service_lines + install_lines) + "\n").encode("utf-8")

    if os.geteuid() == 0:
        store_dir.mkdir(parents=True, exist_ok=True)
        SYSTEMD_GLOBAL_USER_UNIT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(apprunx_abs, stored_bundle)
        stored_unit.write_bytes(unit_bytes)
        stored_bundle.chmod(0o644)
        stored_unit.chmod(0o644)
        _replace_symlink(dest, stored_unit)
    else:
        tmp_unit = _prepare_temp_file(unit_bytes)
        tmp_bundle = _prepare_temp_copy(apprunx_abs)
        try:
            script_parts = [
                f"mkdir -p {shlex.quote(str(store_dir))} {shlex.quote(str(SYSTEMD_GLOBAL_USER_UNIT_DIR))}",
                f"mv {shlex.quote(tmp_bundle)} {shlex.quote(str(stored_bundle))}",
                f"mv {shlex.quote(tmp_unit)} {shlex.quote(str(stored_unit))}",
                f"chmod 644 {shlex.quote(str(stored_bundle))} {shlex.quote(str(stored_unit))}",
                f"ln -sfn {shlex.quote(str(stored_unit))} {shlex.quote(str(dest))}",
            ]
            if not _run_privileged("; ".join(script_parts)):
                return 1
        finally:
            Path(tmp_unit).unlink(missing_ok=True)
            Path(tmp_bundle).unlink(missing_ok=True)

    if enable or start:
        if os.geteuid() == 0:
            proc = subprocess.run(
                ["systemctl", "--global", "enable", f"{svc_name}.service"],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                print(tr("error.systemctl_global_enable_failed", error=proc.stderr), file=sys.stderr)
                return proc.returncode
        else:
            if not _run_privileged(f"systemctl --global enable {shlex.quote(svc_name + '.service')}"):
                return 1

    print(tr("service.global_install_complete", name=svc_name))
    print(tr("label.type", value=svc_type))
    if after_units:
        print(tr("label.after", value=after_units))
    if before_units:
        print(tr("label.before", value=before_units))
    print(tr("label.bundle", value=stored_bundle))
    print(tr("label.unit", value=f"{dest} -> {stored_unit}"))

    if start:
        print(tr("service.global_start_note"))
        print(tr("service.global_start_current_user_hint", name=svc_name))
    elif not enable:
        print(tr("service.global_enable_command", name=svc_name))
    else:
        print(tr("service.global_reload_note"))
    return 0


def handle_uninstall_as_global_user_service(apprunx: str) -> int:
    """--install-as-global-user-service 로 생성된 global user 서비스를 비활성화·삭제."""
    app_id   = libapprun.get_bundle_id(apprunx)
    svc_base = _sanitize_service_name(app_id)
    svc_name = f"{svc_base}.service"
    stored_bundle, stored_unit = _stored_service_paths(GLOBAL_USER_SERVICE_STORE_DIR, svc_base)
    dest = SYSTEMD_GLOBAL_USER_UNIT_DIR / svc_name

    if not (dest.exists() or dest.is_symlink() or stored_unit.exists()):
        print(tr("error.service_file_missing", path=dest), file=sys.stderr)
        return 1

    if not _can_escalate():
        print(tr("error.root_required_global_user_remove"), file=sys.stderr)
        return 1

    if os.geteuid() == 0:
        subprocess.run(["systemctl", "--global", "disable", svc_name],
                       capture_output=True)
        _remove_paths([dest, stored_unit, stored_bundle])
    else:
        script = (
            f"systemctl --global disable {shlex.quote(svc_name)}; "
            f"rm -f {shlex.quote(str(dest))} "
            f"{shlex.quote(str(stored_unit))} "
            f"{shlex.quote(str(stored_bundle))}"
        )
        if not _run_privileged(script):
            return 1

    print(tr("service.global_remove_complete", name=svc_name))
    print(tr("service.global_reload_note"))
    print(tr("service.stop_running_hint", name=svc_name))
    return 0


# ==============================================================================
# GUI autostart 생성/제거 핸들러
# ==============================================================================

def _normalize_gui_startup_scope(scope: str | None) -> str | None:
    resolved = "user" if scope is None else scope.strip().lower()
    if resolved not in ("user", "global"):
        print(tr("error.gui_startup_scope"), file=sys.stderr)
        print(tr("usage.gui_startup"), file=sys.stderr)
        return None
    return resolved


def _parse_startup_args(raw: str, option_name: str) -> list[str]:
    """
    Compact argument strings accept shell-like quoting.
    If no whitespace is present and commas are used, treat commas as separators
    for convenience: --runargs-start=--a=x,--b=y,positional
    """
    value = raw.strip()
    if not value:
        return []

    if "," in value and not any(ch.isspace() for ch in value):
        return [part for part in value.split(",") if part]

    try:
        return shlex.split(value)
    except ValueError as exc:
        print(tr("error.option_parse_failed", option=option_name, error=exc), file=sys.stderr)
        sys.exit(2)


def _gui_startup_launch_env(username: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if username is None:
        return env

    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return env

    env["HOME"] = pw.pw_dir
    env["USER"] = username
    env["LOGNAME"] = username

    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{pw.pw_uid}"
    if Path(runtime_dir).is_dir():
        env["XDG_RUNTIME_DIR"] = runtime_dir
        bus = Path(runtime_dir) / "bus"
        if not env.get("DBUS_SESSION_BUS_ADDRESS") and bus.exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"

    return env


def _start_gui_startup_exec(exec_args: list[str | Path], username: str | None = None) -> bool:
    cmd = [str(arg) for arg in exec_args]
    env = _gui_startup_launch_env(username)

    if username is not None:
        try:
            pw = pwd.getpwnam(username)
        except KeyError:
            print(tr("error.user_not_found", user=username), file=sys.stderr)
            return False

        if os.geteuid() == 0 and pw.pw_uid != 0:
            if shutil.which("runuser"):
                cmd = ["runuser", "-u", username, "--", *cmd]
            elif shutil.which("sudo"):
                cmd = ["sudo", "-u", username, *cmd]
            else:
                print(tr("warning.no_runuser_sudo"), file=sys.stderr)
                return False

    try:
        subprocess.Popen(cmd, env=env, start_new_session=True)
    except OSError as exc:
        print(tr("error.gui_startup_launch_failed", error=exc), file=sys.stderr)
        return False

    print(tr("gui_startup.launched", cmd=_format_desktop_exec(exec_args)))
    return True


def handle_install_as_gui_startup(
    apprunx: str,
    scope: str | None,
    user: str | None,
    start: bool,
    apprun_args: list[str] | None = None,
    run_args: list[str] | None = None,
) -> int:
    """
    .desktop autostart 엔트리를 생성.
    - user   →  ~/.config/autostart
    - global →  /etc/xdg/autostart
    """
    resolved_scope = _normalize_gui_startup_scope(scope)
    if resolved_scope is None:
        return 1

    app_id       = libapprun.get_bundle_id(apprunx)
    desktop_base = _sanitize_service_name(app_id)
    desktop_name = f"{desktop_base}.desktop"
    apprunx_abs  = str(Path(apprunx).resolve())

    if resolved_scope == "global":
        launch_user = get_real_user()
        if os.geteuid() != 0:
            return _reexec_privileged(apprunx)
        store_dir = GLOBAL_GUI_STARTUP_STORE_DIR
        dest_dir  = GLOBAL_GUI_STARTUP_DIR
        owner_user = None
    else:
        real_user     = get_real_user()
        resolved_user = real_user if user is None else user
        if resolved_user != real_user and os.geteuid() != 0:
            return _reexec_privileged(apprunx)
        try:
            pwd.getpwnam(resolved_user)
        except KeyError:
            print(tr("error.user_not_found", user=resolved_user), file=sys.stderr)
            return 1
        store_dir = _user_gui_startup_store_dir(resolved_user)
        dest_dir  = _user_gui_startup_dir(resolved_user)
        owner_user = resolved_user
        launch_user = resolved_user

    stored_bundle, stored_desktop = _stored_gui_startup_paths(store_dir, desktop_base)
    dest = dest_dir / desktop_name
    exec_args = _gui_startup_exec_args(stored_bundle, apprun_args, run_args)
    desktop_bytes = _build_gui_startup_desktop(
        apprunx,
        stored_bundle,
        app_id,
        apprun_args=apprun_args,
        run_args=run_args,
    )

    store_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(apprunx_abs, stored_bundle)
    stored_desktop.write_bytes(desktop_bytes)
    shutil.copy2(stored_desktop, dest)
    stored_bundle.chmod(0o644)
    stored_desktop.chmod(0o644)
    dest.chmod(0o644)

    if owner_user is not None:
        for path in (store_dir, dest_dir, stored_bundle, stored_desktop, dest):
            _chown_to_user(path, owner_user)

    print(tr("gui_startup.install_complete", scope=resolved_scope, name=desktop_name))
    print(tr("label.bundle", value=stored_bundle))
    print(tr("label.item", value=dest))
    if apprun_args:
        print(tr("label.apprun_args", value=" ".join(shlex.quote(arg) for arg in apprun_args)))
    if run_args:
        print(tr("label.run_args", value=" ".join(shlex.quote(arg) for arg in run_args)))

    if start and not _start_gui_startup_exec(exec_args, launch_user):
        return 1

    return 0


def handle_uninstall_as_gui_startup(
    apprunx: str,
    scope: str | None,
    user: str | None,
) -> int:
    """--install-as-gui-startup 로 생성된 .desktop autostart 엔트리를 제거."""
    resolved_scope = _normalize_gui_startup_scope(scope)
    if resolved_scope is None:
        return 1

    app_id       = libapprun.get_bundle_id(apprunx)
    desktop_base = _sanitize_service_name(app_id)
    desktop_name = f"{desktop_base}.desktop"

    if resolved_scope == "global":
        if os.geteuid() != 0:
            return _reexec_privileged(apprunx)
        store_dir = GLOBAL_GUI_STARTUP_STORE_DIR
        dest = GLOBAL_GUI_STARTUP_DIR / desktop_name
    else:
        real_user     = get_real_user()
        resolved_user = real_user if user is None else user
        if resolved_user != real_user and os.geteuid() != 0:
            return _reexec_privileged(apprunx)
        try:
            pwd.getpwnam(resolved_user)
        except KeyError:
            print(tr("error.user_not_found", user=resolved_user), file=sys.stderr)
            return 1
        store_dir = _user_gui_startup_store_dir(resolved_user)
        dest = _user_gui_startup_dir(resolved_user) / desktop_name

    stored_bundle, stored_desktop = _stored_gui_startup_paths(store_dir, desktop_base)

    if not (dest.exists() or stored_desktop.exists() or stored_bundle.exists()):
        print(tr("error.gui_startup_file_missing", path=dest), file=sys.stderr)
        return 1

    _remove_paths([dest, stored_desktop, stored_bundle])
    print(tr("gui_startup.remove_complete", scope=resolved_scope, name=desktop_name))
    return 0

# ==============================================================================
# 서비스 단순 제거 핸들러
# ==============================================================================

def handle_uninstall_services(apprunx: str) -> int:
    """번들 내 services/ 폴더에 해당하는 시스템 서비스를 중지·비활성화·삭제."""
    try:
        file_list = libapprun.list_files(apprunx)
    except Exception as e:
        print(tr("error.bundle_file_list_failed", error=e), file=sys.stderr)
        return 1

    service_files = [
        Path(f).name for f in file_list
        if f.startswith("services/") and f.endswith(".service")
    ]
    if not service_files:
        print(tr("error.no_service_files"), file=sys.stderr)
        return 1

    if not _can_escalate():
        print(tr("error.root_required_service_remove"), file=sys.stderr)
        return 1

    removed = []
    for svc_name in service_files:
        dest = SYSTEMD_UNIT_DIR / svc_name
        stored_unit = SYSTEM_SERVICE_STORE_DIR / svc_name
        if not (dest.exists() or dest.is_symlink() or stored_unit.exists()):
            print(tr("service.skipped_not_installed", name=svc_name))
            continue

        _systemctl_stop_disable(svc_name)
        _remove_paths([dest, stored_unit], use_privilege=True)
        removed.append(svc_name)
        print(tr("service.removed_item", name=svc_name))

    _systemctl_daemon_reload()
    print(tr("service.remove_complete_count", count=len(removed)))
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

    svc_base = _sanitize_service_name(app_id)
    svc_name = f"{svc_base}.service"

    if user_mode:
        store_dir = _user_service_store_dir(resolved_user)
        dest = (
            Path(f"~{resolved_user}").expanduser()
            / ".config" / "systemd" / "user"
            / svc_name
        )
    else:
        store_dir = SYSTEM_SERVICE_STORE_DIR
        dest = SYSTEMD_UNIT_DIR / svc_name

    stored_bundle, stored_unit = _stored_service_paths(store_dir, svc_base)

    if not (dest.exists() or dest.is_symlink() or stored_unit.exists()):
        print(tr("error.service_file_missing", path=dest), file=sys.stderr)
        return 1

    if user_mode:
        user_env = _get_user_systemd_env(resolved_user)
        if user_env is None:
            return 1
        _systemctl_stop_disable(svc_name, user_mode=True, env=user_env)
        _remove_paths([dest, stored_unit, stored_bundle])
        _systemctl_daemon_reload(user_mode=True, env=user_env)
    else:
        if not _can_escalate():
            print(tr("error.root_required_service_remove"), file=sys.stderr)
            return 1
        if not _run_privileged(
                f"systemctl stop {svc_name}; "
                f"systemctl disable {svc_name}; "
                f"rm -f {shlex.quote(str(dest))} "
                f"{shlex.quote(str(stored_unit))} "
                f"{shlex.quote(str(stored_bundle))}; "
                f"systemctl daemon-reload"
        ):
            return 1

    mode_label = "user" if user_mode else "system"
    print(tr("service.remove_complete", mode=mode_label, name=svc_name))
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
        print(tr("error.command_failed", error=proc.stderr), file=sys.stderr)
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
                print(tr("error.systemctl_user_failed", action=action, error=proc.stderr), file=sys.stderr)
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
        _run_privileged(f"rm -f {shlex.quote(str(path))}")

# ==============================================================================
# 도움말
# ==============================================================================

def handle_help() -> int:
    print(tr("help.apprun3"), end="")
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
        elif arg == "--portable":
            flags["portable"] = ["mount", "box"]
        elif arg.startswith("--portable="):
            flags["portable"] = _parse_option_list(arg[len("--portable="):], PORTABLE_TARGETS, "--portable")
        elif arg == "--inherit":
            flags["inherit"] = ["full"]
        elif arg.startswith("--inherit="):
            flags["inherit"] = _parse_option_list(arg[len("--inherit="):], INHERIT_TARGETS, "--inherit")
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
        elif arg == "--install-as-global-user-service":
            flags["install_as_global_user_service"] = None
        elif arg.startswith("--install-as-global-user-service="):
            flags["install_as_global_user_service"] = arg[len("--install-as-global-user-service="):]
        elif arg == "--uninstall-as-global-user-service":
            flags["uninstall_as_global_user_service"] = True
        elif arg == "--install-as-gui-startup":
            flags["install_as_gui_startup"] = None
        elif arg.startswith("--install-as-gui-startup="):
            flags["install_as_gui_startup"] = arg[len("--install-as-gui-startup="):]
        elif arg == "--uninstall-as-gui-startup":
            flags["uninstall_as_gui_startup"] = None
        elif arg.startswith("--uninstall-as-gui-startup="):
            flags["uninstall_as_gui_startup"] = arg[len("--uninstall-as-gui-startup="):]
        elif arg.startswith("--apprunargs="):
            flags.setdefault("gui_startup_apprun_args", []).extend(
                _parse_startup_args(arg[len("--apprunargs="):], "--apprunargs")
            )
        elif arg.startswith("--apprunarg="):
            flags.setdefault("gui_startup_apprun_args", []).append(arg[len("--apprunarg="):])
        elif arg.startswith("--runargs-start="):
            flags.setdefault("gui_startup_run_args", []).extend(
                _parse_startup_args(arg[len("--runargs-start="):], "--runargs-start")
            )
        elif arg.startswith("--runarg="):
            flags.setdefault("gui_startup_run_args", []).append(arg[len("--runarg="):])
        elif arg.startswith("--user=") and (
            "install_as_service" in flags
            or "uninstall_as_service" in flags
            or "install_as_gui_startup" in flags
            or "uninstall_as_gui_startup" in flags
        ):
            flags["service_install_user"] = arg[len("--user="):]
        elif arg == "--uninstall-services":
            flags["uninstall_services"] = True
        elif arg == "--uninstall-as-service":
            flags["uninstall_as_service"] = True
        else:
            print(tr("error.unknown_option", option=arg), file=sys.stderr)
            sys.exit(2)

        remaining.pop(i)

    if "help" in flags:
        return flags, None, []

    has_from = "extract_file_from" in flags
    has_to   = "extract_file_to"   in flags
    if has_from != has_to:
        print(tr("error.extract_options_together"), file=sys.stderr)
        sys.exit(2)

    has_gui_startup_args = (
        "gui_startup_apprun_args" in flags
        or "gui_startup_run_args" in flags
    )
    if has_gui_startup_args and "install_as_gui_startup" not in flags:
        print(tr("error.startup_args_require_install"), file=sys.stderr)
        sys.exit(2)

    if not remaining:
        print(tr("usage.apprun3_short"), file=sys.stderr)
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
        print(tr("error.file_not_found", path=apprunx), file=sys.stderr)
        sys.exit(1)

    if flags:
        if "id"          in flags: sys.exit(handle_id(apprunx))
        if "info"        in flags: sys.exit(handle_info(apprunx, flags["info"] or None))
        if "box_path"    in flags:
            _app_id, _mount_path, box, _portable_targets, _inherit_targets = _resolve_runtime_paths(apprunx, flags)
            sys.exit(handle_box_path(box))
        if "prepare"     in flags:
            app_id, mount_path, box, _portable_targets, inherit_targets = _resolve_runtime_paths(apprunx, flags)
            libapprun.ensure_box_path(box)
            _inherit_box(app_id, box, inherit_targets)
            sys.exit(handle_prepare(apprunx, mount_path, box, register=False))
        if "register"    in flags:
            app_id, mount_path, box, _portable_targets, inherit_targets = _resolve_runtime_paths(apprunx, flags)
            libapprun.ensure_box_path(box)
            _inherit_box(app_id, box, inherit_targets)
            sys.exit(handle_prepare(apprunx, mount_path, box, register=True))
        if "extract_file_from" in flags:
            sys.exit(handle_extract_file(apprunx, flags["extract_file_from"], flags["extract_file_to"]))
        if "install_services"   in flags:
            sys.exit(handle_install_services(apprunx, flags.get("service_install_and_enable", False), flags.get("service_install_and_start", False)))
        if "install_as_service" in flags:
            sys.exit(handle_install_as_service(apprunx, flags["install_as_service"], flags.get("service_install_and_enable", False), flags.get("service_install_and_start", False), flags.get("service_install_user")))
        if "install_as_global_user_service" in flags:
            sys.exit(handle_install_as_global_user_service(apprunx, flags["install_as_global_user_service"], flags.get("service_install_and_enable", False), flags.get("service_install_and_start", False)))
        if "uninstall_as_global_user_service" in flags:
            sys.exit(handle_uninstall_as_global_user_service(apprunx))
        if "install_as_gui_startup" in flags:
            sys.exit(handle_install_as_gui_startup(
                apprunx,
                flags["install_as_gui_startup"],
                flags.get("service_install_user"),
                flags.get("service_install_and_start", False),
                flags.get("gui_startup_apprun_args"),
                flags.get("gui_startup_run_args"),
            ))
        if "uninstall_as_gui_startup" in flags:
            sys.exit(handle_uninstall_as_gui_startup(apprunx, flags["uninstall_as_gui_startup"], flags.get("service_install_user")))
        if "uninstall_services"   in flags: sys.exit(handle_uninstall_services(apprunx))
        if "uninstall_as_service" in flags: sys.exit(handle_uninstall_as_service(apprunx, flags.get("service_install_user")))

    sys.exit(handle_run(apprunx, extra_args, flags))


if __name__ == "__main__":
    main()
