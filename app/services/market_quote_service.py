"""Unified market quote access for analysis, favorites, and paper trading."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.database import get_mongo_db
from app.services.data_sources.manager import DataSourceManager
from app.services.quotes_ingestion_service import QuotesIngestionService

logger = logging.getLogger(__name__)


class MarketQuoteService:
    """Single entry point for quote reads and refreshes across all markets."""

    def __init__(self) -> None:
        self._latest_cn_trade_date: Optional[str] = None
        self._latest_cn_trade_date_at = 0.0
        self._latest_cn_trade_date_signature: Optional[Tuple[Tuple[str, int], ...]] = None
        self._latest_cn_trade_date_lock = asyncio.Lock()
        self._cn_refresh_lock = asyncio.Lock()
        self._cn_refresh_task: Optional[asyncio.Task] = None
        self._foreign_stock_service: Any = None

    def _normalize_market(self, market: Optional[str], code: str) -> str:
        value = str(market or "").strip().upper()
        if value in {"CN", "A股", "A", "ASHARE", "A_SHARES"}:
            return "CN"
        if value in {"HK", "港股"}:
            return "HK"
        if value in {"US", "美股"}:
            return "US"

        text = str(code or "").strip()
        if text.isalpha():
            return "US"
        if text.isdigit() and len(text) in {4, 5}:
            return "HK"
        return "CN"

    @staticmethod
    def _normalize_cn_code(code: str) -> str:
        digits = "".join(character for character in str(code or "") if character.isdigit())
        return digits.zfill(6) if digits else ""

    async def get_cn_source_config_signature(self) -> Tuple[Tuple[str, int], ...]:
        service = QuotesIngestionService()
        return await asyncio.to_thread(service.get_quote_source_config_signature)

    async def get_latest_cn_trade_date(self) -> Optional[str]:
        signature = await self.get_cn_source_config_signature()
        now = time.monotonic()
        if (
            self._latest_cn_trade_date
            and now - self._latest_cn_trade_date_at < 60
            and self._latest_cn_trade_date_signature == signature
        ):
            return self._latest_cn_trade_date

        async with self._latest_cn_trade_date_lock:
            if (
                self._latest_cn_trade_date
                and time.monotonic() - self._latest_cn_trade_date_at < 60
                and self._latest_cn_trade_date_signature == signature
            ):
                return self._latest_cn_trade_date

            value = await asyncio.to_thread(
                lambda: DataSourceManager().find_latest_trade_date_with_fallback()
            )
            text = str(value or "")
            self._latest_cn_trade_date = (
                f"{text[:4]}-{text[4:6]}-{text[6:]}"
                if len(text) == 8 and text.isdigit()
                else text[:10] or None
            )
            self._latest_cn_trade_date_at = time.monotonic()
            self._latest_cn_trade_date_signature = signature
            return self._latest_cn_trade_date

    async def refresh_cn_market(self) -> Dict[str, Any]:
        """Refresh A-share quotes once through the configured source order."""
        async with self._cn_refresh_lock:
            if self._cn_refresh_task is None or self._cn_refresh_task.done():
                self._cn_refresh_task = asyncio.create_task(
                    QuotesIngestionService().refresh_now()
                )
            task = self._cn_refresh_task

        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._cn_refresh_lock:
                    if self._cn_refresh_task is task:
                        self._cn_refresh_task = None

    async def _fetch_cn_quotes_multi(self, codes: List[str]):
        """按代码列表拉取 A 股单只/多只实时行情，写回缓存，返回 (quotes_map, source)。"""
        manager = DataSourceManager()
        quotes_map, source = await asyncio.to_thread(
            manager.get_realtime_quotes_multi_with_fallback, list(codes)
        )
        if not quotes_map:
            return {}, None
        try:
            trade_date = await asyncio.to_thread(
                manager.find_latest_trade_date_with_fallback
            ) or datetime.now().strftime("%Y%m%d")
        except Exception:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            await QuotesIngestionService()._bulk_upsert(quotes_map, trade_date, source)
        except Exception as exc:
            logger.warning("写回单只行情缓存失败（忽略）: %s", exc)
        for code in quotes_map:
            quotes_map[code]["trade_date"] = trade_date
            quotes_map[code]["source"] = source
        return quotes_map, source

    async def get_quotes(
        self,
        instruments: Iterable[Dict[str, Any]],
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Return normalized quotes keyed by ``MARKET:code``.

        A-share requests share one full-market refresh, preventing a watchlist
        from issuing one blocking remote call per stock. Foreign quotes retain
        their configured provider order through ForeignStockService.
        """
        normalized: List[Tuple[str, str]] = []
        for instrument in instruments:
            raw_code = str(instrument.get("code") or instrument.get("symbol") or "").strip()
            if not raw_code:
                continue
            market = self._normalize_market(instrument.get("market"), raw_code)
            code = self._normalize_cn_code(raw_code) if market == "CN" else raw_code
            if code:
                normalized.append((market, code))

        result: Dict[str, Any] = {"quotes": {}, "errors": {}, "refresh": {}}
        cn_codes = sorted({code for market, code in normalized if market == "CN"})
        if cn_codes:
            expected_date = await self.get_latest_cn_trade_date()
            cn_quotes = await self._get_cached_cn_quotes(cn_codes)
            need_fetch = list(cn_codes) if force_refresh else [
                code for code in cn_codes
                if not cn_quotes.get(code)
                or cn_quotes.get(code).get("close") is None
                or (expected_date and self._normalize_trade_date(cn_quotes.get(code).get("trade_date")) != expected_date)
            ]
            if need_fetch:
                fetched, source = await self._fetch_cn_quotes_multi(need_fetch)
                if fetched:
                    result["refresh"]["CN"] = {"source": source, "records_count": len(fetched)}
                    for code in need_fetch:
                        if code in fetched:
                            cn_quotes[code] = {**fetched[code], "source": source}
            for code in cn_codes:
                quote = cn_quotes.get(code)
                key = f"CN:{code}"
                if not quote:
                    result["errors"][key] = "未找到行情缓存"
                    continue
                trade_date = self._normalize_trade_date(quote.get("trade_date"))
                if expected_date and trade_date != expected_date:
                    result["errors"][key] = f"行情日期 {trade_date or '未知'}，最新交易日为 {expected_date}"
                    continue
                if quote.get("close") is None:
                    result["errors"][key] = "行情缺少最新价"
                    continue
                result["quotes"][key] = self._format_cn_quote(code, quote)

        foreign = [(market, code) for market, code in normalized if market in {"HK", "US"}]
        if foreign:
            service = self._get_foreign_stock_service()
            semaphore = asyncio.Semaphore(4)

            async def load_one(market: str, code: str) -> None:
                key = f"{market}:{code}"
                try:
                    async with semaphore:
                        quote = await service.get_quote(market, code, force_refresh=force_refresh)
                    price = quote.get("price") or quote.get("close")
                    if price is None:
                        result["errors"][key] = "行情缺少最新价"
                        return
                    result["quotes"][key] = {
                        "market": market,
                        "code": code,
                        "price": price,
                        "change_percent": quote.get("change_percent") or quote.get("pct_chg"),
                        "volume": quote.get("volume"),
                        "amount": quote.get("amount"),
                        "trade_date": self._normalize_trade_date(
                            quote.get("trade_date") or quote.get("latest_trading_day") or quote.get("timestamp")
                        ),
                        "source": quote.get("source"),
                    }
                except Exception as exc:
                    result["errors"][key] = str(exc)

            await asyncio.gather(*(load_one(market, code) for market, code in foreign))

        return result

    def _get_foreign_stock_service(self) -> Any:
        """Keep foreign quote request deduplication effective across callers."""
        if self._foreign_stock_service is None:
            from app.services.foreign_stock_service import ForeignStockService

            self._foreign_stock_service = ForeignStockService(db=get_mongo_db())
        return self._foreign_stock_service

    async def _get_cached_cn_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        db = get_mongo_db()
        cursor = db["market_quotes"].find(
            {"code": {"$in": codes}},
            {"_id": 0},
        )
        docs = await cursor.to_list(length=None)
        return {str(doc.get("code") or doc.get("symbol")).zfill(6): doc for doc in docs}

    @staticmethod
    def _normalize_trade_date(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text[:10] or None

    def _format_cn_quote(self, code: str, quote: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "market": "CN",
            "code": code,
            "price": quote.get("close"),
            "change_percent": quote.get("pct_chg"),
            "volume": quote.get("volume"),
            "amount": quote.get("amount"),
            "trade_date": self._normalize_trade_date(quote.get("trade_date")),
            "source": quote.get("source"),
        }


_market_quote_service: Optional[MarketQuoteService] = None


def get_market_quote_service() -> MarketQuoteService:
    global _market_quote_service
    if _market_quote_service is None:
        _market_quote_service = MarketQuoteService()
    return _market_quote_service
