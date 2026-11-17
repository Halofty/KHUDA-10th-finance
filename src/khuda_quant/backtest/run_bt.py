# 목표 비중 표 → bt 백테스트
# - RunOnDate, WeighTarget, Rebalance / integer_positions=True
# - 매수 수수료, 매도 수수료 + 세금
# - 체결 가정: 미정 (docs/planning.md "먼저 정할 것"의 신호 시점·체결 가격). 임시안은 execution_date 종가
# - 거래일은 config/krx_holidays.toml(market_day)을 쓴다 (exchange_calendars는 쓰지 않음)
