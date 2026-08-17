import pandas as pd

from tradingagents.dataflows.cache.mongodb_cache_adapter import MongoDBCacheAdapter


class _Cursor:
    def __init__(self, documents):
        self._documents = documents

    def sort(self, *_args):
        return self

    def __iter__(self):
        return iter(self._documents)


class _Collection:
    def __init__(self, documents_by_source):
        self._documents_by_source = documents_by_source

    def find(self, query, _projection):
        return _Cursor(self._documents_by_source.get(query["data_source"], []))


class _Database:
    def __init__(self, documents_by_source):
        self.stock_daily_quotes = _Collection(documents_by_source)


def test_historical_cache_prefers_fresher_source_over_priority(monkeypatch):
    adapter = MongoDBCacheAdapter.__new__(MongoDBCacheAdapter)
    adapter.use_app_cache = True
    adapter.db = _Database(
        {
            "akshare": [
                {"symbol": "002714", "data_source": "akshare", "period": "daily", "trade_date": "2026-08-11", "close": 40.11},
            ],
            "baostock": [
                {"symbol": "002714", "data_source": "baostock", "period": "daily", "trade_date": "2026-08-17", "close": 39.29},
            ],
        }
    )
    monkeypatch.setattr(adapter, "_get_data_source_priority", lambda _symbol: ["akshare", "baostock"])

    result = adapter.get_historical_data("002714")

    assert isinstance(result, pd.DataFrame)
    assert result.iloc[-1]["data_source"] == "baostock"
    assert result.iloc[-1]["trade_date"] == "2026-08-17"
    assert result.iloc[-1]["close"] == 39.29

