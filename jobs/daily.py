# 평일 점검 [운용] — systemd daily.timer가 장 마감 뒤 실행, 주문은 내지 않음
# - 사후 대조(reconcile): KIS 잔고와 SQLite 비교, 불일치는 reconciliations에 open으로 기록
# - 감시: 오늘 예정된 리밸런싱이 runs에 없거나 failed면 알림 (예정 시각에 실행되지 않은 것을 잡는다)
# - 일일 보고: 보유·평가금액·당일 주문·체결·미해결 불일치를 notifier로 전송
