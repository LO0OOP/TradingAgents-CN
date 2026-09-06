"""定时分析任务组 API"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth_db import get_current_user
from app.services import scheduled_analysis_service as svc

router = APIRouter(prefix="/api/scheduled-analysis", tags=["scheduled-analysis"])


class GroupPayload(BaseModel):
    name: str = "定时分析"
    enabled: bool = True
    weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0=周一 .. 6=周日
    time: str = "09:30"  # HH:MM
    symbols: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    weekdays: Optional[List[int]] = None
    time: Optional[str] = None
    symbols: Optional[List[str]] = None
    parameters: Optional[Dict[str, Any]] = None


@router.get("/groups")
async def list_groups(user: dict = Depends(get_current_user)):
    groups = await svc.list_groups(user.get("id", "admin"))
    return {"success": True, "data": groups}


@router.post("/groups")
async def create_group(payload: GroupPayload, user: dict = Depends(get_current_user)):
    group = await svc.create_group(payload.model_dump(), user.get("id", "admin"))
    return {"success": True, "data": group}


@router.put("/groups/{group_id}")
async def update_group(group_id: str, payload: GroupUpdate, user: dict = Depends(get_current_user)):
    group = await svc.update_group(group_id, payload.model_dump(exclude_none=True))
    if group is None:
        raise HTTPException(status_code=404, detail="任务组不存在")
    return {"success": True, "data": group}


@router.delete("/groups/{group_id}")
async def delete_group(group_id: str, user: dict = Depends(get_current_user)):
    ok = await svc.delete_group(group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务组不存在")
    return {"success": True, "message": "已删除"}


@router.post("/groups/{group_id}/toggle")
async def toggle_group(group_id: str, user: dict = Depends(get_current_user)):
    group = await svc.toggle_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="任务组不存在")
    return {"success": True, "data": group}


@router.post("/groups/{group_id}/run")
async def run_group(group_id: str, user: dict = Depends(get_current_user)):
    result = await svc.run_group_now(group_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务组不存在")
    return {"success": True, "data": result}