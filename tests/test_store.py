"""주문 기록의 중복 방지, 원자적 저장, 재접속과 백업 복원을 검증한다."""

from contextlib import closing
from pathlib import Path
import shutil
import sqlite3

import pytest

from khuda_quant.store.db import backup, connect, transaction


@pytest.fixture
def connection(tmp_path):
    # fixture는 각 테스트가 사용할 DB를 준비한다. tmp_path 안에 만들어 실제 로컬 DB를 건드리지 않는다.
    with closing(connect(tmp_path / "operations.sqlite3")) as database:
        # yield 뒤에는 테스트 본문이 실행된다. 끝나면 closing이 연결을 닫는다.
        yield database


def seed_plan(connection, *, run_id="run-1", plan_id="plan-1"):
    # 테스트에서 공통으로 사용할 '실행 1건 + 삼성전자 2주 매수 계획'을 DB에만 저장한다.
    # SQL의 ?에는 뒤의 튜플 값을 순서대로 넣는다. 실제 주문 API는 호출하지 않는다.
    connection.execute(
        "INSERT INTO runs (run_id, job, started_at, status) VALUES (?, 'rebalance', ?, 'running')",
        (run_id, "2026-11-20T09:10:00+09:00"),
    )
    connection.execute(
        "INSERT INTO order_plans (plan_id, run_id, ticker, side, quantity) VALUES (?, ?, '005930', 'buy', 2)",
        (plan_id, run_id),
    )


def request_order(connection, *, plan_id="plan-1"):
    # 증권사 응답 전 상태를 흉내 낸다. order_no는 비워 두고, DB가 만든 내부 ID를 돌려준다.
    return connection.execute(
        "INSERT INTO orders (plan_id, kind, status, requested_at) VALUES (?, 'new', 'requested', ?)",
        (plan_id, "2026-11-20T09:10:01+09:00"),
    ).lastrowid


def record_fill(connection, order_id, *, order_no="0000123", fill_seq="1", quantity=1):
    # 특정 내부 주문에 대한 가상의 부분 체결 한 건을 저장하는 테스트 보조 함수다.
    connection.execute(
        "INSERT INTO fills (order_id, order_no, fill_seq, quantity, price, filled_at) VALUES (?, ?, ?, ?, 70000, ?)",
        (order_id, order_no, fill_seq, quantity, "2026-11-20T09:10:02+09:00"),
    )


def test_connect_creates_operational_tables(tmp_path):
    # 없는 폴더에 DB를 처음 열어도 7개 테이블과 외래 키 검사가 준비되어야 한다.
    with closing(connect(tmp_path / "nested" / "operations.sqlite3")) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert tables == {
            "runs", "targets", "order_plans", "orders", "fills", "snapshots", "reconciliations",
        }
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_committed_records_survive_reconnect_and_schema_reapplication(tmp_path):
    # 저장 뒤 연결을 닫고 다시 열어도, 스키마 적용 때문에 기존 기록이 지워지면 안 된다.
    database = tmp_path / "operations.sqlite3"
    with closing(connect(database)) as connection:
        with transaction(connection):
            seed_plan(connection)
    with closing(connect(database)) as reopened:
        row = reopened.execute("SELECT ticker, quantity FROM order_plans").fetchone()
        assert (row["ticker"], row["quantity"]) == ("005930", 2)
        assert reopened.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("error", [RuntimeError("처리 실패"), KeyboardInterrupt()])
def test_exception_or_interrupt_rolls_back_entire_transaction(connection, error):
    # 일반 오류와 Ctrl+C 중단 모두, 그전에 저장한 실행·계획·주문을 함께 되돌려야 한다.
    with pytest.raises(type(error)):
        with transaction(connection):
            seed_plan(connection)
            request_order(connection)
            raise error
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM order_plans").fetchone()[0] == 0
    assert not connection.in_transaction


def test_constraint_failure_rolls_back_earlier_writes(connection):
    # 같은 주문 계획을 중복 저장해 DB 오류가 나면, 앞서 넣은 실행 기록까지 롤백해야 한다.
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(connection):
            seed_plan(connection)
            connection.execute(
                "INSERT INTO order_plans (plan_id, run_id, ticker, side, quantity) VALUES ('duplicate', 'run-1', '005930', 'buy', 3)"
            )
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_nested_transaction_does_not_commit_outer_block(connection):
    # 실수로 with transaction을 중첩해도 바깥쪽 데이터가 일부 확정되지 않도록 검사한다.
    with pytest.raises(RuntimeError, match="트랜잭션"):
        with transaction(connection):
            seed_plan(connection)
            with transaction(connection):
                pass
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_buy_quantity_is_updated_in_existing_plan(connection):
    # 매수 수량 재계산은 기존 계획을 수정하는 방식이다. 같은 계획을 새 행으로 넣으면 거부한다.
    with transaction(connection):
        seed_plan(connection)
        connection.execute("UPDATE order_plans SET quantity = 3 WHERE plan_id = 'plan-1'")
    assert connection.execute("SELECT quantity FROM order_plans").fetchall()[0][0] == 3
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO order_plans (plan_id, run_id, ticker, side, quantity) VALUES ('second-plan', 'run-1', '005930', 'buy', 1)"
        )
    assert connection.execute("SELECT count(*) FROM order_plans").fetchone()[0] == 1


def test_order_is_saved_before_response_and_can_remain_unknown(connection):
    # 주문번호 없이도 요청을 먼저 저장하고, 응답이 없으면 같은 행을 unknown으로 남길 수 있어야 한다.
    seed_plan(connection)
    order_id = request_order(connection)
    assert connection.execute("SELECT order_no FROM orders WHERE id = ?", (order_id,)).fetchone()[0] is None
    connection.execute("UPDATE orders SET status = 'unknown' WHERE id = ?", (order_id,))
    assert connection.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()[0] == "unknown"
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1


def test_partial_fills_are_distinct_and_duplicate_fill_is_rejected(connection):
    # 서로 다른 체결 순번은 각각 저장하고, 같은 순번을 다시 받았을 때 중복 저장은 차단한다.
    seed_plan(connection)
    order_id = request_order(connection)
    connection.execute("UPDATE orders SET status = 'accepted', order_no = '0000123' WHERE id = ?", (order_id,))
    record_fill(connection, order_id, fill_seq="1")
    record_fill(connection, order_id, fill_seq="2")
    with pytest.raises(sqlite3.IntegrityError):
        record_fill(connection, order_id, fill_seq="1")
    assert connection.execute("SELECT sum(quantity) FROM fills").fetchone()[0] == 2


def test_fill_must_match_parent_broker_order_number(connection):
    # 내부 주문 ID가 맞아도 증권사 주문번호가 다르면 다른 주문의 체결이므로 저장을 거부한다.
    seed_plan(connection)
    order_id = request_order(connection)
    connection.execute("UPDATE orders SET order_no = '0000123' WHERE id = ?", (order_id,))
    with pytest.raises(sqlite3.IntegrityError):
        record_fill(connection, order_id, order_no="different-order")


def test_broker_order_number_can_be_reused_for_a_different_internal_order(connection):
    # 증권사 번호가 같아도 내부 주문이 다르면 구별되어야 한다. 날짜별 번호 재사용에 대비한 검사다.
    seed_plan(connection)
    first_id = request_order(connection)
    connection.execute("UPDATE orders SET order_no = '0000123' WHERE id = ?", (first_id,))
    record_fill(connection, first_id)
    seed_plan(connection, run_id="run-2", plan_id="plan-2")
    second_id = request_order(connection, plan_id="plan-2")
    connection.execute("UPDATE orders SET order_no = '0000123' WHERE id = ?", (second_id,))
    record_fill(connection, second_id)
    assert connection.execute("SELECT count(*) FROM fills").fetchone()[0] == 2


def test_order_cannot_reference_missing_plan(connection):
    # 존재하는 주문 계획에 대해서만 주문 기록을 남길 수 있는지 외래 키 제약을 확인한다.
    with pytest.raises(sqlite3.IntegrityError):
        request_order(connection, plan_id="missing-plan")


@pytest.mark.parametrize("quantity", [-1, 1.5])
def test_plan_rejects_negative_or_fractional_shares(connection, quantity):
    # 주식 수량으로 음수와 1.5주 같은 소수를 저장할 수 없어야 한다.
    seed_plan(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE order_plans SET quantity = ?", (quantity,))


def test_skip_requires_a_reason(connection):
    # 건너뜀 사유가 없으면 거부하고, 사유를 함께 남긴 기록은 허용해야 한다.
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO runs (run_id, job, started_at, status) VALUES ('skip', 'rebalance', ?, 'skipped')",
            ("2026-12-25T09:10:00+09:00",),
        )
    connection.execute(
        "INSERT INTO runs (run_id, job, started_at, status, skip_reason) VALUES ('skip', 'rebalance', ?, 'skipped', '휴장일')",
        ("2026-12-25T09:10:00+09:00",),
    )


def test_targets_cash_only_snapshot_and_reconciliation_are_saved(connection):
    # 목표 비중, 보유 종목 없이 현금만 있는 잔고, 대조 결과의 해결 상태를 저장해 본다.
    seed_plan(connection)
    with transaction(connection):
        connection.execute(
            "INSERT INTO targets VALUES ('run-1', '2026-11-19', '2026-11-20', '005930', 0.2, 'momentum-v1')"
        )
        connection.execute(
            "INSERT INTO snapshots (run_id, captured_at, ticker, quantity, cash_available, market_value) VALUES ('run-1', ?, NULL, 0, 2000000, 0)",
            ("2026-11-20T09:10:00+09:00",),
        )
        connection.execute(
            "INSERT INTO reconciliations (run_id, checked_at, differences) VALUES ('run-1', ?, '[]')",
            ("2026-11-20T15:40:00+09:00",),
        )
        connection.execute("UPDATE reconciliations SET status = 'resolved', resolved_note = '잔고 일치'")
    assert connection.execute("SELECT target_weight FROM targets").fetchone()[0] == 0.2
    assert connection.execute("SELECT cash_available FROM snapshots").fetchone()[0] == 2000000
    assert connection.execute("SELECT status FROM reconciliations").fetchone()[0] == "resolved"


def test_backup_can_be_restored_with_orders_and_fills(connection, tmp_path):
    # 주문과 체결을 백업한 뒤 원본 수량을 바꾼다. 복원본에는 백업 시점의 기록이 남아야 한다.
    with transaction(connection):
        seed_plan(connection)
        order_id = request_order(connection)
        connection.execute("UPDATE orders SET status = 'accepted', order_no = '0000123' WHERE id = ?", (order_id,))
        record_fill(connection, order_id)
    saved = backup(connection, tmp_path / "backups" / "saved.sqlite3")
    connection.execute("UPDATE order_plans SET quantity = 100")
    restored_path = tmp_path / "restored.sqlite3"
    shutil.copyfile(saved, restored_path)
    with closing(connect(restored_path)) as restored:
        assert restored.execute("SELECT quantity FROM order_plans").fetchone()[0] == 2
        assert restored.execute("SELECT sum(quantity) FROM fills").fetchone()[0] == 1
        assert restored.execute("SELECT order_no FROM orders").fetchone()[0] == "0000123"
        # integrity_check는 DB 내부 손상 여부, foreign_key_check는 테이블 연결 오류를 확인한다.
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []


def test_backup_rejects_unfinished_transaction(connection, tmp_path):
    # 저장 중인 작업의 백업은 즉시 거부하고, 불완전한 대상 파일도 만들지 않아야 한다.
    destination = tmp_path / "backup.sqlite3"
    with transaction(connection):
        seed_plan(connection)
        with pytest.raises(RuntimeError, match="트랜잭션"):
            backup(connection, destination)
    assert not destination.exists()


def test_backup_does_not_overwrite_source_or_existing_backup(connection, tmp_path):
    # 백업 경로를 원본이나 기존 백업으로 잘못 지정해도 저장된 내용이 바뀌지 않아야 한다.
    seed_plan(connection)
    source = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    with pytest.raises(ValueError, match="원본"):
        backup(connection, source)
    destination = tmp_path / "backup.sqlite3"
    backup(connection, destination)
    original_bytes = destination.read_bytes()
    with pytest.raises(FileExistsError):
        backup(connection, destination)
    assert destination.read_bytes() == original_bytes
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 1


def test_in_memory_database_can_also_be_backed_up(tmp_path):
    # 메모리에만 존재하는 DB도 파일로 백업하고, 나중에 다시 열어 읽을 수 있어야 한다.
    with closing(connect(":memory:")) as connection:
        seed_plan(connection)
        saved = backup(connection, tmp_path / "memory-backup.sqlite3")
    with closing(connect(saved)) as restored:
        assert restored.execute("SELECT count(*) FROM order_plans").fetchone()[0] == 1
