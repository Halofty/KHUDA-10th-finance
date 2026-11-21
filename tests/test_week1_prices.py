from pathlib import Path

import pandas as pd
import pytest

from khuda_quant.data.fetchers import FdrFetcher
from khuda_quant.data.schema import COLUMNS
from khuda_quant.data.validators import validate_prices


def test_fetch_and_validate_sample(monkeypatch):
    path = Path(__file__).parent / "fixtures" / "sample_prices.csv"
    sample = pd.read_csv(path, dtype={"ticker": str}, parse_dates=["date"])
    raw = sample.set_index("date").drop(columns=["ticker", "source"]).rename(columns=str.title)
    monkeypatch.setattr("khuda_quant.data.fetchers.fdr.DataReader", lambda *args: raw)
    result = FdrFetcher().fetch("005930", "2026-11-19", "2026-11-20")
    dates = pd.DatetimeIndex(sample["date"])
    assert tuple(result.data.columns) == COLUMNS
    assert result.data["ticker"].tolist() == ["005930", "005930"]
    assert result.data["close"].mean() == 10750
    assert validate_prices(result.data, dates) == []
    assert validate_prices(result.data.iloc[:1], dates)
    assert "duplicate date/ticker" in validate_prices(pd.concat([result.data, result.data]))
    assert "OHLC outside low/high" in validate_prices(result.data.assign(close=100_000))
    assert "missing or non-finite value" in validate_prices(result.data.assign(volume=float("nan")))


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    from khuda_quant.data.fetchers import FetchResult
    from khuda_quant.data.storage import save_prices

    path = Path(__file__).parent / "fixtures" / "sample_prices.csv"
    bars = pd.read_csv(path, dtype={"ticker": str}, parse_dates=["date"])
    bars["date"] = bars["date"].dt.date
    target = save_prices(FetchResult(bars, "synthetic", (), bars), tmp_path, "sample.parquet")
    pd.testing.assert_frame_equal(pd.read_parquet(target), bars)
