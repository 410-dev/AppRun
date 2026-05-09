# AppRun

AppRun 은 리눅스 애플리케이션을 `.apprunx` 단일 파일 번들로 패키징하고 실행하는 Format 3 런타임입니다.

Format 3 번들은 squashfs 기반으로 압축되며, Python 가상 환경 생성, `requirements.txt` 설치, 시스템 패키지 요구사항 확인, 데스크톱 등록, systemd 서비스 등록을 지원합니다.

> AppRun 3.2.0 부터 Format 1 과 Format 2 는 완전히 deprecated 되었습니다. 새 번들은 반드시 Format 3 (`.apprunx`) 로 제작하세요.

## 사용방법

Format 3 번들은 다음 명령어로 실행합니다:
```bash
apprun3 <.apprunx 번들 위치> [앱 인자...]
```

`apprun` 명령은 3.x 계열 설치 호환성을 위해 남아 있지만, 문서와 신규 사용법은 `apprun3` 를 기준으로 합니다.

번들 디렉터리는 `apprun3-package` 로 `.apprunx` 파일로 패키징합니다:
```bash
apprun3-package ./my-app/ -o my-app.apprunx
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
[Format 3 문서](docs/format-3.md)

[파일 위치](docs/Paths.md)

[Collection ID](docs/Collection-ID.md)

레거시 Format 1/2 문서는 [archived](docs/archived/Making-Bundle.md) 에 보관되어 있습니다. 3.2.0 부터는 참고용이며 신규 번들 제작에는 사용하지 않습니다.
