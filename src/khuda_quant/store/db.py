"""SQLite 스키마 적용, 명시적 트랜잭션, 새 파일로의 백업을 제공한다."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


def connect(path: str | Path) -> sqlite3.Connection:
    """DB를 열고 스키마를 적용한다. 호출한 쪽에서 close()해야 한다."""
    path = Path(path)
    # :memory:는 파일을 만들지 않는 임시 DB다. 파일 DB라면 저장할 상위 폴더부터 만든다.
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    # 자동 트랜잭션 시작을 끈다. 여러 SQL을 한 작업으로 묶을 때는 아래 transaction()을 사용한다.
    # transaction() 밖에서 실행한 개별 SQL은 바로 반영되는 방식이다.
    connection = sqlite3.connect(str(path), isolation_level=None)
    # 조회한 행을 row[0]뿐 아니라 row['ticker']처럼 컬럼 이름으로도 읽을 수 있게 한다.
    connection.row_factory = sqlite3.Row
    try:
        # 이 파일과 같은 폴더의 SQL을 실행한다. CREATE TABLE IF NOT EXISTS가 기존 기록을 보존한다.
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
    except BaseException:
        # 스키마 생성 실패나 사용자 중단 시, 사용할 수 없는 DB 연결이 남지 않도록 닫는다.
        connection.close()
        raise
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """블록이 성공하면 커밋하고, 예외가 발생하면 블록 전체를 롤백한다."""
    # @contextmanager 덕분에 'with transaction(connection):' 형태로 사용할 수 있다.
    # 중첩을 허용하면 안쪽 작업이 바깥쪽 작업까지 저장할 수 있으므로 먼저 거부한다.
    if connection.in_transaction:
        raise RuntimeError("이미 트랜잭션이 진행 중입니다")
    # BEGIN부터 commit/rollback까지의 SQL들을 하나의 작업 단위로 묶는다.
    connection.execute("BEGIN")
    try:
        # 여기서 호출한 쪽의 with 블록을 실행한다. 정상 종료하면 아래 commit()으로 돌아온다.
        yield connection
        connection.commit()
    except BaseException:
        # 일부만 저장되지 않도록 전부 되돌린다. KeyboardInterrupt(Ctrl+C)도 포함해 처리한다.
        connection.rollback()
        # 오류는 호출한 쪽에도 전달해 실패를 알아차리고 대응할 수 있게 한다.
        raise


def backup(connection: sqlite3.Connection, path: str | Path) -> Path:
    """SQLite backup API로 백업한다. 원본과 기존 백업 파일은 덮어쓰지 않는다."""
    # 아직 끝나지 않은 트랜잭션에서 백업하면 완료를 기다리며 멈출 수 있으므로 차단한다.
    if connection.in_transaction:
        raise RuntimeError("백업 전에 트랜잭션을 마쳐야 합니다")
    destination = Path(path).resolve()
    # PRAGMA database_list의 각 행은 (번호, DB 이름, 파일 경로)다. 원본 경로를 비교한다.
    databases = connection.execute("PRAGMA database_list").fetchall()
    if any(row[2] and Path(row[2]).resolve() == destination for row in databases):
        raise ValueError("원본 DB 파일에 백업할 수 없습니다")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # x는 파일이 이미 있으면 실패하는 생성 모드다. 기존 백업을 덮어쓰는 일을 막는다.
    with destination.open("xb"):
        pass
    try:
        # 단순 파일 복사 대신 SQLite의 백업 기능으로 내용을 옮긴다.
        # closing은 백업 중 오류가 나도 대상 DB의 연결을 닫아 준다.
        with closing(sqlite3.connect(destination)) as target:
            connection.backup(target)
    except BaseException:
        # 실패한 백업이 정상 파일로 오인되지 않도록 이번 호출에서 만든 파일만 지운다.
        destination.unlink()
        raise
    # 백업된 위치를 호출한 쪽에서 로그에 남기거나 다시 열 수 있도록 반환한다.
    return destination
