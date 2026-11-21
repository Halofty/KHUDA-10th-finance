# 시세 수집 실행 [연구·초기] — 사람이 필요할 때 실행
# - 수집(data/fetchers.py) → 검증(data/validators.py) → data/market/에 Parquet 저장(data/storage.py)
# - 처음 시작할 때, 백테스트 전에 실행. 운용 중 갱신은 rebalance.py가 같은 모듈로 직접 한다

import argparse
from pathlib import Path

import pandas as pd

from khuda_quant.data.fetchers import FdrFetcher
from khuda_quant.data.storage import save_prices
from khuda_quant.data.validators import validate_prices


def main():
    parser = argparse.ArgumentParser(description="Fetch and validate Korean daily bars")
    parser.add_argument("tickers", nargs="+", help="Six-digit KRX codes")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--sessions", type=Path, help="Optional CSV with expected trading dates")
    parser.add_argument("--output", type=Path, default=Path("data/market"))
    args = parser.parse_args()
    if any(len(t) != 6 or not t.isascii() or not t.isdigit() for t in args.tickers):
        parser.error("tickers must be six ASCII digits")
    start, end = args.start, args.end
    start_date, end_date = pd.to_datetime([start, end], format="%Y-%m-%d")
    if start_date > end_date or [start, end] != [d.strftime("%Y-%m-%d") for d in (start_date, end_date)]:
        parser.error("조회 범위를 YYYY-MM-DD 형식으로 입력하세요.")
    sessions = None
    if args.sessions is not None:
        sessions = pd.DatetimeIndex(pd.read_csv(args.sessions, parse_dates=["date"])["date"])
        if sessions.empty or sessions.hasnans or sessions.has_duplicates:
            parser.error("거래일 목록에는 유효한 날짜가 중복 없이 있어야 합니다.")
    fetcher = FdrFetcher()
    results = {}
    for ticker in dict.fromkeys(args.tickers):
        result = fetcher.fetch(ticker, start, end)
        if problems := validate_prices(result.data, sessions, start_date, end_date):
            parser.exit(1, f"{ticker}: {'; '.join(problems)}\n")
        results[ticker] = result
    for ticker, result in results.items():
        print(save_prices(result, args.output, f"{ticker}_{start}_{end}.parquet"))


if __name__ == "__main__":
    main()

