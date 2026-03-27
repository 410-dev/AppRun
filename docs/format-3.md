# AppRun Format 3 Documentation

---

## 목차

1. 개요
2. 설치
3. 번들 구조
4. AppRunMeta/meta.json 레퍼런스
5. 번들 제작 가이드
6. 명령어 레퍼런스
7. 고급 기능
8. 문제 해결

---

## 1. 개요

AppRun 은 리눅스용 애플리케이션 번들 프레임워크입니다. macOS 의 `.app` 형식에서 영감을 받아, 앱 실행에 필요한 모든 파일을 하나의 번들로 묶고 더블클릭으로 실행할 수 있게 합니다.

**Format 3** 은 AppRun 의 세 번째 번들 포맷으로, 이전 포맷과의 주요 차이점은 다음과 같습니다.

| 항목 | Format 1/2 | Format 3 |
|------|-----------|---------|
| 번들 형태 | 디렉터리 (`.apprun`) | squashfs 압축 파일 (`.apprunx`) |
| 실행 방법 | `apprun <dir>` 만 가능 | 더블클릭 또는 `apprun3 <file>` |
| 메타데이터 | 개별 파일 | `meta.json` 통합 |
| 언어 지원 | Python, Java, Bash, Binary | + `EntryPoint` 로 모든 언어 |
| 체크섬 | md5 | sha256 |

---

## 2. 설치

### Debian 계열

```bash
# 빌드
./build.sh

# 설치
sudo apt install ./apprun.deb -y
```


### 의존성 패키지 (수동)

uv 및 의존성 패키지와 MIME 업데이트 등 설치에 관련된 작업은 dpkg / apt 로 설치시 자동 수행됩니다.

```bash
# 필수
sudo apt install squashfs-tools squashfuse fuse python3 libnotify-bin

# 권장 (GUI 알림)
sudo apt install zenity

# Java 번들 실행 시
sudo apt install default-jre
```

### uv 설치 (Python 번들용)

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

### MIME 타입 및 기본 앱 등록

```bash
# MIME 타입 등록
sudo update-mime-database /usr/share/mime

# 기본 앱 등록 (.apprunx 더블클릭 시 apprun3 으로 실행)
sudo update-desktop-database /usr/share/applications
xdg-mime default apprun3.desktop application/x-apprunx

# 썸네일 캐시 초기화
rm -rf ~/.cache/thumbnails/
nautilus -q && nautilus
```

---

## 3. 번들 구조

`.apprunx` 파일은 내부적으로 squashfs 압축 파일시스템입니다. 번들을 제작할 때는 다음 디렉터리 구조를 가진 폴더를 만든 후 `apprun3-package` 로 패키징합니다.

### 전체 구조

```
my-app/                               ← 번들 루트
│
├── AppRunMeta/                       ← 필수, 메타데이터 디렉터리
│   ├── id                            ← 필수, 번들 고유 ID
│   ├── meta.json                     ← 권장, 앱 정보 및 실행 설정
│   ├── libs                          ← 옵셔널, PYTHONPATH 주입용
│   └── DesktopLinks/
│       └── Icon.png                  ← 권장, 앱 아이콘
│
├── main.py                           ← Python 앱 진입점
├── main.jar                          ← Java 앱 진입점
├── main.sh                           ← Bash 앱 진입점
├── main                              ← 바이너리 진입점 (실행 권한 필요)
└── requirements.txt                  ← 옵셔널, Python 의존성
```

진입점은 위 중 하나만 있으면 됩니다. `meta.json` 의 `entry_point` 를 사용하면 파일명 제한 없이 자유롭게 지정할 수 있습니다.

### AppRunMeta/id

번들의 고유 식별자입니다. 실행 시 캐시 디렉터리, 가상환경 경로 등 모든 경로의 기준이 됩니다.

```
my_awesome_app
```

**규칙:**
- 영문 소문자, 숫자, 언더스코어(`_`) 만 사용
- 공백 없음
- 다른 앱과 겹치지 않도록 고유하게 작성

---

## 4. AppRunMeta/meta.json 레퍼런스

### 전체 예시

```json
{
    "name":               "My Awesome App",
    "version":            "1.0.0",
    "description":        "앱에 대한 간단한 설명",
    "type":               "Application",
    "author":             "홍길동",

    "entry_point":        "python {APPDIR}/src/main.py",

    "enforce_root_launch": false,
    "keep_environment":    false,
    "launch_in_terminal":  false,
    "launch_in_screen":    "recommend"
}
```

### 키 레퍼런스

#### 앱 정보

| 키 | 필수 여부 | 타입 | 설명 |
|----|----------|------|------|
| `name` | 🟡 권장 | string | 사람이 읽을 수 있는 앱 이름. 런처에 표시됨 |
| `version` | 🟡 권장 | string | 앱 버전. 형식 자유 (`1.0.0`, `2024.01` 등) |
| `description` | 🔵 옵셔널 | string | 앱 설명. 런처 툴팁에 표시됨 |
| `type` | 🟡 권장 | string | `Application` 또는 `Utility`. 크래시 감지 여부 결정 |
| `author` | 🔵 옵셔널 | string | 제작자 이름 |

`type` 이 `Application` 이면 앱이 비정상 종료되거나 1초 안에 종료될 경우 크래시 알림이 표시됩니다. `Utility` 는 크래시 감지를 하지 않습니다.

#### 실행 설정

| 키 | 필수 여부 | 타입 | 기본값 | 설명 |
|----|----------|------|--------|------|
| `entry_point` | 🔵 옵셔널 | string | 없음 | 실행 명령어. 없으면 `main.*` 파일로 자동 감지 |
| `enforce_root_launch` | 🔵 옵셔널 | bool | `false` | `true` 면 `sudo` 로 실행 |
| `keep_environment` | 🔵 옵셔널 | bool | `false` | `true` 면 `sudo -E` 로 실행 (환경변수 유지) |
| `launch_in_terminal` | 🔵 옵셔널 | bool | `false` | `true` 면 터미널 에뮬레이터 창을 띄워서 실행 |
| `launch_in_screen` | 🔵 옵셔널 | string | 없음 | `recommend` 또는 `enforced`. GNU screen 세션으로 실행 |

#### `entry_point` 변수

`entry_point` 문자열 안에서 다음 변수를 사용할 수 있습니다:

| 변수 | 설명 | 예시 |
|------|------|------|
| `{APPDIR}` | 마운트된 번들 루트 경로 | `/home/user/.local/apprun/mounts/my_app` |

예시:
```json
"entry_point": "python {APPDIR}/src/app.py --config {APPDIR}/config.ini"
```

#### `launch_in_screen` 값

| 값 | 동작 |
|----|------|
| `"recommend"` | `screen` 이 없으면 경고 후 일반 실행 |
| `"enforced"` | `screen` 이 없으면 오류 후 실행 중단 |

---

## 5. 번들 제작 가이드

### Python 앱 예시

#### 디렉터리 준비

```
my-python-app/
├── AppRunMeta/
│   ├── id
│   ├── meta.json
│   └── DesktopLinks/
│       └── Icon.png
├── main.py
└── requirements.txt
```

#### AppRunMeta/id

```
my_python_app
```

#### AppRunMeta/meta.json

```json
{
    "name":        "My Python App",
    "version":     "1.0.0",
    "description": "Python 으로 만든 앱",
    "type":        "Application"
}
```

#### requirements.txt

```
requests==2.31.0
Pillow==10.0.0
```

#### 패키징

```bash
apprun3-package ./my-python-app/
# → my-python-app.apprunx 생성
```

---

### Java 앱 예시

```
my-java-app/
├── AppRunMeta/
│   ├── id
│   └── meta.json
└── main.jar
```

```json
{
    "name":    "My Java App",
    "version": "1.0.0",
    "type":    "Application"
}
```

```bash
apprun3-package ./my-java-app/
```

---

### 커스텀 EntryPoint 예시 (Node.js)

`entry_point` 를 사용하면 Python/Java/Bash/Binary 외의 런타임도 지원할 수 있습니다.

```
my-node-app/
├── AppRunMeta/
│   ├── id
│   └── meta.json
├── index.js
└── node_modules/
```

```json
{
    "name":        "My Node App",
    "version":     "1.0.0",
    "type":        "Application",
    "entry_point": "node {APPDIR}/index.js"
}
```

---

### libs 파일 (PYTHONPATH 주입)

시스템에 설치된 Python 라이브러리를 특정 경로에서 불러와야 할 때 사용합니다. `AppRunMeta/libs` 파일에 키:값 쌍으로 작성합니다.

```
PYPATH:/usr/lib/python3/dist-packages
```

`/usr/share/dictionaries/apprun-python/` 디렉터리의 JSON 파일들이 키를 실제 경로로 변환해 `PYTHONPATH` 에 주입합니다.

---

## 6. 명령어 레퍼런스

### apprun3

```
apprun3 [--flags] <apprunx> [앱 인자...]
```

flags 없이 실행하면 번들을 실행합니다. flags 가 있으면 해당 정보를 출력하고 종료합니다.

| 명령어 | 설명 |
|--------|------|
| `apprun3 app.apprunx` | 번들 실행 |
| `apprun3 --id app.apprunx` | 번들 ID 출력 |
| `apprun3 --is-format=3 app.apprunx` | Format 3 여부 출력 (`true`/`false`) |
| `apprun3 --info app.apprunx` | 전체 메타데이터 출력 |
| `apprun3 --info=name,version app.apprunx` | 특정 키만 출력 |
| `apprun3 --box-path app.apprunx` | Box 경로 출력 |
| `apprun3 --prepare app.apprunx` | 실행 환경 준비 (venv, 마운트 등) |
| `apprun3 --extract-file-from=<내부경로> --extract-file-to=<대상경로> app.apprunx` | 번들 내 파일 추출 |

#### 앱 인자 전달

`apprunx` 경로 이후의 모든 인자는 앱으로 그대로 전달됩니다.

```bash
apprun3 my-app.apprunx --verbose --port 8080
```

---

### apprun3-package

```
apprun3-package <번들 디렉터리> [-o <출력 경로>] [--prefer speed|balanced|size]
```

| 옵션 | 설명 |
|------|------|
| `-o <경로>` | 출력 파일 경로. 기본값: `<번들 이름>.apprunx` |
| `--prefer speed` | lz4 압축. 빠른 속도, 큰 파일. 개발/테스트용 |
| `--prefer balanced` | zstd 압축. 속도/크기 균형. **(기본값)** |
| `--prefer size` | xz 압축. 최고 압축률, 느린 속도. 배포용 |

```bash
# 기본 패키징
apprun3-package ./my-app/

# 출력 경로 지정
apprun3-package ./my-app/ -o /tmp/my-app.apprunx

# 배포용 최고 압축
apprun3-package ./my-app/ -o my-app-release.apprunx --prefer size
```

패키징 전 자동으로 번들 구조를 검사합니다. 오류가 있으면 패키징이 중단되고, 경고는 출력 후 계속 진행됩니다.

**검사 항목:**

| 항목 | 수준 |
|------|------|
| `AppRunMeta/id` 존재 여부 | 오류 |
| 실행 가능한 entry point 존재 여부 | 오류 |
| `meta.json` 의 `name`, `version`, `type` | 경고 |
| `DesktopLinks/Icon.png` 존재 여부 | 경고 |

---

## 7. 고급 기능

### Box 디렉터리

앱 실행에 필요한 캐시와 가상환경은 `~/.local/apprun/boxes/<app-id>/` 에 저장됩니다.

```
~/.local/apprun/boxes/<app-id>/
├── pyvenv/                    ← Python 가상환경
├── requirements.txt.sha256    ← 의존성 변경 감지용 체크섬
├── source.path                ← 원본 .apprunx 경로
└── .lock                      ← 준비 중일 때 생성되는 잠금 파일
```

Box 를 수동으로 초기화하려면:

```bash
rm -rf ~/.local/apprun/boxes/<app-id>/
```

다음 실행 시 자동으로 재구성됩니다.

---

### 마운트 포인트

실행 중인 번들은 `~/.local/apprun/mounts/<app-id>/` 에 마운트됩니다. 읽기 전용입니다. 실행이 완료되면 자동으로 언마운트됩니다.

마운트 해제 조건은 해당 위치에서 실행중인 모든 프로세스가 종료되어 카운트가 0이 되는 것입니다.

```bash
# 마운트 상태 확인
ls ~/.local/apprun/mounts/

# 수동 언마운트
fusermount -u ~/.local/apprun/mounts/<app-id>/
```

---

### 번들 내용 확인

패키징된 `.apprunx` 파일의 내용을 마운트 없이 확인할 수 있습니다.

```bash
# 파일 목록
unsquashfs -l my-app.apprunx

# 특정 파일 내용 출력
unsquashfs -cat my-app.apprunx AppRunMeta/meta.json

# apprun3 으로 메타데이터 확인
apprun3 --info my-app.apprunx
```

---

### 수정 후 재패키징

```bash
# 1. 압축 해제
unsquashfs -d ./my-app-src/ my-app.apprunx

# 2. 수정
nano ./my-app-src/AppRunMeta/meta.json

# 3. 재패키징 (-noappend 는 apprun3-package 가 자동 처리)
apprun3-package ./my-app-src/ -o my-app.apprunx
```

---

### 하위 호환성

AppRun Format 1/2 번들(`.apprun` 디렉터리)은 `apprun` 명령어로 계속 실행할 수 있습니다. `apprun` 명령어는 입력된 경로가 `.apprunx` 파일이면 자동으로 `apprun3` 으로 라우팅합니다.

```bash
apprun my-old-app.apprun    # Format 2, 기존 방식
apprun my-new-app.apprunx   # Format 3, apprun3 으로 자동 라우팅
```

---

## 8. 문제 해결

### 더블클릭해도 실행이 안 됩니다

```bash
# MIME 타입이 올바르게 등록됐는지 확인
xdg-mime query filetype my-app.apprunx
# 출력이 application/x-apprunx 여야 합니다

# 기본 앱 확인
xdg-mime query default application/x-apprunx
# 출력이 apprun3.desktop 이어야 합니다

# 아니라면 재등록
sudo update-mime-database /usr/share/mime
sudo update-desktop-database /usr/share/applications
xdg-mime default apprun3.desktop application/x-apprunx
```

---

### 실행 시 패키지 설치가 너무 오래 걸립니다

첫 실행 시에만 `requirements.txt` 의 패키지를 설치합니다. 이후 실행부터는 `requirements.txt` 가 변경되지 않은 한 설치를 건너뜁니다. 설치 속도를 높이려면 `requirements.txt` 에 버전을 명시하세요.

```
# 버전 명시 (권장)
requests==2.31.0

# 버전 미명시 (매번 최신 버전 탐색으로 느려질 수 있음)
requests
```

---

### 앱이 실행되자마자 크래시 알림이 뜹니다

터미널에서 직접 실행해 오류 메시지를 확인하세요:

```bash
apprun3 my-app.apprunx
```

또는 `meta.json` 에 터미널 출력을 활성화:

```json
"launch_in_terminal": true
```

---

### 썸네일이 표시되지 않습니다

```bash
# 썸네일 캐시 초기화 후 Nautilus 재시작
rm -rf ~/.cache/thumbnails/
nautilus -q && nautilus
```

그래도 안 되면 `imagemagick` 이 설치됐는지 확인하세요:

```bash
sudo apt install imagemagick
```

---

### Box 를 초기화하고 싶습니다

```bash
# 특정 앱 Box 초기화
rm -rf ~/.local/apprun/boxes/<app-id>/

# 전체 Box 초기화
rm -rf ~/.local/apprun/boxes/
```