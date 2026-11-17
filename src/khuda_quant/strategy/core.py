# 모든 전략이 지켜야 할 공통 규칙
# - 계산 단계: universe(투자 대상) → alpha(신호) → portfolio(비중) → risk(비중 조정)
#   universe·risk는 공통 파일(universe.py, risk.py), alpha·portfolio는 전략 파일(<이름>.py)이 구현
# - 출력 표: as_of(신호 기준일), execution_date(주문일), ticker, target_weight, strategy_version
# - check_targets: 음수 비중, 합계 1 초과, as_of >= execution_date(미래 정보)
# - 이름으로 전략 파일(strategy/<name>.py)을 찾아 불러오는 함수 (backtest·rebalance 공용)
