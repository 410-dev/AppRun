from frameworks.AppRun.src.usr.lib.AppRun.libs.AppContext import AppContext

import os
import time

ctx = AppContext()

def __time__():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def __date__():
    return time.strftime("%Y-%m-%d", time.localtime())

def __write__(msg: str):
    # 로그 디렉터리 생성
    os.makedirs(f"{ctx.box()}/logs", exist_ok=True)
    with open(f"{ctx.box()}/logs/{__date__()}.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    #
    # # 만약 {{AQUAROOT}}/logs 에 쓰기가 가능하다면 거기도 쓴다.
    # if os.access("{{AQUAROOT}}/logs", os.W_OK):
    #     os.makedirs(f"{{AQUAROOT}}/logs/{ctx.id()}", exist_ok=True)
    #     with open(f"{{AQUAROOT}}/logs/{ctx.id()}/{__date__()}.log", "a", encoding="utf-8") as f:
    #         f.write(msg + "\n")

    # 만약 각각의 디렉터리에 n 일이 지난 로그 파일 혹은 그보다 오래된 파일이 있다면 삭제
    n = 14
    for log_dir in [f"{ctx.box()}/logs"]: #, f"{{AQUAROOT}}/logs/{ctx.id()}"]:
        if os.path.exists(log_dir):
            for filename in os.listdir(log_dir):
                if filename.endswith(".log"):
                    filepath = os.path.join(log_dir, filename)
                    try:
                        file_date_str = filename.replace(".log", "")
                        file_time = time.strptime(file_date_str, "%Y-%m-%d")
                        file_timestamp = time.mktime(file_time)
                        if time.time() - file_timestamp > n * 86400:  # 86400초 = 1일
                            os.remove(filepath)
                    except Exception as e:
                        # 파일 이름이 날짜 형식이 아니면 무시
                        pass

def info(msg: str):
    strval = f"[INFO] {__time__()} {msg}"
    print(strval)
    __write__(strval)
    # log.setLevel(logging.INFO)
    # log.info(msg)

def error(msg: str):
    strval = f"[ERROR] {__time__()} {msg}"
    print(strval)
    __write__(strval)
    # log.setLevel(logging.ERROR)
    # log.error(msg)

def debug(msg: str):
    if ctx.read_str_or_default("LOGGER_CONFIG_ENABLE_DEBUG", "0") != "1":
        return
    strval = f"[DEBUG] {__time__()} {msg}"
    print(strval)
    __write__(strval)
    # log.setLevel(logging.DEBUG)
    # log.debug(msg)

def warning(msg: str):
    strval = f"[WARNING] {__time__()} {msg}"
    print(strval)
    __write__(strval)
    # log.setLevel(logging.WARNING)
    # log.warning(msg)
