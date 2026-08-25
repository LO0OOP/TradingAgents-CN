"""统一行情查询接口。

- GET /api/quotes/market     获取/刷新全市场 A 股行情（写入 market_quotes 缓存）
- GET /api/quotes?codes=...  按代码列表获取单只/多只 A 股行情（按配置的数据源优先级）
"""
import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.market_quote_service import get_market_quote_service
from app.services.quotes_ingestion_service import QuotesIngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("/market")
async def get_market_quotes(current_user: dict = Depends(get_current_user)):
    """获取/刷新全市场 A 股实时行情（全量，写入市场行情缓存）。"""
    try:
        result = await QuotesIngestionService().refresh_now()
        return ok(data=result)
    except Exception as exc:
        logger.error("全市场行情刷新失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"全市场行情刷新失败: {str(exc)}") from exc


@router.get("")
async def get_quotes_by_codes(
    codes: str = Query(..., description="股票代码列表，逗号分隔，如 000001,600000,300750"),
    current_user: dict = Depends(get_current_user),
):
    """获取单只/多只 A 股实时行情（按配置的数据源优先级依次请求）。"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="codes 参数不能为空")
    if len(code_list) > 500:
        raise HTTPException(status_code=400, detail="单次最多查询 500 只股票")

    try:
        service = get_market_quote_service()
        instruments = [{"code": c, "market": "CN"} for c in code_list]
        result = await service.get_quotes(instruments, force_refresh=True)
        return ok(data=result)
    except Exception as exc:
        logger.error("单只/多只行情查询失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"单只/多只行情查询失败: {str(exc)}") from exc