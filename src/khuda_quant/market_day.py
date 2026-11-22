"""휴장일 파일을 기준으로 날짜 단위 거래일을 계산한다.

1주차 범위: 주말·휴장일 판단과 다음 거래일 계산.
ExecCondition의 시간대·KIS 대조·건너뜀 기록은 후속 작업이다.

후속 구현 메모:
- python -m khuda_quant.market_day <job>: 0=실행, 1=건너뜀, 255=연도 목록 없음.
- Asia/Seoul 기준 rebalance는 거래일 + settings.yaml의 order_window, daily는 거래일만 확인.
- 거래일이면 KIS chk_holiday(opnd_yn)와 대조하고 결과를 SQLite에 1일 1회 저장·재사용.
  모의 계좌 지원 여부는 미확인이다. 불일치면 건너뜀 + 알림.
- 건너뛸 때는 서비스가 실행되지 않으므로 종료 전에 runs에 skipped와 사유를 기록.
"""

from datetime import date, timedelta
from pathlib import Path
import tomllib


# 현재 작업 폴더 대신 이 소스 파일의 위치를 기준으로 프로젝트의 설정 파일을 찾는다.
# __file__은 이 파일의 경로이며, parents[2]는 src 위의 프로젝트 폴더다.
DEFAULT_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "config" / "krx_holidays.toml"


def _load_calendar(path: str | Path) -> tuple[set[int], set[date]]:
    """잘못된 설정은 평일을 거래일로 간주하지 않고 즉시 거부한다."""
    # tomllib은 TOML 설정을 딕셔너리로 읽는다. rb는 이 함수가 요구하는 바이너리 읽기 모드다.
    # with 블록이 끝나면 설정 파일은 자동으로 닫힌다.
    with Path(path).open("rb") as calendar_file:
        calendar = tomllib.load(calendar_file)
    years, closed = calendar.get("covered_years"), calendar.get("closed")
    # 지원 연도는 비어 있지 않은 정수 목록이어야 한다. 실제 날짜에 가능한 연도만 허용한다.
    # type(year) is int로 검사해 Python에서 정수처럼 취급되는 True/False도 제외한다.
    if (
        not isinstance(years, list)
        or not years
        or any(type(year) is not int or not 1 <= year <= 9999 for year in years)
    ):
        raise ValueError("covered_years에는 지원하는 연도 목록이 필요합니다")
    # "2026-01-01" 같은 문자열이나 시각이 포함된 값은 date와 다르므로 설정 오류로 처리한다.
    if not isinstance(closed, list) or any(type(day) is not date for day in closed):
        raise ValueError("closed에는 따옴표 없는 TOML 날짜 목록이 필요합니다")
    # set은 중복을 제거하므로, 변환 전후 개수가 다르면 같은 값이 두 번 등록된 것이다.
    if len(set(years)) != len(years) or len(set(closed)) != len(closed):
        raise ValueError("연도와 휴장일은 중복해서 등록할 수 없습니다")
    # weekday()는 월요일=0, 일요일=6이다. 주말은 별도로 판단하므로 휴장일 목록에서는 제외한다.
    if any(day.year not in years or day.weekday() >= 5 for day in closed):
        raise ValueError("closed에는 지원하는 연도의 평일 휴장일만 등록합니다")
    # 반환값을 set으로 만들면 이후에 '이 날짜가 휴장일에 포함되는가'를 빠르게 확인할 수 있다.
    return set(years), set(closed)


def _check_year(day: date, years: set[int]) -> None:
    # datetime은 시각까지 포함해 휴장일의 date와 비교 결과가 달라질 수 있어 명시적으로 거부한다.
    if type(day) is not date:
        raise TypeError("날짜는 datetime.date로 전달해야 합니다")
    # 주말이라도 미등록 연도라면 중단한다. 휴장일을 모르는 해를 임의로 판단하지 않는다.
    if day.year not in years:
        raise LookupError(f"{day.year}년 휴장일 목록이 없습니다")


def is_trading_day(day: date, *, calendar_path: str | Path = DEFAULT_CALENDAR_PATH) -> bool:
    """지원하는 연도에서 주말과 등록된 휴장일을 제외한다."""
    # * 뒤의 calendar_path는 이름을 지정해 전달하는 선택 인자다. 테스트용 설정도 넣을 수 있다.
    years, closed = _load_calendar(calendar_path)
    _check_year(day, years)
    # 평일이고 휴장일 목록에도 없을 때만 True(거래일)를 반환한다.
    return day.weekday() < 5 and day not in closed


def next_trading_day(day: date, *, calendar_path: str | Path = DEFAULT_CALENDAR_PATH) -> date:
    """입력 날짜 다음 날부터 찾는다. 미등록 연도에 도달하면 멈춘다."""
    # 탐색하는 동안 설정 파일을 반복해서 읽지 않도록 연도와 휴장일을 한 번만 불러온다.
    years, closed = _load_calendar(calendar_path)
    _check_year(day, years)
    while True:
        # 입력 당일은 제외하고 하루씩 이동하며, 처음 만나는 거래일에서 탐색을 끝낸다.
        day += timedelta(days=1)
        # 12월에서 다음 해로 넘어가면 새 연도의 목록도 있는지 다시 검사한다.
        _check_year(day, years)
        if day.weekday() < 5 and day not in closed:
            return day
