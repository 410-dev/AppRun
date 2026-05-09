# Collection ID

이 문서는 AppRun 3.2.0 계열에서 Python 번들의 `AppRunMeta/libs` 파일이 참조하는 Collection ID 를 설명합니다.


## Collection ID 란
Python 실행 파일을 가진 Format 3 번들은 라이브러리 레퍼런스 파일을 사용할 수 있습니다. 이 때, 애플리케이션 개발 단에서 위치를 고정하지 않고 각 시스템이 가지고 있는 ID 와 실제 위치값의 연결을 사용해 라이브러리 레퍼런스를 불러오도록 합니다.

AppRun 은 번들 내부 `AppRunMeta/libs` 또는 레거시 `libs` 파일을 읽고, `/usr/share/dictionaries/apprun-python/*.json` 의 키를 실제 경로로 치환한 뒤 `PYTHONPATH` 에 추가합니다.

## Collection ID 규칙

Collection ID 는 이름을 지을 때 다음과 같은 규칙을 권장합니다:
```
[개발자 ID].[라이브러리 ID]@[언어]
```

예시:

만약 개발자 ID 가 `me.hysong` 이고, 라이브러리 ID 가 `common` 이며, Python 을 위한 라이브러리라면 다음과 같은 Collection ID 가 만들어집니다:
```
me.hysong.common@python
```

시스템 공용 별칭처럼 짧은 키를 사용할 수도 있습니다. 기본 사전은 예를 들어 `system-site` 를 `/usr/lib/python3/dist-packages` 로 치환할 수 있습니다.

## Collection ID 등록
Collection ID 는 `/usr/bin/dictionary.py` 에 의해 읽어집니다.

Collection ID 등록을 위해선 다음과 같은 파일을 우선 작성합니다:
```json
{
    "Collection ID": "실제 위치",
    "Collection ID2": "실제 위치 2",
    ...
}
```
예:
```json
{
    "me.hysong.common@python": "/usr/share/lib/me.hysong/common/python",
    "system-site": "/usr/lib/python3/dist-packages"
}
```
이후 이 파일을 다음 위치에 저장합니다: `/usr/share/dictionaries/apprun-python`

예시: `/usr/share/dictionaries/apprun-python/me.hysong.common@python.json`

## AppRunMeta/libs 예시

번들 내부에 다음 파일을 둡니다:

```
AppRunMeta/libs
```

내용은 `:` 로 여러 경로 또는 Collection ID 를 연결할 수 있습니다:

```
me.hysong.common@python:system-site:/opt/my-extra-python-libs
```

실행 시 AppRun 은 위 문자열의 Collection ID 를 실제 경로로 치환하고 `PYTHONPATH` 에 주입합니다.
