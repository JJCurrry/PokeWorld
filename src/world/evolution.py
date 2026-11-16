"""G4 成长 / 形态阶段：线性成长 + 由种子派生的个体修正（零改表）。

设计依据 `docs/adr/ADR-004-图鉴成长事件脚本与存档.md`：
- 全部成长刻度集中在**本模块唯一的模块级常量**，登记为 G4 实现约定，
  **不是 A11 平衡数值**；三张受保护表零改动，也不散落到其他模块。
- 个体值由既有 `rng(world_seed, cid, 0, 0, stream="growth")` 派生；
  该流名与区块生成的默认流正交，因此不触发 R7 快照变化（不变量 #1 / #5）。
- 形态阶段只推进 `stage` 并重算数值，**不产生新的生物 id**（不扩大 R5 溯源表）。
- `PartyMember` 是 frozen，`train` 用 `dataclasses.replace` 返回新对象。

纯函数契约：不读时钟、不做 I/O、不改传入的表 / 状态；非法输入显式抛
`ValueError`（禁 assert，`python -O` 下同样生效）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..gen.rng import rng

# —— G4 成长刻度（唯一事实源；ADR-004 登记为实现约定，非 A11 平衡数值）——
MAX_LEVEL = 20
PER_LEVEL = 2
IV_SPAN = 6
EVOLVE_LEVELS = (8, 16)
STAGE_BONUS = (0, 4, 9)
GROWTH_STREAM = "growth"


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class PartyMember:
    """队伍成员的可持久化最小状态；数值由表 + 本模块刻度确定性重算。"""

    cid: str
    level: int
    stage: int
    iv: int

    def row(self) -> tuple[str, int, int, int]:
        """投影成存档用的不可变四元组（不含生成结果）。"""
        return (self.cid, self.level, self.stage, self.iv)


def stage_of(level: int) -> int:
    """等级 → 形态阶段 0/1/2；阈值来自单一常量 EVOLVE_LEVELS。"""
    _require(type(level) is int and 1 <= level <= MAX_LEVEL,
             f"等级必须是 1..{MAX_LEVEL} 的整数")
    return sum(1 for threshold in EVOLVE_LEVELS if level >= threshold)


def individual_value(world_seed: str, cid: str) -> int:
    """个体修正；同 (world_seed, cid) 永远一致，且不占用区块生成的随机流。"""
    return rng(world_seed, cid, 0, 0, stream=GROWTH_STREAM).below(IV_SPAN)


def _species_ids(tables: dict) -> tuple[str, ...]:
    return tuple(str(row["id"]) for row in tables["species.json"]["creatures"])


def new_member(tables: dict, world_seed: str, cid: str,
               level: int = 1) -> PartyMember:
    """从表校验 cid，个体值由种子派生，形态阶段由等级机械决定。"""
    _require(cid in _species_ids(tables), f"未登记的潮灵：{cid}")
    _require(type(level) is int and 1 <= level <= MAX_LEVEL,
             f"等级必须是 1..{MAX_LEVEL} 的整数")
    return PartyMember(cid, level, stage_of(level),
                       individual_value(world_seed, cid))


def member_from_row(tables: dict, row: object) -> PartyMember:
    """从存档四元组还原成员；逐字段显式校验，不接受畸形 / 越界值。"""
    _require(isinstance(row, (tuple, list)) and len(row) == 4,
             "队伍成员存档行必须是四元组")
    cid, level, stage, iv = row
    _require(isinstance(cid, str) and cid in _species_ids(tables),
             f"存档含未登记的潮灵：{cid!r}")
    _require(type(level) is int and 1 <= level <= MAX_LEVEL,
             f"存档等级越界：{level!r}")
    _require(type(stage) is int and stage == stage_of(level),
             f"存档形态阶段与等级不一致：{stage!r}")
    _require(type(iv) is int and 0 <= iv < IV_SPAN, f"存档个体值越界：{iv!r}")
    return PartyMember(cid, level, stage, iv)


def stats_of(member: PartyMember, tables: dict) -> tuple[tuple[str, int], ...]:
    """数值 = 表内 base + 等级线性成长 + 个体修正 + 形态阶段加成（纯函数）。

    属性键与基础值全部读表，不在代码里复制平衡常数。
    """
    _require(isinstance(member, PartyMember), "member 必须是 PartyMember")
    keys = tuple(str(key) for key in tables["species.json"]["base_keys"])
    row = next((c for c in tables["species.json"]["creatures"]
                if c["id"] == member.cid), None)
    _require(row is not None, f"表中找不到潮灵：{member.cid}")
    _require(len(row["base"]) == len(keys), "基础值长度与 base_keys 不一致")
    delta = (member.level - 1) * PER_LEVEL + member.iv + STAGE_BONUS[member.stage]
    return tuple((key, int(value) + delta)
                 for key, value in zip(keys, row["base"]))


def train(member: PartyMember) -> PartyMember:
    """升一级；`replace` 返回新对象，原对象逐字段不变。"""
    _require(isinstance(member, PartyMember), "member 必须是 PartyMember")
    _require(member.level < MAX_LEVEL, f"已达等级上限 {MAX_LEVEL}")
    level = member.level + 1
    return replace(member, level=level, stage=stage_of(level))


def train_to(member: PartyMember, level: int) -> PartyMember:
    """直接推进到指定等级（供形态阶段阈值测试 / 报告使用）。"""
    _require(isinstance(member, PartyMember), "member 必须是 PartyMember")
    _require(type(level) is int and member.level <= level <= MAX_LEVEL,
             f"目标等级必须在 {member.level}..{MAX_LEVEL}")
    return replace(member, level=level, stage=stage_of(level))
