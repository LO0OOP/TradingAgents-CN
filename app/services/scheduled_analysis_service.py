"""定时分析服务

管理定时分析任务组（股票 + 触发时间 + 分析参数），并在触发时间复用批量分析执行。
"""
import asyncio
import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.core.database import get_mongo_db
from app.models.analysis import AnalysisParameters
from app.services.simple_analysis_service import get_simple_analysis_service
from app.services import email_service
from app.utils.timezone import now_tz

logger = logging.getLogger("webapi")

COLLECTION = "scheduled_analysis_groups"


def _now() -> datetime:
    """当前本地时间（naive，与调度器约定一致）"""
    return now_tz().replace(tzinfo=None)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """把 MongoDB 文档转换为前端友好结构"""
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    for field in ("created_at", "updated_at", "last_run_at"):
        v = d.get(field)
        if isinstance(v, datetime):
            d[field] = v.isoformat()
    return d


async def list_groups(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_mongo_db()
    query = {} if not user_id else {"user_id": user_id}
    cursor = db[COLLECTION].find(query).sort("created_at", -1)
    result = []
    async for doc in cursor:
        result.append(_serialize(doc))
    return result


async def get_group(group_id: str) -> Optional[Dict[str, Any]]:
    db = get_mongo_db()
    doc = await db[COLLECTION].find_one({"group_id": group_id})
    return _serialize(doc) if doc else None


async def create_group(data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    db = get_mongo_db()
    now = _now()
    doc = {
        "group_id": str(uuid.uuid4()),
        "name": data.get("name") or "定时分析",
        "enabled": bool(data.get("enabled", True)),
        "weekdays": data.get("weekdays") or [0, 1, 2, 3, 4],
        "time": data.get("time") or "09:30",
        "symbols": data.get("symbols") or [],
        "parameters": data.get("parameters") or {},
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
        "last_run_key": None,
    }
    await db[COLLECTION].insert_one(doc)
    logger.info(f"✅ 创建定时分析任务组: {doc['group_id']} - {doc['name']}")
    return _serialize(doc)


async def update_group(group_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = get_mongo_db()
    update: Dict[str, Any] = {}
    for field in ("name", "weekdays", "time", "symbols", "parameters", "enabled"):
        if field in data and data[field] is not None:
            update[field] = data[field]
    if not update:
        return await get_group(group_id)
    update["updated_at"] = _now()
    await db[COLLECTION].update_one({"group_id": group_id}, {"$set": update})
    return await get_group(group_id)


async def delete_group(group_id: str) -> bool:
    db = get_mongo_db()
    res = await db[COLLECTION].delete_one({"group_id": group_id})
    return res.deleted_count > 0


async def toggle_group(group_id: str) -> Optional[Dict[str, Any]]:
    db = get_mongo_db()
    doc = await db[COLLECTION].find_one({"group_id": group_id})
    if not doc:
        return None
    new_enabled = not bool(doc.get("enabled", True))
    await db[COLLECTION].update_one(
        {"group_id": group_id},
        {"$set": {"enabled": new_enabled, "updated_at": _now()}},
    )
    return await get_group(group_id)


async def _run_group(group: Dict[str, Any]) -> Dict[str, Any]:
    """实际执行一次任务组：复用批量分析"""
    symbols = group.get("symbols") or []
    if not symbols:
        return {"error": "任务组未配置股票"}

    params = group.get("parameters") or {}
    try:
        parameters = AnalysisParameters(**params) if params else AnalysisParameters()
    except Exception:
        logger.warning(f"⚠️ 定时分析参数解析失败，使用默认参数: {group.get('group_id')}")
        parameters = AnalysisParameters()

    svc = get_simple_analysis_service()
    result = await svc.run_batch_analysis(
        user_id=group.get("user_id", "admin"),
        symbols=symbols,
        parameters=parameters,
        title=group.get("name") or "定时分析",
    )
    return result


async def _mark_run(group_id: str) -> None:
    db = get_mongo_db()
    now = _now()
    await db[COLLECTION].update_one(
        {"group_id": group_id},
        {"$set": {"last_run_at": now, "last_run_key": now.strftime("%Y-%m-%d %H:%M")}},
    )


async def _wait_for_completion(task_ids: List[str]) -> List[Dict[str, Any]]:
    """轮询任务完成情况，返回每个任务的结果文档（保持原始顺序）"""
    db = get_mongo_db()
    entries: Dict[str, Dict[str, Any]] = {}
    pending = set(task_ids)
    deadline = asyncio.get_running_loop().time() + 7200  # 最长等待 2 小时
    while pending and asyncio.get_running_loop().time() < deadline:
        for tid in list(pending):
            task_doc = await db.analysis_tasks.find_one({"task_id": tid})
            status = task_doc.get("status") if task_doc else None
            if status in ("completed", "failed", "cancelled"):
                if status == "completed":
                    report_doc = await db.analysis_reports.find_one({"task_id": tid})
                    entries[tid] = report_doc or {"task_id": tid, "status": "failed", "error": "报告未生成"}
                else:
                    entries[tid] = {"task_id": tid, "status": status, "error": (task_doc or {}).get("last_error", "")}
                pending.discard(tid)
        if pending:
            await asyncio.sleep(10)
    for tid in task_ids:
        if tid not in entries:
            entries[tid] = {"task_id": tid, "status": "timeout", "error": "等待完成超时"}
    return [entries[tid] for tid in task_ids]


async def _notify_after_completion(group: Dict[str, Any], task_ids: List[str]) -> None:
    """等待任务完成并发送邮件通知（后台执行）"""
    try:
        entries = await _wait_for_completion(task_ids)
        await email_service.send_report_email(group.get("name") or "定时分析", entries)
    except Exception as e:
        logger.error(f"❌ 定时分析结果邮件通知失败: {e}", exc_info=True)


def _schedule_group_run(group: Dict[str, Any]) -> None:
    """后台执行任务组并在完成后发邮件"""
    group_id = group.get("group_id")

    async def _job():
        try:
            result = await _run_group(group)
            await _mark_run(group_id)
            task_ids = (result or {}).get("task_ids") or []
            if task_ids:
                asyncio.create_task(_notify_after_completion(group, task_ids))
        except Exception as e:
            logger.error(f"❌ 定时分析任务组执行失败 {group_id}: {e}", exc_info=True)

    asyncio.create_task(_job())


async def run_group_now(group_id: str) -> Optional[Dict[str, Any]]:
    """手动立即执行某个任务组（后台执行，完成后发邮件）"""
    group = await get_group(group_id)
    if not group:
        return None
    _schedule_group_run(group)
    return {"started": True, "group_id": group_id}


async def run_due_groups() -> int:
    """调度器每分钟调用一次：执行所有到期任务组"""
    try:
        db = get_mongo_db()
        now = now_tz()
        weekday = now.weekday()
        hm = now.strftime("%H:%M")
        run_key = now.strftime("%Y-%m-%d %H:%M")

        cursor = db[COLLECTION].find({"enabled": True, "weekdays": weekday, "time": hm})
        run_count = 0
        async for doc in cursor:
            if doc.get("last_run_key") == run_key:
                continue  # 本分钟内已触发过，避免重复
            group_id = doc.get("group_id")
            _schedule_group_run(doc)
            run_count += 1
            logger.info(f"⏰ 定时分析任务组已触发: {group_id}")
        return run_count
    except Exception as e:
        logger.error(f"❌ 定时分析调度检查失败: {e}", exc_info=True)
        return 0