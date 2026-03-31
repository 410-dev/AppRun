#!/usr/bin/env python3
"""
apprun3-dropin — AppRun Format 3 DropIn 서비스 (시스템 데몬)
/usr/bin/apprun3-dropin

format3prober.conf.json 에 정의된 디렉터리들을 스캔/감시하여
.apprunx 번들의 .desktop 파일을 각 사용자의 Gnome App Grid 에 자동 등록합니다.

systemd 서비스로 root 권한 하에 실행되며, 장치의 모든 일반 사용자를 대상으로 합니다.
"""

import sys
import os
import json
import hashlib
import signal
import time
import pwd
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import libapprun

try:
    import pyinotify
except ImportError:
    print("Error: pyinotify 가 필요합니다. 'pip install pyinotify' 로 설치하세요.", file=sys.stderr)
    sys.exit(1)


# ==============================================================================
# 상수
# ==============================================================================

CONFIG_PATH         = "/etc/AppRun/format3prober.conf.json"
CACHE_BASE          = "/var/lib/apprun-dropin"       # 시스템 전역 캐시
CACHE_FILE          = Path(CACHE_BASE) / "desktop_hashes.json"
MIN_USER_UID        = 1000
NOLOGIN_SHELLS      = ("/usr/sbin/nologin", "/bin/false", "/sbin/nologin")
PASSWD_PATH         = "/etc/passwd"

DESKTOP_INNER_PATH  = "AppRunMeta/DesktopLinks/desktopfile.desktop"
ICON_INNER_PATH     = "AppRunMeta/DesktopLinks/Icon.png"


# ==============================================================================
# 사용자 검색
# ==============================================================================

class UserInfo:
    """시스템 사용자 한 명의 정보."""

    def __init__(self, username: str, uid: int, home: Path):
        self.username = username
        self.uid      = uid
        self.home     = home

    @property
    def desktop_dir(self) -> Path:
        return self.home / ".local/share/applications"

    @property
    def icons_dir(self) -> Path:
        return self.home / ".local/share/icons"

    def __repr__(self):
        return f"UserInfo({self.username}, uid={self.uid}, home={self.home})"

    def __eq__(self, other):
        return isinstance(other, UserInfo) and self.uid == other.uid

    def __hash__(self):
        return hash(self.uid)


def list_normal_users() -> list[UserInfo]:
    """
    /etc/passwd 에서 UID >= 1000 이고 유효한 홈 디렉터리와 로그인 셸을 가진
    일반 사용자 목록을 반환.
    """
    users = []
    for pw in pwd.getpwall():
        if pw.pw_uid < MIN_USER_UID:
            continue
        if pw.pw_shell in NOLOGIN_SHELLS:
            continue
        home = Path(pw.pw_dir)
        if not home.is_dir():
            continue
        # nobody 등 특수 계정 필터
        if pw.pw_name in ("nobody", "nogroup"):
            continue
        users.append(UserInfo(pw.pw_name, pw.pw_uid, home))
    return users


# ==============================================================================
# 설정 로드
# ==============================================================================

def load_config() -> dict:
    """
    format3prober.conf.json 원본을 반환.
    파일이 없으면 기본값으로 생성.
    """
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        print(f"WARNING: 설정 파일을 찾을 수 없습니다: {CONFIG_PATH}", file=sys.stderr)
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            default = {
                "global": ["/applications", "/opt/applications"],
                "user":   ["applications", ".local/applications"],
            }
            with open(config_path, "w") as f:
                json.dump(default, f, indent=4)
            print(f"기본 설정 파일이 생성되었습니다: {CONFIG_PATH}")
        except Exception as e:
            print(f"Error creating config file: {e}", file=sys.stderr)
            return {"global": [], "user": []}

    with open(config_path, "r") as f:
        return json.load(f)


def resolve_watch_dirs(config: dict, users: list[UserInfo]) -> dict[str, list[UserInfo]]:
    """
    설정의 global/user 경로를 실제 절대경로로 확장.
    반환값: { "<절대경로>": [해당 경로가 속한 UserInfo 목록 (global 이면 모든 사용자)] }

    global 경로는 모든 사용자에게 영향을 미침 (desktop 파일이 모든 사용자에게 등록됨).
    user 경로는 해당 사용자에게만 영향.
    """
    dir_to_users: dict[str, list[UserInfo]] = {}

    # global 디렉터리 → 모든 사용자
    for global_path in config.get("global", []):
        key = str(Path(global_path).resolve())
        if key not in dir_to_users:
            dir_to_users[key] = []
        for u in users:
            if u not in dir_to_users[key]:
                dir_to_users[key].append(u)

    # user 디렉터리 → 해당 사용자만
    for user_relpath in config.get("user", []):
        for u in users:
            abs_path = str((u.home / user_relpath).resolve())
            if abs_path not in dir_to_users:
                dir_to_users[abs_path] = []
            if u not in dir_to_users[abs_path]:
                dir_to_users[abs_path].append(u)

    return dir_to_users


# ==============================================================================
# 캐시 관리
# ==============================================================================

def load_cache() -> dict:
    """
    캐시 파일 로드.
    구조:
    {
        "<apprunx 절대경로>": {
            "desktop_hash": "...",
            "app_id": "...",
            "registered_users": ["username1", "username2", ...]
        }
    }
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache: dict) -> None:
    Path(CACHE_BASE).mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# ==============================================================================
# 해시 유틸
# ==============================================================================

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ==============================================================================
# 파일 소유권 유틸
# ==============================================================================

def _write_as_user(path: Path, content: str | bytes, user: UserInfo, mode: int = 0o644) -> None:
    """
    파일을 쓴 뒤 소유권을 해당 사용자로 변경.
    상위 디렉터리가 없으면 생성하고 소유권도 변경.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 상위 디렉터리 소유권 보정 (root 가 만들었으므로)
    _chown_parents(path, user)

    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    path.chmod(mode)
    os.chown(str(path), user.uid, -1)


def _chown_parents(path: Path, user: UserInfo) -> None:
    """
    path 의 상위 디렉터리 중 사용자 홈 하위에 있는 것들의 소유권을 보정.
    """
    home_str = str(user.home)
    current = path.parent
    dirs_to_fix = []
    while str(current).startswith(home_str) and current != user.home:
        dirs_to_fix.append(current)
        current = current.parent
    for d in reversed(dirs_to_fix):
        if d.exists():
            try:
                os.chown(str(d), user.uid, -1)
            except OSError:
                pass


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


# ==============================================================================
# .desktop 등록 / 해제
# ==============================================================================

def _build_desktop_content(
    apprunx_path: str,
    desktop_data: bytes,
    app_id: str,
    icon_extracted: bool,
) -> str:
    """
    .desktop 파일 원본 바이트를 받아 Exec, Icon, StartupWMClass 를 처리한
    최종 텍스트를 반환.
    """
    desktop_text = desktop_data.decode("utf-8", errors="replace")
    lines = desktop_text.splitlines()

    # Exec 처리
    processed = []
    has_exec = False
    for line in lines:
        if line.strip().startswith("Exec="):
            has_exec = True
            processed.append(f"Exec=apprun3 {apprunx_path}")
        else:
            processed.append(line)
    if not has_exec:
        processed.append(f"Exec=apprun3 {apprunx_path}")

    # Icon 처리
    final = []
    has_icon = False
    for line in processed:
        if line.strip().startswith("Icon="):
            has_icon = True
            if icon_extracted:
                final.append(f"Icon=apprun-{app_id}")
            else:
                final.append(line)
        else:
            final.append(line)

    if not has_icon:
        if icon_extracted:
            final.append(f"Icon=apprun-{app_id}")
        else:
            final.append("Icon=apprun-default")

    # StartupWMClass
    if not any(l.strip().startswith("StartupWMClass=") for l in final):
        final.append(f"StartupWMClass={app_id}")

    return "\n".join(final) + "\n"

def _generate_desktop_from_meta(apprunx_path: str) -> Optional[bytes]:
    """
    meta.json 을 읽어 .desktop 파일 내용을 생성.
    name 이 없으면 None 반환 (등록 불가).
    """
    meta = libapprun.get_bundle_meta(apprunx_path)
    if not meta:
        return None

    name = meta.get("name", "").strip()
    if not name:
        return None

    try:
        app_id = libapprun.get_bundle_id(apprunx_path)
    except Exception:
        app_id = Path(apprunx_path).stem

    app_type    = meta.get("type", "Application")
    description = meta.get("description", "")
    terminal    = "true" if meta.get("launch_in_terminal", False) else "false"
    args_launch = meta.get("desktopfile-args", [])

    # 각 args 에 quotation 으로 감싸기
    for i, arg in enumerate(args_launch):
        if not (arg.startswith('"') and arg.endswith('"')):
            args_launch[i] = f'"{arg}"'

    lines = [
        "[Desktop Entry]",
        f"Name={name}",
        f"Type={app_type}",
        f"Exec=apprun3 {apprunx_path} {' '.join(args_launch)}",
        f"Terminal={terminal}",
        f"StartupWMClass={app_id}",
        "Categories=Application;",
    ]

    if description:
        lines.append(f"Comment={description}")

    return ("\n".join(lines) + "\n").encode("utf-8")

def register_desktop(
    apprunx_path: str,
    target_users: list[UserInfo],
    cache: dict,
) -> bool:
    """
    .apprunx 에서 desktopfile.desktop 을 추출하여 대상 사용자들에게 등록.
    해시가 캐시와 동일하고 대상 사용자 목록에 변화가 없으면 스킵.
    반환값: 캐시가 변경되었으면 True.
    """
    apprunx_path = str(Path(apprunx_path).resolve())

    DEFAULT_ICON = Path("/usr/share/apprun/default-icon.png")

    # .desktop 파일 읽기 시도
    try:
        desktop_data = libapprun.peek_file_bytes(apprunx_path, DESKTOP_INNER_PATH)
    except (FileNotFoundError, RuntimeError):
        desktop_data = None

    # desktopfile.desktop 이 없으면 meta.json 으로 생성
    if desktop_data is None:
        desktop_data = _generate_desktop_from_meta(apprunx_path)
        if desktop_data is None:
            return False  # meta.json 도 없거나 name 이 없으면 스킵

    new_hash = hash_bytes(desktop_data)
    target_names = sorted(u.username for u in target_users)

    # 캐시 비교
    cached = cache.get(apprunx_path)
    if cached:
        if (cached.get("desktop_hash") == new_hash
                and sorted(cached.get("registered_users", [])) == target_names):
            return False  # 변경 없음

    # 번들 ID
    try:
        app_id = libapprun.get_bundle_id(apprunx_path)
    except Exception:
        app_id = Path(apprunx_path).stem

    # 아이콘 추출 (임시)
    icon_data: Optional[bytes] = None
    try:
        icon_data = libapprun.peek_file_bytes(apprunx_path, ICON_INNER_PATH)
    except (FileNotFoundError, RuntimeError):
        pass

    icon_extracted = icon_data is not None

    # .desktop 내용 생성
    content = _build_desktop_content(apprunx_path, desktop_data, app_id, icon_extracted)

    # 각 사용자에게 등록
    for user in target_users:

        desktop_file = user.desktop_dir / f"apprun-dropin-{app_id}.desktop"
        try:
            _write_as_user(desktop_file, content, user, mode=0o755)
        except OSError as e:
            print(f"[DropIn] 경고: {user.username} .desktop 쓰기 실패: {e}", file=sys.stderr)
            continue

        if icon_data is not None:
            icon_file = user.icons_dir / f"apprun-{app_id}.png"
            try:
                _write_as_user(icon_file, icon_data, user)
            except OSError as e:
                print(f"[DropIn] 경고: {user.username} 아이콘 쓰기 실패: {e}", file=sys.stderr)
        else:
            # 번들에 아이콘이 없으면 기본 아이콘 복사
            if DEFAULT_ICON.exists():
                default_dest = user.icons_dir / "apprun-default.png"
                if not default_dest.exists():
                    try:
                        _write_as_user(default_dest, DEFAULT_ICON.read_bytes(), user)
                    except OSError:
                        pass

    # 캐시 업데이트
    action = "업데이트" if cached else "등록"
    cache[apprunx_path] = {
        "desktop_hash": new_hash,
        "app_id": app_id,
        "registered_users": target_names,
    }

    print(f"[DropIn] {action}: {app_id} → {target_names}")
    try:
        libapprun.notify(f"[AppRun DropIn] 앱 {action}", app_id)
    except Exception:
        pass

    return True


def unregister_desktop(apprunx_path: str, cache: dict) -> bool:
    """
    캐시에 기록된 번들의 .desktop 파일 및 아이콘을 모든 등록 사용자에게서 삭제.
    반환값: 캐시가 변경되었으면 True.
    """
    apprunx_path = str(Path(apprunx_path).resolve())

    cached = cache.get(apprunx_path)
    if not cached:
        return False

    app_id = cached.get("app_id", "")
    registered = cached.get("registered_users", [])

    # 등록된 사용자들에게서 파일 삭제
    for username in registered:
        try:
            pw = pwd.getpwnam(username)
        except KeyError:
            continue  # 사용자가 이미 삭제됨

        home = Path(pw.pw_dir)
        _unlink_if_exists(home / ".local/share/applications" / f"apprun-dropin-{app_id}.desktop")
        _unlink_if_exists(home / ".local/share/icons" / f"apprun-{app_id}.png")

    del cache[apprunx_path]

    print(f"[DropIn] 삭제: {app_id}")
    try:
        libapprun.notify("[AppRun DropIn] 앱 삭제", app_id)
    except Exception:
        pass

    return True


# ==============================================================================
# 전체 스캔
# ==============================================================================

def scan_all(dir_to_users: dict[str, list[UserInfo]], cache: dict) -> bool:
    """
    모든 감시 디렉터리를 스캔하여 .apprunx 파일을 처리.
    반환값: 캐시가 변경되었으면 True.
    """
    changed = False
    found_paths: set[str] = set()

    for watch_dir_str, users in dir_to_users.items():
        watch_dir = Path(watch_dir_str)
        if not watch_dir.is_dir():
            continue

        try:
            entries = list(watch_dir.iterdir())
        except PermissionError:
            print(f"[DropIn] 경고: 접근 불가: {watch_dir}", file=sys.stderr)
            continue

        for entry in entries:
            if entry.suffix != ".apprunx" or not entry.is_file():
                continue

            resolved = str(entry.resolve())
            found_paths.add(resolved)

            if register_desktop(resolved, users, cache):
                changed = True

    # 캐시에는 있지만 파일이 사라진 항목 삭제
    stale = [p for p in list(cache.keys()) if p not in found_paths]
    for s in stale:
        if unregister_desktop(s, cache):
            changed = True

    return changed


# ==============================================================================
# inotify 감시
# ==============================================================================

class ApprunxEventHandler(pyinotify.ProcessEvent):
    """
    .apprunx 파일 이벤트를 처리.
    dir_to_users 참조를 유지하여 어느 디렉터리의 이벤트인지에 따라
    대상 사용자를 결정.
    """

    def __init__(self, cache: dict, dir_to_users: dict[str, list[UserInfo]]):
        super().__init__()
        self._cache = cache
        self._dir_to_users = dir_to_users

    def _is_apprunx(self, event) -> bool:
        return event.pathname.endswith(".apprunx")

    def _resolve(self, event) -> str:
        return str(Path(event.pathname).resolve())

    def _users_for_event(self, event) -> list[UserInfo]:
        """이벤트가 발생한 디렉터리에 매핑된 사용자 목록 반환."""
        watch_dir = str(Path(event.path).resolve())
        return self._dir_to_users.get(watch_dir, [])

    def process_IN_CREATE(self, event):
        if not self._is_apprunx(event):
            return
        time.sleep(0.5)
        path = self._resolve(event)
        users = self._users_for_event(event)
        if users and Path(path).exists() and register_desktop(path, users, self._cache):
            save_cache(self._cache)

    def process_IN_MOVED_TO(self, event):
        self.process_IN_CREATE(event)

    def process_IN_CLOSE_WRITE(self, event):
        if not self._is_apprunx(event):
            return
        path = self._resolve(event)
        users = self._users_for_event(event)
        if users and Path(path).exists() and register_desktop(path, users, self._cache):
            save_cache(self._cache)

    def process_IN_DELETE(self, event):
        if not self._is_apprunx(event):
            return
        path = self._resolve(event)
        if unregister_desktop(path, self._cache):
            save_cache(self._cache)

    def process_IN_MOVED_FROM(self, event):
        self.process_IN_DELETE(event)


class PasswdEventHandler(pyinotify.ProcessEvent):
    """
    /etc/passwd 변경을 감지하여 새 사용자 추가 시 watch 목록을 갱신.
    """

    def __init__(self, state: "ServiceState"):
        super().__init__()
        self._state = state

    def process_IN_CLOSE_WRITE(self, event):
        if event.pathname != PASSWD_PATH and not event.pathname.endswith("/passwd"):
            return
        print("[DropIn] /etc/passwd 변경 감지, 사용자 목록 갱신 중...")
        time.sleep(0.3)
        self._state.refresh_users()

    def process_IN_MOVED_TO(self, event):
        self.process_IN_CLOSE_WRITE(event)


# ==============================================================================
# 서비스 상태 관리
# ==============================================================================

def _find_owner_user(dir_path: str, users: list[UserInfo]) -> Optional[UserInfo]:
    """
    경로가 특정 사용자의 홈 디렉터리 하위에 있으면 해당 사용자를 반환.
    global 경로이거나 매칭되는 사용자가 없으면 None.
    """
    for user in users:
        if dir_path.startswith(str(user.home) + "/"):
            return user
    return None


def _chown_recursive(path: Path, user: UserInfo) -> None:
    """
    path 및 그 상위 디렉터리 중 사용자 홈 하위에 있는 것들의
    소유권을 해당 사용자로 변경.
    """
    home_str = str(user.home)
    # path 자체
    try:
        os.chown(str(path), user.uid, -1)
    except OSError:
        pass

    # 상위 디렉터리 (홈 바로 아래까지)
    current = path.parent
    while str(current).startswith(home_str + "/") and current != user.home:
        try:
            os.chown(str(current), user.uid, -1)
        except OSError:
            pass
        current = current.parent


class ServiceState:
    """
    서비스 전체 상태를 관리. 사용자 목록 갱신 시 watch 재구성 담당.
    """

    def __init__(self):
        self.config: dict = {}
        self.users: list[UserInfo] = []
        self.dir_to_users: dict[str, list[UserInfo]] = {}
        self.cache: dict = {}
        self.wm: pyinotify.WatchManager = pyinotify.WatchManager()
        self._watch_descriptors: dict[str, int] = {}  # path → wd

        self._apprunx_mask = (
            pyinotify.IN_CREATE
            | pyinotify.IN_DELETE
            | pyinotify.IN_MOVED_FROM
            | pyinotify.IN_MOVED_TO
            | pyinotify.IN_CLOSE_WRITE
        )

    def init(self):
        self.config = load_config()
        self.cache  = load_cache()
        self.users  = list_normal_users()
        self.dir_to_users = resolve_watch_dirs(self.config, self.users)

        print(f"[DropIn] 감지된 사용자: {[u.username for u in self.users]}")

    def setup_apprunx_watches(self):
        """현재 dir_to_users 의 모든 디렉터리에 inotify watch 설정."""
        handler = ApprunxEventHandler(self.cache, self.dir_to_users)

        for dir_path, users in self.dir_to_users.items():
            if dir_path in self._watch_descriptors:
                continue  # 이미 감시 중
            p = Path(dir_path)
            try:
                if not p.exists():
                    p.mkdir(parents=True, exist_ok=True)
                    # 사용자 홈 하위 경로면 해당 사용자 소유로 변경
                    owner = _find_owner_user(dir_path, users)
                    if owner:
                        _chown_recursive(p, owner)
            except PermissionError:
                print(f"[DropIn] 경고: 디렉터리 생성 불가: {dir_path}", file=sys.stderr)
                continue
            wd_dict = self.wm.add_watch(dir_path, self._apprunx_mask, proc_fun=handler, rec=False)
            wd = wd_dict.get(dir_path)
            if wd and wd > 0:
                self._watch_descriptors[dir_path] = wd
                print(f"[DropIn] 감시 시작: {dir_path}")
            else:
                print(f"[DropIn] 경고: watch 등록 실패: {dir_path}", file=sys.stderr)

    def setup_passwd_watch(self):
        """
        /etc/passwd 변경 감시.
        일부 시스템에서 passwd 업데이트가 rename 으로 이루어지므로
        /etc 디렉터리 자체를 감시.
        """
        handler = PasswdEventHandler(self)
        mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO
        self.wm.add_watch("/etc", mask, proc_fun=handler, rec=False)
        print("[DropIn] /etc/passwd 변경 감시 시작")

    def refresh_users(self):
        """
        사용자 목록을 다시 읽고, 새 사용자의 경로에 watch 를 추가.
        새 사용자에 대해 전체 스캔도 수행.
        """
        old_users = set(self.users)
        self.users = list_normal_users()
        new_users = set(self.users) - old_users

        if not new_users:
            return

        new_names = [u.username for u in new_users]
        print(f"[DropIn] 새 사용자 감지: {new_names}")

        # dir_to_users 재구성
        self.dir_to_users = resolve_watch_dirs(self.config, self.users)

        # 새 디렉터리에 watch 추가
        self.setup_apprunx_watches()

        # 새 사용자 대상으로 전체 스캔 (기존 global 디렉터리의 앱도 등록되어야 함)
        if scan_all(self.dir_to_users, self.cache):
            save_cache(self.cache)

    def remove_stale_watches(self):
        """
        더 이상 dir_to_users 에 없는 경로의 watch 제거.
        """
        current_dirs = set(self.dir_to_users.keys())
        stale = [p for p in self._watch_descriptors if p not in current_dirs]
        for p in stale:
            wd = self._watch_descriptors.pop(p)
            self.wm.rm_watch(wd, quiet=True)
            print(f"[DropIn] 감시 해제: {p}")


# ==============================================================================
# 진입점
# ==============================================================================

def main():
    print("[DropIn] AppRun Format 3 DropIn 서비스 시작 (시스템 데몬)")

    state = ServiceState()

    # 설정 로드 (실패 시 재시도)
    while True:
        try:
            state.init()
            if not state.dir_to_users:
                print("[DropIn] 경고: 감시할 디렉터리가 없습니다. 10초 후 재시도...", file=sys.stderr)
                time.sleep(10)
                continue
            break
        except Exception as e:
            print(f"[DropIn] 초기화 실패: {e}. 10초 후 재시도...", file=sys.stderr)
            time.sleep(10)

    print(f"[DropIn] 감시 대상 디렉터리: {len(state.dir_to_users)} 개")
    for d, users in state.dir_to_users.items():
        names = [u.username for u in users]
        print(f"  - {d} → {names}")

    # 초기 전체 스캔
    print("[DropIn] 초기 스캔 시작...")
    try:
        if scan_all(state.dir_to_users, state.cache):
            save_cache(state.cache)
    except Exception as e:
        print(f"[DropIn] 초기 스캔 중 오류: {e}", file=sys.stderr)
    print("[DropIn] 초기 스캔 완료")

    # inotify 감시 설정
    state.setup_apprunx_watches()
    state.setup_passwd_watch()

    notifier = pyinotify.Notifier(state.wm)

    # 시그널 핸들러
    def shutdown(signum, frame):
        print("\n[DropIn] 종료 중...")
        notifier.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 이벤트 루프
    print("[DropIn] 이벤트 루프 시작")
    try:
        notifier.loop()
    except KeyboardInterrupt:
        print("\n[DropIn] 종료")
        notifier.stop()
    except Exception as e:
        print(f"[DropIn] 이벤트 루프 오류: {e}", file=sys.stderr)
        # systemd 가 재시작하도록 비정상 종료
        sys.exit(1)


if __name__ == "__main__":
    main()
