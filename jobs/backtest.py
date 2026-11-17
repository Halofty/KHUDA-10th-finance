# 백테스트 실행 [연구] — 사람이 전략을 검증할 때 반복 실행, 주문과 무관
# - --strategy <이름> + 파라미터로 strategy/ 의 어떤 전략이든 선택
# - 저장된 시세 → 전략 → check_targets → backtest/run_bt.py → backtest/metrics.py → 결과 출력
# - 검증이 끝나면 config/settings.yaml의 strategy 항목을 고쳐 운용 전략으로 확정한다
