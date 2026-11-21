# 주가 가져오고, 우리 팀 표 양식으로 바꾸어줌
# 시세 수집 (FinanceDataReader)
# - OpenBB식 TET: transform_query → extract_data → transform_data
# - FdrFetcher, 결과는 FetchResult(data, provider, warnings)
# - 결과는 data/schema.py의 표준 컬럼으로 변환

#준비물!
from dataclasses import dataclass   #데이터담는 클래스.. FetchResult 만들 때 사용

import FinanceDataReader as fdr   #주가데이터가져오는 라이브러리
import pandas as pd

from .schema import COLUMNS, OHLCV      #schema.py에서 열 이름과 시세 열 5개

PROVIDER = "FinanceDataReader"


@dataclass(frozen=True)           #아래적힌 항목들.. 받아 객체 만듦
class FetchResult:
    data: pd.DataFrame
    provider: str
    warnings: tuple[str, ...]
    raw: pd.DataFrame


class FdrFetcher:                     #시세수집에 필요한 함수들 모아놓은 클래스
    def fetch(self, ticker: str, start: str, end: str) -> FetchResult:
        query = self.transform_query(ticker, start, end)      #조회조건정리, query에 담기
        raw = self.extract_data(query)               #정리된 조건으로 시세 가져와 raw에
        return self.transform_data(raw, query[0])      #원본시세, 종목코드 넘겨 표준화한 결과 돌려줌

    @staticmethod            #조회할 종목과 날짜 정리 (오류있는가?)
    def transform_query(ticker, start, end):
        ticker = ticker.strip()            
        if len(ticker) != 6 or not ticker.isascii() or not ticker.isdigit():   #길이 6, ascii, 숫자여야함 > 아니면 오류
            raise ValueError("ticker must be six ASCII digits")
        dates = pd.to_datetime([start, end], format="%Y-%m-%d")  
        if dates.hasnans or dates[0] > dates[1]:    #날짜맞는지..
            raise ValueError("invalid date range")
        return ticker, *dates.strftime("%Y-%m-%d")

    @staticmethod                  #실제 시세 가져옴
    def extract_data(query):
        return fdr.DataReader(*query)

    @staticmethod               #가져온표>팀양식으로
    def transform_data(raw, ticker):
        if raw.empty:
            return FetchResult(pd.DataFrame(columns=COLUMNS), PROVIDER, ("no data",), raw)
        bars = raw.rename(columns=str.lower).loc[:, list(OHLCV)].copy()
        for name in OHLCV:
            bars[name] = pd.to_numeric(bars[name], errors="coerce")
        bars.insert(0, "date", pd.to_datetime(raw.index).date)
        bars = bars.reset_index(drop=True).assign(ticker=ticker, source=PROVIDER)
        return FetchResult(bars.loc[:, list(COLUMNS)], PROVIDER, (), raw)
