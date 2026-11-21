from dataclasses import dataclass

import FinanceDataReader as fdr
import pandas as pd

from .schema import COLUMNS, OHLCV

PROVIDER = "FinanceDataReader"


@dataclass(frozen=True)
class FetchResult:
    data: pd.DataFrame
    provider: str
    warnings: tuple[str, ...]
    raw: pd.DataFrame


class FdrFetcher:
    def fetch(self, ticker: str, start: str, end: str) -> FetchResult:
        raw = fdr.DataReader(ticker, start, end)
        if raw.empty:
            return FetchResult(pd.DataFrame(columns=COLUMNS), PROVIDER, ("no data",), raw)
        bars = raw.rename(columns=str.lower).loc[:, list(OHLCV)].copy()
        for name in OHLCV:
            bars[name] = pd.to_numeric(bars[name], errors="coerce")
        bars.insert(0, "date", pd.to_datetime(raw.index).date)
        bars = bars.reset_index(drop=True).assign(ticker=ticker, source=PROVIDER)
        return FetchResult(bars.loc[:, list(COLUMNS)], PROVIDER, (), raw)
# 시세 수집 (FinanceDataReader)
# - OpenBB식 TET: transform_query → extract_data → transform_data
# - FdrFetcher, 결과는 FetchResult(data, provider, warnings)
# - 결과는 data/schema.py의 표준 컬럼으로 변환
