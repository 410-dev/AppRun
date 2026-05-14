# AppRun Paths

이 문서는 AppRun 3.2.0 계열이 참조하는 주요 파일 위치를 설명합니다. Format 1/2 관련 경로는 deprecated 되었으며, 아래 경로는 Format 3 (`.apprunx`) 기준입니다.

## /usr/bin

AppRun 실행 파일과 호환성 링크가 위치합니다.

- `apprun` / `apprun3`
- `apprun-package` / `apprun3-package`
- `apprunx-thumbnailer`
- `dictionary`

`apprun3` 와 `apprun3-package` 는 3.x 문서의 기준 명령입니다. `apprun` 과 `apprun-package` 이름은 기존 설치 호환성을 위해 남아 있습니다.

## /usr/lib/python3/dist-packages

공용 Python 모듈이 위치합니다.

- `libapprun.py`
- `apprun_i18n.py`
- `AppContext.py` 링크

## /usr/lib/AppRun

AppRun 런타임 보조 파일과 내장 서비스 번들이 위치합니다.

- `libs/AppContext.py`
- `AppRunDropInService.apprunx`

## /usr/share/dictionaries/apprun-python

`dictionary.py` 가 AppRun Python Collection ID 를 실제 경로로 치환할 때 읽는 JSON 사전 디렉터리입니다.

## /usr/share/apprun/lang

AppRun CLI, 알림, GUI 다이얼로그 다국어 출력용 JSON 언어 파일이 위치합니다. 기본 제공 파일은 `en.json`, `ko.json` 이며, 같은 키 구조의 `<언어코드>.json` 파일을 추가하면 다른 언어를 확장할 수 있습니다.

## /usr/share/applications

`.apprunx` MIME 기본 실행 앱을 등록하는 desktop 파일이 위치합니다.

- `apprun3.desktop`

## /usr/share/mime/packages

`.apprunx` MIME 타입 정의가 위치합니다.

- `apprunx.xml`

## /usr/share/thumbnailers

`.apprunx` 썸네일러 정의가 위치합니다.

- `apprunx.thumbnailer`

## /usr/share/services.apprd

AppRun 이 systemd 서비스 등록을 위해 번들과 service 파일을 보관하는 공간입니다.

- `/usr/share/services.apprd/system`
- `/usr/share/services.apprd/global`
- `/usr/share/services.apprd/gui-startup/global`

## ~/.local/apprun

사용자별 AppRun 스토리지입니다.

## ~/.local/apprun/boxes

실행한 Format 3 번들의 캐시와 준비된 실행 환경을 보관합니다.

## ~/.local/apprun/boxes/\<id>

번들 ID 별 독립 공간입니다. Python 가상 환경, 원본 번들 경로, 실행 보조 파일을 저장합니다.

`--portable=box` 또는 `meta.json` 의 `EnforcePortable: ["box"]` 를 사용하면 같은 역할의 Box 가 `.apprunx` 파일 옆의 `<id>.apprunx.data.d/box` 에 생성됩니다.

## ~/.local/apprun/boxes/\<id>/requirements.txt.sha256

Python 번들 실행 시 `requirements.txt` 변경 여부를 확인하는 sha256 체크섬 파일입니다. 이 파일이 없거나 번들 내부 `requirements.txt` 의 체크섬과 다르면 Python 가상 환경을 다시 준비합니다.

## ~/.local/apprun/boxes/\<id>/python_version

Python 번들의 venv 생성에 사용한 `meta.json` 의 `python_version` 값을 저장합니다. 값이 달라지면 다음 준비 과정에서 `pyvenv` 를 다시 생성하고 의존성을 재설치합니다.

## ~/.local/apprun/boxes/\<id>/pyvenv

Python 번들을 최초 준비할 때 생성하는 가상 환경입니다.

## ~/.local/apprun/boxes/\<id>/source.path

데스크톱 등록 시 참조할 원본 `.apprunx` 경로를 저장합니다.

## ~/.local/apprun/boxes/\<id>/.run

실행 중인 마운트 포인트와 원본 `.apprunx` 경로를 연결하는 임시 런타임 정보를 저장합니다.

## ~/.local/apprun/mounts/\<id>.\<random>

Format 3 번들을 실행할 때 squashfs 이미지를 읽기 전용으로 마운트하는 공간입니다. 실행이 끝나면 자동으로 언마운트됩니다.

`--portable=mount` 또는 `meta.json` 의 `EnforcePortable: ["mount"]` 를 사용하면 마운트 포인트가 `.apprunx` 파일 옆의 `<id>.apprunx.data.d/mounts/<id>.<random>` 에 생성됩니다.

## \<apprunx 위치>/\<id>.apprunx.data.d

portable 실행 시 사용하는 번들 옆 데이터 디렉터리입니다. `--portable` 을 값 없이 사용하면 Box 와 마운트 포인트가 모두 이 디렉터리 아래에 생성됩니다.

## \<apprunx 위치>/\<id>.apprunx.data.d/box

portable Box 입니다. `--inherit` 또는 `meta.json` 의 `EnforceInherit` 를 사용하면 기존 `~/.local/apprun/boxes/<id>` 에서 선택한 내용을 이 위치로 복사합니다.

## \<apprunx 위치>/\<id>.apprunx.data.d/mounts/\<id>.\<random>

portable 마운트 포인트입니다. 실행이 끝나면 기본 마운트 포인트와 동일하게 자동으로 언마운트됩니다.

## ~/.local/share/services.apprd

사용자 단위 systemd 서비스와 GUI 시작 프로그램 등록 시 번들 및 생성된 파일을 저장합니다.
