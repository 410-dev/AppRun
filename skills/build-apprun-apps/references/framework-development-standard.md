# AppRun 프레임워크 개발 표준

## 목차

1. 적용 범위
2. 아키텍처 경계
3. 변경 위치 선택
4. 공개 호환성
5. 입력 검증과 host 보안
6. Subprocess 및 권한 상승
7. Desktop과 systemd 생성
8. 파일 쓰기와 경로
9. 국제화
10. 테스트 표준
11. Build와 package 검증
12. 변경 완료 기준

## 1. 적용 범위

이 문서는 AppRun runtime, public CLI, Python library, Debian package, desktop integration과 내장 서비스 수정에 적용한다. 애플리케이션 bundle 제작에는 [Format 3 기술 표준](format3-standard.md)을 사용하라.

AppRun은 untrusted bundle metadata를 읽어 host 파일, process, package, desktop과 systemd를 조작할 수 있다. 모든 변경을 security boundary 변경으로 검토하라.

## 2. 아키텍처 경계

현재 공개 명령과 구현 경계를 유지하라.

```text
/usr/bin/apprun.py
    └── apprun_cli.main.main()
            ├── parser.py
            ├── constants.py
            └── command.py

libapprun/__init__.py
    ├── bundle.py
    ├── mounts.py
    ├── boxes.py
    ├── packages.py
    ├── ui.py
    ├── util.py
    └── constants.py
```

역할은 다음과 같다.

- `/usr/bin/apprun.py`: 개발 import path를 준비하고 stable CLI entry를 호출하는 facade
- `apprun_cli/parser.py`: AppRun option parsing과 normalization
- `apprun_cli/command.py`: dispatch와 command handler
- `apprun_cli/constants.py`: CLI path, systemd store와 option allowlist
- `libapprun`: bundle, mount, Box, package와 UI 재사용 API
- `apprun_validation.py`: host-facing 값 검증
- `apprun_desktop.py`: desktop entry parsing/serialization
- `apprun_systemd.py`: systemd unit parsing/serialization
- `apprun_safeio.py`: privileged no-symlink write
- `apprun_i18n.py`: locale 선택과 JSON message lookup

`command.py`가 더 분리될 경우 behavior 단위 module로 옮기되 `apprun_cli.main.main()`을 유지하라.

## 3. 변경 위치 선택

| 변경 종류 | 기본 위치 |
|---|---|
| 새 CLI option parsing | `apprun_cli/parser.py` |
| CLI dispatch/handler | `apprun_cli/command.py` 또는 behavior module |
| 공용 runtime constant | `libapprun/constants.py` |
| CLI 전용 system path | `apprun_cli/constants.py` |
| bundle metadata/inspection | `libapprun/bundle.py` |
| mount lifecycle | `libapprun/mounts.py` |
| Box path/lock | `libapprun/boxes.py` |
| Debian requirement | `libapprun/packages.py` |
| desktop generation | `apprun_desktop.py` |
| systemd generation | `apprun_systemd.py` |
| host input validator | `apprun_validation.py` |
| privileged file write | `apprun_safeio.py` |
| user-facing message | `lang/en.json`, `lang/ko.json` |
| package install/remove | `src/DEBIAN/` |
| build composition | `build.sh`, `build-uv.sh`, `build.json` |

동일한 검증, quoting 또는 serialization 로직을 여러 caller에 복사하지 말고 shared module로 모으라.

## 4. 공개 호환성

다음을 stable contract로 취급하라.

- `apprun3`와 `apprun3-package` public behavior
- 설치 호환성을 위한 `apprun`, `apprun-package` alias
- `apprun_cli.main.main()`
- `libapprun/__init__.py`가 export하는 public name
- 기존 tool이 아직 사용하는 leading underscore compatibility export
- Format 3 metadata key와 CLI option spelling

구현을 이동할 때 `libapprun/__init__.py`에서 기존 import를 유지하라. 제거 또는 동작 변경이 필요하면 migration과 deprecation 계획 없이 즉시 삭제하지 마라.

Format 1/2 기능을 신규 경로에 다시 추가하지 마라. legacy 문서는 참고용으로만 유지하라.

## 5. 입력 검증과 host 보안

bundle과 metadata 값을 host operation에 전달하기 전에 적절한 validator를 사용하라.

| 값 | validator/경계 |
|---|---|
| bundle ID | `validate_app_id` |
| host-derived fallback ID | `sanitize_identifier` |
| Debian package | `validate_debian_package_name` |
| systemd unit | `validate_systemd_unit_name` |
| bundled service path | `validate_service_file_path` |
| desktop scalar | `validate_desktop_value` |
| bundle relative path | `validate_safe_relative_path` |

검증 실패를 normalize하여 계속 진행하지 말고 host 변경 전 중단하라. fallback ID는 host-derived filename에만 사용하고 bundle-supplied invalid ID를 조용히 고치지 마라.

다음 malicious input을 테스트하라.

- absolute path와 `../` escape
- slash/backslash와 leading dash
- NUL, newline와 control character
- duplicate/empty path component
- unsafe Debian package와 systemd unit
- symlinked output target
- invalid/non-object JSON metadata
- unexpected metadata type

## 6. Subprocess 및 권한 상승

subprocess는 argv list로 실행하라.

```python
subprocess.run(["systemctl", "--user", "start", unit_name], check=True)
```

다음을 피하라.

- bundle 값을 포함한 `shell=True`
- string concatenation으로 만든 command
- `bash -c`에 untrusted metadata 전달
- option operand 앞의 unvalidated leading dash
- package 또는 unit list를 shell separator로 연결

권한 상승은 `_sudo_cmd`, `_reexec_privileged` 등 기존 흐름을 재사용하라. GUI/headless, root/real user, `sudo`/`pkexec`, XDG runtime과 D-Bus 환경을 구분하라.

현재 real user 판별은 `SUDO_USER`, `SUDO_UID`, `PKEXEC_UID` 영향을 받는다. root가 user home에 쓰는 변경은 owner, parent symlink와 privilege drop을 검토하라.

## 7. Desktop과 systemd 생성

desktop entry는 `apprun_desktop.py`의 fixed serializer와 argv quoting을 사용하라.

- bundled desktop에서 allowlist field만 읽어라.
- `Exec`, `Icon`, `Type`, `Terminal`, `StartupWMClass`를 host-generated 값으로 덮어쓰라.
- `%`와 quote를 Desktop Entry specification에 맞게 escape하라.
- newline/control character를 거부하라.

systemd unit은 `apprun_systemd.py`를 사용하라.

- service type을 allowlist로 제한하라.
- dependency unit을 각각 검증하라.
- `ExecStart`를 argv에서 serialization하라.
- `Description`, `User`, unit name에 control/path injection을 허용하지 마라.
- bundled service는 `services/<name>.service` 형태만 허용하라.

host-sensitive config를 bundle line 그대로 passthrough하지 마라.

## 8. 파일 쓰기와 경로

privileged 또는 다른 사용자 소유 경로에는 `apprun_safeio.py`의 no-symlink helper를 사용하라. chmod/chown은 path를 다시 따라가지 말고 open file descriptor 또는 `follow_symlinks=False`를 사용하라.

recursive delete/move 전에 resolved path가 의도한 root 안인지 확인하라. bundle ID 또는 metadata에서 만든 path를 검증 없이 삭제하지 마라.

다음 runtime root를 구분하라.

- system package: `/usr`, `/etc`, `/var`
- service store: `/usr/share/services.apprd`
- user AppRun: `~/.local/apprun`
- user service/startup: `~/.config`, `~/.local/share/services.apprd`
- portable: bundle 옆 `<id>.apprunx.data.d`

partial write가 위험한 state/cache에는 atomic replacement를 사용하라.

## 9. 국제화

새 CLI, notification, GUI dialog message를 hard-code하지 마라. `tr("message.key", ...)`를 사용하고 다음 파일에 동일한 key를 추가하라.

```text
src/usr/share/apprun/lang/en.json
src/usr/share/apprun/lang/ko.json
```

영어를 fallback source로 유지하라. format placeholder 이름을 모든 언어에서 동일하게 유지하고, 누락 key와 잘못된 placeholder가 원문 key 노출로 이어지지 않는지 테스트하라.

argparse 표준 문구를 바꾸면 `_configure_argparse_i18n` 흐름을 확인하라.

## 10. 테스트 표준

프로젝트 test는 표준 library `unittest`를 사용한다. root에서 다음을 실행하라.

```bash
./run-tests.sh
```

script는 다음 환경을 설정한다.

```text
PYTHONPATH=$PWD/src/usr/lib/python3/dist-packages
APPRUN_LANG=en
```

변경 유형별 최소 test를 추가하라.

| 변경 | 필수 test |
|---|---|
| parser | option order, invalid value, missing pair, app args split |
| metadata | directory/bundle, invalid JSON/type, fallback/invalid ID |
| validation | valid boundary와 traversal/control cases |
| desktop | quoting, sensitive override, injection rejection |
| systemd | unit validation, argv serialization, invalid type |
| packages | version constraint, invalid package, installed/missing |
| safe I/O | symlink target/parent rejection, mode/content |
| runtime path | default/portable/inherit combination |
| host integration | subprocess argv, user/root branch, cleanup on failure |

root/systemd/desktop integration test는 실제 host를 변경하지 않도록 mock 또는 disposable VM을 사용하라.

Windows에서는 `pwd`, `grp`, `fcntl`, FUSE와 systemd가 없으므로 전체 suite를 Linux/WSL에서 확인하라. Windows-only pass를 release evidence로 사용하지 마라.

## 11. Build와 package 검증

package/install 파일을 바꿨으면 headless build를 실행하라.

```bash
./build.sh --no-gui
```

GUI integration, DropIn service, MIME, thumbnailer 또는 desktop asset을 바꿨으면 GUI build도 실행하라.

```bash
./build.sh
```

GUI build는 내장 `AppRunDropInService.apprunxproj`를 package할 수 있는 `apprun3-package` 또는 호환 command가 필요하다.

uv package build를 바꿨으면 target architecture와 checksum verification을 확인하라.

```bash
./build-uv.sh
./build-uv.sh arm64
```

build가 workspace의 source mode/owner를 재귀적으로 바꾸지 않는지 확인하라. 임시 stage를 사용하고 cleanup trap을 유지하라.

## 12. 변경 완료 기준

다음을 만족하라.

- 변경이 올바른 module boundary에 있다.
- public command/import compatibility가 유지된다.
- bundle-controlled input이 host operation 전에 검증된다.
- subprocess와 generated config가 안전하게 serialization된다.
- privileged write가 symlink와 ownership을 검토한다.
- 영어/한국어 message key가 동기화된다.
- 변경에 대응하는 positive/negative regression test가 있다.
- `./run-tests.sh`가 Linux에서 통과한다.
- 영향 범위에 따라 headless/GUI build가 통과한다.
- 실행하지 못한 integration test와 남은 위험을 명시한다.
