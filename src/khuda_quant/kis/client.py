# KIS 연결부 — vendor(open-trading-api 예제 원본)를 고치지 않고 우리 설정으로 인증
#
# 구조
# 1. write_config(): .env의 KIS_* 값으로 ~/KIS/config/kis_devlp.yaml을 만든다 (권한 600).
#    vendor의 kis_auth.py는 import하는 순간 이 yaml을 읽으므로, 반드시 import 전에 만들어야 한다.
#
# 2. connect(env): vendor 폴더를 sys.path에 넣고 kis_auth를 import한 뒤 ka.auth()로 토큰을 받는다.
#    demo → 모의 서버(vps)        /        real → 실전 서버(prod).
#    성공하면 ka.getTREnv()(계좌·토큰·도메인 묶음)를 돌려줌
#    토큰 재사용은 vendor의 kis_auth로 함: 발급한 토큰을 ~/KIS/config/KIS<날짜>_<서버> 파일에 두고, 만료 전이면 재사용
#    (KIS는 토큰 발급을 1분 1회로 제한하고 발급마다 알림톡을 보내므로 재사용이 중요하다)
#
# 3. 직접 확인: uv run --env-file .env python -m khuda_quant.kis.client demo
#
# 4. 호출 제한기: connect()가 vendor의 ka._url_fetch(모든 API 함수가 거치는 공통 호출)를 limit_fetch로 감싼다.
#    vendor 파일은 고치지 않는다. vendor 함수는 호출할 때마다 ka._url_fetch를 찾으므로 감싼 함수가 쓰인다.
#    - lock으로 한 번에 하나씩, 최소 간격(INTERVAL: demo 0.5초, real 1/15초)을 지킨다. 연속조회 다음 페이지도 포함
#    - 조회(GET): EGW00201(초당 호출 초과)이면 1초 쉬고 다시 (최대 RATE_LIMIT_RETRIES번)
#    - 주문(POST): 자동 재시도 안 함
#
# 5. call(fn, **kwargs): vendor 함수를 실행하고, 실패면 KisError를 낸다.
#    vendor 함수는 실패해도 메시지만 출력하고 빈 표(또는 None)를 돌려주므로 "잔고 없음"과 "조회 실패"가 구분되지 않는다.
#    그래서 limit_fetch가 마지막 응답을 기억해 두고 call이 그 응답으로 성공 여부를 판단한다.
#
# 다음 작업 (주문 때)
# - 주문 응답이 없으면 접수됐을 수 있으므로 orders.status=unknown으로 두고,
#   당일 주문·체결 조회(종목·매매구분·수량)로 미접수가 확인된 뒤에만 재전송 (주문번호가 없으므로)
# - 로그 가리기: vendor의 _DEBUG를 켜지 않는다(헤더의 키·토큰을 출력함). 계좌번호는 mask()로 가림


import logging
import os
import sys
import threading
import time
from pathlib import Path

import yaml

VENDOR_DIR = Path(__file__).parent / "vendor"
SERVERS = {"demo": "vps", "real": "prod"}
INTERVAL = {"demo": 0.5, "real": 1 / 15}  # 최소 호출 간격(초)
RATE_LIMIT_CODE = "EGW00201"
RATE_LIMIT_RETRIES = 3
# ponytail: 마지막 응답 하나만 기억 — 한 프로세스에서 한 스레드로 호출한다고 가정. 여러 스레드면 threading.local로 바꾼다
_last_response = None


class KisError(RuntimeError):
    pass


# 환경별로 반드시 있어야 하는 .env 항목 (yaml 키 ← 환경변수)
REQUIRED = {
    "demo": {"paper_app": "KIS_PAPER_APP_KEY", "paper_sec": "KIS_PAPER_APP_SECRET", "my_paper_stock": "KIS_PAPER_ACCT_STOCK"},
    "real": {"my_app": "KIS_APP_KEY", "my_sec": "KIS_APP_SECRET", "my_acct_stock": "KIS_ACCT_STOCK"},
}


def config_path() -> Path:
    return Path.home() / "KIS" / "config" / "kis_devlp.yaml"


def write_config(env: str) -> Path:
    missing = [name for name in REQUIRED[env].values() if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f".env에 값이 없음: {', '.join(missing)}")
    cfg = {key: os.environ.get(name, "") for keys in REQUIRED.values() for key, name in keys.items()}
    cfg.update({
        "my_htsid": os.environ.get("KIS_HTS_ID", ""),
        "my_prod": os.environ.get("KIS_ACCT_PROD", "01"),
        "my_acct_future": "", "my_paper_future": "",  # 선물옵션은 안 쓰지만 vendor가 이 키를 찾아서 넣음
        "prod": "https://openapi.koreainvestment.com:9443",
        "vps": "https://openapivts.koreainvestment.com:29443",
        "ops": "ws://ops.koreainvestment.com:21000",
        "vops": "ws://ops.koreainvestment.com:31000",
        "my_token": "",
        "my_agent": "khuda-quant",
    })
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # 처음부터 600으로 만들어, 키가 다른 사용자에게 읽히는 순간이 없도록
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    os.chmod(path, 0o600)  # 이미 있던 파일의 권한도 600으로
    return path


def connect(env: str):
    if env not in SERVERS:
        raise ValueError(f"env는 demo 또는 real: {env}")
    write_config(env)
    if str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))
    import kis_auth as ka  # yaml을 만든 뒤에 import해야 함

    ka.auth(svr=SERVERS[env])
    # 발급에 실패하면 vendor는 메시지만 출력하고 넘어가므로 여기서 stop
    # getTREnv().my_token은 안 씀: vendor changeTREnv 버그로 새 토큰이 아니라 이전 값("")이 들어감
    # 성공하면 토큰이 서버별 파일에 저장되므로 그 파일로 확인
    if not ka.read_token(SERVERS[env]):
        raise RuntimeError(f"KIS {env} 인증 실패 (앱키·시크릿 확인, 토큰 발급은 1분 1회)")
    if not getattr(ka._url_fetch, "limited", False):  # 두 번 연결해도 한 번만 감싼다
        ka._url_fetch = limit_fetch(ka._url_fetch, INTERVAL[env])
    return ka.getTREnv()


def _rate_limited(res) -> bool:
    return not res.isOK() and RATE_LIMIT_CODE in f"{res.getErrorCode()} {res.getErrorMessage()}"


def limit_fetch(fetch, interval):
    # fetch는 vendor의 _url_fetch
    lock = threading.Lock()
    last_at = [float("-inf")]

    def limited(api_url, ptr_id, tr_cont, params, appendHeaders=None, postFlag=False, hashFlag=True):
        global _last_response
        with lock:
            for attempt in range(RATE_LIMIT_RETRIES + 1):
                wait = last_at[0] + interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                last_at[0] = time.monotonic()
                res = fetch(api_url, ptr_id, tr_cont, params, appendHeaders, postFlag, hashFlag)
                # 주문(postFlag)은 재전송하지 않고, 조회만 초당 제한에 걸렸을 때 쉬고 다시
                if postFlag or not _rate_limited(res) or attempt == RATE_LIMIT_RETRIES:
                    break
                logging.warning("KIS 초당 호출 초과(%s) — 1초 쉬고 다시: %s", RATE_LIMIT_CODE, api_url)
                time.sleep(1)
            _last_response = res
            return res

    limited.limited = True
    return limited


def call(fn, **kwargs):
    global _last_response
    _last_response = None
    result = fn(**kwargs)
    res = _last_response
    if res is None:
        raise KisError(f"{fn.__name__}: KIS 호출이 없었음 (connect()를 먼저 해야 함)")
    if not res.isOK():
        raise KisError(f"{fn.__name__}: {res.getErrorCode()} {res.getErrorMessage()}")
    return result


def mask(account: str) -> str:
    return "*" * (len(account) - 4) + account[-4:]


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "demo"
    trenv = connect(env)
    print(f"KIS {env} 인증 성공: 계좌 {mask(trenv.my_acct)}-{trenv.my_prod}, 서버 {trenv.my_url}")
