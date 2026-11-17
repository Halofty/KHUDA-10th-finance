# 시세 수집 실행 [연구·초기] — 사람이 필요할 때 실행
# - 수집(data/fetchers.py) → 검증(data/validators.py) → data/market/에 Parquet 저장(data/storage.py)
# - 처음 시작할 때, 백테스트 전에 실행. 운용 중 갱신은 rebalance.py가 같은 모듈로 직접 한다
