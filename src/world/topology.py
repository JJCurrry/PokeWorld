"""骨架层只读访问（ADR-001 A 层 / 不变量 #2、#3）。

把 schema.load_all() 得到的三张表转成查询接口；不缓存、不写回、
不在运行时改写拓扑。能力门判定属于 G3，本模块不实现，也不把边上的
条件写成代码分支。
"""
from __future__ import annotations

from pathlib import Path

from src import schema


class Topology:
    """三张受保护数据表的只读视图；构造时不触碰磁盘。"""

    __slots__ = ("_tables",)

    def __init__(self, tables: dict) -> None:
        self._tables = tables

    @classmethod
    def load(cls, root: str | Path | None = None) -> "Topology":
        """显式只读加载入口。生成函数不调用它，避免 I/O 混进纯函数。"""
        return cls(schema.load_all(root))

    @property
    def _topo(self) -> dict:
        return self._tables["topology.json"]

    def region_ids(self) -> tuple[str, ...]:
        return tuple(r["id"] for r in self._topo["regions"])

    def _region(self, region_id: str) -> dict:
        for region in self._topo["regions"]:
            if region["id"] == region_id:
                return region
        raise ValueError(f"未知区域：{region_id}")

    def chunk_grid(self, region_id: str) -> tuple[int, int]:
        width, height = self._region(region_id)["chunks"]
        return int(width), int(height)

    def pool(self, region_id: str) -> tuple[str, ...]:
        return tuple(self._region(region_id)["pool"])

    def terrains(self) -> tuple[str, ...]:
        return tuple(self._tables["encounters.json"]["terrain"])

    def terrain_weight(self) -> dict[str, float]:
        return self._tables["encounters.json"]["terrain_weight"]

    def time_weight(self) -> dict[str, float]:
        return self._tables["encounters.json"]["time_weight"]

    def creature(self, creature_id: str) -> dict:
        for creature in self._tables["species.json"]["creatures"]:
            if creature["id"] == creature_id:
                return creature
        raise ValueError(f"未登记潮灵：{creature_id}")

    def rarity(self) -> dict[str, float]:
        """物种固有出没系数（ADR-002）；与捕捉难度 base_catch 正交，互不参与对方公式。"""
        return {c["id"]: float(c["rarity"])
                for c in self._tables["species.json"]["creatures"]}
