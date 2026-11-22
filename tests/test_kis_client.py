"""KIS 인증 전 단계: .env 값으로 vendor용 yaml을 만들고 권한·누락 검사를 하는지 검증한다 (네트워크 호출 없음)."""

import stat

import pytest
import yaml

from khuda_quant.kis.client import mask, write_config

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
