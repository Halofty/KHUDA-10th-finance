-- 1주차 운영 상태 스키마. 날짜는 ISO 날짜, 시각은 시간대를 포함한 ISO 문자열로 저장한다.
-- ticker는 앞자리 0을 보존하는 TEXT, 수량은 정수 주, 금액은 원 단위다.
-- 한 DB는 한 계좌·한 환경에 사용한다. 모의/실전은 별도 DB 파일로 구분한다.
-- PRIMARY KEY는 행을 구별하는 값, REFERENCES/FOREIGN KEY는 다른 테이블과의 연결이다.
-- NOT NULL은 필수 입력, CHECK는 허용할 값의 조건, UNIQUE는 같은 조합의 중복 금지다.
-- 연결된 실행·주문이 없는 기록이 저장되지 않도록 외래 키 검사를 켠다.
PRAGMA foreign_keys = ON;
-- 테이블과 인덱스를 모두 만든 뒤 한 번에 확정해, 스키마가 일부만 만들어지는 것을 막는다.
BEGIN;

-- 한 번의 작업 실행을 기록한다. 실행되지 않고 건너뛴 경우도 이 테이블에 남길 수 있다.
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY NOT NULL, -- 한 실행을 구분하는 내부 ID
    job TEXT NOT NULL, -- rebalance, daily 등 실행한 작업 이름
    started_at TEXT NOT NULL, -- 시간대가 포함된 시작 시각
    finished_at TEXT, -- 실행 중이면 아직 없을 수 있는 종료 시각
    -- running=실행 중, ok=성공, skipped=건너뜀, failed=실패, locked=다른 실행의 잠금으로 종료
    status TEXT NOT NULL CHECK (status IN ('running', 'ok', 'skipped', 'failed', 'locked')),
    skip_reason TEXT,
    -- 건너뜀 상태에는 공백이 아닌 사유가 반드시 있어야 한다.
    CHECK (status != 'skipped' OR length(trim(coalesce(skip_reason, ''))) > 0)
);

-- 해당 실행에서 사용한 전략의 목표 비중을 저장한다. 예: 0.2는 전체 자산의 20%다.
CREATE TABLE IF NOT EXISTS targets (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    as_of TEXT NOT NULL, -- 전략 신호의 기준일
    execution_date TEXT NOT NULL, -- 주문을 실행할 날짜
    ticker TEXT NOT NULL,
    target_weight REAL NOT NULL CHECK (target_weight BETWEEN 0 AND 1),
    strategy_version TEXT NOT NULL,
    PRIMARY KEY (run_id, ticker), -- 같은 실행에서 한 종목의 목표 비중은 한 행만 저장
    -- ISO 날짜 문자열끼리 비교해 신호 기준일이 주문일보다 앞서도록 제한한다.
    CHECK (as_of < execution_date)
);

-- 실제 주문 요청 전에 만든 계획이다. 증권사에 전송한 주문 기록과는 별도로 보관한다.
CREATE TABLE IF NOT EXISTS order_plans (
    plan_id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    -- INTEGER 선언 외에 typeof도 확인해 소수 수량이 저장되지 않게 한다. 0주 계획은 허용한다.
    quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity >= 0),
    limit_price REAL CHECK (limit_price IS NULL OR limit_price > 0),
    -- planned=계획, blocked=점검에서 차단, sent=전송, done=처리 완료
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'blocked', 'sent', 'done')),
    gate_result TEXT NOT NULL DEFAULT '[]', -- 점검 사유 JSON 배열
    -- 같은 실행·종목·매매 구분의 계획을 새 행으로 중복 생성하지 못하게 한다.
    UNIQUE (run_id, ticker, side)
);
-- 매도 체결 뒤 매수 수량을 다시 계산할 때는 같은 plan_id의 quantity를 UPDATE한다.

-- 신규·정정·취소 요청을 남긴다. 응답을 받기 전에도 내부 ID로 먼저 저장할 수 있다.
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, -- 증권사 주문번호와 별개인 DB 내부 주문 ID
    plan_id TEXT NOT NULL REFERENCES order_plans(plan_id),
    -- kind: new=신규, revise=정정, cancel=취소
    kind TEXT NOT NULL CHECK (kind IN ('new', 'revise', 'cancel')),
    -- status: requested=요청 기록, accepted=접수, rejected=거절, unknown=접수 여부 불명확
    status TEXT NOT NULL CHECK (status IN ('requested', 'accepted', 'rejected', 'unknown')),
    order_no TEXT, -- 응답 전에는 NULL. 요청 기록을 먼저 남긴 뒤 응답으로 채운다.
    requested_at TEXT NOT NULL,
    responded_at TEXT,
    UNIQUE (id, order_no) -- fills에서 내부 ID와 증권사 번호의 조합을 함께 확인하기 위한 키
);

-- 한 주문이 여러 번 나누어 체결될 수 있으므로, 체결 순번마다 별도 행으로 저장한다.
CREATE TABLE IF NOT EXISTS fills (
    order_id INTEGER NOT NULL,
    order_no TEXT NOT NULL,
    fill_seq TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity > 0),
    price REAL NOT NULL CHECK (price > 0),
    filled_at TEXT NOT NULL,
    PRIMARY KEY (order_id, fill_seq), -- 같은 주문의 같은 체결 순번을 다시 저장하면 오류
    -- 체결의 증권사 주문번호가 연결된 내부 주문의 번호와 일치해야 저장할 수 있다.
    FOREIGN KEY (order_id, order_no) REFERENCES orders(id, order_no)
);
-- 체결 키에 내부 주문 ID를 사용해 다른 날짜에 같은 증권사 주문번호가 와도 구분한다.

-- 특정 시점의 종목별 보유 수량과 계좌 금액을 기록해 나중에 잔고를 대조할 때 사용한다.
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    captured_at TEXT NOT NULL,
    ticker TEXT, -- 보유 종목이 없으면 NULL로 현금만 기록할 수 있다.
    quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity >= 0),
    cash_available REAL NOT NULL CHECK (cash_available >= 0),
    market_value REAL NOT NULL CHECK (market_value >= 0),
    CHECK (ticker IS NOT NULL OR quantity = 0)
);

-- 내부 기록과 계좌를 대조한 결과를 저장한다. 실제 비교 계산은 reconcile 모듈의 후속 작업이다.
CREATE TABLE IF NOT EXISTS reconciliations (
    reconciliation_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    checked_at TEXT NOT NULL,
    differences TEXT NOT NULL, -- 차이 내역을 담은 JSON
    -- open=확인·해결이 필요한 상태, resolved=해결하고 설명을 남긴 상태
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolved_note TEXT,
    -- 해결 처리 시 어떤 이유로 해결됐는지 설명을 필수로 남긴다.
    CHECK (status != 'resolved' OR length(trim(coalesce(resolved_note, ''))) > 0)
);

-- 미완료 주문이나 실행별 미해결 대조 결과를 찾는 조회를 빠르게 하기 위한 인덱스다.
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_reconciliations_run ON reconciliations(run_id, status);
-- 여기까지 문제가 없으면 위에서 시작한 스키마 생성을 확정한다.
COMMIT;
