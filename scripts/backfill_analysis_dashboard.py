# -*- coding: utf-8 -*-
"""一次性回填脚本：统一 research_depth、回填 analysis_price、建索引。

用法：
    python scripts/backfill_analysis_dashboard.py --dry-run   # 只统计，不写入
    python scripts/backfill_analysis_dashboard.py             # 实际写入
"""

import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # 确保 .env 与项目配置从项目根加载

import pymongo  # noqa: E402
MONGO_URI = os.environ.get("MONGO_URI") or "mongodb://admin:tradingagents123@localhost:27017/tradingagentscn?authSource=admin"
MONGO_DB = os.environ.get("MONGO_DB") or "tradingagentscn"
from app.utils.analysis_metrics import normalize_analysis_price, normalize_research_depth, extract_analysis_price  # noqa: E402

# 分析时价格应落在当日 [low, high] 区间内，允许 0.2% 容差以吸收精度误差
PRICE_TOLERANCE = 0.002


def _quote_by_date(quotes, code, date):
    return quotes.find_one(
        {"code": str(code), "trade_date": str(date)},
        {"_id": 0, "open": 1, "high": 1, "low": 1, "close": 1},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    args = parser.parse_args()

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    ar = db["analysis_reports"]
    quotes = db["stock_daily_quotes"]

    # 打印类型样本，便于排查日期字段匹配问题
    sample_report = ar.find_one({}, {"analysis_date": 1, "stock_symbol": 1})
    sample_quote = quotes.find_one({}, {"trade_date": 1, "code": 1})
    print("analysis_reports 样本 analysis_date 类型:",
          type(sample_report.get("analysis_date")).__name__ if sample_report else None,
          repr(sample_report.get("analysis_date")) if sample_report else None)
    print("stock_daily_quotes 样本 trade_date 类型:",
          type(sample_quote.get("trade_date")).__name__ if sample_quote else None,
          repr(sample_quote.get("trade_date")) if sample_quote else None)

    docs = list(ar.find({}))
    stats = {
        "total": 0,
        "depth_changed": 0,
        "depth_noop": 0,
        "price_from_report": 0,
        "price_from_close": 0,
        "price_crosscheck_failed": 0,
        "price_none": 0,
        "price_already_set": 0,
        "updated": 0,
    }
    depth_counter = {}

    for d in docs:
        stats["total"] += 1
        updates = {}

        # 1) research_depth 归一化
        old_depth = d.get("research_depth")
        new_depth = normalize_research_depth(old_depth)
        depth_counter[str(old_depth)] = depth_counter.get(str(old_depth), 0) + 1
        if new_depth != old_depth:
            updates["research_depth"] = new_depth
            stats["depth_changed"] += 1
        else:
            stats["depth_noop"] += 1

        # 2) analysis_price 归一化/回填
        # 历史数据中该字段可能不存在、为 None，或被写成字符串；这里统一为 float 或 None。
        raw_price = d.get("analysis_price")
        normalized_price = normalize_analysis_price(raw_price)

        if normalized_price is None:
            price = extract_analysis_price(d.get("reports"))
            analysis_date = d.get("analysis_date")
            code = d.get("stock_symbol")
            qd = _quote_by_date(quotes, code, analysis_date) if code and analysis_date else None

            if qd:
                close = qd.get("close")
                low = qd.get("low")
                high = qd.get("high")

                if price is not None and close is not None and low is not None and high is not None:
                    lo = float(low) * (1 - PRICE_TOLERANCE)
                    hi = float(high) * (1 + PRICE_TOLERANCE)
                    if not (lo <= price <= hi):
                        stats["price_crosscheck_failed"] += 1
                        price = float(close)

                if price is None and close is not None:
                    price = float(close)
                    stats["price_from_close"] += 1
                elif price is not None:
                    stats["price_from_report"] += 1
                else:
                    stats["price_none"] += 1
            else:
                # 无日K数据（港股/美股等）
                if price is not None:
                    stats["price_from_report"] += 1
                else:
                    stats["price_none"] += 1

            updates["analysis_price"] = round(float(price), 4) if price is not None else None
        else:
            stats["price_already_set"] += 1
            rounded = round(normalized_price, 4)
            # 字符串价格转回 float；已有 float/int 且精度未变化时不再写库。
            if not isinstance(raw_price, (int, float)) or rounded != raw_price:
                updates["analysis_price"] = rounded

        if updates:
            stats["updated"] += 1
            if not args.dry_run:
                ar.update_one({"_id": d["_id"]}, {"$set": updates})

    # 3) 建索引（幂等）
    if not args.dry_run:
        quotes.create_index([("code", 1), ("trade_date", 1)])
        ar.create_index([("stock_symbol", 1), ("analysis_date", 1)])
        ar.create_index([("research_depth", 1), ("analysis_date", 1)])
        print("索引已创建（如不存在）")

    print("=== 统计 ===")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print("=== research_depth 原始取值分布 ===")
    for k, v in sorted(depth_counter.items(), key=lambda x: str(x[0])):
        print(f"  {k!r}: {v}")

    if args.dry_run:
        print("DRY-RUN：未写入任何数据")


if __name__ == "__main__":
    main()
