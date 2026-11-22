"""실제 2026년 휴장일과 연도 경계에서 거래일 계산을 검증한다."""

from datetime import date, datetime
import tomllib

import pytest

from khuda_quant.market_day import DEFAULT_CALENDAR_PATH, is_trading_day, next_trading_day

# parametrize는 아래 목록의 값을 하나씩 넣어 같은 검사를 반복한다.
# assert는 기대한 결과와 다르면 테스트를 실패시키며, assert not은 False인지 확인한다.


@pytest.mark.parametrize("day", [date(2026, 1, 2), date(2026, 6, 8), date(2026, 11, 20)])
def test_weekday_is_trading_day(day):
    # 일반 평일과 대체휴일이 아닌 현충일 다음 월요일은 거래일이어야 한다.
    assert is_trading_day(day)


@pytest.mark.parametrize("day", [date(2026, 11, 21), date(2026, 11, 22)])
def test_weekend_is_closed(day):
    # 토요일과 일요일은 휴장일 파일에 따로 적지 않아도 거래일에서 제외한다.
    assert not is_trading_day(day)


@pytest.mark.parametrize("day", [
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 2), date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 25),
    date(2026, 6, 3), date(2026, 7, 17), date(2026, 8, 17), date(2026, 9, 24),
    date(2026, 9, 25), date(2026, 10, 5), date(2026, 10, 9), date(2026, 12, 25),
    date(2026, 12, 31),
])
def test_2026_holiday_is_closed(day):
    # 설정 파일에 등록한 공휴일·대체공휴일·선거일·연말 휴장이 모두 제외되는지 검사한다.
    assert not is_trading_day(day)


@pytest.mark.parametrize(("day", "expected"), [
    (date(2026, 11, 19), date(2026, 11, 20)),
    (date(2026, 11, 20), date(2026, 11, 23)),
    (date(2026, 11, 21), date(2026, 11, 23)),
    (date(2026, 2, 13), date(2026, 2, 19)),
    (date(2026, 5, 22), date(2026, 5, 26)),
    (date(2026, 9, 23), date(2026, 9, 28)),
    (date(2026, 12, 24), date(2026, 12, 28)),
])
def test_next_trading_day_skips_closed_days(day, expected):
    # 정상 평일, 주말, 설·추석 연휴 등을 지나 예상한 첫 거래일에 도착해야 한다.
    assert next_trading_day(day) == expected


@pytest.mark.parametrize("day", [date(2025, 12, 31), date(2027, 1, 2)])
@pytest.mark.parametrize("function", [is_trading_day, next_trading_day])
def test_uncovered_year_always_raises(day, function):
    # 두 함수 모두 미등록 연도에서 멈춰야 한다. raises 안에서 예상한 오류가 나면 통과한다.
    with pytest.raises(LookupError, match=str(day.year)):
        function(day)


@pytest.mark.parametrize("day", [date(2026, 12, 30), date(2026, 12, 31)])
def test_next_trading_day_stops_at_uncovered_year(day):
    # 2026년 말에서 다음 거래일을 찾다가 2027년 목록이 필요해지면 오류로 중단해야 한다.
    with pytest.raises(LookupError, match="2027"):
        next_trading_day(day)


@pytest.mark.parametrize("function", [is_trading_day, next_trading_day])
def test_datetime_requires_explicit_date_conversion(function):
    # 시각이 포함된 값을 실수로 넘기면 거부한다. 호출자는 먼저 .date()로 변환해야 한다.
    with pytest.raises(TypeError, match="datetime.date"):
        function(datetime(2026, 12, 25, 9))


def test_default_calendar_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    # tmp_path는 테스트용 임시 폴더다. 작업 위치를 옮겨도 프로젝트의 휴장일 파일을 찾아야 한다.
    # monkeypatch가 바꾼 작업 위치는 이 테스트가 끝나면 자동으로 복구된다.
    monkeypatch.chdir(tmp_path)
    assert not is_trading_day(date(2026, 12, 25))


def test_explicit_calendar_supports_year_boundary(tmp_path):
    # 실제 설정은 바꾸지 않고, 2027년까지 지원하는 임시 파일로 연도 경계의 정상 계산을 확인한다.
    calendar = tmp_path / "holidays.toml"
    calendar.write_text("covered_years = [2026, 2027]\nclosed = [2027-01-01]\n", encoding="utf-8")
    assert next_trading_day(date(2026, 12, 31), calendar_path=calendar) == date(2027, 1, 4)


@pytest.mark.parametrize("content", [
    "covered_years = []\nclosed = []",
    "covered_years = [true]\nclosed = []",
    "covered_years = [2026, 2026]\nclosed = []",
    'covered_years = [2026]\nclosed = ["2026-01-01"]',
    "covered_years = [2026]\nclosed = [2027-01-01]",
    "covered_years = [2026]\nclosed = [2026-11-21]",
    "covered_years = [2026]\nclosed = [2026-01-01, 2026-01-01]",
    "covered_years = [2026]",
])
def test_invalid_calendar_is_rejected(tmp_path, content):
    # 빈 연도 목록·잘못된 날짜 형식·중복·주말 등록 등 설정 오류를 조용히 무시하면 안 된다.
    calendar = tmp_path / "invalid.toml"
    calendar.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        is_trading_day(date(2026, 11, 20), calendar_path=calendar)


def test_missing_calendar_is_not_treated_as_open(tmp_path):
    # 설정 파일이 없을 때도 평일이라는 이유만으로 거래 가능하다고 판단하지 않아야 한다.
    with pytest.raises(FileNotFoundError):
        is_trading_day(date(2026, 11, 20), calendar_path=tmp_path / "missing.toml")


def test_calendar_covers_exactly_2026_weekday_closures():
    # 실제 설정의 지원 연도와 휴장일 개수가 이번에 확인한 2026년 자료와 일치하는지 검사한다.
    with DEFAULT_CALENDAR_PATH.open("rb") as calendar_file:
        calendar = tomllib.load(calendar_file)
    assert calendar["covered_years"] == [2026]
    assert len(calendar["closed"]) == 17
