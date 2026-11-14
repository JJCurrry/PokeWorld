"""G2 状态：不可变快照（不变量 #4 / #6）。

`BattleState` 是 frozen dataclass，字段全部为不可变值；`step` 通过
`dataclasses.replace` 返回**新对象**，绝不原地修改传入的状态或规则快照。
生成结果不入库：状态可由四元组 + 骨架表重建，存档不需要存战斗日志。
"""
from __future__ import annotations

from dataclasses import dataclass

from .rules import Rules


@dataclass(frozen=True)
class Creature:
    cid: str
    hp: int
    max_hp: int
    statused: bool = False


@dataclass(frozen=True)
class BattleState:
    region: str
    coord: tuple[int, int]
    time_phase: str
    tick: int
    outcome: str
    ally: Creature | None
    wild: Creature | None
    weights: tuple[tuple[str, float], ...]
    rules: Rules
    log: tuple[str, ...] = ()


def new_state(tables: dict, region: str, cx: int, cy: int, time_phase: str,
              ally_id: str, weights: dict[str, float] | None = None,
              wild_id: str | None = None, wild_hp_ratio: float = 1.0) -> BattleState:
    """构造初始状态；`weights` 由调用方从 G1 区块结果按当前时段取出（相对量）。

    `wild_id` / `wild_hp_ratio` 供平衡采样直接构造待测局面，不产生随机。
    """
    rules = Rules.from_tables(tables)
    ally_row = rules.creature(ally_id)
    ally = Creature(ally_id, ally_row[2], ally_row[2])
    wild = None
    if wild_id is not None:
        row = rules.creature(wild_id)
        wild = Creature(wild_id, max(1, int(row[2] * wild_hp_ratio)), row[2])
    frozen_weights = tuple(sorted((cid, float(weight))
                                  for cid, weight in (weights or {}).items()))
    outcome = "active" if wild is not None else "idle"
    return BattleState(region, (cx, cy), time_phase, 0, outcome,
                       ally, wild, frozen_weights, rules)
