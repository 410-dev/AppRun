# 애플리케이션 컨텍스트를 정의하는 모듈

import os
import hashlib

class AppContext:

    def __init__(self):
        # 인스턴스 초기화시, 현재 작업중인 인터프리터의 위치를 찾음
        import sys
        self._interpreter_path = sys.executable

        # 컨텍스트 기본 설정
        self.unreadable_filename: bool = False  # 앱박스 내에 파일을 쓰기 할 때, 파일 명을 다이제스트 함

        # 현재 인터프리터 위치에서 "pyvenv/bin/" 이 없다면 별도로 핸들링 시도
        if 'pyvenv/bin/' not in self._interpreter_path:
            self._apprun_box_path = os.getcwd() + '/'  # 현재 작업 디렉토리를 AppRun Box 로 간주
            self._bundle_id = self._apprun_box_path.rstrip('/').split('/')[-1]  # Box 베이스 네임
            self._is_running_in_venv = False
        else:
            # AppRun Box 위치 가져오기
            # AppRun Box: 인터프리터에서 pyvenv/bin/ 를 기준으로 자른 후 앞쪽
            self._apprun_box_path = self._interpreter_path.split('pyvenv/bin/')[0]

            # 현재 번들 ID 를 불러옴
            # 번들 ID: AppRun Box 에서 베이스 네임
            self._bundle_id = self._apprun_box_path.rstrip('/').split('/')[-1]

            self._is_running_in_venv = True

        # 엔트리 스크립트 및 번들 경로 계산
        self._entry_script_path = self._detect_entry_script()
        self._bundle_path = self._compute_bundle_path(self._entry_script_path)
        self._pid = os.getpid()

    # ---------- 내부 유틸 ----------

    def _detect_entry_script(self) -> str:
        """
        프로세스를 시작한 '첫 엔트리 스크립트' 경로를 최대한 보수적으로 추정.
        우선순위:
          1) __main__.__file__
          2) sys.argv[0] (빈 문자열/'-'/'-c' 제외, 디렉터리면 __main__.py 시도)
          3) 상호작용 환경일 경우 CWD 내 가상 파일명으로 대체
        """
        import sys
        try:
            import __main__
            main_file = getattr(__main__, '__file__', None)
        except Exception:
            main_file = None

        candidates = [main_file]
        if getattr(sys, 'argv', None):
            candidates.append(sys.argv[0])

        for cand in candidates:
            if not cand:
                continue
            if cand in ('', '-', '-c'):
                continue
            path = os.path.abspath(os.path.realpath(os.path.expanduser(cand)))
            # 디렉터리면 패키지 실행 케이스: 디렉터리/__main__.py 탐색
            if os.path.isdir(path):
                maybe = os.path.join(path, '__main__.py')
                if os.path.isfile(maybe):
                    return maybe
            if os.path.exists(path):
                return path

        # Jupyter/REPL/대화형 등: 실제 스크립트 파일이 없으므로 현재 작업 디렉터리 기준
        return os.path.join(os.getcwd(), '__interactive__')

    def _compute_bundle_path(self, entry_script_path: str) -> str:
        """
        번들 경로: '첫 엔트리 스크립트'의 부모 디렉터리.
        상호작용 환경 등 가상 엔트리인 경우 CWD를 번들 경로로 사용.
        """
        # 가상 엔트리 마커인 경우
        if entry_script_path.endswith('__interactive__') and not os.path.exists(entry_script_path):
            return os.getcwd() + '/'
        # 일반 케이스: 스크립트의 부모 디렉터리
        parent = os.path.dirname(os.path.abspath(entry_script_path))
        return parent + ('/' if not parent.endswith('/') else '')

    # ---------- 공개 API ----------

    def is_venv(self):
        return self._is_running_in_venv

    def interpreter(self):
        return self._interpreter_path

    def box(self):
        return self._apprun_box_path

    def id(self):
        return self._bundle_id
    
    def pid(self):
        return self._pid

    def bundle(self):
        """
        번들 경로를 반환.
        번들 경로는 '첫 엔트리 스크립트'의 부모 디렉터리로 정의됨.
        """
        return self._bundle_path

    def entry_script(self):
        """
        탐지된 첫 엔트리 스크립트의 절대 경로를 반환.
        디버그/로깅 용도.
        """
        return self._entry_script_path

    def write(self, filename: str, data: bytes):
        # 파일을 쓰기
        # unreadable_filename 이 True 면, 파일명을 다이제스트 함
        if self.unreadable_filename:
            # 파일명을 다이제스트 함
            digest = hashlib.sha256(filename.encode()).hexdigest()
            filename = digest

        file_path = os.path.join(self._apprun_box_path, filename)

        # 상위 디렉터리 생성 보장 (box 경로 내 서브디렉터리에 쓸 수 있도록)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'wb') as f:
            f.write(data)

        return file_path

    def read(self, filename: str) -> bytes:
        # 파일을 읽기
        if self.unreadable_filename:
            # 파일명을 다이제스트 함
            digest = hashlib.sha256(filename.encode()).hexdigest()
            filename = digest

        file_path = os.path.join(self._apprun_box_path, filename)
        with open(file_path, 'rb') as f:
            data = f.read()
        return data

    def read_or_default(self, filename: str, default: bytes) -> bytes:
        # 파일을 읽기, 없으면 기본값 반환
        try:
            return self.read(filename)
        except FileNotFoundError:
            return default

    def write_str(self, filename: str, data: str, encoding='utf-8'):
        # 문자열 데이터를 파일에 쓰기
        return self.write(filename, data.encode(encoding))

    def read_str(self, filename: str, encoding='utf-8') -> str:
        # 파일에서 문자열 데이터를 읽기
        data = self.read(filename)
        return data.decode(encoding)

    def read_str_or_default(self, filename: str, default: str, encoding='utf-8') -> str:
        # 파일에서 문자열 데이터를 읽기, 없으면 기본값 반환
        try:
            return self.read_str(filename, encoding)
        except FileNotFoundError:
            return default
        
    def username(self) -> str:
        # 현재 사용자 이름 반환
        import getpass
        return getpass.getuser()
    
    def euid(self) -> int:
        # 현재 프로세스의 EUID 반환
        return os.geteuid()
    
    def uid(self) -> int:
        # 현재 프로세스의 UID 반환
        return os.getuid()
    
    def userhome(self) -> str:
        # 현재 사용자의 홈 디렉터리 반환
        import os
        return os.path.expanduser('~')

    def app_exit(self, message: str = "", code: int = 0, wait_for_input: bool | None = None):
        # 애플리케이션 종료
        import sys
        if message:
            print(message)

        # 만약 이 번들 타입이 Application 이고 Terminal 모드라면, 종료 전에 사용자 입력 대기
        if wait_for_input is None:
            wait_for_input = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())

            # 번들에서 AppRunMeta/DesktopLink/Terminal 파일이 존재하고 내부 값이 true 면 대기
            terminal_flag_path = os.path.join(self._apprun_box_path, 'AppRunMeta', 'DesktopLink', 'Terminal')
            if os.path.isfile(terminal_flag_path):
                try:
                    flag_value = self.read_str(terminal_flag_path).strip().lower()
                    if flag_value in ('1', 'true', 'yes', 'on'):
                        wait_for_input = True
                    elif flag_value in ('0', 'false', 'no', 'off'):
                        wait_for_input = False
                except Exception:
                    pass  # 무시하고 기본값 유지

        if wait_for_input:
            input("Press Enter to exit...")

        sys.exit(code)

    def __str__(self):
        return (
            "AppContext("
            f"interpreter_path={self._interpreter_path}, "
            f"apprun_box_path={self._apprun_box_path}, "
            f"bundle_path={self._bundle_path}, "
            f"entry_script={self._entry_script_path}, "
            f"bundle_id={self._bundle_id}"
            ")"
        )
    
