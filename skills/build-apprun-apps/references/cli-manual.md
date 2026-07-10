# `apprun3` 및 `apprun3-package` 사용 매뉴얼

## 목차

1. 전제 조건
2. 명령 문법과 옵션 순서
3. 도움말과 일반 실행
4. 정보 조회
5. 준비와 desktop 등록
6. Portable과 Box 상속
7. 번들 파일 추출
8. Bundled systemd service
9. Generated systemd service
10. Global user service
11. GUI 로그인 자동 시작
12. 환경 변수와 자동화
13. 종료 코드
14. `apprun3-package` 패키징
15. 표준 검증 시나리오
16. 문제 해결

## 1. 전제 조건

신규 문서와 자동화에는 호환성 별칭 `apprun`/`apprun-package` 대신 `apprun3`/`apprun3-package`를 사용하라.

실행 환경에 다음이 필요하다.

- AppRun 3.x
- squashfs mount/inspection 도구
- Python 번들에는 `uv`
- Format 3 package 생성에는 `mksquashfs`
- 선택 기능에는 Java, screen, desktop, systemd 등 해당 host dependency

명령은 Linux에서 실행하라. Windows에서 파일 구조와 JSON은 검사할 수 있지만 실제 package, FUSE mount, UID, desktop, systemd 동작을 검증했다고 간주하지 마라.

## 2. 명령 문법과 옵션 순서

기본 문법은 다음과 같다.

```text
apprun3 [AppRun 옵션...] <bundle.apprunx> [앱 인자...]
```

모든 AppRun 옵션을 bundle 경로 앞에 놓아라. 파서는 처음 만나는 비옵션 값을 bundle로 처리하고 나머지를 앱 인자로 전달한다.

```bash
# AppRun portable option
apprun3 --portable ./MyApp.apprunx

# application option named --portable
apprun3 ./MyApp.apprunx --portable
```

공백이 있는 경로는 shell에서 하나의 argv가 되도록 인용하라.

```bash
apprun3 --info "./Release Builds/My App.apprunx"
```

정보 조회, 준비, 등록, 추출, service 설치/제거 같은 주 작업은 한 호출에 하나만 사용하라. 여러 주 작업을 같이 주면 구현의 dispatch 순서에서 먼저 일치한 하나만 실행될 수 있다.

`--user`는 관련 install/uninstall 옵션보다 뒤, bundle보다 앞에 놓아라. 현재 parser는 앞에서 이미 확인한 작업 종류에 따라 `--user`를 해석한다.

## 3. 도움말과 일반 실행

| 명령 | 동작 |
|---|---|
| `apprun3 --help` | 전체 도움말 출력, bundle 불필요 |
| `apprun3 app.apprunx` | 준비 후 앱 실행 |
| `apprun3 app.apprunx --flag value` | 앱에 `--flag value` 전달 |

앱 exit code는 가능한 경우 `apprun3` exit code로 전달된다.

```bash
apprun3 ./MyServer.apprunx --host 127.0.0.1 --port 8080
status=$?
```

표준 출력과 표준 오류를 함께 수집하라. 앱 exit와 AppRun 준비 실패를 메시지 없이 숫자만으로 구분하지 마라.

## 4. 정보 조회

| 명령 | 출력 |
|---|---|
| `apprun3 --is-format3 app.apprunx` | `true` 또는 `false` |
| `apprun3 --id app.apprunx` | 검증된 bundle ID |
| `apprun3 --info app.apprunx` | ID, format, 전체 metadata |
| `apprun3 --info=name,version app.apprunx` | 선택한 키를 `key: value` 형식으로 출력 |
| `apprun3 --box-path app.apprunx` | 현재 옵션을 적용한 Box path |

`--is-format3`는 파일과 최소 Format 3 metadata를 검사한다. `false` 출력 시 nonzero로 종료할 수 있으므로 stdout과 exit code를 함께 확인하라.

```bash
apprun3 --is-format3 ./MyApp.apprunx
apprun3 --id ./MyApp.apprunx
apprun3 --info=id,name,version,type ./MyApp.apprunx
apprun3 --portable=box --box-path ./MyApp.apprunx
```

`--info` 출력은 JSON이 아니다. 구조화된 자동화가 필요하면 key별 line format을 엄격히 처리하거나 `AppRunMeta/meta.json`을 별도로 추출하라.

## 5. 준비와 desktop 등록

| 명령 | 동작 |
|---|---|
| `apprun3 --prepare app.apprunx` | mount, Box, Python venv와 dependency를 준비하고 앱은 실행하지 않음 |
| `apprun3 --register app.apprunx` | 준비 후 현재 사용자 desktop entry와 icon 등록 |

```bash
apprun3 --prepare ./MyApp.apprunx
apprun3 --register ./MyApp.apprunx
```

CI 또는 설치 진단에서 dependency 문제를 앱 실행과 분리할 때 `--prepare`를 사용하라. `--register`는 `~/.local/share/applications`와 icon 상태를 변경하므로 명시적 요청에서만 사용하라.

## 6. Portable과 Box 상속

`--portable`은 기본 `~/.local/apprun` 대신 bundle 옆 `<id>.apprunx.data.d/`를 사용한다.

| 옵션 | 동작 |
|---|---|
| `--portable` | portable mount와 Box 모두 사용 |
| `--portable=mount` | mount만 bundle 옆에 생성 |
| `--portable=box` | Box만 bundle 옆에 생성 |
| `--portable=mount,box` | 둘 다 명시적으로 사용 |
| `--inherit` | `full` 상속, portable Box 자동 활성화 |
| `--inherit=venv` | 기존 기본 Box의 `pyvenv/` 복사 |
| `--inherit=data` | `pyvenv/`, `.lock`, `.run`을 제외한 데이터 복사 |
| `--inherit=full` | venv와 data 모두 복사 |

```bash
apprun3 --portable ./MyApp.apprunx
apprun3 --portable=box --inherit=venv ./MyApp.apprunx
apprun3 --inherit=data ./MyApp.apprunx
```

상속은 기본 Box에서 portable Box로 복사하고 양방향 동기화하지 않는다. 중요한 기존 데이터는 backup과 크기를 확인하라. portable data directory를 source control이나 package 입력에 포함하지 마라.

## 7. 번들 파일 추출

두 옵션을 항상 함께 사용하라.

```bash
apprun3 \
  --extract-file-from=AppRunMeta/meta.json \
  --extract-file-to=./extracted-meta.json \
  ./MyApp.apprunx
```

- `--extract-file-from`에는 bundle root 기준 내부 경로를 사용하라.
- `--extract-file-to`의 부모 디렉터리는 필요하면 생성된다.
- 대상 파일을 덮어쓸 수 있으므로 보존 정책을 먼저 확인하라.
- 전체 bundle 또는 여러 파일에는 `unsquashfs`를 사용하라.

```bash
unsquashfs -l ./MyApp.apprunx
unsquashfs -cat ./MyApp.apprunx AppRunMeta/meta.json
unsquashfs -d ./unpacked ./MyApp.apprunx
```

## 8. Bundled systemd service

bundle의 `services/*.service`를 그대로 설치할 때 사용하라. unit 내용을 신뢰하지 말고 privileged directive와 executable path를 먼저 검토하라.

```bash
sudo apprun3 --install-services ./MyApp.apprunx
sudo apprun3 --install-services --enable ./MyApp.apprunx
sudo apprun3 --install-services --start ./MyApp.apprunx
sudo apprun3 --uninstall-services ./MyApp.apprunx
```

- `--enable`: 설치 후 enable
- `--start`: enable 후 즉시 start
- `--uninstall-services`: 해당 bundle의 service를 stop, disable, remove

이 작업은 `/usr/share/services.apprd/system`과 `/etc/systemd/system`을 변경한다. 명시적 승인과 root 권한 범위 안에서 실행하라.

## 9. Generated systemd service

AppRun이 bundle 자체를 실행하는 unit을 만들게 하려면 다음 형식을 사용하라.

```text
--install-as-service=<type>[,<after-units>][,<before-units>]
```

허용 type은 `simple`, `oneshot`, `forking`, `notify`, `idle`이다. 여러 unit은 `+`로 연결한다.

```bash
# 현재 실제 사용자의 user service
apprun3 \
  --install-as-service=simple,network-online.target \
  --enable --start \
  ./MyServer.apprunx

# 다른 사용자로 실행하는 system service
sudo apprun3 \
  --install-as-service=oneshot,network.target+dbus.service,graphical.target \
  --user=appuser \
  --enable \
  ./MyJob.apprunx

# Before만 지정
apprun3 \
  --install-as-service=simple,,graphical.target \
  ./MyApp.apprunx
```

`--user`를 생략하거나 현재 실제 사용자를 지정하면 user service를 만든다. 다른 사용자를 지정하면 `User=`를 가진 system service를 만들며 privilege가 필요하다.

```bash
apprun3 --uninstall-as-service ./MyServer.apprunx
sudo apprun3 --uninstall-as-service --user=appuser ./MyJob.apprunx
```

user service에는 실행 중인 user systemd와 D-Bus runtime이 필요할 수 있다.

## 10. Global user service

모든 사용자의 systemd user unit을 설치할 때만 사용하라.

```bash
sudo apprun3 --install-as-global-user-service ./MyApp.apprunx
sudo apprun3 \
  --install-as-global-user-service=simple,network-online.target \
  --enable \
  ./MyApp.apprunx
sudo apprun3 --uninstall-as-global-user-service ./MyApp.apprunx
```

명세를 생략하면 `simple`을 사용한다. `--start`는 global enable을 수행하지만 모든 사용자의 instance를 즉시 시작하지 않는다. 로그인 중인 사용자는 `systemctl --user daemon-reload`와 별도 start가 필요할 수 있다.

## 11. GUI 로그인 자동 시작

```bash
# 현재 사용자
apprun3 --install-as-gui-startup ./MyApp.apprunx

# 특정 사용자
sudo apprun3 \
  --install-as-gui-startup=user \
  --user=alice \
  ./MyApp.apprunx

# 모든 사용자
sudo apprun3 --install-as-gui-startup=global ./MyApp.apprunx

# 등록 후 즉시 실행
apprun3 --install-as-gui-startup --start ./MyApp.apprunx
```

생성된 `Exec`에서 bundle 앞의 AppRun 옵션과 bundle 뒤의 앱 인자를 구분하라.

```bash
apprun3 \
  --install-as-gui-startup \
  --apprunarg=--portable=box \
  --runarg=--minimized \
  --runargs-start="--profile 'work user' --silent" \
  ./MyApp.apprunx
```

| 옵션 | 용도 |
|---|---|
| `--apprunarg=<arg>` | 단일 AppRun option, 반복 가능 |
| `--apprunargs=<args>` | 여러 AppRun option |
| `--runarg=<arg>` | 단일 app argument, 반복 가능 |
| `--runargs-start=<args>` | 여러 app argument |

공백이 있으면 shell-like quoting을 사용한다. 공백 없이 comma만 있으면 comma가 argument separator로 처리된다. 이 옵션들은 `--install-as-gui-startup`과 함께만 사용하라.

```bash
apprun3 --uninstall-as-gui-startup ./MyApp.apprunx
sudo apprun3 --uninstall-as-gui-startup=user --user=alice ./MyApp.apprunx
sudo apprun3 --uninstall-as-gui-startup=global ./MyApp.apprunx
```

## 12. 환경 변수와 자동화

언어 선택 우선순위는 `APPRUN_LANG`, `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`이다.

```bash
APPRUN_LANG=en apprun3 --help
APPRUN_LANG=ko apprun3 --info ./MyApp.apprunx
```

headless에서 누락된 `apt-requirements`를 묻지 않고 설치하려면 `AUTO_INSTALL_BASEPKG=1`을 사용할 수 있다.

```bash
AUTO_INSTALL_BASEPKG=1 apprun3 --prepare ./MyApp.apprunx
```

이 값은 `sudo apt-get install -y`를 유발할 수 있다. disposable image 또는 사용자가 승인한 배포 자동화에서만 사용하라. GUI 환경에서는 별도 확인 흐름이 적용될 수 있다.

## 13. 종료 코드

| 코드 | 의미 |
|---|---|
| `0` | AppRun 작업 성공 또는 앱 정상 종료 |
| `1` | 일반 오류, 설치 거부/실패, mount/준비 실패 등 |
| `2` | CLI 사용법 오류, unknown option, 잘못된 조합 |
| `9` | 준비 단계에서 진입점 없음 |
| `10` | 실행 단계에서 명령 생성 실패 |
| `127` | `launch_in_screen: "enforced"`이고 screen 없음 |
| 기타 | 실행 앱 또는 external command exit code일 수 있음 |

자동화에서는 stderr와 작업 종류를 함께 기록하라.

## 14. `apprun3-package` 패키징

문법은 다음과 같다.

```text
apprun3-package <bundle-directory> [-o <output>] \
  [--prefer speed|balanced|size] [--force]
```

| 옵션 | 동작 |
|---|---|
| `-o`, `--output` | output path 지정, 기본 `<directory-name>.apprunx` |
| `--prefer speed` | lz4, 개발/테스트용 |
| `--prefer balanced` | zstd, 기본값 |
| `--prefer size` | xz, 크기 우선 배포 |
| `--force` | 기존 output 삭제 후 덮어쓰기 |

입력 이름이 `.apprunxproj`로 끝나면 기본 output에서 해당 suffix를 제거한다.

```bash
mkdir -p dist

# 빠른 개발 build
apprun3-package ./MyApp.apprunxproj \
  -o ./dist/MyApp.apprunx \
  --prefer speed \
  --force

# 일반 release
apprun3-package ./MyApp.apprunxproj \
  -o ./dist/MyApp.apprunx \
  --prefer balanced \
  --force

# 크기 최적화 release
apprun3-package ./MyApp.apprunxproj \
  -o ./dist/MyApp-small.apprunx \
  --prefer size
```

기존 파일을 덮어쓸 의도가 명확할 때만 `--force`를 사용하라. 패키징 실패 시 partial output은 제거된다.

패키징 검사는 다음을 다룬다.

- `AppRunMeta/id`: 누락/unsafe이면 error
- 실행 가능한 entry point: 없으면 error
- `name`, `version`, `type`: 누락 시 warning
- `python_version`: string이 아니면 error
- `DesktopLinks/Icon.png`: 누락 시 warning

경고를 무시해야 하는 제품 요구사항이 없으면 해결하라.

## 15. 표준 검증 시나리오

```bash
set -eu

bundle=./dist/MyApp.apprunx

apprun3 --is-format3 "$bundle"
apprun3 --id "$bundle"
apprun3 --info "$bundle"
apprun3 --prepare "$bundle"
apprun3 "$bundle" --self-test
```

추가로 확인하라.

- clean Box 첫 실행
- 두 번째 실행에서 venv/cache reuse
- space/non-ASCII bundle path
- app argument forwarding
- normal과 portable path
- read-only mount와 writable data 분리
- GUI icon/desktop/crash behavior
- service/autostart install와 uninstall
- target architecture native dependency

## 16. 문제 해결

- `no entry point found`: `AppRunMeta/id`, `entry_point`, 자동 진입점과 binary execute bit를 확인하라.
- Python 설치 반복/실패: `requirements.txt`, `python_version`, Box checksum, `uv`를 확인하라.
- metadata 출력 오류: `meta.json`이 UTF-8 JSON object인지 확인하라.
- bundle write 실패: mount에 쓰지 말고 XDG 또는 Box로 옮겨라.
- portable 위치 오류: CLI와 `EnforcePortable`/`EnforceInherit` 합성 결과를 확인하라.
- 앱 option이 적용되지 않음: AppRun option과 bundle path의 순서를 확인하라.
- `--user`가 unknown option: install/uninstall 작업 flag보다 뒤에 배치하라.
- desktop/service 실패: ID, control character, relative path와 unit/package name을 검증하라.
- `false` Format 3: squashfs, `AppRunMeta/id`, `AppRunMeta/meta.json` 존재를 확인하라.
