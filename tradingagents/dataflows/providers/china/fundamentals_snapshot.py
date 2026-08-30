from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime

import pandas as pd

from tradingagents.utils.logging_manager import get_logger

logger = get_logger('agents')


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if pd.isna(v):
            return None
        return v
    except Exception:
        return None


def _get_tushare_snapshot(symbol: str) -> Dict[str, Optional[float]]:
    try:
        from .providers.china.tushare import get_tushare_provider
        provider = get_tushare_provider()
        if not getattr(provider, 'connected', False):
            return {}
        # 先取 ts_code
        info = provider.get_stock_info(symbol)
        ts_code = info.get('ts_code') if isinstance(info, dict) else None
        if not ts_code:
            return {}
        # daily_basic 拿 pe/pb/total_mv
        api = provider.api
        if api is None:
            return {}
        db = api.daily_basic(ts_code=ts_code, fields='ts_code,trade_date,pe,pb,total_mv')
        pe = pb = mv = None
        if db is not None and not db.empty:
            db = db.sort_values('trade_date').iloc[-1]
            pe = _safe_float(db.get('pe'))
            pb = _safe_float(db.get('pb'))
            mv = _safe_float(db.get('total_mv'))
        # roe 通过 fina_indicator（若不可用则忽略）
        roe = None
        try:
            fi = api.fina_indicator(ts_code=ts_code, fields='ts_code,end_date,roe')
            if fi is not None and not fi.empty:
                fi = fi.sort_values('end_date').iloc[-1]
                roe = _safe_float(fi.get('roe'))
        except Exception:
            pass
        return {
            'pe': pe,
            'pb': pb,
            'market_cap': mv,  # 单位：万元
            'roe': roe,
        }
    except Exception as e:
        logger.debug(f"[fund_snapshot] tushare snapshot failed: {e}")
        return {}


def _get_akshare_financial(symbol: str) -> Dict[str, Optional[float]]:
    """用 AKShare（新浪财务指标 + 财报摘要）获取最新财务快照，不依赖 Tushare。"""
    try:
        import akshare as ak

        roe = debt_ratio = bps = eps = None
        try:
            ind = ak.stock_financial_analysis_indicator(
                symbol=symbol, start_year=str(datetime.now().year - 2)
            )
            if ind is not None and not ind.empty:
                ind = ind.sort_values("日期").iloc[-1]
                roe = _safe_float(ind.get("净资产收益率(%)"))
                debt_ratio = _safe_float(ind.get("资产负债率(%)"))
                bps = _safe_float(ind.get("每股净资产_调整后(元)"))
                eps = _safe_float(ind.get("每股收益_调整后(元)"))
        except Exception as e:
            logger.debug(f"[fund_snapshot] akshare indicator failed: {e}")

        revenue = None
        try:
            absdf = ak.stock_financial_abstract(symbol=symbol)
            if absdf is not None and not absdf.empty:
                latest_col = absdf.columns[2]
                for name in ("营业总收入", "营业收入"):
                    row = absdf[absdf["指标"] == name]
                    if not row.empty:
                        revenue = _safe_float(row.iloc[0][latest_col])
                        if revenue is not None:
                            break
        except Exception as e:
            logger.debug(f"[fund_snapshot] akshare abstract failed: {e}")

        return {
            "roe": roe,
            "debt_to_assets": debt_ratio,
            "bps": bps,
            "eps": eps,
            "revenue": revenue,
        }
    except Exception as e:
        logger.debug(f"[fund_snapshot] akshare financial failed: {e}")
        return {}

def get_cn_fund_snapshot(symbol: str) -> Dict[str, Optional[float]]:
    """
    获取A股基础基本面快照（pe/pb/roe/market_cap）。
    优先Tushare，失败则返回空字典（后续可扩展AKShare/东方财富等）。
    """
    snap = _get_tushare_snapshot(symbol)
    if snap:
        return snap
    return _get_akshare_financial(symbol)

