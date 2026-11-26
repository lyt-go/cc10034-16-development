"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None


class RollbackPreviewPayload(BaseModel):
    """回滚预览入参：缺省时取策略记录上的回滚版本。"""

    目标版本: str | None = None


class RollbackConfirmPayload(BaseModel):
    """回滚确认入参：执行指定预览生成的回滚差异单，可重复提交。"""

    ticket_id: int


class LevelAdjustPayload(BaseModel):
    """分级标签安全等级调整入参。"""

    安全等级: str
