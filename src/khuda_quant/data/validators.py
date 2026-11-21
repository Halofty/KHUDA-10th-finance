# 시세 검증 → 문제 목록 반환 (빈 목록이면 통과)
# - 중복, 결측, 0 이하 가격, 고가 < 저가, 오래된 데이터

import numpy as np
import pandas as pd

from .schema import OHLCV


def validate_prices(bars, expected_dates=None, start=None, end=None) -> list[str]:
    if bars.empty:
        return ["no data"]
    problems = []
    prices = bars[list(OHLCV[:-1])]
    if bars.duplicated(["date", "ticker"]).any():
        problems.append("duplicate date/ticker")
    if bars.isna().any().any() or not np.isfinite(bars[list(OHLCV)]).all().all():
        problems.append("missing or non-finite value")
    if prices.le(0).any().any() or bars["volume"].lt(0).any():
        problems.append("invalid price or volume")
    if (bars["low"].gt(prices.min(axis=1)) | bars["high"].lt(prices.max(axis=1))).any():
        problems.append("OHLC outside low/high")
    actual = pd.DatetimeIndex(bars["date"])
    if (start is not None and (actual < start).any()) or (end is not None and (actual > end).any()):
        problems.append("dates outside requested range")
    if expected_dates is None:
        return problems
    missing = expected_dates.difference(actual)
    extra = actual.difference(expected_dates)
    if len(missing):
        problems.append(f"missing sessions: {missing.strftime('%Y-%m-%d').tolist()}")
    if len(extra):
        problems.append(f"unexpected sessions: {extra.strftime('%Y-%m-%d').tolist()}")
    return problems
