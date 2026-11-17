# Broker의 KIS 구현 (auth·주문·잔고·체결을 따로 나누지 않음: vendor가 이미 API별로 나뉘어 있음)
# - 인자값은 open-trading-api의 chk_*.py 예시를 따른다
# - 잔고 inquire_balance, 주문 가능 금액 inquire_psbl_order, 주문 order_cash, 정정·취소 order_rvsecncl
# - 체결 조회 inquire_daily_ccld는 odno로 좁혀 한 페이지 안에서 (연속조회 버그 회피, 필요해지면 vendor 수정)
#   주문번호가 없는 unknown 주문은 종목(PDNO)·매매구분으로 좁혀 당일 주문을 찾는다
