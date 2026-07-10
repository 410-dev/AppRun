---
name: build-apprun-apps
description: Design, build, package, inspect, run, register, and troubleshoot Linux software using AppRun Format 3 .apprunx bundles. Use when Codex needs to create or review an AppRun application project, define AppRunMeta metadata and entry points, manage Python or Debian dependencies, use the apprun3 or apprun3-package CLI, configure portable execution, desktop or systemd integration, or modify the AppRun framework itself.
---

# Build AppRun applications

AppRun Format 3으로 Linux 애플리케이션을 설계하고 `.apprunx` 단일 파일로 패키징하라. 신규 작업에는 deprecated된 Format 1/2를 사용하지 마라.

## 문서 선택

작업에 필요한 문서만 읽어라.

- 번들 구조, ID, 메타데이터, 진입점, 의존성, 데이터와 보안 규칙을 설계하거나 검토할 때 [Format 3 기술 표준](references/format3-standard.md)을 읽어라.
- 패키징, 실행, 조회, portable, 추출, desktop 등록, systemd와 GUI startup 명령을 사용할 때 [`apprun3` CLI 사용 매뉴얼](references/cli-manual.md)을 읽어라.
- AppRun 런타임, CLI, 라이브러리, 설치 패키지 또는 번역을 수정할 때 [프레임워크 개발 표준](references/framework-development-standard.md)을 읽어라.
- Python 앱에서 Box 파일, 런타임 경로, 단일 프로세스, GUI 아이콘 또는 host integration API가 필요할 때 [AppContext 스킬](../use-appcontext/SKILL.md)을 읽어라.

저장소 문서와 동작이 충돌하면 현재 구현과 테스트를 우선하고, 발견한 차이를 결과에 기록하라.

## 작업 유형 결정

요청을 먼저 다음 중 하나로 분류하라.

1. 새 앱 제작: 애플리케이션 코드와 `.apprunxproj` 번들 소스를 함께 구성하라.
2. 기존 앱 패키징: 기존 빌드 구조를 보존하고 AppRun 전용 파일만 최소한으로 추가하라.
3. 번들 운영: 기존 `.apprunx`를 변경하지 않고 `apprun3`로 조회, 준비, 실행 또는 등록하라.
4. 프레임워크 개발: 공개 CLI/API 호환성과 host security boundary를 보존하며 `src/`와 테스트를 수정하라.

사용자가 기존 프로젝트를 제공하면 언어, GUI toolkit, 데이터 경로, 빌드 시스템과 대상 아키텍처를 저장소에서 먼저 확인하라. 결과를 크게 바꾸거나 host 상태를 변경하는 선택만 사용자에게 확인하라.

## 앱 제작 절차

다음 순서로 작업하라.

1. 대상 Debian/Ubuntu 계열 버전과 CPU 아키텍처를 확인하라.
2. 자동 진입점 `main.py`, `main.jar`, `main.sh`, 실행 가능한 `main` 중 하나를 우선 선택하라.
3. `<app-name>.apprunxproj/` 아래에 `AppRunMeta/id`, `AppRunMeta/meta.json`, 앱 코드와 필요한 리소스를 구성하라.
4. 앱 ID, 메타데이터와 의존성을 [Format 3 기술 표준](references/format3-standard.md)에 맞추라.
5. 번들 mount를 읽기 전용으로 취급하고, 변경 데이터는 XDG 디렉터리 또는 AppRun Box에 저장하라.
6. 패키징 전에 앱 자체 단위 테스트와 빌드를 실행하라.
7. Linux에서 `apprun3-package`로 패키징하고 정보 조회, 준비, 실제 실행을 검증하라.
8. 수행한 검증과 수행하지 못한 Linux/GUI/systemd 검증을 구분해 보고하라.

## 핵심 규칙

- `.apprunx`는 생성 산출물로 취급하고 직접 수정하지 마라. 소스 디렉터리를 고친 뒤 다시 패키징하라.
- AppRun CLI 옵션은 번들 경로 앞에, 앱 인자는 번들 경로 뒤에 놓아라.
- `entry_point`의 shell quoting, pipe, redirect 또는 환경 변수 대입에 의존하지 마라. 복잡한 실행은 `main.sh`로 감싸라.
- Python 자동 venv가 필요하면 최상위 `main.py`와 `requirements.txt`를 사용하라.
- 번들 입력과 메타데이터를 신뢰하지 마라. ID, 경로, Debian 패키지, desktop 값과 systemd unit을 검증하라.
- `enforce_root_launch`, service 설치, global GUI startup, 자동 apt 설치는 최소 권한 원칙과 사용자 승인 범위 안에서만 사용하라.
- 기존 산출물을 덮어쓸 의도가 명확할 때만 `apprun3-package --force`를 사용하라.
- native binary와 bundled runtime은 대상 아키텍처에서 검증하라.
- 문서 예제보다 `src/` 구현과 회귀 테스트를 우선하라.

## 최소 번들 예시

```text
my-app.apprunxproj/
├── AppRunMeta/
│   ├── id
│   ├── meta.json
│   └── DesktopLinks/
│       └── Icon.png
├── main.py
└── requirements.txt
```

```json
{
  "name": "My App",
  "version": "1.0.0",
  "description": "Short application description",
  "type": "Application",
  "python_version": "3.12"
}
```

## 기본 검증

Linux/AppRun 환경에서 다음 최소 흐름을 실행하라. 상세 옵션은 [CLI 사용 매뉴얼](references/cli-manual.md)을 따르라.

```bash
mkdir -p dist
apprun3-package ./my-app.apprunxproj \
  -o ./dist/my-app.apprunx \
  --prefer speed \
  --force

apprun3 --is-format3 ./dist/my-app.apprunx
apprun3 --id ./dist/my-app.apprunx
apprun3 --info ./dist/my-app.apprunx
apprun3 --prepare ./dist/my-app.apprunx
apprun3 ./dist/my-app.apprunx
```

개발 반복에는 `--prefer speed`, 일반 배포에는 기본 `balanced`, 크기가 우선인 최종 배포에만 `--prefer size`를 사용하라.

## 완료 기준

다음을 확인한 뒤 완료로 보고하라.

- 필수 번들 구조와 안전한 ID가 존재한다.
- 메타데이터가 유효한 UTF-8 JSON 객체다.
- 선택한 진입점과 앱 인자 전달이 동작한다.
- Python 및 Debian 의존성 준비가 깨끗한 Box에서 성공한다.
- 앱이 읽기 전용 mount에 데이터를 쓰지 않는다.
- 첫 실행과 캐시된 두 번째 실행을 모두 확인했다.
- 공백 또는 비 ASCII 문자가 있는 번들 경로를 확인했다.
- portable을 지원하면 Box와 mount 조합을 별도로 확인했다.
- GUI, desktop, service 기능은 필요한 범위에서 대상 Linux 환경으로 확인했다.
- 생성한 `.apprunx` 경로와 남은 미검증 항목을 명시했다.

Linux/AppRun 실행 환경이 없으면 소스 테스트, JSON, 파일 구조와 코드 수준 검증만 수행하라. 실제 `.apprunx`를 만들거나 실행하지 못했다면 그 사실과 사용자가 실행할 명령을 명확히 남겨라.
