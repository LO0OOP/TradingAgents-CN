# -*- coding: utf-8 -*-
"""分析结果看板相关：研究深度归一化、分析时价格解析

供落库、存量回填、看板查询复用，避免各处重复实现。
"""

import re
from typing import Any, Dict, Optional

# 数字等级 -> 中文等级
_NUMERIC_TO_CHINESE = {
    1: "快速",
    2: "基础",
    3: "标准",
    4: "深度",
    5: "全面",
}
_VALID_DEPTHS = frozenset(_NUMERIC_TO_CHINESE.values())


def normalize_research_depth(value: Any) -> str:
    """把数字(1-5)、字符串数字、中文等级统一为标准中文等级。

    历史数据中 research_depth 存在 '4'/'深度' 等混合取值，这里统一口径。
    无法识别时回落到默认的“标准”。
    """
    if value is None or isinstance(value, bool):
        return "标准"

    if isinstance(value, (int, float)):
        return _NUMERIC_TO_CHINESE.get(int(value), "标准")

    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return _NUMERIC_TO_CHINESE.get(int(s), "标准")
        if s in _VALID_DEPTHS:
            return s

    return "标准"


def normalize_analysis_price(value: Any) -> Optional[float]:
    """把历史数据中可能出现的字符串价格统一转为 float。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# 报告文本中的“当前价格”等标签。
# 允许标签后出现 **、空格等格式噪声，再跟中文/英文冒号，价格前允许货币符号。
_PRICE_PATTERN = re.compile(
    r"(?:当前价格|最新价|现价|股价|当前价)"
    r"\s*\**\s*[：:]\s*"
    r"[¥￥$]?\s*"
    r"(\d+(?:\.\d+)?)"
)


def extract_analysis_price(reports: Optional[Dict[str, Any]]) -> Optional[float]:
    """从 reports.market_report 文本解析分析时价格。

    解析失败返回 None，由调用方决定是否用当日收盘价兜底。
    """
    if not reports or not isinstance(reports, dict):
        return None

    text = reports.get("market_report") or ""
    if not isinstance(text, str):
        return None

    m = _PRICE_PATTERN.search(text)
    if not m:
        return None

    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None
