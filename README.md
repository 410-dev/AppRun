# AppRun

리눅스에서 `requirements.txt` 가 포함된, 번들된 애플리케이션을 쉽게 실행할 수 있도록 합니다.

Python 가상 환경을 자동으로 생성하고 의존성 패키지를 설치합니다.

## 사용방법
```bash
apprun <.apprun 번들 위치>
```

## 설치 방법

### Debian / Ubuntu
Release 페이지에서 최신 .deb 파일 다운로드 후 다음 명령 실행:

```
sudo apt install ./apprun.deb
```

### 기타 리눅스
1. 이 레포지토리를 클론합니다.
2. 클론된 위치의 src 폴더에 들어갑니다.
3. usr/local/sbin 의 내용물을 모두 /usr/local/sbin 으로 복사합니다.
4. usr/share/dictionaries 디렉터리를 /usr/share 로 복사합니다.
5. usr/share/lib 디렉터리를 /usr/share 로 복사합니다.


## Documentation
[파일 위치](docs/Paths.md)

[번들 만들기](docs/Making-Bundle.md)

[Collection ID](docs/Collection-ID.md)
