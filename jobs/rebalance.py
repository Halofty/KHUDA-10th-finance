# 리밸런싱 실행 [운용] — systemd timer가 실행, 백테스트는 돌리지 않음
# - config/settings.yaml의 strategy(확정 전략)만 실행한다
# - --env paper|live, --mode plan|trade (기본 plan), live + trade는 --confirm-live 필수
# - 실행 잠금: data/rebalance.lock을 flock으로 잡는다. 이미 잡혀 있으면 runs에 locked로 남기고 종료 (수동 실행 중복 방지)
# - 흐름 (거래일·시간·chk_holiday 판단은 systemd ExecCondition = market_day가 먼저 한다):
#   ① 이전 실행 상태와 미체결·unknown 주문 확인 → 먼저 정리 (정리 안 되면 중단 + 알림)
#   ② 시세 갱신(data/: 수집 → 검증 → 저장) → 확정 전략으로 목표 비중
#   ③ 잔고 조회 → 주문 계획(store 기록) → 사전 점검
#   ④ 매도 주문 → 체결 확인(fill_tracker)
#   ⑤ 주문 가능 금액 재조회(inquire_psbl_order) → ⑥ 매수 재계산 → 사전 점검 → 매수 주문 → 체결 확인
#   → 미체결 처리 → 사후 대조(reconcile) → SQLite 기록 → 알림
# - 처음 시작할 때(보유 0)도 같은 흐름으로 목표 비중만큼 매수한다
