# 퀀트 운용 프로젝트 기본 아키텍처

KIS Open API 연동은 `open-trading-api`를 기준으로 삼고, 목표 비중 리밸런싱과 안전 점검은 프로젝트에서 구현한다.

구조도: [system-architecture.html](system-architecture.html)

## 설계 원칙

- 전략팀의 출력은 `as_of, execution_date, ticker, target_weight, strategy_version`으로 통일한다.
  `as_of`는 신호 기준일, `execution_date`는 주문일이며 `as_of < execution_date`여야 한다(미래 정보 차단).
- 백테스트와 운용은 같은 `Strategy Core`를 사용하되 따로 실행한다. 운용은 `settings.yaml`에 확정된 전략만 실행한다.
- 시세는 Parquet, 운영 상태는 SQLite에 저장한다.
- 주문 전에 주문 계획을 저장하고 사전 점검을 통과해야 한다.
- 정해진 시각의 실행은 systemd timer가 맡고, 거래일과 주문 가능 시간대는 `ExecCondition`에서 판단한다. 주문 서비스 timer에는 `Persistent`를 쓰지 않는다.
  건너뛴 실행도 `ExecCondition`(market_day)이 사유를 `runs`에 남긴다.
- 주문은 요청 전에 내부 ID로 먼저 기록하고, 증권사 주문번호는 응답 후 채운다. 응답이 없으면 `unknown`으로 두고 자동 재전송하지 않는다.
- 리밸런싱은 실행 잠금으로 겹쳐 실행되지 않게 하고, 평일 점검 job이 누락된 실행을 감시한다.
- 로그와 알림에는 키·토큰·계좌번호를 남기지 않는다.
- 주문 접수와 체결을 구분하고, 체결 후 KIS 잔고와 내부 기록을 대조한다.
- `open-trading-api`는 API 규격의 기준으로 사용한다.

## 구성 요소

| 구성 요소 | 역할 | 주요 기술 | 담당 |
| --- | --- | --- | --- |
| Fetchers | 시세·종목 수집, 표준 스키마 변환 | FinanceDataReader, pykrx | 개발팀 |
| 데이터 검증 | 결측, 이상값, 거래일 확인 | pandas, 휴장일 파일 | 개발팀 |
| Parquet | 연구·운용 공용 시세 저장. 원본(raw)과 표준(std)을 나누고 수집일·소스·버전 기록 | Parquet, pyarrow | 개발팀 |
| Strategy Core | 대상 선택(공통), 신호·비중(전략별), 리스크 조정(공통) | pandas, NumPy | 전략팀, 공동 |
| 백테스트 | 목표 비중 기반 성과 시뮬레이션 | bt | 공동 |
| 성과·검증 | 성과 분석과 민감도 확인 | bt, pandas, Matplotlib | 공동 |
| 릴리스 점검 | 계산과 안전 규칙 테스트 | pytest | 개발팀 |
| 설정 | 한도·비용·확정 전략·체결 정책은 `settings.yaml`(커밋), 키는 `.env`(커밋 안 함). 모의·실전은 실행 인자로 구분 | YAML, .env | 개발팀 |
| systemd timer | 주간 리밸런싱(월 09:10), 평일 점검(15:40) | systemd 사용자 서비스, `Asia/Seoul` | 개발팀 |
| 실행 조건 | 거래일·시간대 판단, 휴장일 파일과 `chk_holiday` 대조, 건너뜀 사유 기록 | `ExecCondition`, 휴장일 파일, KIS `chk_holiday` | 개발팀 |
| 주문 계획 | 목표 차이를 주문으로 변환 | pandas, 직접 구현 | 개발팀 |
| 사전 점검 | 한도, 중복, 데이터, 긴급 정지, 거래정지·상하한가 확인 | 직접 구현 | 개발팀 |
| Broker | 주문 인터페이스, 환경 전환 | `PaperBroker`, `KisBroker` | 개발팀 |
| 체결 확인 | 체결·미체결 확인, 정책에 따른 취소·재주문 | KIS Adapter, `settings.yaml` execution | 개발팀 |
| SQLite | 주문, 체결, 잔고, 실행 기록 | SQLite | 개발팀 |
| 사후 대조 | KIS 잔고(`inquire_balance`)와 내부 기록 비교, 해결 상태 기록 | pandas | 개발팀 |
| 평일 점검 | 사후 대조, 리밸런싱 누락 감시, 일일 보고 (`jobs/daily.py`) | systemd timer | 개발팀 |
| 알림 | 체결, 오류, 불일치, 건너뜀, 일일 보고 전달. 대상은 `settings.yaml`의 `notify` | Requests, Slack 또는 Telegram | 개발팀 |

## open-trading-api 연결

| 우리 구성 요소 | 참고 코드 | 적용 방식 |
| --- | --- | --- |
| KIS Adapter 인증 | `kis_auth` | 인증과 토큰 처리 기준 |
| 주문 전송 | `examples_llm/domestic_stock/order_cash/order_cash.py` | TR ID와 파라미터 기준 |
| 체결 확인 | `examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py` | 주문번호(odno)로 좁혀 1페이지 조회. 응답이 없어 주문번호가 없는 주문은 종목·매매구분으로 찾음. 연속조회 재귀 호출의 인자 순서 버그는 여러 페이지가 필요해질 때 수정 |
| 정정·취소 | `examples_llm/domestic_stock/order_rvsecncl/order_rvsecncl.py` | 취소 가능 수량 확인 후 사용 |
| 잔고 조회 | `examples_llm/domestic_stock/inquire_balance/inquire_balance.py` (구조는 `strategy_builder/core/position_manager.py` 참고) | 주문 전 강제 갱신, 사후 대조에도 사용 |
| 주문 가능 금액 | `examples_llm/domestic_stock/inquire_psbl_order/inquire_psbl_order.py` | 매수 한도 계산 |
| 휴장일 조회 | `examples_llm/domestic_stock/chk_holiday/chk_holiday.py` | `ExecCondition`에서 `opnd_yn`으로 휴장일 파일 대조, 1일 1회 호출. 모의 계좌 지원 여부 미확인 |
| 주문 흐름 | `strategy_builder/core/order_executor.py` | 흐름만 참고, 수량·안전장치 재구현 |
| 전략 인터페이스 | `strategy_builder/strategy` | 구조 참고, `target_weight` 출력으로 변경 |

## 처리 흐름

```
[연구] 사람이 반복 실행 (jobs/fetch_prices.py, jobs/backtest.py)
시세 수집 → 전략 명세 → Strategy Core → bt → 성과·검증 → 전략 확정 → pytest → settings.yaml strategy 지정

[운용] systemd timer가 실행 (jobs/rebalance.py, 백테스트는 돌리지 않음)
systemd timer(월) → ExecCondition: 거래일·시간 + 휴장일 대조(chk_holiday), 건너뛰면 runs에 사유 기록
→ 실행 잠금 → ① 미체결·이전 상태 정리 → 시세 갱신 → Strategy Core(확정 전략)
→ ② 잔고 조회 → ③ 주문 계획 → 사전 점검 → ④ 매도 → 체결 확인
→ ⑤ 주문 가능 금액 재조회 → ⑥ 매수 재계산 → 사전 점검 → 매수 → 체결 확인(미체결 정책) → 사후 대조 → 알림

[운용] systemd timer(평일 15:40) (jobs/daily.py, 주문 없음)
사후 대조 → 리밸런싱 누락 감시 → 일일 보고
```

## 디렉터리 구조

```
config/
  krx_holidays.toml
  settings.yaml           한도 · 비용 · 확정 전략 · 체결 정책 (키는 .env)
src/khuda_quant/
  market_day.py           거래일 판단 (ExecCondition이 python -m 으로 실행)
  data/
    schema.py
    fetchers.py
    validators.py
    storage.py
  strategy/
    core.py               공통 규칙, 단계 순서, 전략 불러오기
    universe.py           [공통] 투자 대상
    risk.py               [공통] 비중 조정
    momentum.py           [전략별] alpha · portfolio
  backtest/
    run_bt.py
    metrics.py
  execution/
    order_planner.py
    risk_gate.py
    broker.py
    fill_tracker.py
    reconcile.py
  kis/
    client.py             인증 · 호출 제한기
    kis_broker.py         잔고 · 주문 · 체결 · 정정취소
    vendor/               open-trading-api 예제 원본
  store/
    schema.sql
    db.py
  reporting/
    notifier.py
jobs/
  fetch_prices.py         [연구·초기]
  backtest.py             [연구]
  rebalance.py            [운용] 주간 리밸런싱
  daily.py                [운용] 평일 사후 대조 · 누락 감시 · 일일 보고
deploy/systemd/
  rebalance.service
  rebalance.timer
  daily.service
  daily.timer
  install.sh
tests/
```

### 처음 설계와 다르게 합친 것

| 처음 설계 | 현재 | 이유 |
| --- | --- | --- |
| `execution/cost_model.py` | `settings.yaml`의 `fee_rate`, `sell_tax_rate` | 지금은 숫자 몇 개. 슬리피지 모델이 필요해지면 분리 |
| `kis/auth.py`, `orders.py`, `balances.py`, `fills.py` | `kis/client.py`, `kis/kis_broker.py` | vendor가 이미 API별 파일. 우리 쪽은 얇은 연결부만 |
| `reporting/store.py` | `store/schema.sql`, `store/db.py` | 스키마를 SQL 파일로 분리 |
| `jobs/market_day.py` | `src/khuda_quant/market_day.py` | ExecCondition, rebalance, 테스트가 모두 import |
| `risk/rules.py` | `strategy/risk.py` | target_weight를 만드는 과정은 strategy/ 안에. 주문 단위 점검은 `execution/risk_gate.py` |
| `strategy/alpha.py`, `portfolio.py` | `strategy/<전략 이름>.py` | 전략마다 alpha·portfolio가 다름. settings에서 전략 파일 하나를 지정 |

### 세미나 발표와 달라진 것 (전략팀에 공유)

| 발표 | 현재 | 이유 |
| --- | --- | --- |
| `paper.yaml`, `live.yaml` | `settings.yaml` 하나 + `--env paper\|live`, 알림 대상은 `notify` 항목 | 같은 값을 두 파일에 중복하지 않기 위해 |
| Python 3.11 이상 | Python 3.12 이상 | 의존성 numpy 2.5가 3.12 이상만 지원 |
| bt 거래일에 exchange_calendars | `config/krx_holidays.toml` | 운용의 거래일 판단과 같은 기준을 쓰기 위해 |

## 체결 정책 (전략팀 결정 사항)

미체결 처리와 재점검은 코드에 고정하지 않고 `config/settings.yaml`의 `execution` 항목으로 둔다.
전략팀 방향에 따라 값을 바꾸고 커밋하면 `execution/fill_tracker.py`가 그대로 따른다.

| 항목 | 정할 것 | 선택지 |
| --- | --- | --- |
| `order_type` | 주문 방식 | 지정가 / 시장가 |
| `limit_price` | 지정가 기준 가격 | 직전 종가, 현재가 ± n호가 등 |
| `fill_wait_sec` | 체결 대기 시간 | 초 |
| `on_unfilled` | 미체결 처리 | 취소 / 정정 후 재주문 / 유지 |
| `max_retries` | 재주문 최대 횟수 | 정수 |
| `recheck_before_retry` | 재주문 전 잔고 재조회 + 사전 점검 재통과 | 예 / 아니오 |

현재 값은 모두 미확정 예시다. 정책을 바꿀 때는 무엇을 왜 바꿨는지 `docs/progress.md`에 남긴다.

## 구현 전 확정 사항

- 신호 계산 시각과 주문 시각
- 지정가·시장가 기본값과 미체결 재시도 규칙
- systemd를 실행할 상시 구동 VM (Lightsail 2GB 기본안)
- 수정주가 기준
- ETF 호가 단위와 KIS 호출 제한
