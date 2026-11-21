SCHEMA_VERSION = "1"
OHLCV = ("open", "high", "low", "close", "volume")
COLUMNS = ("date", "ticker", *OHLCV, "source")
# 시세 표준 스키마 — fetchers·validators·storage가 함께 쓰는 약속
# - 컬럼: date, ticker, open, high, low, close, volume, source
# - 타입: date는 날짜, 가격·거래량은 숫자, ticker는 6자리 문자열
# - 거래 가능 여부는 가격과 따로 둔다: date, ticker, halted(거래정지), upper_limit, lower_limit(상·하한가)
#   평가에는 가격을, 주문 가능 판단(risk_gate)에는 거래 가능 여부를 쓴다
