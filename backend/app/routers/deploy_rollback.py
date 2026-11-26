"""策略回滚与覆盖范围 API：回滚预览/确认、当前与历史覆盖、分级视角覆盖。

必须比通用 /{module}/{entry_id} 资源路由更早注册，
否则 /api/classify_tag/coverage 会被当作 entry_id 解析。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import LevelAdjustPayload, RollbackConfirmPayload, RollbackPreviewPayload
from app.services import service_for
from app.services.classify_tag import ClassifyTagService
from app.services.deploy_policy import DeployPolicyService

router = APIRouter(prefix="/api", tags=["策略回滚"])


def _deploy_service() -> DeployPolicyService:
    service = service_for("deploy_policy")
    if not isinstance(service, DeployPolicyService):  # pragma: no cover - 注册表恒定
        raise HTTPException(status_code=500, detail="策略下发服务未注册")
    return service


def _classify_service() -> ClassifyTagService:
    service = service_for("classify_tag")
    if not isinstance(service, ClassifyTagService):  # pragma: no cover - 注册表恒定
        raise HTTPException(status_code=500, detail="分级分类服务未注册")
    return service


@router.post("/deploy_policy/{entry_id}/rollback/preview")
def rollback_preview(entry_id: int, payload: RollbackPreviewPayload) -> dict[str, Any]:
    """回滚预览：比较当前与目标版本的资源覆盖，生成回滚差异单。"""
    ticket, message = _deploy_service().rollback_preview(entry_id, payload.目标版本)
    return {"ok": ticket is not None, "message": message, "ticket": ticket}


@router.post("/deploy_policy/{entry_id}/rollback/confirm")
def rollback_confirm(entry_id: int, payload: RollbackConfirmPayload) -> dict[str, Any]:
    """回滚确认：执行差异单并按节点返回 恢复/未动/未能恢复 回执，可重试。"""
    ticket, message = _deploy_service().rollback_confirm(entry_id, payload.ticket_id)
    return {"ok": ticket is not None, "message": message, "ticket": ticket}


@router.get("/deploy_policy/{entry_id}/rollback/tickets")
def rollback_tickets(entry_id: int) -> dict[str, Any]:
    """该策略分发的全部回滚差异单（含执行回执）。"""
    tickets = _deploy_service().rollback_tickets(entry_id)
    return {"items": tickets, "total": len(tickets)}


@router.get("/deploy_policy/{entry_id}/rollback/tickets/{ticket_id}")
def rollback_ticket(entry_id: int, ticket_id: int) -> dict[str, Any]:
    ticket = _deploy_service().rollback_ticket(entry_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"回滚差异单 {ticket_id} 不存在")
    return ticket


@router.get("/deploy_policy/{entry_id}/coverage")
def current_coverage(entry_id: int) -> dict[str, Any]:
    """当前覆盖：节点此刻真实可见的资源。"""
    items = _deploy_service().current_coverage(entry_id)
    return {"items": items, "total": len(items)}


@router.get("/deploy_policy/{entry_id}/coverage/history")
def coverage_history(entry_id: int) -> dict[str, Any]:
    """历史下发的覆盖记录：每次版本下发的 节点×资源 快照。"""
    items = _deploy_service().coverage_history(entry_id)
    return {"items": items, "total": len(items)}


@router.get("/classify_tag/coverage")
def classify_coverage() -> dict[str, Any]:
    """分级分类视角的当前覆盖：每个数据资源当前在哪些节点真实可见。"""
    items = _classify_service().classify_coverage()
    return {"items": items, "total": len(items)}


@router.post("/classify_tag/{tag_id}/level")
def adjust_level(tag_id: int, payload: LevelAdjustPayload) -> dict[str, Any]:
    """调整数据资源的安全等级。"""
    entry, message = _classify_service().adjust_level(tag_id, payload.安全等级)
    return {"ok": entry is not None, "message": message, "entry": entry}
