# Collection ID

이 문서는 AppRun 이 참조하는 Collection ID 에 관해 서술하는 문서입니다.


## Collection ID 란
Python 실행 파일을 가진 AppRun 번들은 라이브러리 레퍼런스 파일을 사용할 수 있습니다. 이 때, 애플리케이션 개발 단에서 위치를 고정하지 않고 각 시스템이 가지고 있는 ID 와 실제 위치값의 연결을 사용해 라이브러리 레퍼런스를 불러오도록 합니다.

## Collection ID 규칙

Collection ID 는 이름을 지을때 다음과 같은 규칙을 가집니다:
```
[개발자 ID].[라이브러리 ID]@[언어]
```

예시:

만약 개발자 ID 가 `me.hysong` 이고, 라이브러리 ID 가 `common` 이며, Python 을 위한 라이브러리라면 다음과 같은 Collection ID 가 만들어집니다:
```
me.hysong.common@python
```

## Collection ID 등록
Collection ID 는 `/usr/local/sbin/dictionary.py` 에 의해 읽어집니다. 

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
    ...
}
```
이후 이 파일을 다음 위치에 저장합니다: `/usr/share/dictionaries/apprun-python`

예시: `/usr/share/dictionaries/apprun-python/me.hysong.common@python.json`

