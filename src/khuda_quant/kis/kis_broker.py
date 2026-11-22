# Broker의 KIS 구현 (auth·주문·잔고·체결을 따로 나누지 않음: vendor가 이미 API별로 나뉘어 있음)
# - 인자값은 open-trading-api의 chk_*.py 예시를 따른다
# - 잔고 inquire_balance, 주문 가능 금액 inquire_psbl_order, 주문 order_cash, 정정·취소 order_rvsecncl
# - 체결 조회 inquire_daily_ccld는 odno로 좁혀 한 페이지 안에서 (연속조회 버그 회피, 필요해지면 vendor 수정)
#   주문번호가 없는 unknown 주문은 종목(PDNO)·매매구분으로 좁혀 당일 주문을 찾는다
#
# 구조
# - KisBroker(env): client.connect(env)로 인증한 뒤 vendor 함수를 import한다 (import 전에 yaml이 있어야 하므로)
# - 모든 vendor 호출은 client.call()로 한다 → 호출 간격 제한, 실패하면 KisError
# - positions(): 잔고 조회(종목별) → {종목코드: 보유 수량}. 당일 전량 매도한 0주 행은 뺀다
# - cash_available(ticker): 매수 가능 조회 → 미수 없이 살 수 있는 금액(nrcvb_buy_amt, 원)
# - 직접 확인: uv run --env-file .env python -m khuda_quant.kis.kis_broker demo
#
# 다음 작업: 주문(place), 체결 조회(fills), 취소(cancel)
import sys
import time

import pandas as pd

from khuda_quant.kis import client


def parse_positions(holdings: pd.DataFrame) -> dict[str, int]:
    # 잔고 output1 → {종목코드: 보유 수량}. 계좌가 비어 있으면 열도 없는 빈 table
    if holdings.empty:
        return {}
    qty = holdings.set_index("pdno")["hldg_qty"].astype(int)
    return qty[qty > 0].to_dict()


class KisBroker:
    def __init__(self, env: str):
        self.env = env
        self.trenv = client.connect(env)
        from inquire_balance import inquire_balance  # vendor (connect가 sys.path에 넣음)
        from inquire_psbl_order import inquire_psbl_order

        self._inquire_balance = inquire_balance
        self._inquire_psbl_order = inquire_psbl_order

    def _account(self) -> dict:
        return {"env_dv": self.env, "cano": self.trenv.my_acct, "acnt_prdt_cd": self.trenv.my_prod}

    def positions(self) -> dict[str, int]:
        # ponytail: 보유 수량(hldg_qty)만 반환,  매도 가능 수량(ord_psbl_qty)이 따로 필요해지면 함께 return
        holdings, _ = client.call(
            self._inquire_balance, **self._account(),
            afhr_flpr_yn="N", inqr_dvsn="02", unpr_dvsn="01",  # 02: 종목별
            fund_sttl_icld_yn="N", fncg_amt_auto_rdpt_yn="N", prcs_dvsn="00",  # 00: 전일매매 포함
        )
        return parse_positions(holdings)

    def cash_available(self, ticker: str) -> int:
        # vendor 설명: 가능 금액·수량은 시장가(01)로 조회해야 증거금율이 반영, 시장가는 단가 "0"
        result = client.call(
            self._inquire_psbl_order, **self._account(),
            pdno=ticker, ord_unpr="0", ord_dvsn="01", cma_evlu_amt_icld_yn="N", ovrs_icld_yn="N",
        )
        return int(result.loc[0, "nrcvb_buy_amt"])


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "demo"
    broker = KisBroker(env)
    print(f"계좌 {client.mask(broker.trenv.my_acct)}-{broker.trenv.my_prod} ({env})")
    print("보유:", broker.positions())
    print("매수 가능 금액(005930 기준):", broker.cash_available("005930"))
    # 호출 간격 확인: 잔고 조회 5번을 연달아 —> 초당 호출 초과가 나면 경고 로그
    start = time.monotonic()
    for _ in range(5):
        broker.positions()
    print(f"잔고 조회 5회: {time.monotonic() - start:.2f}초")
