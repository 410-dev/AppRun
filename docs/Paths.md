# Paths
이 문서는 AppRun 이 참조하는 위치에 대해 서술한 문서입니다. 


## /usr/local/sbin
AppRun 실행 파일이 위치하는 곳입니다.
- appid
- apprun-prepare
- apprun
- apprunutil
- dictionary

## /usr/share/dictionaries/apprun-python
`dictionary.py` 스크립트가 Collection ID 를 참조할 때 쿼리되는 공간입니다.

## /usr/share/lib
라이브러리 레퍼런스 파일들이 존재하는 공간입니다. 

## ~/.local/apprun
AppRun 의 스토리지입니다.

## ~/.local/apprun/boxes
AppRun 이 실행한 AppRun 번들의 독립된 공간입니다.

## ~/.local/apprun/boxes/\<id>
AppRun 번들이 권장 정책에 따라 임의로 파일을 작성할 수 있는 공간입니다.

## ~/.local/apprun/boxes/\<id>/requirements.txt.checksum
AppRun 이 Python 번들을 실행할 때 체크한 체크섬 파일입니다. 이 체크섬이 존재하지 않거나, 번들 내 requirements.txt 의 체크섬이 같지 않다면 Python 가상 환경을 초기화 합니다.

## ~/.local/apprun/boxes/\<id>/pyvenv
AppRun 이 Python 번들을 최초 실행할 때 생성하는 가상환경입니다.