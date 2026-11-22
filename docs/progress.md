# 진행 기록

## 결정 사항 및 다음 할 일


### 26.11.17.
전체 구조 구상 및 그에 빈 폴더 및 파일 생성(코드 구현은 이후 구현)
11.16(월) 세션 발표한 노션 내용 따라 planning.md 작성
기타 초안 

### 26.11.20. 운영 1주차 로컬 구현

- `market_day.py`: `is_trading_day(date)`, `next_trading_day(date)` 구현.
  주말·평일 휴장일을 제외하고, 미등록 연도는 주말이어도 `LookupError`로 멈춘다.
  다음 거래일은 입력 날짜 다음 날부터 찾으며 연도 경계에서도 같은 규칙을 적용한다.
- `config/krx_holidays.toml`: 2026년 평일 휴장일 17개와 출처를 기록.
  우주항공청·한국천문연구원 자료, KRX 노동절·연말 휴장 규칙,
  6/3 지방선거·7/17 제헌절 추가 휴장 공지를 반영했다.
- `store/schema.sql`: runs, targets, order_plans, orders, fills, snapshots,
  reconciliations를 생성. 외래 키, 주문 계획·체결 중복 방지, 정수 수량 조건을 적용.
- `store/db.py`: `connect(path)`, `transaction(connection)`, `backup(connection, path)` 구현.
  연결을 다시 열어도 기록을 유지하고, 예외·중단 시 트랜잭션 전체를 롤백한다.
  백업은 SQLite backup API를 사용하며 진행 중 트랜잭션이나 기존 파일 덮어쓰기를 거부한다.
- `tests/test_market_day.py`, `tests/test_store.py`: 거래일·연도 경계·설정 오류,
  중복 차단·롤백·재접속·백업 복원을 임시 파일로 검증한다. 실제 KIS 키는 사용하지 않는다.
- Python 3.12.4에서 전체 테스트 **69개 통과**. 예시 DB와 백업도 별도로 생성·재접속 검증.
  `data/week1-demo.sqlite3`, `data/backups/week1-demo.sqlite3`는 로컬 확인용이며 Git에서 제외한다.

스키마의 구체화 사항(주문 담당과 PR 검토 시 확인):

- 실행 중 상태 식별을 위해 `runs.status`에 `running`을 추가했다.
- 매매 구분은 `buy`/`sell`, 사전 점검 사유는 JSON 배열 문자열이다.
- 주문번호가 아직 없어도 내부 ID로 요청을 기록할 수 있다.
  체결 키는 `(order_id, fill_seq)`로 두고, 증권사 주문번호는 원본 필드로 보존한다.
  내부 주문과 증권사 주문번호를 함께 외래 키로 확인하며,
  다른 날짜·주문의 같은 증권사 주문번호가 전체 DB에서 충돌하지 않게 했다.
- 한 DB는 한 계좌·한 환경에 사용한다. 모의/실전은 별도 DB 파일로 구분한다.
- DB 경로와 백업 파일명은 호출하는 쪽에서 명시한다. 연결 종료도 호출자가 맡는다.

로컬 확인(PowerShell, 프로젝트 폴더에서):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

최소 DB 사용 예:

```python
from contextlib import closing
from khuda_quant.store.db import backup, connect, transaction

with closing(connect("data/operations.sqlite3")) as connection:
    with transaction(connection):
        connection.execute(
            "INSERT INTO runs (run_id, job, started_at, status, skip_reason) VALUES (?, ?, ?, ?, ?)",
            ("demo-20261120", "rebalance", "2026-11-20T09:10:00+09:00", "skipped", "로컬 예시"),
        )
    # 백업 경로는 매번 새 이름을 사용한다.
    backup(connection, "data/backups/demo-20261120.sqlite3")
```

후속 범위: KIS `chk_holiday` 대조, 주문 시간대·ExecCondition·건너뜀 기록 연결,
`risk_gate`, 알림, 리밸런싱 실행 잠금·흐름, systemd 배포와 실계좌 대조.
주문 한도·사람의 주문 확인·체결 정책·알림 채널은 팀 합의가 필요한 상태다.

### 26.11.22. 최신 데이터 기능과 운영 코드 통합

- 최신 `origin/main`(`c2bf5bc`)의 데이터 수집·검증·Parquet 저장 관련 14개 커밋을 반영했다.
- 변경 파일이 겹치지 않아 기존 운영 코드와 설명 주석을 그대로 보존했다.
- 예시 시세와 데이터 테스트를 포함한 전체 테스트 **71개 통과**(Python 3.12.4).
- README의 시세 수집 예시를 현재 실행 인자에 맞게 갱신했다.
