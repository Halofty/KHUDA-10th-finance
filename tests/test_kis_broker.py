"""잔고 조회 응답(output1)을 {종목코드: 보유 수량}으로 바꾸는지 검증한다 (네트워크 호출 없음)."""

import pandas as pd

from khuda_quant.kis.kis_broker import parse_positions


def test_positions_keep_leading_zero_and_drop_sold_out():
    # KIS는 숫자도 문자열로 준다. 당일 전량 매도한 종목은 0주로 남는다
    holdings = pd.DataFrame({"pdno": ["005930", "069500"], "prdt_name": ["삼성전자", "KODEX 200"], "hldg_qty": ["3", "0"]})
    assert parse_positions(holdings) == {"005930": 3}


def test_empty_account_has_no_positions():
    assert parse_positions(pd.DataFrame()) == {}
