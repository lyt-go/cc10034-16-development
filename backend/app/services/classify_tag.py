"""分级分类领域服务：通用骨架之外，承载安全等级调整与分级视角的当前覆盖。

分级视角的当前覆盖从策略下发的真实执行结果推导：只有真正执行过的
下发/回滚会改变节点可见性，预览不产生任何覆盖变化。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

LEVELS = ["未分级", "L1", "L2", "L3", "L4"]


class ClassifyTagService(BaseModuleService):
    MODULE = "classify_tag"
    ENTITY = "分级标签"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["标签编号", "数据资源", "安全等级", "数据类型", "合规要求", "保留期限", "脱敏要求", "标签时间"]
    REQUIRED_FIELDS = ["标签编号", "数据资源", "安全等级"]
    STATUS_ORDER = ["待分级", "已分级", "需重审", "已降级"]
    ACTION_RULES = {"确认分级": "已分级", "标记重审": "需重审", "标记降级": "已降级"}
    NEGATIVE_ACTIONS = []

    def adjust_level(self, tag_id: int, new_level: str) -> tuple[dict[str, Any] | None, str]:
        """调整数据资源的安全等级；提高等级后，回滚不能再恢复已失去的可见性。"""
        entry = self.get_entry(tag_id)
        if entry is None:
            return None, f"{self.ENTITY} {tag_id} 不存在或已归档"
        level = (new_level or "").strip().upper()
        if level not in LEVELS:
            return None, f"安全等级「{new_level}」不在可识别范围：{'、'.join(LEVELS)}"
        old = str(entry.get("安全等级", "未分级"))
        entry["安全等级"] = level
        if entry.get("status") == "待分级":
            entry["status"] = "已分级"
        entry["标签时间"] = date.today().isoformat()
        return entry, f"{entry.get('数据资源')} 安全等级 {old} → {level}"

    def classify_coverage(self) -> list[dict[str, Any]]:
        """分级分类视角的当前覆盖：每个数据资源当前在哪些节点真实可见。"""
        coverage = store.aux("deploy_current_coverage")
        result: list[dict[str, Any]] = []
        for tag in store.rows(self.MODULE):
            resource = str(tag.get("数据资源", ""))
            nodes = sorted({
                str(row.get("节点"))
                for row in coverage
                if str(row.get("资源")) == resource and row.get("可见")
            })
            result.append({
                "id": tag.get("id"),
                "标签编号": tag.get("标签编号"),
                "数据资源": resource,
                "安全等级": tag.get("安全等级"),
                "status": tag.get("status"),
                "覆盖节点": nodes,
                "覆盖节点数": len(nodes),
            })
        return result
