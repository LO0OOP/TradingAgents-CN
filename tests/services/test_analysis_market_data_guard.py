import asyncio

import pytest

from app.services import analysis_market_data_guard as guard


def test_normalize_trade_date_supports_provider_formats():
    assert guard._normalize_trade_date("20260820") == "2026-08-20"
    assert guard._normalize_trade_date("2026-08-20T09:31:00+08:00") == "2026-08-20"
    assert guard._normalize_trade_date(None) is None


def test_cn_analysis_accepts_latest_cached_quote_without_refresh(monkeypatch):
    class FakeQuoteService:
        async def get_cn_source_config_signature(self):
            return (("akshare", 20),)

        async def refresh_cn_market(self):
            raise AssertionError("latest cache should not trigger a network refresh")

    class FakeCollection:
        async def find_one(self, *_args, **_kwargs):
            return {"code": "000001", "trade_date": "20260819", "close": 10.0}

    class FakeDb:
        def __getitem__(self, _name):
            return FakeCollection()

    monkeypatch.setattr(guard, "get_market_quote_service", lambda: FakeQuoteService())
    monkeypatch.setattr(guard, "get_mongo_db", lambda: FakeDb())
    async def latest_trade_date():
        return "2026-08-19"
    monkeypatch.setattr(guard, "_get_latest_cn_trade_date", latest_trade_date)
    monkeypatch.setattr(guard, "_cn_refresh_at", None)
    monkeypatch.setattr(guard, "_cn_refresh_trade_date", None)
    monkeypatch.setattr(guard, "_cn_refresh_source_config", None)

    result = asyncio.run(guard.require_current_market_data("000001", "A股"))

    assert result["trade_date"] == "2026-08-19"
    assert result["price"] == 10.0


def test_cn_analysis_rejects_quote_without_trade_date(monkeypatch):
    class FakeQuoteService:
        async def get_cn_source_config_signature(self):
            return (("akshare", 20),)

        async def refresh_cn_market(self):
            return {"success": True, "source": "akshare", "trade_date": None}

    class FakeCollection:
        async def find_one(self, *_args, **_kwargs):
            return {"code": "000001", "trade_date": None, "close": 10.0}

    class FakeDb:
        def __getitem__(self, _name):
            return FakeCollection()

    monkeypatch.setattr(guard, "get_market_quote_service", lambda: FakeQuoteService())
    monkeypatch.setattr(guard, "get_mongo_db", lambda: FakeDb())
    async def latest_trade_date():
        return "2026-08-19"
    monkeypatch.setattr(guard, "_get_latest_cn_trade_date", latest_trade_date)
    monkeypatch.setattr(guard, "_cn_refresh_at", None)
    monkeypatch.setattr(guard, "_cn_refresh_trade_date", None)
    monkeypatch.setattr(guard, "_cn_refresh_source_config", None)

    with pytest.raises(guard.MarketDataFreshnessError, match="缺少交易日期"):
        asyncio.run(guard.require_current_market_data("000001", "A股"))
