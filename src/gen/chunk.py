"""区块生成（G1 · S-02 拆通道 / G2 返工 · ADR-002 稀有度）：地形格 + 遭遇相对权重。

不变量 #1：随机只来自 rng(world_seed, region_id, cx, cy)。
不变量 #5：同参逐格一致，golden seed 快照锁定（G1-v3 起口径见下）。
不变量 #6：生成结果不入库，由种子重建。
人裁决 S-02（2026-11-14 17:56）仍成立：遭遇权重**不乘捕捉难度**，
`base_catch` 只进 G2 的捕捉公式。
人裁决（2026-11-14 22:24 / 2026-11-15 确认）新增 `species.rarity` 出没系数：
`w(cid) = 时段权重 × 区块地形均值 × rarity[cid]`，与 `base_catch` 正交、公式上不耦合。
产出的权重是供 G2 按 wᵢ/Σw 加权抽样消费的**相对量**，不是概率、不是最终平衡定稿；
全部数值仍属 A11 候选占位。快照口径 G1-v2 → G1-v3 由人确认后重拍（R7）。
"""
from __future__ import annotations

from src.world.topology import Topology

from .rng import rng

CHUNK_SIZE = 8
# 模块级只放不可变常量；映射字典在函数内由该元组临时构造。
_TILE_CODE_PAIRS = (
    ("grass", "g"),
    ("deep_grass", "G"),
    ("shoal", "s"),
    ("deep_water", "W"),
)


def encode_tiles(tiles) -> str:
    """把地形格压成可读单行，供 golden seed 快照逐格比对。"""
    codes = dict(_TILE_CODE_PAIRS)
    out = []
    for row in tiles:
        for terrain in row:
            if terrain not in codes:
                raise ValueError(f"未登记地形：{terrain}")
            out.append(codes[terrain])
    return "".join(out)


def generate_chunk(tables: dict, world_seed: str | int, region_id: str,
                   cx: int, cy: int) -> dict:
    """纯函数：给定骨架表与四元组，返回该区块的地形与遭遇相对权重。

    不做 I/O、不读时钟、不改模块级或全局状态；同参调用逐格一致。
    """
    view = Topology(tables)
    if region_id not in view.region_ids():
        raise ValueError(f"未知区域：{region_id}")
    width, height = view.chunk_grid(region_id)
    if not (0 <= cx < width and 0 <= cy < height):
        raise ValueError(f"区块坐标越界：{region_id} ({cx},{cy})，网格 {width}x{height}")

    terrains = view.terrains()
    terrain_weight = view.terrain_weight()
    weights = [float(terrain_weight[name]) for name in terrains]
    stream = rng(world_seed, region_id, cx, cy)

    tiles = []
    counts = {name: 0 for name in terrains}
    for _ in range(CHUNK_SIZE):
        row = []
        for _ in range(CHUNK_SIZE):
            terrain = terrains[stream.pick(weights)]
            row.append(terrain)
            counts[terrain] += 1
        tiles.append(tuple(row))

    cell_count = CHUNK_SIZE * CHUNK_SIZE
    terrain_mean = sum(float(terrain_weight[name]) * count
                       for name, count in counts.items()) / cell_count
    pool = view.pool(region_id)

    # 人裁决 S-02：捕捉难度 base_catch 不参与遭遇，避免「越好抓越常遇到」的耦合。
    # ADR-002：rarity 是与捕捉难度正交的独立维度，使同 pool 内出现频率差异化。
    rarity = view.rarity()
    for cid in pool:
        if cid not in rarity:
            raise ValueError(f"区域 {region_id} 的 pool 含未登记稀有度的潮灵：{cid}")
    encounter = {}
    for phase, phase_weight in view.time_weight().items():
        encounter[phase] = {
            cid: round(float(phase_weight) * terrain_mean * rarity[cid], 6)
            for cid in pool
        }

    return {
        "region": region_id,
        "coord": (cx, cy),
        "tiles": tuple(tiles),
        "terrain_counts": counts,
        "encounter_weights": encounter,
    }
