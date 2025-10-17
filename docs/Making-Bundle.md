# 번들 만들기

이 문서는 AppRun 구조의 애플리케이션 번들을 만드는 방법을 서술합니다.

## 패키지 기본 구조
1. [필수] 실행 파일
2. [선택] ID 파일
3. [선택] 라이브러리 레퍼런스 파일
4. [선택] 의존성 파일

```
MyPythonApplication.apprun
\
 main.py          [필수, 실행 파일]
 requirements.txt [선택, 의존성 파일]
 AppRunMeta
 \
  libs              [선택      , 라이브러리 레퍼런스 파일]
  id                [선택 (권장), 번들 ID 파일]
  DesktopLink       [선택      , .desktop 파일 내용]
  EnforceRootLaunch [선택      , 존재시 번들 실행을 sudo 로 실행함]
  KeepEnvironment   [선택      , 존재시 EnforceRootLaunch 에서 sudo -E 효과를 냄]
```

## 실행 파일
실행 파일은 AppRun 실행기가 실행할 실제 코드 파일입니다.

현재 지원하는 코드 파일은 Java 의 Jar 파일과 Python 입니다.

두 종류의 언어 모두 파일의 실제 명칭은 main 이여야 합니다.

예: `main.py` 혹은 `main.jar`


## ID 파일
ID 파일은 번들 ID 를 가지고 있으며, `id` 라는 파일 명을 가집니다.

번들의 ID 값은 다음과 같은 규칙을 가집니다:

`[개발자  ID].application.[애플리케이션 ID]`

예를 들어, 개발자 ID 가 `me.hysong` 이고 MyProgram 라는 애플리케이션 번들이라면, 다음과 같은 번들 ID 를 가집니다:
`me.hysong.application.MyProgram`

## 라이브러리 레퍼런스 파일
* Java 애플리케이션은 지원하지 않는 기능입니다.

라이브러리 레퍼런스 파일은 `libs` 라는 파일 명을 가지며, 로컬 시스템에서 Python 파일을 임포트 할 수 있도록 합니다.

파일은 여러가지의 위치 경로를 `:` 로 나누거나, 컬렉션 ID 를 설정하여 동적으로 처리할 수 있습니다. 컬렉션 ID 는 [관련 문서](Collection-ID.md) 를 참조하세요.

**예제**

`/usr/share/lib/me.hysong/common/python` 디렉터리에 다음과 같은 `libcalc.py` 와 같은 파일이 있다고 가정합니다.

```python
def add(a: int, b: int) -> int:
    return a + b
```
위 라이브러리 위치 (`/usr/share/lib/me.hysong/common/python`) 은 `me.hysong.common@python` 컬렉션 ID 가 선언되어 있습니다.

따라서 위 라이브러리 파일을 사용하고자 하면 `libs` 파일에 다음과 같이 기입할 수 있습니다:
```
me.hysong.common@python
```

혹은 정적 위치를 사용하고 싶다면:
```
/usr/share/lib/me.hysong/common/python
```

컬렉션 ID 와 정적 위치를 혼합하여 사용이 가능하며 여러가지 경로를 추가할 수 있습니다:
```
/usr/share/lib/me.hysong/common/python:me.hysong.common@python:/usr/share/lib/org.apache/common/python
```
이렇게 기입했을 때, `main.py` 파일은 다음과 같이 작성할 수 있습니다:

```python
import libcalc as calculator

def main():
    print(calculator.add(1, 2))

if __name__ == "__main__":
    main()
```
위와 같이 위치에 상관 없이 공통으로 사용할 수 있는 스크립트 파일을 불러올 수 있습니다.

## 의존성 파일
* Java 애플리케이션은 지원하지 않는 기능입니다.

의존성 파일은 현재 애플리케이션 번들이 실행되기 전 AppRun 실행기에 의해 애플리케이션의 독립적인 가상환경 (Python Venv) 에 설치할 의존성 라이브러리를 명시합니다.

이는 Python 표준의 `requirements.txt` 와 완전히 동일하며, 애플리케이션의 첫 실행시 자동으로 읽어들여 설치합니다.

만약 애플리케이션이 업데이트 되어 `requirements.txt` 파일이 변경되었을 경우, 기존의 가상환경은 제거되고 다시 설치됩니다.

## 기타 파일
번들에는 애플리케이션 구동에 필요한 다른 리소스들을 포함할 수 있습니다. 이는 AppRun 에 예약된 파일 명이 아니면 인식되지 않습니다.