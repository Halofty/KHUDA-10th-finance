# 사후 대조 — 체결이 끝난 뒤 KIS 잔고와 내부 기록(SQLite)을 비교
# - 잔고는 inquire_balance로 조회 (하루치 체결 조회는 모의 15건 초과 시 연속조회 버그에 걸림)
# - 결과는 store의 reconciliations에 기록, 불일치면 알림
