# 거래일 판단
# - config/krx_holidays.toml의 평일 휴장일 + 주말로 is_trading_day(d), next_trading_day(d)
# - 목록 없는 해는 LookupError (추측하지 않고 멈춤)
# - `python -m khuda_quant.market_day <job>` → 종료 코드 0=실행, 1=건너뜀, 255=목록 없음 (systemd ExecCondition), Asia/Seoul
#   - rebalance: 거래일 + settings.yaml의 order_window 안 / daily: 거래일만
#   - 거래일이면 KIS chk_holiday(opnd_yn)로 휴장일 파일과 대조 (1일 1회, 결과는 SQLite에 두고 재사용, 모의 계좌 지원 여부 미확인)
#     불일치면 건너뜀 + 알림
#   - 건너뛸 때는 종료 전에 runs에 skipped와 사유를 직접 기록한다 (rebalance가 실행되지 않으므로)
