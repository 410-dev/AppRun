# AppRun

리눅스에서 `requirements.txt` 가 포함된, 번들된 애플리케이션을 쉽게 실행할 수 있도록 합니다.

Python 가상 환경을 자동으로 생성하고 의존성 패키지를 설치합니다.

## 사용방법

Format 1, 2, 3 모두 동일하게 다음 명령어로 실행할 수 있습니다:
```bash
apprun <.apprun / .apprunx 번들 위치>
```

Format 3만 실행하려면 다음 명령어를 사용하세요:
```bash
apprun3 <.apprunx 번들 위치>
```

## 설치 방법


### GUI 환경이 없는 Debian / Ubuntu
AppRun 은 GUI 환경을 전제하고 설계되었지만 GUI 환경이 없는 서버에도 설치할 수 있습니다.
1. `src/DEBIAN/control` 파일에서 `Depends` 항목 중 다음 항목을 삭제하세요:
```
imagemagick, zenity, libnotify-bin
```
2. 이후 다음 명령을 통해 빌드하세요.
```bash
./build.sh
```
3. 빌드된 .deb 파일을 설치하세요.
```bash
sudo apt install ./apprun.deb
```


### GUI 환경이 있는 Debian / Ubuntu
Release 페이지에서 최신 .deb 파일 다운로드 후 다음 명령 실행:

```
sudo apt install ./apprun.deb
```

### 기타 리눅스
1. 이 레포지토리를 클론합니다.
2. 클론된 위치의 src 폴더에 들어갑니다.
3. usr 의 내용물을 모두 /usr 으로 복사합니다.
4. 프로젝트 루트에서 다음 명령을 실행합니다:
```bash
chmod +x src/DEBIAN/postinst
sudo ./src/DEBIAN/postinst
```



## Documentation
[파일 위치](docs/Paths.md)

### Format 3 번들 관련
[AppRun 3.1 이상 번들 관련](docs/format-3.md)

### Format 1, 2 번들 관련
[번들 만들기](docs/Making-Bundle.md)

[Collection ID](docs/Collection-ID.md)
