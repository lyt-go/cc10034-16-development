"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_CURRENT_COVERAGE, SEED_ROWS, SEED_VERSION_COVERAGE


class Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """重置全部数据：模块表回到种子状态，领域附属表一并重建。"""
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 领域附属表：不参与模块清单/概览统计，只服务特定领域逻辑。
        self._aux: dict[str, list[dict[str, Any]]] = {
            # 历史下发的覆盖记录（版本×节点×资源），回滚后仍可查看
            "deploy_version_coverage": [dict(row) for row in SEED_VERSION_COVERAGE],
            # 节点当前真实可见的资源覆盖，只被真正执行的下发/回滚改变
            "deploy_current_coverage": [dict(row) for row in SEED_CURRENT_COVERAGE],
            # 回滚差异单（预览生成）及其执行回执
            "rollback_tickets": [],
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def aux(self, table: str) -> list[dict[str, Any]]:
        """读取领域附属表（版本覆盖、当前覆盖、回滚差异单等）。"""
        return self._aux.setdefault(table, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
