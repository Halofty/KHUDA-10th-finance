import bt
import pandas as pd

# 1. 손계산에서 사용한 날짜와 가격을 입력한다.
dates = pd.to_datetime(["2026-11-09", "2026-11-16", "2026-11-17"])
prices = pd.DataFrame({
    "A": [10000, 15000, 16500],
    "B": [20000, 20000, 20000],
    "C": [5000, 2500, 2500],
}, index=dates)

# 2. 매주 세 종목의 투자 비중을 똑같이 맞춘다.
strategy = bt.Strategy("weekly_equal", [
    bt.algos.RunWeekly(),
    bt.algos.SelectAll(),
    bt.algos.WeighEqually(),
    bt.algos.Rebalance(),
])

# 3. 시작 자금 90만 원으로 정수 단위 주식을 사고판다.
test = bt.Backtest(strategy, prices, initial_capital=900_000, integer_positions=True)
bt.run(test)

# 4. 손계산과 bt 평가액을 나란히 보여주고, 날짜별 보유 수량도 출력한다.
comparison = pd.DataFrame({"손계산": [900000, 900000, 930000]}, index=dates)
comparison["bt 평가액"] = test.strategy.values.loc[dates]
comparison["차이"] = comparison["bt 평가액"] - comparison["손계산"]
print(comparison)
print(test.positions.loc[dates, ["A", "B", "C"]])