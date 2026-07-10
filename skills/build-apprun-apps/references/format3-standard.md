# AppRun Format 3 기술 표준

## 목차

1. 적용 범위와 규범 용어
2. 번들 모델
3. 표준 디렉터리 구조
4. 애플리케이션 ID
5. 메타데이터 표준
6. 진입점 표준
7. Python 의존성
8. Debian 및 기타 런타임 의존성
9. 번들 리소스와 데이터 저장
10. Portable 정책
11. Desktop 및 서비스 통합
12. 보안 표준
13. 호환성과 배포 검증

## 1. 적용 범위와 규범 용어

이 문서는 AppRun 3.x Format 3 애플리케이션 프로젝트와 `.apprunx` 산출물의 기술 표준을 정의한다. 신규 앱, 기존 앱의 AppRun 패키징, 번들 리뷰에 적용하라.

규범 수준을 다음처럼 해석하라.

- **필수**: 만족하지 않으면 유효하거나 안전한 번들로 간주하지 마라.
- **권장**: 특별한 근거가 없으면 따르라. 예외 근거를 기록하라.
- **선택**: 요구사항에 필요한 경우에만 사용하라.

Format 1/2와 디렉터리형 `.apprun` 번들은 deprecated 상태다. 신규 제작과 기능 추가는 Format 3만 대상으로 하라.

## 2. 번들 모델

Format 3 산출물은 squashfs 기반 `.apprunx` 단일 파일이다. 런타임은 실행 시 임시 경로에 읽기 전용으로 mount하고, 앱별 쓰기 상태는 Box에 둔다.

다음 경계를 유지하라.

- 번들 소스: 개발자가 수정하는 `.apprunxproj/` 또는 일반 디렉터리
- 번들 산출물: `apprun3-package`가 만든 `.apprunx`
- mount: 실행 중인 읽기 전용 번들 내용
- Box: venv, dependency checksum, 앱 상태를 담는 쓰기 가능 공간

산출물을 직접 편집하지 말고 소스를 수정한 뒤 재패키징하라.

## 3. 표준 디렉터리 구조

최소 구조는 다음과 같다.

```text
my-app.apprunxproj/
├── AppRunMeta/
│   ├── id                         # 필수
│   ├── meta.json                  # 필수로 취급
│   ├── libs                       # 선택: Python Collection ID/PYTHONPATH
│   └── DesktopLinks/
│       ├── Icon.png               # GUI 앱에 권장
│       └── desktopfile.desktop    # 선택
├── main.py | main.jar | main.sh | main
├── requirements.txt               # 선택: Python 앱
└── services/                       # 선택: bundled systemd units
    └── example.service
```

다음을 필수로 적용하라.

- `AppRunMeta/id`를 UTF-8 텍스트 파일로 만들라.
- `AppRunMeta/meta.json`을 JSON object로 만들라.
- 자동 진입점 또는 유효한 `entry_point` 하나 이상을 제공하라.
- binary `main`을 사용할 때 실행 권한을 보존하라.

패키징 도구는 `__pycache__`, `*.pyc`, `*.pyo`, `.git`, `.gitignore`, `.DS_Store`, `*.apprunx`를 기본 제외한다. 민감 정보와 개발 전용 파일은 제외 목록에만 의존하지 말고 번들 소스에 넣지 마라.

## 4. 애플리케이션 ID

ID는 Box, mount, desktop, service와 host 경로의 기준이다. 전역적으로 고유하고 장기간 안정적인 값을 사용하라.

권장 형식은 소문자 reverse-DNS다.

```text
com.example.my-app
```

다음 규칙을 필수로 적용하라.

- 첫 글자와 마지막 글자에 영문자 또는 숫자를 사용하라.
- 슬래시, 역슬래시, 공백, 제어 문자와 `..` 컴포넌트를 사용하지 마라.
- 선행 `.` 또는 `-`를 사용하지 마라.
- 앱 업데이트에서 ID를 바꾸지 마라. 변경하면 새 Box와 새 등록 항목으로 취급될 수 있다.
- 사용자 입력이나 파일명을 검증 없이 ID로 사용하지 마라.

현재 validator는 호환성을 위해 영문 대소문자, 숫자, `_`, `.`, `-`를 최대 128자 범위에서 허용한다. 새 ID에는 더 보수적인 소문자 표준을 사용하라.

## 5. 메타데이터 표준

`AppRunMeta/meta.json`은 UTF-8 JSON object여야 한다. 배열, scalar, 주석, trailing comma를 사용하지 마라.

### 5.1 기본 메타데이터

| 키 | 수준 | 타입 | 규칙 |
|---|---|---|---|
| `name` | 권장 | string | 사람에게 표시할 안정적인 이름 |
| `version` | 권장 | string | 앱 릴리스 버전 |
| `description` | 권장 | string | 한 줄 설명, desktop/service에도 사용 가능 |
| `type` | 권장 | string | `Application` 또는 `Utility` |
| `author` | 선택 | string | 제작자/조직 |

`type: "Application"`은 nonzero 종료를 crash로 알린다. 정상적으로 빠르게 종료되는 단발성 도구에는 `Utility`를 사용하라. 1초 미만 정상 종료 경고가 필요할 때만 `warn_on_fast_exit: true`를 추가하라.

### 5.2 실행 메타데이터

| 키 | 수준 | 타입 | 허용값/의미 |
|---|---|---|---|
| `entry_point` | 선택 | string | 커스텀 실행 명령, `{APPDIR}` 지원 |
| `python_version` | 선택 | string | `uv venv --python`에 전달할 버전 |
| `apt-requirements` | 선택 | string[] | Debian 패키지와 단순 버전 조건 |
| `enforce_root_launch` | 선택 | boolean | 전체 앱을 `sudo`로 실행 |
| `keep_environment` | 선택 | boolean | root 실행 시 `sudo -E` 사용 |
| `launch_in_terminal` | 선택 | boolean | 터미널 emulator로 감싸 실행 |
| `launch_in_screen` | 선택 | string | `recommend` 또는 `enforced` |
| `warn_on_fast_exit` | 선택 | boolean | Application의 빠른 정상 종료 경고 |

`enforce_root_launch`는 일반 앱에 사용하지 마라. 작은 privileged helper로 권한 경계를 분리할 수 없는 명확한 근거가 있을 때만 선택하라. `keep_environment`는 환경 변수 공격면을 검토한 경우에만 사용하라.

### 5.3 Portable 메타데이터

| 키 | 수준 | 타입 | 허용값 |
|---|---|---|---|
| `EnforcePortable` | 선택 | string[] | `mount`, `box` |
| `EnforceInherit` | 선택 | string[] | `venv`, `data`, `full` |

키의 대소문자를 그대로 유지하라. 새 번들에는 배열 타입을 사용하라. `EnforceInherit`는 portable Box를 자동 활성화한다.

### 5.4 표준 예시

```json
{
  "name": "Example App",
  "version": "1.0.0",
  "description": "Example AppRun application",
  "type": "Application",
  "author": "Example Organization",
  "python_version": "3.12",
  "apt-requirements": ["libnotify-bin"]
}
```

## 6. 진입점 표준

런타임 실행 선택 순서는 다음과 같다.

1. `meta.json`의 nonempty `entry_point`
2. `main.py`
3. `main.jar`
4. `main.sh`
5. 실행 가능한 `main`

자동 진입점을 우선 사용하라.

| 파일 | 실행 방식 | 적용 기준 |
|---|---|---|
| `main.py` | Box의 `pyvenv/bin/python3 main.py` | Python 앱 기본 |
| `main.jar` | `/usr/bin/java -jar main.jar` | Java 앱 |
| `main.sh` | `/bin/bash main.sh` | 복합 시작 로직 또는 shell 앱 |
| `main` | binary 직접 실행 | native/self-contained 앱 |

`entry_point`는 단순 argv로만 작성하라.

```json
{
  "entry_point": "node {APPDIR}/src/index.js"
}
```

현재 구현은 `{APPDIR}` 치환 후 문자열을 공백으로 분할한다. 다음을 `entry_point`에 넣지 마라.

- 공백을 보존해야 하는 quoted argument
- pipe, redirect, `&&`, `;`
- shell variable assignment 또는 expansion
- 사용자 입력을 포함하는 명령 문자열

복잡한 경우 최상위 `main.sh`에서 안전한 shell script로 구현하고, 인자를 `"$@"`로 전달하라.

## 7. Python 의존성

자동 venv가 필요한 Python 앱은 최상위 `main.py`를 제공해야 한다. AppRun 준비 단계는 `main.py`가 있을 때만 Python venv를 생성한다.

다음을 적용하라.

- PyPI 의존성을 최상위 `requirements.txt`에 선언하라.
- 재현 가능한 배포에는 버전을 pin하라.
- 필요한 경우 `python_version`을 문자열로 지정하라.
- 앱 데이터와 사용자 cache를 `pyvenv/`에 저장하지 마라.
- `requirements.txt` 또는 `python_version` 변경 시 venv가 재생성될 수 있음을 전제로 하라.

AppRun은 `requirements.txt`의 SHA-256을 Box에 저장한다. checksum이 바뀌면 venv를 다시 만들고 `uv pip install`을 실행한다.

시스템 Python 모듈이 필요할 때만 `AppRunMeta/libs`를 사용하라.

```text
system-site:com.example.shared@python:/opt/example/python
```

각 항목은 `:`로 구분한다. Collection ID는 대상 시스템의 `/usr/share/dictionaries/apprun-python/*.json`에 등록되어야 한다. 일반 Python dependency에는 Collection ID보다 `requirements.txt`를 우선하라.

AppContext를 사용할 때는 [AppContext 스킬](../../use-appcontext/SKILL.md)을 따르라.

## 8. Debian 및 기타 런타임 의존성

`apt-requirements`에는 유효한 소문자 Debian package 이름과 필요한 경우 단순 비교 조건을 사용하라.

```json
{
  "apt-requirements": [
    "nodejs",
    "ffmpeg",
    "python3>=3.10"
  ]
}
```

지원 연산자는 `>=`, `<=`, `==`, `>`, `<`다. 대상 배포판의 실제 package 이름과 버전 비교 결과를 검증하라. 사용자가 설치를 거부하거나 설치가 실패하면 앱 실행이 중단될 수 있다.

다른 언어/runtime에는 다음 중 하나를 선택하라.

1. host package를 `apt-requirements`에 선언하라.
2. 라이선스와 아키텍처를 확인해 runtime을 번들에 포함하라.
3. self-contained native binary를 제공하라.

bundled binary가 mount 내부에서 실행되고 write 가능한 설치 경로를 전제하지 않는지 확인하라.

## 9. 번들 리소스와 데이터 저장

mount된 번들 내부는 읽기 전용이다. `APPDIR`, `main.py`의 위치, 번들 resource directory에 다음을 쓰지 마라.

- 설정 변경
- SQLite/database journal
- log
- downloaded update
- model/cache
- temporary file

쓰기 데이터에는 다음 우선순위를 적용하라.

1. 일반 Linux 앱: XDG data/config/cache/runtime 디렉터리
2. AppRun 결합 데이터: Box 또는 AppContext file API
3. 사용자가 명시한 portable 데이터: portable Box

resource path와 writable path를 코드에서 별도 변수와 API로 유지하라.

## 10. Portable 정책

기본 데이터 경로는 다음과 같다.

```text
~/.local/apprun/boxes/<id>/
~/.local/apprun/mounts/<id>.<random>/
```

portable 실행은 번들 옆에 다음 구조를 만든다.

```text
<id>.apprunx.data.d/
├── box/
└── mounts/<id>.<random>/
```

`venv`, `data`, `full` 상속 범위를 이해하고 선택하라. `data`는 `pyvenv/`, `.lock`, `.run`을 제외한다. 상속은 기본 Box에서 portable Box로 복사하는 동작이며 양방향 동기화가 아니다.

portable을 metadata로 강제하지 않는 것을 기본으로 하라. 제품 요구사항일 때만 `EnforcePortable`과 `EnforceInherit`를 사용하고, 대용량 또는 민감 데이터 복사를 사용자에게 설명하라.

## 11. Desktop 및 서비스 통합

GUI 앱에는 `AppRunMeta/DesktopLinks/Icon.png`를 권장한다. PNG 파일이 실제 이미지인지 확인하라.

custom desktop metadata가 필요할 때만 `desktopfile.desktop`을 추가하라. AppRun은 host-sensitive 필드인 `Exec`, `Icon`, `Type`, `Terminal`, `StartupWMClass`를 안전한 값으로 재생성할 수 있다. newline/control character를 metadata에 넣지 마라.

bundled systemd unit은 다음 경로에만 배치하라.

```text
services/<safe-name>.service
```

unit 이름, `ExecStart`, dependency와 privileged directive를 설치 전에 검토하라. 앱이 단순히 번들을 서비스로 실행하면 custom unit보다 AppRun generated service를 우선 검토하라.

## 12. 보안 표준

다음을 필수로 적용하라.

- 번들과 메타데이터를 untrusted input으로 취급하라.
- ID와 모든 host path fragment를 검증하라.
- 상대 경로에서 absolute path, `..`, NUL과 symlink escape를 거부하라.
- subprocess를 argv list로 실행하고 shell string 결합을 피하라.
- Debian package 이름과 systemd unit 이름을 allowlist 형식으로 검증하라.
- desktop scalar에서 newline과 control character를 거부하라.
- privileged path를 쓸 때 symlink를 따라가지 마라.
- root 실행, package 설치, service/autostart 등록을 자동으로 수행하지 마라.
- secret, token, private key와 사용자 데이터를 번들 산출물에 포함하지 마라.

## 13. 호환성과 배포 검증

최종 번들을 다음 환경과 시나리오에서 검증하라.

- 지원하는 최소 Debian/Ubuntu 릴리스
- 지원하는 각 CPU 아키텍처
- 깨끗한 사용자와 깨끗한 Box의 첫 실행
- dependency가 이미 준비된 두 번째 실행
- 공백과 비 ASCII 문자가 있는 bundle path
- normal 및 portable Box/mount 조합
- GUI가 있는 desktop과 headless 환경 중 지원 대상
- 앱 인자, nonzero exit, signal 종료
- native library/runtime 로딩
- desktop/service 설치와 제거가 요구되는 경우 disposable system

검증하지 않은 플랫폼과 host integration을 릴리스 결과에 명시하라.
