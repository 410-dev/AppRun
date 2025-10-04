# 애플리케이션 컨텍스트를 정의하는 모듈

import os
import hashlib

class AppContext:

    def __init__(self):
        # 인스턴스 초기화시, 현재 작업중인 인터프리터의 위치를 찾음
        import sys
        self._interpreter_path = sys.executable

        # AppRun Box 위치 가져오기
        # AppRun Box: 인터프리터에서 pyvenv/bin/ 를 기준으로 자른 후 앞쪽
        self._apprun_box_path = self.interpreter_path.split('pyvenv/bin/')[0]

        # 현재 번들 ID 를 불러옴
        # 번들 ID: AppRun Box 에서 베이스 네임
        self._bundle_id = self.apprun_box_path.split('/')[-1]

        # 컨텍스트 기본 설정
        self.unreadable_filename: bool = False # 앱박스 내에 파일을 쓰기 할 때, 파일 명을 다이제스트 함
        

    def interpreter(self):
        return self._interpreter_path
    
    def box(self):
        return self._apprun_box_path
    
    def id(self):
        return self._bundle_id
    
    def write(self, filename: str, data: bytes):
        # 파일을 쓰기
        # unreadable_filename 이 True 면, 파일명을 다이제스트 함

        if self.unreadable_filename:
            # 파일명을 다이제스트 함
            digest = hashlib.sha256(filename.encode()).hexdigest()
            filename = digest
        
        file_path = os.path.join(self._apprun_box_path, filename)
        
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


    def __str__(self):
        return f"AppContext(interpreter_path={self._interpreter_path}, apprun_box_path={self._apprun_box_path}, bundle_id={self._bundle_id})"
    