"""腾讯财经行情数据源适配器（qt.gtimg.cn）。

- 单只/多只实时行情：GET https://qt.gtimg.cn/q=sh600000,sz000001
- 返回 GBK 编码文本；腾讯不提供一次性全市场快照，get_realtime_quotes 返回 None。
"""
import logging
import re
from typing import Dict, List, Optional

import requests

from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


class TencentAdapter(DataSourceAdapter):
    """腾讯财经 A 股实时行情数据源（可配置，优先级由 datasource_groupings 控制）"""

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://gu.qq.com/",
        })

    @property
    def name(self) -> str:
        return "tencent"

    def _get_default_priority(self) -> int:
        return 80

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _to_secid(code: str) -> str:
        code = str(code or "").zfill(6)
        if code.startswith(("6", "9")):
            return f"sh{code}"
        if code.startswith(("4", "8")):
            return f"bj{code}"
        return f"sz{code}"

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            if value is None or value == "" or value == "-":
                return None
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def get_realtime_quotes_multi(self, codes: List[str]) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
        if not codes:
            return None
        secids = [self._to_secid(c) for c in codes]
        url = "https://qt.gtimg.cn/q=" + ",".join(secids)
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            text = resp.content.decode("gbk", errors="ignore")
        except Exception as exc:
            logger.error("腾讯行情请求失败: %s", exc)
            return None

        result: Dict[str, Dict[str, Optional[float]]] = {}
        pattern = re.compile(r'v_(?:sh|sz|bj)(\d{6})="([^"]*)"')
        for match in pattern.finditer(text):
            code6 = match.group(1)
            fields = match.group(2).split("~")
            if len(fields) < 39:
                continue
            close = self._safe_float(fields[3])
            if close is None:
                continue
            pre_close = self._safe_float(fields[4])
            open_ = self._safe_float(fields[5])
            volume = self._safe_float(fields[6])
            high = self._safe_float(fields[33])
            low = self._safe_float(fields[34])
            amount = None
            amount_volume = None
            if len(fields) > 35 and fields[35]:
                parts = fields[35].split("/")
                if len(parts) >= 3:
                    amount = self._safe_float(parts[2])
                    amount_volume = self._safe_float(parts[1])
            if volume is None:
                volume = amount_volume
            pct_chg = self._safe_float(fields[32])
            turnover_rate = self._safe_float(fields[38]) if len(fields) > 38 else None
            pe_ttm = self._safe_float(fields[39]) if len(fields) > 39 else None
            pb = self._safe_float(fields[46]) if len(fields) > 46 else None
            total_mv = self._safe_float(fields[45]) if len(fields) > 45 else None
            circ_mv = self._safe_float(fields[44]) if len(fields) > 44 else None
            name = fields[1] if len(fields) > 1 else None
            result[code6] = {
                "close": close,
                "pct_chg": pct_chg,
                "amount": amount,
                "volume": volume,
                "open": open_,
                "high": high,
                "low": low,
                "pre_close": pre_close,
                "turnover_rate": turnover_rate,
                "pe": pe_ttm,
                "pe_ttm": pe_ttm,
                "pb": pb,
                "total_mv": total_mv,
                "circ_mv": circ_mv,
                "name": name,
            }

        return result or None

    def get_realtime_quotes(self):
        return None

    def get_stock_list(self):
        return None

    def get_daily_basic(self, trade_date: str):
        return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        return None

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        return None

    def find_latest_trade_date(self):
        return None