"""G4 图鉴（Atlas）：按「出没条件」登记潮灵，而非编号递增。

设计依据 `docs/adr/ADR-004-图鉴成长事件脚本与存档.md`：
- 登记项 `AtlasEntry = (cid, region, terrain, phase)` 记录「在哪、什么地形、什么时段遇到」；
- 里程碑按区域划分（GDD-v0 §2），`complete` 必须由巡图证据达成，且能被死端
  拓扑反证为 False —— 禁止写成恒真；
- `Atlas` 与 `AtlasEntry` 都是 frozen，登记用 `dataclasses.replace` 返回新对象；
- 本模块不读时钟、不做 I/O、不用裸随机；随机只由调用方从 `rng(world_seed,...)`
  生成的区块结果间接提供。校验一律显式抛 `ValueError`（禁 assert）。

图鉴登记**只读**传入的区块结果与区域池，不修改 `World` / `Progress` / 数据表。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .progress import World


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, order=True)
class AtlasEntry:
    """一次「出没条件」观察：某潮灵在某区域的某地形 / 时段可被遇到。"""

    cid: str
    region: str
    terrain: str
    phase: str


@dataclass(frozen=True)
class Atlas:
    """图鉴凝固快照；`entries` 为排序去重的不可变元组。"""

    entries: tuple[AtlasEntry, ...] = field(default_factory=tuple)

    def contains(self, cid: str) -> bool:
        return any(entry.cid == cid for entry in self.entries)

    def conditions(self, cid: str) -> tuple[AtlasEntry, ...]:
        return tuple(entry for entry in self.entries if entry.cid == cid)

    def regions(self) -> tuple[str, ...]:
        return tuple(sorted({entry.region for entry in self.entries}))


def new_atlas() -> Atlas:
    return Atlas()


def observe(atlas: Atlas, cid: str, region: str, terrain: str,
            phase: str) -> Atlas:
    """登记一条出没条件；重复登记返回**等价**的新对象（幂等、不改原对象）。"""
    _require(isinstance(atlas, Atlas), "atlas 必须是 Atlas")
    _require(bool(cid) and bool(region) and bool(terrain) and bool(phase),
             "登记项的四个字段都不得为空")
    entry = AtlasEntry(str(cid), str(region), str(terrain), str(phase))
    if entry in atlas.entries:
        return replace(atlas)
    return replace(atlas, entries=tuple(sorted(atlas.entries + (entry,))))


def observe_chunk(atlas: Atlas, region: str, chunk: dict) -> Atlas:
    """从既有 `generate_chunk` 结果机械派生登记项（纯函数）。

    主导地形取 `terrain_counts` 的最大值（同分时按地形名字典序，保证确定性）；
    时段键来自 `encounter_weights`；权重 > 0 的 cid 才登记。
    不引入随机抽样 —— 图鉴是「可遇到」的事实，不是抽样结果。
    """
    _require(isinstance(atlas, Atlas), "atlas 必须是 Atlas")
    counts = chunk["terrain_counts"]
    _require(bool(counts), "区块缺少地形计数")
    terrain = min(counts, key=lambda name: (-counts[name], name))
    result = atlas
    for phase in sorted(chunk["encounter_weights"]):
        for cid in sorted(chunk["encounter_weights"][phase]):
            if chunk["encounter_weights"][phase][cid] > 0:
                result = observe(result, cid, region, terrain, phase)
    return result


def region_pool(tables: dict, region: str) -> tuple[str, ...]:
    """从骨架表读取某区域的出没池；表只读，不缓存。"""
    for row in tables["topology.json"]["regions"]:
        if row["id"] == region:
            return tuple(sorted(row["pool"]))
    raise ValueError(f"未知区域：{region}")


def milestone(world: World, tables: dict, atlas: Atlas,
              visited: frozenset[str] | set[str]) -> dict:
    """区域里程碑的机器事实：每个区域的 pool 是否都被登记，且该区域是否已巡查。

    `complete` 要求：全部区域都被巡查、全部 pool 物种都已登记、且至少有一条
    登记项。因此死端拓扑（只有 start 可达）会给出 `complete=False`，不是恒真。
    r7 的 pool 为空 → 该区域平凡达成，报告中以 `trivial=True` 如实标注。
    """
    _require(isinstance(world, World), "world 必须是 World 凝固快照")
    _require(isinstance(atlas, Atlas), "atlas 必须是 Atlas")
    seen_regions = set(visited)
    per_region: list[dict] = []
    for region in world.regions:
        pool = region_pool(tables, region)
        observed = {entry.cid for entry in atlas.entries if entry.region == region}
        missing = tuple(cid for cid in pool if cid not in observed)
        surveyed = region in seen_regions
        per_region.append({
            "region": region,
            "pool": pool,
            "missing": missing,
            "trivial": not pool,
            "surveyed": surveyed,
            "achieved": surveyed and not missing,
        })
    species = {c["id"] for c in tables["species.json"]["creatures"]}
    registered = {entry.cid for entry in atlas.entries}
    complete = bool(atlas.entries) and all(row["achieved"] for row in per_region)
    return {
        "regions": tuple(per_region),
        "complete": complete,
        "registered_species": tuple(sorted(registered)),
        "species_total": len(species),
        "species_covered": len(registered & species),
        "entries": len(atlas.entries),
    }
