"""策略下发回滚预览/确认 与 分级分类覆盖联动测试。

场景主线：两个节点预览上一版 → 只提高其中一个节点所用资源的分级 →
交错提交回滚 → 比较预览、执行回执和两个节点的实际覆盖 →
重试后仍能识别已处理部分。

运行：cd backend && python3 -m pytest tests/test_rollback.py -v
"""
from __future__ import annotations

import pytest

from app.services import ClassifyTagService, DeployPolicyService
from app.store import store

POLICY_ID = 2  # DEPL-0002：含 v1.2（上一版）/ v2.0（当前版）两版覆盖记录
NODE_A = "网关节点A"
NODE_B = "网关节点B"


@pytest.fixture(autouse=True)
def fresh_store():
    """每个用例前后都重置内存仓库，用例之间、以及与 test_services.py 之间互不影响。"""
    store.reset()
    yield
    store.reset()


def _deploy() -> DeployPolicyService:
    return DeployPolicyService()


def _classify() -> ClassifyTagService:
    return ClassifyTagService()


def _tag_id(resource: str) -> int:
    for tag in store.rows("classify_tag"):
        if tag["数据资源"] == resource:
            return int(tag["id"])
    raise AssertionError(f"缺少 {resource} 的分级标签种子数据")


def _visible_pairs(entry_id: int = POLICY_ID) -> set[tuple[str, str]]:
    return {
        (str(row["节点"]), str(row["资源"]))
        for row in _deploy().current_coverage(entry_id)
        if row["可见"]
    }


def _receipt_node(ticket: dict, receipt_index: int, node: str) -> dict:
    receipt = ticket["回执列表"][receipt_index]
    return next(n for n in receipt["节点结果"] if n["节点"] == node)


# ================================================================
# 1. 回滚预览：服务端比较当前与目标版本，生成回滚差异单
# ================================================================

class TestRollbackPreview:
    def test_preview_generates_diff_ticket_per_node(self):
        ticket, message = _deploy().rollback_preview(POLICY_ID)
        assert ticket is not None, message
        assert ticket["状态"] == "待确认"
        assert ticket["当前版本"] == "v2.0"
        assert ticket["目标版本"] == "v1.2"  # 默认取策略记录上的回滚版本
        assert ticket["执行次数"] == 0

        items = {(i["节点"], i["资源"]): i for i in ticket["items"]}
        # 两个节点各自失去的资源进入恢复项
        assert items[(NODE_A, "订单汇总接口")]["变更"] == "恢复可见"
        assert items[(NODE_B, "风控评分接口")]["变更"] == "恢复可见"
        # 两版都覆盖的保持不变
        assert items[(NODE_A, "用户画像查询接口")]["变更"] == "保持不变"
        assert items[(NODE_B, "用户画像查询接口")]["变更"] == "保持不变"
        # 仅当前版本覆盖的不摘除
        assert items[(NODE_A, "实时库存接口")]["变更"] == "仅当前版本覆盖"
        assert items[(NODE_B, "实时库存接口")]["变更"] == "仅当前版本覆盖"
        # 预览时无分级冲突，恢复项均可恢复
        restores = [i for i in ticket["items"] if i["变更"] == "恢复可见"]
        assert all(i["预览结论"] == "可恢复" for i in restores)
        assert all(i["执行结果"] is None for i in ticket["items"])

    def test_preview_does_not_change_current_coverage(self):
        before = _visible_pairs()
        ticket, _ = _deploy().rollback_preview(POLICY_ID)
        assert ticket is not None
        assert _visible_pairs() == before
        # 分级视角的当前覆盖也不因预览改变
        coverage = {c["数据资源"]: c["覆盖节点"] for c in _classify().classify_coverage()}
        assert coverage["订单汇总接口"] == []
        assert coverage["风控评分接口"] == []

    def test_preview_marks_conflict_when_level_already_raised(self):
        _classify().adjust_level(_tag_id("订单汇总接口"), "L4")
        ticket, _ = _deploy().rollback_preview(POLICY_ID)
        assert ticket is not None
        item = next(i for i in ticket["items"] if i["资源"] == "订单汇总接口")
        assert item["预览结论"] == "分级冲突"
        assert item["当前安全等级"] == "L4"
        assert item["下发时安全等级"] == "L2"

    def test_preview_without_version_records(self):
        ticket, message = _deploy().rollback_preview(1)
        assert ticket is None
        assert "没有版本覆盖记录" in message

    def test_preview_unknown_target_version(self):
        ticket, message = _deploy().rollback_preview(POLICY_ID, "v9.9")
        assert ticket is None
        assert "不在已下发版本" in message

    def test_preview_same_as_current_version(self):
        ticket, message = _deploy().rollback_preview(POLICY_ID, "v2.0")
        assert ticket is None
        assert "无需回滚" in message

    def test_preview_missing_policy(self):
        ticket, message = _deploy().rollback_preview(9999)
        assert ticket is None
        assert "不存在" in message


# ================================================================
# 2. 主场景：两节点预览 → 提高单节点资源分级 → 交错提交回滚
# ================================================================

class TestInterleavedRollbackScenario:
    def test_preview_raise_level_interleaved_confirm_and_retry(self):
        deploy, classify = _deploy(), _classify()

        # ① 两个节点预览上一版 v1.2，生成差异单 T1
        t1, message = deploy.rollback_preview(POLICY_ID)
        assert t1 is not None, message
        assert t1["状态"] == "待确认"

        # ② 预览后只提高节点A所用资源的分级（订单汇总接口 L2 → L4）
        entry, message = classify.adjust_level(_tag_id("订单汇总接口"), "L4")
        assert entry is not None, message
        assert entry["安全等级"] == "L4"

        # ③ 交错提交：确认前先再预览一单 T2（T2 已能看到分级冲突）
        t2, message = deploy.rollback_preview(POLICY_ID)
        assert t2 is not None, message
        t2_item = next(i for i in t2["items"] if i["资源"] == "订单汇总接口")
        assert t2_item["预览结论"] == "分级冲突"

        # ④ 确认 T1：执行时按当前分级重新校验，预览时的"可恢复"被翻成"未能恢复"
        t1, message = deploy.rollback_confirm(POLICY_ID, t1["id"])
        assert t1 is not None, message
        assert t1["状态"] == "部分恢复"
        assert t1["执行次数"] == 1

        node_a = _receipt_node(t1, -1, NODE_A)
        node_b = _receipt_node(t1, -1, NODE_B)
        assert [r["资源"] for r in node_a["未能恢复"]] == ["订单汇总接口"]
        assert "分级冲突" in node_a["未能恢复"][0]["原因"]
        assert [r["资源"] for r in node_b["已恢复"]] == ["风控评分接口"]
        # 保持不变与仅当前版本覆盖的资源都归入未动
        assert {r["资源"] for r in node_a["未动"]} == {"用户画像查询接口", "实时库存接口"}
        assert {r["资源"] for r in node_b["未动"]} == {"用户画像查询接口", "实时库存接口"}

        # 差异单条目结果：恢复/未动/未能恢复 按节点可区分
        results = {(i["节点"], i["资源"]): i["执行结果"] for i in t1["items"]}
        assert results[(NODE_A, "订单汇总接口")] == "未能恢复"
        assert results[(NODE_B, "风控评分接口")] == "已恢复"
        assert results[(NODE_A, "用户画像查询接口")] == "未动"
        assert results[(NODE_B, "实时库存接口")] == "未动"

        # ⑤ 实际覆盖：节点B恢复了风控评分，节点A的订单汇总仍未恢复
        visible = _visible_pairs()
        assert (NODE_B, "风控评分接口") in visible
        assert (NODE_A, "订单汇总接口") not in visible
        # 仅当前版本覆盖的资源未被摘除
        assert (NODE_A, "实时库存接口") in visible
        assert (NODE_B, "实时库存接口") in visible

        # ⑥ 分级分类的当前覆盖反映真正执行的回滚
        coverage = {c["数据资源"]: c["覆盖节点"] for c in classify.classify_coverage()}
        assert coverage["风控评分接口"] == [NODE_B]
        assert coverage["订单汇总接口"] == []
        assert coverage["用户画像查询接口"] == [NODE_A, NODE_B]

        # ⑦ 历史下发的覆盖记录仍可查看
        history = deploy.coverage_history(POLICY_ID)
        assert {row["版本"] for row in history} == {"v1.2", "v2.0"}
        assert len(history) == 8

        # 策略记录本身同步为已回滚，当前版本指向目标版本
        policy = deploy.get_entry(POLICY_ID)
        assert policy["status"] == "已回滚"
        assert policy["当前版本"] == "v1.2"
        assert policy["abnormal"] is True  # 存在未能恢复的资源

        # ⑧ 交错确认 T2（预览于执行前）：已覆盖的不重复恢复，冲突的仍不能恢复
        t2, message = deploy.rollback_confirm(POLICY_ID, t2["id"])
        assert t2 is not None, message
        assert t2["状态"] == "部分恢复"
        t2_node_b = _receipt_node(t2, -1, NODE_B)
        t2_node_a = _receipt_node(t2, -1, NODE_A)
        assert t2_node_b["已恢复"] == []  # 风控评分已被 T1 恢复，T2 不再重复执行
        assert {r["资源"] for r in t2_node_b["未动"]} >= {"风控评分接口"}
        assert [r["资源"] for r in t2_node_a["未能恢复"]] == ["订单汇总接口"]
        # 实际覆盖不因 T2 改变
        assert _visible_pairs() == visible

        # ⑨ 重试 T1：已处理部分可识别，未恢复部分按当前分级再次校验
        t1, message = deploy.rollback_confirm(POLICY_ID, t1["id"])
        assert t1 is not None, message
        assert t1["执行次数"] == 2
        assert len(t1["回执列表"]) == 2
        retry_a = _receipt_node(t1, -1, NODE_A)
        retry_b = _receipt_node(t1, -1, NODE_B)
        # 已恢复的风控评分在重试回执中标记为未动（此前已处理）
        assert retry_b["已恢复"] == []
        assert {r["资源"] for r in retry_b["未动"]} >= {"风控评分接口"}
        skipped = next(r for r in retry_b["未动"] if r["资源"] == "风控评分接口")
        assert "此前已处理" in skipped["原因"]
        # 分级仍冲突，订单汇总依旧未能恢复
        assert [r["资源"] for r in retry_a["未能恢复"]] == ["订单汇总接口"]
        # 重试不产生新的覆盖变化
        assert _visible_pairs() == visible

    def test_retry_recovers_after_level_lowered_back(self):
        """分级降回可接受范围后，重试同一差异单可以把未能恢复的资源补回来。"""
        deploy, classify = _deploy(), _classify()
        t1, _ = deploy.rollback_preview(POLICY_ID)
        assert t1 is not None
        classify.adjust_level(_tag_id("订单汇总接口"), "L4")
        t1, _ = deploy.rollback_confirm(POLICY_ID, t1["id"])
        assert t1 is not None and t1["状态"] == "部分恢复"

        classify.adjust_level(_tag_id("订单汇总接口"), "L2")
        t1, _ = deploy.rollback_confirm(POLICY_ID, t1["id"])
        assert t1 is not None
        assert t1["状态"] == "已执行"
        retry_a = _receipt_node(t1, -1, NODE_A)
        assert [r["资源"] for r in retry_a["已恢复"]] == ["订单汇总接口"]
        assert (NODE_A, "订单汇总接口") in _visible_pairs()
        coverage = {c["数据资源"]: c["覆盖节点"] for c in classify.classify_coverage()}
        assert coverage["订单汇总接口"] == [NODE_A]
        # 全部恢复后策略记录不再是异常
        assert deploy.get_entry(POLICY_ID)["abnormal"] is False


# ================================================================
# 3. 确认执行与分级调整的边界
# ================================================================

class TestConfirmAndLevelEdges:
    def test_confirm_unknown_ticket(self):
        ticket, message = _deploy().rollback_confirm(POLICY_ID, 9999)
        assert ticket is None
        assert "不存在" in message

    def test_confirm_ticket_belongs_to_other_policy(self):
        ticket, _ = _deploy().rollback_preview(POLICY_ID)
        assert ticket is not None
        other, message = _deploy().rollback_confirm(3, ticket["id"])
        assert other is None
        assert "不属于" in message

    def test_confirm_missing_policy(self):
        ticket, message = _deploy().rollback_confirm(9999, 1)
        assert ticket is None
        assert "不存在" in message

    def test_full_restore_when_no_conflict(self):
        deploy = _deploy()
        ticket, _ = deploy.rollback_preview(POLICY_ID)
        assert ticket is not None
        ticket, _ = deploy.rollback_confirm(POLICY_ID, ticket["id"])
        assert ticket is not None
        assert ticket["状态"] == "已执行"
        visible = _visible_pairs()
        assert (NODE_A, "订单汇总接口") in visible
        assert (NODE_B, "风控评分接口") in visible
        # 重试完全执行的差异单：所有恢复项都识别为已处理
        ticket, _ = deploy.rollback_confirm(POLICY_ID, ticket["id"])
        assert ticket is not None
        assert ticket["状态"] == "已执行"
        for node_result in ticket["回执列表"][-1]["节点结果"]:
            assert node_result["已恢复"] == []
            assert node_result["未能恢复"] == []

    def test_adjust_level_validation(self):
        entry, message = _classify().adjust_level(_tag_id("订单汇总接口"), "L9")
        assert entry is None
        assert "不在可识别范围" in message
        entry, message = _classify().adjust_level(9999, "L3")
        assert entry is None
        assert "不存在" in message

    def test_adjust_level_confirms_pending_tag(self):
        entry, message = _classify().adjust_level(1, "L2")  # CLAS-0001 原为待分级
        assert entry is not None, message
        assert entry["status"] == "已分级"
        assert entry["安全等级"] == "L2"

    def test_classify_coverage_lists_all_tagged_resources(self):
        coverage = _classify().classify_coverage()
        resources = {row["数据资源"] for row in coverage}
        assert "用户画像查询接口" in resources
        assert "客户签约合同" in resources
        by_resource = {row["数据资源"]: row for row in coverage}
        assert by_resource["用户画像查询接口"]["覆盖节点数"] == 2
        assert by_resource["订单汇总接口"]["覆盖节点数"] == 0

    def test_rollback_tickets_listing(self):
        deploy = _deploy()
        assert deploy.rollback_tickets(POLICY_ID) == []
        t1, _ = deploy.rollback_preview(POLICY_ID)
        t2, _ = deploy.rollback_preview(POLICY_ID)
        assert t1 is not None and t2 is not None
        tickets = deploy.rollback_tickets(POLICY_ID)
        assert [t["id"] for t in tickets] == [t1["id"], t2["id"]]
        assert deploy.rollback_ticket(POLICY_ID, t2["id"])["id"] == t2["id"]
        assert deploy.rollback_ticket(POLICY_ID, 9999) is None
