"""KIS 인증 전 단계: .env 값으로 vendor용 yaml을 만들고 권한·누락 검사를 하는지 검증한다 (네트워크 호출 없음)."""

import stat
import time

import pytest
import yaml

from khuda_quant.kis.client import KisError, call, limit_fetch, mask, write_config

DEMO_ENV = {"KIS_PAPER_APP_KEY": "pk", "KIS_PAPER_APP_SECRET": "ps", "KIS_PAPER_ACCT_STOCK": "50001234"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    # 실제 ~/KIS를 건드리지 않도록 HOME을 임시 폴더로 바꾸고, KIS_* 환경변수를 비운다
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCT_STOCK", "KIS_ACCT_PROD", "KIS_HTS_ID", *DEMO_ENV]:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_demo_config_has_vendor_keys_and_is_private(home, monkeypatch):
    for name, value in DEMO_ENV.items():
        monkeypatch.setenv(name, value)

    path = write_config("demo")

    assert path == home / "KIS" / "config" / "kis_devlp.yaml"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert (cfg["paper_app"], cfg["paper_sec"], cfg["my_paper_stock"]) == ("pk", "ps", "50001234")
    assert cfg["my_prod"] == "01"
    assert cfg["vps"] == "https://openapivts.koreainvestment.com:29443"
    # vendor kis_auth.py가 import 때와 auth 때 읽는 키가 모두 있어야 한다
    for key in ["my_app", "my_sec", "my_acct_stock", "my_htsid", "prod", "ops", "vops", "my_agent"]:
        assert key in cfg


def test_missing_env_stops_before_writing(home, monkeypatch):
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "pk")
    with pytest.raises(RuntimeError, match="KIS_PAPER_APP_SECRET"):
        write_config("demo")
    assert not (home / "KIS").exists()


def test_mask_keeps_last_four_digits():
    assert mask("50001234") == "****1234"


class FakeResp:
    # vendor APIResp에서 limit_fetch·call이 쓰는 부분만 흉내 낸다
    def __init__(self, ok=True, code="", msg=""):
        self.ok, self.code, self.msg = ok, code, msg

    def isOK(self):
        return self.ok

    def getErrorCode(self):
        return self.code

    def getErrorMessage(self):
        return self.msg


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    # limit_fetch가 쓰는 time.sleep·time.monotonic을 가짜 시계로 덮어쓴다 (테스트가 끝나면 자동으로 원래대로)
    fake = FakeClock()
    monkeypatch.setattr(time, "sleep", fake.sleep)
    monkeypatch.setattr(time, "monotonic", fake)
    return fake


def make_fetch(responses):
    sent = []

    def fetch(api_url, ptr_id, tr_cont, params, appendHeaders=None, postFlag=False, hashFlag=True):
        sent.append(postFlag)
        return responses.pop(0)

    return fetch, sent


RATE_LIMITED = FakeResp(False, "500", '{"msg_cd":"EGW00201","msg1":"초당 거래건수를 초과하였습니다."}')


def test_calls_keep_minimum_interval(clock):
    fetch, _ = make_fetch([FakeResp(), FakeResp()])
    limited = limit_fetch(fetch, 0.5)
    limited("/a", "T", "", {})
    limited("/a", "T", "", {})
    assert clock.sleeps == [0.5]  # 첫 호출은 바로, 두 번째는 0.5초 기다림


def test_query_retries_on_rate_limit_but_order_does_not(clock):
    fetch, sent = make_fetch([RATE_LIMITED, FakeResp()])
    limited = limit_fetch(fetch, 0.5)
    assert limited("/q", "T", "", {}).isOK()  # 조회: 한 번 걸리고 다시 보내 성공
    assert sent == [False, False]

    fetch, sent = make_fetch([RATE_LIMITED, FakeResp()])
    limited = limit_fetch(fetch, 0.5)
    assert not limited("/o", "T", "", {}, postFlag=True).isOK()  # 주문: 다시 보내지 않음
    assert sent == [True]


def test_call_raises_when_vendor_swallowed_error(clock):
    fetch, _ = make_fetch([FakeResp(False, "EGW00123", "기간이 만료된 token")])
    limited = limit_fetch(fetch, 0)

    def vendor_fn():
        limited("/q", "T", "", {})
        return None  # vendor처럼 실패해도 예외 없이 빈 결과

    with pytest.raises(KisError, match="EGW00123"):
        call(vendor_fn)
