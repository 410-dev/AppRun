---
name: use-appcontext
description: Develop, integrate, test, and troubleshoot Python applications that use AppRun's AppContext API. Use when Codex needs to access an AppRun Box, persist app data, discover bundle or mount paths, enforce a single running process, set Tk or Qt icons, handle application exit, inspect user or privilege context, or connect an AppRun application to GUI startup and systemd service workflows.
---

# Use AppContext

AppRun Python 애플리케이션에서 런타임 경로, Box 데이터, 단일 프로세스, GUI 아이콘, 사용자 정보와 호스트 통합을 다룰 때 `AppContext`를 사용하라. AppContext가 Linux/AppRun 전용 API임을 전제로 하고, 애플리케이션 비즈니스 로직과 호스트 변경 작업을 분리하라.

## 기준 구현 확인

작업 전에 필요한 범위에서 다음 소스를 확인하라.

- 공개 동작과 현재 제약: `src/usr/lib/AppRun/libs/AppContext.py`
- AppRun 설치 경로: `docs/Paths.md`
- Format 3 Box와 portable 동작: `docs/format-3.md`
- AppContext 경로 보안 배경: `docs/security-hardening-0514.md`
- 번들 제작 지침: `../build-apprun-apps/SKILL.md`
- CLI 사용 매뉴얼: `../build-apprun-apps/references/cli-manual.md`

이 스킬과 구현이 충돌하면 현재 `AppContext.py`를 우선하라. private 메서드와 `_` 접두사 속성을 애플리케이션 코드에서 호출하지 마라.

## 번들에 연결

AppContext는 AppRun 설치가 제공하는 시스템 모듈이다. PyPI 패키지처럼 `requirements.txt`에 추가하지 마라. Python venv에서 import할 수 있도록 번들의 `AppRunMeta/libs`에 시스템 Collection ID를 선언하라.

```text
system-site
```

대상 시스템의 `/usr/share/dictionaries/apprun-python/` 사전이 `system-site`를 `/usr/lib/python3/dist-packages`로 해석하는지 확인하라. 그 뒤 다음처럼 import하라.

```python
from AppContext import AppContext, ProcessAlreadyRunningError

ctx = AppContext()
```

프로세스 시작 시 인스턴스를 한 번 만들고 필요한 모듈에 명시적으로 전달하라. 테스트가 쉬워지도록 전역 import 시점에 호스트 변경 메서드를 호출하지 마라.

AppRun venv 밖에서 실행하면 AppContext는 현재 작업 디렉터리를 Box로 간주하고 그 디렉터리 이름을 앱 ID로 사용한다. 개발 실행과 실제 `.apprunx` 실행의 경로가 다를 수 있으므로 양쪽을 별도로 검증하라.

## 빠른 시작

Box 안에 애플리케이션 상태를 저장하고 사용자별 단일 인스턴스를 적용하라.

```python
import json

from AppContext import AppContext, ProcessAlreadyRunningError


def main() -> int:
    ctx = AppContext()

    try:
        ctx.ensure_single_process_user()
    except ProcessAlreadyRunningError as exc:
        print(f"Already running with PID {exc.existing_pid}")
        return 0

    settings = json.loads(ctx.read_str_or_default("state/settings.json", "{}"))
    settings["launch_count"] = int(settings.get("launch_count", 0)) + 1
    ctx.write_str("state/settings.json", json.dumps(settings, ensure_ascii=False))

    print(f"app={ctx.id()} box={ctx.box()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Box는 앱의 쓰기 가능한 상태 공간으로 사용하고, 읽기 전용 번들 리소스는 mount 경로에서 읽어라.

## 런타임 경로와 사용자 정보

| 메서드 | 반환값과 용도 |
|---|---|
| `is_venv()` | 인터프리터 경로가 AppRun의 `pyvenv/bin/` 안인지 반환 |
| `interpreter()` | 감지한 실제 Python 인터프리터 경로 반환 |
| `box()` | 쓰기 가능한 AppRun Box 경로 반환 |
| `id()` | Box 디렉터리 이름에서 추론한 ID 반환 |
| `pid()` | 현재 프로세스 PID 반환 |
| `entry_script()` | 감지한 최초 진입 스크립트 경로 반환 |
| `mount_point()` | 실행 중인 번들의 읽기 전용 mount 디렉터리 반환 |
| `bundle()` | Format 3에서는 가능한 경우 원본 `.apprunx` 경로, 개발 실행에서는 진입 스크립트 디렉터리 반환 |
| `username()` | 현재 사용자 이름 반환 |
| `uid()` / `euid()` | 실제 UID와 effective UID 반환 |
| `userhome()` | 현재 프로세스 환경에서 확장한 홈 디렉터리 반환 |

번들에 포함된 정적 리소스는 `mount_point()`를 기준으로 찾고, 서비스/자동 시작 등록처럼 원본 번들 파일이 필요한 작업에는 `bundle()`을 사용하라.

```python
from pathlib import Path

icon = Path(ctx.mount_point()) / "AppRunMeta" / "DesktopLinks" / "Icon.png"
database = Path(ctx.file_in_box("data/app.sqlite3"))
```

`bundle()`이 항상 파일이라고 가정하지 마라. 호스트 등록 전에 `Path(ctx.bundle()).is_file()`과 `.apprunx` 실행 여부를 확인하라.

`id()`를 검증된 `AppRunMeta/id`와 동일한 보안 식별자로 취급하지 마라. 현재 구현은 Box basename을 사용하므로 개발 실행에서는 작업 디렉터리 이름, portable Box에서는 `box`가 될 수 있다. 로그 표시 외에 파일 권한, IPC namespace, 전역 자원 이름에 사용할 때는 번들의 검증된 ID를 별도로 읽거나 호출자가 고정한 안전한 식별자를 사용하라.

## Box 파일 API

모든 AppContext 파일명에는 Box 기준의 안전한 상대 경로만 전달하라.

- 허용: `settings.json`, `state/session.json`, `cache/index.bin`
- 금지: `/etc/passwd`, `../escape`, `state/../escape`, NUL 문자가 있는 값
- 존재하는 symlink 또는 symlink 부모를 통과하는 경로를 사용하지 마라.
- 사용자 입력을 그대로 파일명으로 사용하지 말고 애플리케이션이 통제하는 ID나 검증된 이름으로 변환하라.

| 메서드 | 동작 |
|---|---|
| `file_in_box(path)` | Box 내부 절대 경로를 안전하게 계산하되 파일은 만들지 않음 |
| `has_file_in_box(path)` | 일반 파일 존재 여부 반환 |
| `write(path, bytes)` | 부모 디렉터리를 만들고 bytes를 기록한 뒤 경로 반환 |
| `read(path)` | bytes 반환 |
| `write_str(path, text, encoding)` | 문자열을 인코딩해 기록 |
| `read_str(path, encoding)` | bytes를 디코딩해 문자열 반환 |
| `read_or_default(path, default)` | 파일이 없을 때 bytes 기본값 반환 |
| `read_str_or_default(path, default, encoding)` | 파일이 없을 때 문자열 기본값 반환 |

`read_*_or_default`는 `FileNotFoundError`만 기본값으로 바꾼다. 권한 오류, 잘못된 경로, symlink 거부, 디코딩 오류를 누락 파일처럼 숨기지 마라.

`write()`는 원자적 저장이나 다중 프로세스 잠금을 제공하지 않는다. 설정/DB가 손상되면 안 되는 경우 Box 내부 같은 디렉터리에 임시 파일을 쓰고 `os.replace()`하거나 해당 파일 포맷의 transaction을 사용하라. 여러 프로세스가 같은 파일을 쓸 수 있으면 별도 파일 잠금을 적용하라.

### 핵심 파일 보호

기본 보호 설정은 `pyvenv/`, `requirements.txt.sha256`, `requirements.txt.checksum` 쓰기를 막는다. 애플리케이션 데이터 이름으로 이 경로를 사용하지 마라. 다음 보호를 해제하지 마라.

```python
ctx.xmem_get("APPCONTEXT_ENABLE_COREFILE_PROTECTIONS")
```

`xmem_set()`은 AppContext 내부 동작을 조정하는 저수준 API로 취급하라. 보호 목록이나 보호 활성화 값을 바꾸기 전에 명시적인 요구사항과 보안 영향을 확인하라.

### 파일명 해시 모드

`ctx.unreadable_filename = True`로 설정하면 Box API가 전달받은 전체 파일명 문자열을 SHA-256 파일명으로 바꾼다.

```python
ctx.unreadable_filename = True
ctx.write_str("user-session", "opaque state")
```

이 기능은 파일 이름을 알아보기 어렵게 할 뿐 콘텐츠를 암호화하지 않는다. 디렉터리 구조가 필요한 앱, 운영자가 파일을 직접 관리해야 하는 앱, 캐시 API를 사용하는 앱에는 활성화하지 마라. 기밀 데이터에는 별도 암호화와 키 관리 방식을 사용하라.

## Box 목록 조회

| 메서드 | 동작 |
|---|---|
| `list_file_in_box_flat(...)` | Box 항목을 상대 경로 리스트로 반환 |
| `list_file_in_box_structured(...)` | 디렉터리를 중첩 dict, 파일을 `"file"` 값으로 반환 |

기본값은 재귀하지 않고 최상위 `pyvenv/`를 제외한다. 재귀가 필요하면 `recursive=True`, 깊이 제한은 `depth`, 디렉터리 포함 여부는 `include_directories`, venv 포함 여부는 `include_pyvenv`로 지정하라.

```python
files = ctx.list_file_in_box_flat(
    recursive=True,
    include_directories=False,
    depth=2,
    include_pyvenv=False,
)
```

목록 함수는 표시/진단 용도로만 사용하라. 디렉터리 순회 결과 자체를 보안 경계로 신뢰하지 말고, 실제 접근에는 `read`, `write`, `file_in_box`의 경로 검증을 다시 통과시켜라. 대형 Box나 `pyvenv`를 무제한 재귀하지 마라.

## 메모리 캐시

`cache(path)`는 이후 `read(path)` 결과를 프로세스 메모리에 유지하고, `decache(path)`는 저장된 값을 제거하며, `nocache(path)`는 값과 캐시 대상 등록을 모두 제거한다.

```python
ctx.cache("cache/catalog.bin")
catalog = ctx.read("cache/catalog.bin")

ctx.write("cache/catalog.bin", new_catalog)
ctx.decache("cache/catalog.bin")
```

현재 구현을 사용할 때 다음 제한을 지켜라.

- `write()`는 기존 캐시를 자동 무효화하지 않으므로 쓰기 뒤 `decache()`를 호출하라.
- bytes 타입을 유지하려면 `cache(path, read_now=True)`를 사용하지 말고 `cache(path)` 후 `read(path)`를 호출하라.
- `unreadable_filename`과 캐시를 함께 사용하지 마라.
- 프로세스 메모리 캐시는 비밀 저장소, 프로세스 간 캐시, 영속 캐시가 아니다.

## 단일 프로세스 보장

일반 desktop 앱에는 사용자별 잠금을 우선 사용하라.

```python
try:
    ctx.ensure_single_process_user()
except ProcessAlreadyRunningError as exc:
    print(exc.lock_id, exc.existing_pid)
    raise SystemExit(0)
```

- `ensure_single_process_user()`는 `$XDG_RUNTIME_DIR` 또는 `~/.local/run` 아래에서 현재 사용자만 제한한다.
- `ensure_single_process_globally()`는 `/tmp`의 공유 잠금을 사용해 모든 사용자를 제한한다. 시스템 전체 단일 인스턴스가 실제 요구사항일 때만 사용하라.
- 둘 중 하나만 메인 스레드에서 한 번 호출하라. 내부에서 `SIGINT`와 `SIGTERM` handler 및 `atexit` 정리를 등록한다.
- 두 메서드는 `ctx.id()`를 잠금 ID로 사용한다. portable Box에서 `ctx.id() == "box"`이면 서로 다른 앱이 같은 잠금 이름을 사용할 수 있으므로 이 잠금 API를 사용하지 말고 검증된 앱 ID를 사용하는 별도 잠금 또는 systemd service 단일성을 구현하라.
- 잠금 이후 자체 signal handler를 설치하면 AppContext 정리 handler를 덮어쓸 수 있다. 필요한 경우 애플리케이션 handler에서 정상 종료 경로를 보장하라.
- global 잠금은 다른 사용자의 파일 권한이나 예측 가능한 `/tmp` 경로 영향을 받을 수 있으므로 서비스 수준의 systemd 단일성으로 해결 가능한지 먼저 검토하라.

예외를 포괄적으로 삼키고 계속 실행하지 마라. `existing_pid == -1`이면 소유 프로세스 PID를 읽지 못한 잠금 충돌로 처리하라.

## GUI 아이콘과 종료

`update_icon(window)`은 `AppRunMeta/DesktopLinks/Icon.png`를 Tkinter, PyQt5/6, PySide2/6 창에 적용하려고 시도하고 성공 여부를 bool로 반환한다. 창과 toolkit application을 만든 뒤 호출하라.

```python
root = tk.Tk()
if not ctx.update_icon(root):
    # 필요한 경우 mount_point()의 Icon.png를 toolkit API로 직접 적용
    pass
```

Linux/X11에서는 `xprop`으로 WM_CLASS 설정을 시도할 수 있으며 실패해도 앱 실행은 계속된다. Wayland, 아직 생성되지 않은 창, 원본 번들 경로 감지 방식에 따라 `False`가 반환될 수 있으므로 기능 성공을 가정하지 마라.

`app_exit(message, code, wait_for_input)`는 메시지를 출력하고 필요하면 Enter 입력을 기다린 뒤 `sys.exit(code)`를 호출한다. 라이브러리 계층에서 호출하지 말고 CLI 최상위에서만 사용하라. 비대화형/GUI 환경에서는 입력 대기로 멈추지 않도록 값을 명시하라.

```python
ctx.app_exit("Finished", code=0, wait_for_input=False)
```

legacy Terminal marker를 통한 자동 판단에 의존하지 마라. stdin/stdout에 `fileno()`가 없는 테스트 환경도 있으므로 테스트에서는 `wait_for_input=False`를 지정하거나 `SystemExit`을 검사하라.

## 권한과 그룹

`ensure_privileged(throw_error_instead_of_exit=False, exit_code=1)`는 root가 아니면 프로세스를 종료한다. 재사용 가능한 코드에서는 예외 모드를 사용하라.

```python
ctx.ensure_privileged(throw_error_instead_of_exit=True)
```

root일 때도 의미 있는 bool을 반환하지 않으므로 조건식에 사용하지 마라. 권한 분기에는 `ctx.euid() == 0`을 사용하라.

```python
allowed = ctx.euid() == 0 or ctx.is_user_in_group("plugdev")
```

`is_user_in_group(group)`은 보조 그룹과 기본 그룹을 확인하며 그룹/사용자가 없으면 `False`를 반환한다. `is_user_in_group_or_privileged()`는 비root에서 종료할 수 있고 root에서도 참인 bool을 보장하지 않으므로 새 코드에서 사용하지 마라.

## GUI startup과 서비스

AppContext는 다음 호스트 통합 wrapper를 제공한다.

| 메서드 | 용도 | 반환/주의 |
|---|---|---|
| `install_as_gui_startup(...)` | user/global GUI autostart 등록 | 성공 bool 반환 |
| `install_gui_startup(...)` | 위 메서드의 alias | 성공 bool 반환 |
| `uninstall_as_gui_startup(...)` | GUI autostart 제거 | 성공 bool 반환 |
| `uninstall_gui_startup(...)` | 제거 메서드의 alias | 성공 bool 반환 |
| `install_as_service(...)` | 생성 systemd service 등록 | 대화형 동작과 후속 `systemctl` 포함 |
| `uninstall_service(user)` | 생성 service 제거 | 결과를 출력하며 bool을 반환하지 않음 |
| `install_as_global_user(...)` | global user service 등록 | 권한 상승과 현재 user systemd 동작 포함 |

이 메서드는 파일 작성, 번들 복사, 권한 상승, systemd 또는 autostart 상태 변경을 유발한다. 사용자 요청을 처리하는 일반 앱 시작 경로에서 자동 호출하지 마라. 사용자가 명시적으로 선택하는 설치 UI나 별도 관리 명령에서만 호출하라.

GUI startup의 단순 user 등록처럼 wrapper가 직접 필요한 경우 인자를 리스트로 전달하라.

```python
ok = ctx.install_as_gui_startup(
    globally=False,
    no_interaction=False,
    start=False,
    apprun_args=["--portable=box"],
    run_args=["--minimized"],
)
```

`no_interaction=True`는 권한 승인을 의미하지 않고 AppContext 자체 확인 질문만 생략한다. 무인 설치가 사용자의 명시적 요청과 격리된 배포 흐름 안에 있는지 확인하라.

서비스와 global 등록에는 wrapper보다 `../build-apprun-apps/references/cli-manual.md`의 현재 `apprun3` CLI 매뉴얼을 우선하라. 현재 wrapper는 호환성 명령 `apprun`을 호출하고 옵션 순서 및 후속 `systemctl --user`에 대한 제약이 있으므로, 자동화에서는 argv를 명시적으로 구성하고 종료 코드/표준 오류를 검사하라.

```python
import subprocess
from pathlib import Path

bundle = Path(ctx.bundle())
if not bundle.is_file():
    raise RuntimeError("Service registration requires a packaged .apprunx file")

subprocess.run(
    [
        "apprun3",
        "--install-as-service=simple,network-online.target",
        "--enable",
        str(bundle),
    ],
    check=True,
)
```

테스트에서는 subprocess와 GUI 질문을 mock하고 실제 systemd, autostart, 사용자 홈을 변경하지 마라.

## 구현 및 테스트 절차

AppContext를 앱에 적용할 때 다음 순서를 따르라.

1. AppRun venv import를 위해 `AppRunMeta/libs`를 설정하라.
2. 진입점에서 AppContext 인스턴스를 하나 만들라.
3. 읽기 전용 리소스는 `mount_point()`, 쓰기 데이터는 Box API로 분리하라.
4. 필요한 경우 사용자별 단일 프로세스 잠금을 메인 스레드에서 적용하라.
5. UI와 호스트 통합은 핵심 로직 뒤의 선택 기능으로 분리하라.
6. 경로 탈출, symlink, 누락 파일, 캐시 무효화와 동시 실행을 테스트하라.
7. Linux에서 소스 실행과 패키징된 `.apprunx` 실행을 모두 검증하라.

최소 회귀 테스트에 다음을 포함하라.

- bytes와 UTF-8 문자열 read/write round trip
- 중첩 디렉터리 자동 생성
- 절대 경로, `..`, NUL 입력 거부
- Box 밖을 가리키는 symlink 거부
- 보호된 venv/checksum 경로 쓰기 거부
- 누락 파일 기본값과 다른 예외의 구분
- write 후 cache invalidation
- 두 번째 프로세스의 `ProcessAlreadyRunningError`
- `update_icon()` 실패 시 앱이 계속 실행되는 동작
- host integration wrapper의 argv와 실패 반환 처리

Windows에서는 `fcntl`, `pwd`, `grp`, Linux UID/signal 동작 때문에 AppContext를 직접 검증하지 마라. WSL 또는 Linux 환경에서 실행하라. 실제 서비스 및 권한 테스트는 disposable VM/container에서 수행하고, 일반 개발 머신에서는 subprocess mock으로 제한하라.

## 문제 해결

- `ModuleNotFoundError: AppContext`: `AppRunMeta/libs`의 `system-site`와 AppRun dictionary 설치를 확인하라.
- Box가 현재 디렉터리로 나옴: AppRun의 `pyvenv/bin/python3`가 아닌 Python으로 실행 중인지 확인하라.
- 번들 리소스를 찾지 못함: `bundle()` 대신 `mount_point()`에서 `AppRunMeta/DesktopLinks`를 찾으라.
- `ValueError: Path escapes AppRun box`: 절대 경로, `..`, 빈 컴포넌트, symlink 부모를 제거하라.
- write 뒤 이전 값이 읽힘: 해당 경로를 `decache()`하거나 `nocache()`하라.
- 두 번째 실행이 차단되지 않음: 잠금 메서드를 메인 스레드의 초기 경로에서 한 번 호출했는지 확인하라.
- portable 앱끼리 실행이 잘못 충돌함: `ctx.id()`가 `box`인지 확인하고 AppContext 잠금 대신 검증된 번들 ID 기반 잠금을 사용하라.
- 앱 종료 시 입력에서 멈춤: `app_exit(..., wait_for_input=False)`를 사용하라.
- service/autostart 등록 실패: `ctx.bundle()`이 실제 `.apprunx` 파일인지 확인하고 같은 작업을 `apprun3` CLI로 재현하라.
