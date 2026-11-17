# 체결 확인 — 주문 후 체결·미체결을 확인하고 정책대로 처리
# - 정책은 config/settings.yaml의 execution 항목을 따른다 (전략팀 결정, 코드에 고정하지 않음)
#   fill_wait_sec 동안 broker.fills(order_no)로 확인 (unknown 주문은 종목·매매구분으로 먼저 찾아 order_no를 채운다)
#   → 미체결이면 on_unfilled: cancel(취소) | reprice(정정 후 재주문) | keep(유지)
#   → 재주문 전 recheck_before_retry면 잔고 재조회 + risk_gate 재통과, max_retries까지
# - 정정·취소는 KIS order_rvsecncl (취소 가능 수량 먼저 확인)
# - 결과는 store의 orders(kind: new/revise/cancel), fills에 기록
