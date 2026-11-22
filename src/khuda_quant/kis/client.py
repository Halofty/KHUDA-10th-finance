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
# 다음 작업 (잔고 조회 때)
# - call(fn, **kwargs): 호출 제한기 — lock으로 직렬화, 최소 간격 (real 1/15초, demo 0.5초)
# - 재시도 규칙 (조회와 주문 분리)
#   조회: EGW00201(초당 호출 초과)이면 잠시 쉬고 재시도
#   주문: 자동 재시도 안 함. 응답이 없으면 접수됐을 수 있으므로 orders.status=unknown으로 두고,
#         당일 주문·체결 조회(종목·매매구분·수량)로 미접수가 확인된 뒤에만 재전송 (주문번호가 없으므로)
# - 로그 가리기: vendor의 _DEBUG를 켜지 않는다(헤더의 키·토큰을 출력함). 계좌번호는 mask()로 가림


import os
import sys
from pathlib import Path

import yaml

VENDOR_DIR = Path(__file__).parent / "vendor"
SERVERS = {"demo": "vps", "real": "prod"}
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
        "my_acct_future": "", "my_paper_future": "",  # 선물옵션은 쓰지 않지만 vendor가 키를 찾는다
        "prod": "https://openapi.koreainvestment.com:9443",
        "vps": "https://openapivts.koreainvestment.com:29443",
        "ops": "ws://ops.koreainvestment.com:21000",
        "vops": "ws://ops.koreainvestment.com:31000",
        "my_token": "",
        "my_agent": "khuda-quant",
    })
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # 처음부터 600으로 만들어, 키가 다른 사용자에게 읽히는 순간이 없게 한다
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    os.chmod(path, 0o600)  # 이미 있던 파일의 권한도 600으로 맞춘다
    return path


def connect(env: str):
    if env not in SERVERS:
        raise ValueError(f"env는 demo 또는 real: {env}")
    write_config(env)
    if str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))
    import kis_auth as ka  # yaml을 만든 뒤에 import해야 한다

    ka.auth(svr=SERVERS[env])
    # 발급에 실패하면 vendor는 메시지만 출력하고 넘어가므로 여기서 멈춘다.
    # getTREnv().my_token은 쓰지 않는다: vendor changeTREnv가 새 토큰이 아니라 이전 값("")을 넣는다.
    # 성공하면 토큰이 서버별 파일에 저장되므로 그 파일로 확인한다.
    if not ka.read_token(SERVERS[env]):
        raise RuntimeError(f"KIS {env} 인증 실패 (앱키·시크릿 확인, 토큰 발급은 1분 1회)")
    return ka.getTREnv()


def mask(account: str) -> str:
    return "*" * (len(account) - 4) + account[-4:]


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "demo"
    trenv = connect(env)
    print(f"KIS {env} 인증 성공: 계좌 {mask(trenv.my_acct)}-{trenv.my_prod}, 서버 {trenv.my_url}")
