"""Hard freshness gate for analysis-time market quotes."""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from app.core.database import get_mongo_db
from app.services.market_quote_service import get_market_quote_service

logger = logging.getLogger(__name__)


class MarketDataFreshnessError(RuntimeError):
    """Raised when an analysis cannot obtain a verified latest provider quote."""


_CN_REFRESH_LOCK = asyncio.Lock()
_cn_refresh_at: Optional[datetime] = None
_cn_refresh_trade_date: Optional[str] = None
_cn_refresh_source_config: Optional[Tuple[Tuple[str, int], ...]] = None
_CN_REFRESH_REUSE_SECONDS = 60


def _normalize_trade_date(value: Any) -> Optional[str]:
    """Normalize common provider date/timestamp formats to YYYY-MM-DD."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=ZoneInfo("UTC")).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else None


async def _refresh_cn_quotes() -> Dict[str, Any]:
    """Refresh A-share quotes once for concurrently-started analysis tasks."""
    global _cn_refresh_at, _cn_refresh_trade_date, _cn_refresh_source_config

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    async with _CN_REFRESH_LOCK:
        service = get_market_quote_service()
        source_config = await service.get_cn_source_config_signature()
        if (
            _cn_refresh_at
            and now - _cn_refresh_at < timedelta(seconds=_CN_REFRESH_REUSE_SECONDS)
            and _cn_refresh_trade_date
            and _cn_refresh_source_config == source_config
        ):
            return {"success": True, "trade_date": _cn_refresh_trade_date, "reused": True}

        result = await service.refresh_cn_market()
        if not result.get("success"):
            raise MarketDataFreshnessError(
                f"A股实时行情刷新失败: {result.get('error') or '没有可用行情源'}"
            )

        _cn_refresh_at = now
        _cn_refresh_trade_date = _normalize_trade_date(result.get("trade_date"))
        _cn_refresh_source_config = source_config
        return result


async def _get_latest_cn_trade_date() -> Optional[str]:
    """Read the latest trading day via the user's enabled source priority."""
    try:
        value = await get_market_quote_service().get_latest_cn_trade_date()
    except Exception as exc:
        logger.warning("无法确认 A股最新交易日: %s", exc)
        return None
    return _normalize_trade_date(value)


def _build_cn_quote_result(
    code: str,
    quote: Dict[str, Any],
    source: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "market": "A股",
        "code": code,
        "trade_date": _normalize_trade_date(quote.get("trade_date")),
        "source": quote.get("source") or source,
        "price": quote.get("close"),
    }


async def _ensure_cn_quote(stock_code: str) -> Dict[str, Any]:
    db = get_mongo_db()
    code = str(stock_code).zfill(6)
    quote = await db["market_quotes"].find_one(
        {"$or": [{"code": code}, {"symbol": code}]},
        {"_id": 0},
    )
    expected_date = await _get_latest_cn_trade_date()
    quote_date = _normalize_trade_date(quote.get("trade_date")) if quote else None
    if not expected_date:
        raise MarketDataFreshnessError("无法确认 A股最新交易日")

    # A cache is valid when it belongs to the latest trading day confirmed from
    # the configured sources. Do not request the quote API again in that case.
    if quote and quote_date == expected_date and quote.get("close") is not None:
        logger.info(
            "✅ [行情新鲜度] A股 %s 使用最新缓存行情: date=%s source=%s",
            code,
            quote_date,
            quote.get("source"),
        )
        return _build_cn_quote_result(code, quote)

    logger.info(
        "🔄 [行情新鲜度] A股 %s 缓存%s，按配置优先级刷新行情",
        code,
        "缺失" if not quote else f"日期 {quote_date or '未知'} 落后于 {expected_date}",
    )
    quote_result = await get_market_quote_service().get_quotes(
        [{"code": code, "market": "CN"}],
        force_refresh=True,
    )
    key = f"CN:{code}"
    refreshed = quote_result["quotes"].get(key)
    if not refreshed:
        raise MarketDataFreshnessError(
            f"A股 {code} 实时行情刷新失败: {quote_result['errors'].get(key, '没有可用行情源')}"
        )
    quote = {
        "close": refreshed.get("price"),
        "trade_date": refreshed.get("trade_date"),
        "pct_chg": refreshed.get("change_percent"),
        "source": refreshed.get("source"),
    }
    return _build_cn_quote_result(code, quote, refreshed.get("source"))


async def _ensure_foreign_quote(market_type: str, stock_code: str) -> Dict[str, Any]:
    market = "HK" if market_type == "港股" else "US"
    quote_result = await get_market_quote_service().get_quotes(
        [{"code": stock_code, "market": market}],
        force_refresh=True,
    )
    key = f"{market}:{stock_code}"
    quote = quote_result["quotes"].get(key)
    if not quote:
        raise MarketDataFreshnessError(
            f"{market_type} {stock_code} 实时行情刷新失败: "
            f"{quote_result['errors'].get(key, '没有可用行情源')}"
        )
    quote_date = _normalize_trade_date(
        quote.get("trade_date") or quote.get("latest_trading_day") or quote.get("timestamp")
    )
    if not quote_date:
        raise MarketDataFreshnessError(
            f"{market_type} {stock_code} 最新行情缺少交易日期，无法确认数据是否为最新"
        )
    price = quote.get("price") or quote.get("close")
    if price is None:
        raise MarketDataFreshnessError(f"{market_type} {stock_code} 最新行情缺少有效价格")
    return {
        "market": market_type,
        "code": stock_code,
        "trade_date": quote_date,
        "source": quote.get("source"),
        "price": price,
    }


async def require_current_market_data(stock_code: str, market_type: str) -> Dict[str, Any]:
    """Refresh and verify the latest provider quote before model analysis."""
    if market_type == "A股":
        quote = await _ensure_cn_quote(stock_code)
    elif market_type in {"港股", "美股"}:
        quote = await _ensure_foreign_quote(market_type, stock_code)
    else:
        raise MarketDataFreshnessError(f"不支持的市场类型: {market_type}")

    logger.info(
        "✅ [行情新鲜度] %s %s 已刷新并校验最新行情: date=%s source=%s price=%s",
        quote["market"], quote["code"], quote["trade_date"], quote.get("source"), quote.get("price"),
    )
    return quote
