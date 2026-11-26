"""策略下发领域服务：通用骨架之外，承载版本覆盖比较、回滚预览与确认执行。

回滚语义：只恢复目标版本曾经覆盖、当前已失去可见性的资源，不摘除当前已有覆盖。
预览生成回滚差异单；确认执行时按当前分级重新校验——目标版本的覆盖与当前分级
冲突时，该资源已失去的可见性不能通过回滚恢复。执行回执按节点区分
恢复/未动/未能恢复，重复提交能识别此前已处理的部分。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

# 安全等级高低次序：等级越高越敏感，可见性约束越强
LEVEL_RANK = {"未分级": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}

# 差异单变更类型
CHANGE_RESTORE = "恢复可见"
CHANGE_KEEP = "保持不变"
CHANGE_CURRENT_ONLY = "仅当前版本覆盖"

# 执行结果
RESULT_RESTORED = "已恢复"
RESULT_UNTOUCHED = "未动"
RESULT_BLOCKED = "未能恢复"

# 差异单状态
TICKET_PENDING = "待确认"
TICKET_DONE = "已执行"
TICKET_PARTIAL = "部分恢复"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def classify_level_of(resource: str) -> str:
    """资源当前的安全等级（来自分级分类模块）；未打标视为未分级。"""
    for tag in store.rows("classify_tag"):
        if str(tag.get("数据资源", "")) == resource:
            return str(tag.get("安全等级", "未分级"))
    return "未分级"


def level_conflict(resource: str, distributed_level: str) -> tuple[bool, str]:
    """目标版本覆盖与当前分级是否冲突：当前等级高于下发时等级即冲突。"""
    current = classify_level_of(resource)
    if LEVEL_RANK.get(current, 0) > LEVEL_RANK.get(distributed_level, 0):
        return True, (
            f"分级冲突：当前安全等级{current}高于目标版本下发时"
            f"{distributed_level}，已失去的可见性不能通过回滚恢复"
        )
    return False, ""


class DeployPolicyService(BaseModuleService):
    MODULE = "deploy_policy"
    ENTITY = "策略分发"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["分发编号", "策略内容", "目标节点", "当前版本", "下发状态", "生效时间", "冲突策略", "回滚版本", "操作时间"]
    REQUIRED_FIELDS = ["分发编号", "策略内容", "目标节点"]
    STATUS_ORDER = ["待下发", "已生效", "冲突待处理", "已回滚"]
    ACTION_RULES = {"下发策略": "已生效", "标记冲突": "冲突待处理", "回滚策略": "已回滚"}
    NEGATIVE_ACTIONS = ["回滚策略"]

    # ——————————— 覆盖记录查询 ———————————

    def coverage_history(self, entry_id: int) -> list[dict[str, Any]]:
        """历史下发的覆盖记录：每次版本下发的 节点×资源 快照，回滚后仍可查看。"""
        return [
            row for row in store.aux("deploy_version_coverage")
            if int(row.get("policy_id", 0)) == entry_id
        ]

    def current_coverage(self, entry_id: int) -> list[dict[str, Any]]:
        """当前覆盖：节点此刻真实可见的资源，只反映真正执行过的下发/回滚。"""
        return [
            row for row in store.aux("deploy_current_coverage")
            if int(row.get("policy_id", 0)) == entry_id
        ]

    def _version_map(self, entry_id: int, version: str) -> dict[str, set[str]]:
        """指定版本下发时的覆盖：节点 -> 资源集合。"""
        result: dict[str, set[str]] = {}
        for row in self.coverage_history(entry_id):
            if str(row.get("版本")) == version:
                result.setdefault(str(row["节点"]), set()).add(str(row["资源"]))
        return result

    def _current_map(self, entry_id: int) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for row in self.current_coverage(entry_id):
            if row.get("可见"):
                result.setdefault(str(row["节点"]), set()).add(str(row["资源"]))
        return result

    def _distributed_level(self, entry_id: int, version: str, node: str, resource: str) -> str:
        for row in self.coverage_history(entry_id):
            if (str(row.get("版本")) == version and str(row.get("节点")) == node
                    and str(row.get("资源")) == resource):
                return str(row.get("下发时安全等级", "未分级"))
        return "未分级"

    # ——————————— 回滚预览：比较当前与目标版本，生成回滚差异单 ———————————

    def rollback_preview(
        self, entry_id: int, target_version: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        versions = sorted({str(row.get("版本")) for row in self.coverage_history(entry_id)})
        if not versions:
            return None, f"{self.ENTITY} {entry_id} 没有版本覆盖记录，无法生成回滚差异单"
        current_version = str(entry.get("当前版本") or versions[-1])
        target = (target_version or "").strip() or str(entry.get("回滚版本") or "").strip()
        if target in ("", "无", "等待人工决策"):
            earlier = [v for v in versions if v != current_version]
            if not earlier:
                return None, f"{self.ENTITY} {entry_id} 没有可回滚的历史版本"
            target = earlier[-1]
        if target not in versions:
            return None, f"目标版本 {target} 不在已下发版本 {versions} 中"
        if target == current_version:
            return None, f"目标版本 {target} 与当前版本一致，无需回滚"

        target_map = self._version_map(entry_id, target)
        current_map = self._current_map(entry_id)
        items: list[dict[str, Any]] = []
        for node in sorted(set(target_map) | set(current_map)):
            resources = sorted(target_map.get(node, set()) | current_map.get(node, set()))
            for resource in resources:
                in_target = resource in target_map.get(node, set())
                in_current = resource in current_map.get(node, set())
                item: dict[str, Any] = {
                    "节点": node,
                    "资源": resource,
                    "下发时安全等级": self._distributed_level(entry_id, target, node, resource) if in_target else "",
                    "当前安全等级": classify_level_of(resource),
                    "执行结果": None,
                }
                if in_target and not in_current:
                    conflict, reason = level_conflict(resource, str(item["下发时安全等级"]))
                    item["变更"] = CHANGE_RESTORE
                    item["预览结论"] = "分级冲突" if conflict else "可恢复"
                    item["说明"] = reason or "目标版本覆盖而当前未覆盖，确认后恢复可见性"
                elif in_target and in_current:
                    item["变更"] = CHANGE_KEEP
                    item["预览结论"] = "无需处理"
                    item["说明"] = "当前覆盖与目标版本一致"
                else:
                    item["变更"] = CHANGE_CURRENT_ONLY
                    item["预览结论"] = "不摘除"
                    item["说明"] = "回滚仅恢复目标版本可见性，不摘除当前已有覆盖"
                items.append(item)

        tickets = store.aux("rollback_tickets")
        ticket = {
            "id": max((int(t.get("id", 0)) for t in tickets), default=0) + 1,
            "policy_id": entry_id,
            "分发编号": entry.get("分发编号"),
            "当前版本": current_version,
            "目标版本": target,
            "状态": TICKET_PENDING,
            "items": items,
            "预览时间": _now(),
            "执行时间": None,
            "执行次数": 0,
            "回执列表": [],
        }
        tickets.append(ticket)
        return ticket, f"已生成回滚差异单 #{ticket['id']}：{current_version} → {target}"

    # ——————————— 回滚确认：按当前分级重新校验后执行，可重试 ———————————

    def rollback_confirm(
        self, entry_id: int, ticket_id: int
    ) -> tuple[dict[str, Any] | None, str]:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        ticket = self.rollback_ticket(entry_id, ticket_id)
        if ticket is None:
            return None, f"回滚差异单 {ticket_id} 不存在或不属于{self.ENTITY} {entry_id}"

        node_results: dict[str, dict[str, list[dict[str, str]]]] = {}

        def bucket(node: str) -> dict[str, list[dict[str, str]]]:
            return node_results.setdefault(node, {RESULT_RESTORED: [], RESULT_UNTOUCHED: [], RESULT_BLOCKED: []})

        for item in ticket["items"]:
            node = str(item["节点"])
            resource = str(item["资源"])
            if item["变更"] != CHANGE_RESTORE:
                # 保持不变 / 仅当前版本覆盖：执行不改变它们
                item["执行结果"] = item["执行结果"] or RESULT_UNTOUCHED
                bucket(node)[RESULT_UNTOUCHED].append({"资源": resource, "原因": str(item["说明"])})
                continue
            if item["执行结果"] == RESULT_RESTORED:
                # 重试/交错提交：此前已处理的部分直接识别出来，不重复执行
                bucket(node)[RESULT_UNTOUCHED].append({"资源": resource, "原因": "此前已处理，本次跳过"})
                continue
            item["当前安全等级"] = classify_level_of(resource)
            conflict, reason = level_conflict(resource, str(item["下发时安全等级"]))
            if conflict:
                item["执行结果"] = RESULT_BLOCKED
                item["说明"] = reason
                bucket(node)[RESULT_BLOCKED].append({"资源": resource, "原因": reason})
            elif resource in self._current_map(entry_id).get(node, set()):
                # 已被其它差异单或操作恢复过：目标状态已达成，本次不再重复执行
                item["执行结果"] = RESULT_RESTORED
                item["说明"] = "当前已覆盖，无需重复恢复"
                bucket(node)[RESULT_UNTOUCHED].append({"资源": resource, "原因": "当前已覆盖，无需重复恢复"})
            else:
                self._restore_coverage(entry_id, node, resource, str(ticket["目标版本"]))
                item["执行结果"] = RESULT_RESTORED
                item["说明"] = "已恢复目标版本可见性"
                bucket(node)[RESULT_RESTORED].append({"资源": resource, "原因": ""})

        blocked = any(
            item["变更"] == CHANGE_RESTORE and item["执行结果"] == RESULT_BLOCKED
            for item in ticket["items"]
        )
        ticket["执行次数"] = int(ticket.get("执行次数", 0)) + 1
        ticket["执行时间"] = _now()
        ticket["状态"] = TICKET_PARTIAL if blocked else TICKET_DONE
        ticket["回执列表"].append({
            "序号": ticket["执行次数"],
            "时间": ticket["执行时间"],
            "结论": ticket["状态"],
            "节点结果": [
                {"节点": node, **results} for node, results in sorted(node_results.items())
            ],
        })

        # 策略分发记录本身同步到已回滚，当前版本指向目标版本
        entry["status"] = "已回滚"
        entry["pending"] = False
        entry["abnormal"] = blocked
        entry["当前版本"] = ticket["目标版本"]
        entry["下发状态"] = f"已回滚至{ticket['目标版本']}" + ("（部分资源未能恢复）" if blocked else "")
        entry["操作时间"] = _now()
        return ticket, f"回滚差异单 #{ticket['id']} 已执行：{ticket['状态']}"

    def _restore_coverage(self, entry_id: int, node: str, resource: str, version: str) -> None:
        rows = store.aux("deploy_current_coverage")
        for row in rows:
            if (int(row.get("policy_id", 0)) == entry_id and str(row.get("节点")) == node
                    and str(row.get("资源")) == resource):
                row["可见"] = True
                row["来源版本"] = version
                row["更新时间"] = _now()
                return
        rows.append({
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "policy_id": entry_id,
            "节点": node,
            "资源": resource,
            "可见": True,
            "来源版本": version,
            "更新时间": _now(),
        })

    # ——————————— 差异单查询 ———————————

    def rollback_tickets(self, entry_id: int) -> list[dict[str, Any]]:
        return [
            ticket for ticket in store.aux("rollback_tickets")
            if int(ticket.get("policy_id", 0)) == entry_id
        ]

    def rollback_ticket(self, entry_id: int, ticket_id: int) -> dict[str, Any] | None:
        for ticket in self.rollback_tickets(entry_id):
            if int(ticket.get("id", 0)) == ticket_id:
                return ticket
        return None
