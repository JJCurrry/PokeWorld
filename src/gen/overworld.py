"""G8 开放世界生成（ADR-009）：连续坐标地形 + 地标布局（纯函数）。

不变量 #1：随机只来自 rng(world_seed, ...)；无裸随机 / 无时钟。
不变量 #2：区域 / 地名 / 门控全部来自受保护三表，代码零专名、零能力名。
不变量 #5：同种子同坐标逐格一致——地形由坐标哈希派生的 value-noise 决定。
不变量 #6：生成结果不入存档，由种子 + 坐标重建。

与 G1 的 8×8 区块生成正交：本模块按**连续世界坐标**采样，不改
`generate_chunk`（其 golden 快照 R7 锁定，必须保持逐格不变）。
"""
from __future__ import annotations

import math

from src.world.topology import Topology

from .rng import rng

WORLD_TILES = 64
LATTICE_STEP = 8
LANDMARK_RADIUS = 3.0
LANDMARK_LIFT_RADIUS = 12.0
LANDMARK_LIFT = 0.85
BRIDGE_WIDTH = 5.0
BRIDGE_LIFT = 0.9


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _lattice(seed: str | int, gx: int, gy: int) -> float:
    return rng(seed, "overworld", gx, gy, stream="height").unit()


def height_at(seed: str | int, x: float, y: float) -> float:
    """连续高度场 [0,1)：格点值双线性插值 + smoothstep，地形因此连片。"""
    _require(0.0 <= x <= WORLD_TILES and 0.0 <= y <= WORLD_TILES,
             f"世界坐标越界：({x},{y})，世界 {WORLD_TILES}×{WORLD_TILES}")
    lx, ly = x / LATTICE_STEP, y / LATTICE_STEP
    x0, y0 = math.floor(lx), math.floor(ly)
    fx, fy = lx - x0, ly - y0
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    top = _lattice(seed, x0, y0) + (_lattice(seed, x0 + 1, y0) - _lattice(seed, x0, y0)) * sx
    bottom = _lattice(seed, x0, y0 + 1) + (_lattice(seed, x0 + 1, y0 + 1) - _lattice(seed, x0, y0 + 1)) * sx
    return top + (bottom - top) * sy


def landmarks(tables: dict) -> tuple[tuple[str, float, float], ...]:
    """地标坐标：区域按表序排成方阵、落在各自格中心，非长id / 硬编码座标。"""
    regions = Topology(tables).region_ids()
    _require(bool(regions), "区域表为空")
    cols = math.ceil(math.sqrt(len(regions)))
    rows = math.ceil(len(regions) / cols)
    cell_w, cell_h = WORLD_TILES / cols, WORLD_TILES / rows
    out = []
    for index, region in enumerate(regions):
        col, row = index % cols, index // cols
        out.append((region, (col + 0.5) * cell_w, (row + 0.5) * cell_h))
    return tuple(out)


def nearest_landmark(tables: dict, x: float, y: float) -> tuple[str, float, float, float]:
    """返回最近 (区域 id, 地标 x, 地标 y, 距离)；地标坐标由表序派生。"""
    best: tuple[str, float, float, float] | None = None
    for region, lx, ly in landmarks(tables):
        distance = math.hypot(x - lx, y - ly)
        if best is None or distance < best[3]:
            best = (region, lx, ly, distance)
    _require(best is not None, "区域表为空，无法确定地标")
    return best


def _segment_distance(px: float, py: float,
                      ax: float, ay: float, bx: float, by: float) -> float:
    """点到线段距离（纯几何）；用于沿拓扑边抬出陆桥。"""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _elevation(tables: dict, seed: str | int, x: float, y: float) -> float:
    """高度场 = 噪声 + 地标隆起 + 陆桥：地标周围及拓扑边连线抬升成可走陆地。

    陆桥沿 `topology.json` 的边连接地标，保证开放世界陆路连通（可从起点走到
    任意地标）。位置全部由表序 / 边派生，零硬编码座标与区域 id。
    """
    base = height_at(seed, x, y)
    places = {rid: (lx, ly) for rid, lx, ly in landmarks(tables)}
    lift = 0.0
    for lx, ly in places.values():
        distance = math.hypot(x - lx, y - ly)
        lift = max(lift, max(0.0, 1.0 - distance / LANDMARK_LIFT_RADIUS) * LANDMARK_LIFT)
    for edge in tables["topology.json"]["edges"]:
        a, b = places.get(str(edge["from"])), places.get(str(edge["to"]))
        if a is None or b is None:
            continue
        distance = _segment_distance(x, y, a[0], a[1], b[0], b[1])
        lift = max(lift, max(0.0, 1.0 - distance / BRIDGE_WIDTH) * BRIDGE_LIFT)
    return min(1.0, base + lift)


def _terrain_index(tables: dict, seed: str | int, x: float, y: float) -> int:
    terrains = Topology(tables).terrains()
    count = len(terrains)
    _require(bool(terrains), "地形表为空")
    # 表序 [陆地, ..., 水域]：海拔越高 index 越小（越靠陆地），地标隆起成陆地。
    level = _elevation(tables, seed, x, y)
    return min(count - 1, max(0, count - 1 - int(level * count)))


def terrain_at(tables: dict, seed: str | int, x: float, y: float) -> str:
    """坐标 → 地形名；地形集合与顺序来自 encounters.json::terrain，代码零地形名字面量。"""
    return Topology(tables).terrains()[_terrain_index(tables, seed, x, y)]


def walkable(tables: dict, seed: str | int, x: float, y: float) -> bool:
    """前半段地形可步行（陆地类），后半段为水域类——按表序派生，不写地形名。"""
    count = len(Topology(tables).terrains())
    return _terrain_index(tables, seed, x, y) < (count + 1) // 2


def encounter_weights(tables: dict, region: str, phase: str,
                      seed: str | int, x: float, y: float) -> dict[str, float]:
    """当前位置遭遇相对权重 = 时段权重 × 地形权重 × 稀有度（与 G1 同公式）。

    池来自该地标的 `pool`；空池（终局区域）返回空字典，调用方据此不触发遭遇。
    """
    view = Topology(tables)
    pool = view.pool(region)
    if not pool:
        return {}
    terrain = terrain_at(tables, seed, x, y)
    tw = float(view.time_weight()[phase])
    ew = float(view.terrain_weight()[terrain])
    rarity = view.rarity()
    return {cid: round(tw * ew * rarity[cid], 6) for cid in pool}


def matrix(tables: dict, seed: str | int) -> tuple[tuple[str, ...], ...]:
    """整张世界地形矩阵（报告 / 测试用）；行列为整数格中心的地形。"""
    return tuple(
        tuple(terrain_at(tables, seed, x + 0.5, y + 0.5)
              for x in range(WORLD_TILES))
        for y in range(WORLD_TILES)
    )
