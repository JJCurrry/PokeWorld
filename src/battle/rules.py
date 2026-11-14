"""G2 规则层：把三张受保护表凝固成不可变只读数据 + 纯函数公式。

不变量 #2：本模块只读表、不写回；不变量 #3：克制倍率只来自 `type_chart`，
代码中零硬编码。表数据在 `new_state` 时一次性凝固进 `Rules`（frozen），
使 `step(state, action, rng) -> state'` 不必再触碰磁盘或外部字典。

伤害公式属 **G2-01 · AI 占位**（GDD-v0 §4 未定义），待人复核；
结构常数（保底 1 点、防御减半）不来自三张表，已如实登记在 G2 工单。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    """凝固后的规则快照；全部字段为不可变 tuple / float。

    creatures 每行：(cid, 属性, hp, power, guard, base_catch)
    chart 每行：(攻击方属性, ((防守方属性, 倍率), ...))
    """

    creatures: tuple[tuple[str, str, int, int, int, float], ...]
    chart: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    catch_min: float
    catch_max: float
    ball_bonus: float
    status_bonus: float

    @classmethod
    def from_tables(cls, tables: dict) -> "Rules":
        """只读构造；不缓存、不写回，调用方可安全传入深拷贝的表。"""
        creatures = tuple(
            (c["id"], c["type"], int(c["base"][0]), int(c["base"][1]),
             int(c["base"][2]), float(c["base_catch"]))
            for c in tables["species.json"]["creatures"]
        )
        chart = tuple(
            (atk, tuple((dfn, float(mult)) for dfn, mult in row.items()))
            for atk, row in tables["encounters.json"]["type_chart"].items()
        )
        formula = tables["encounters.json"]["catch_formula"]
        return cls(creatures, chart, float(formula["min"]), float(formula["max"]),
                   float(formula["ball_bonus"]), float(formula["status_bonus"]))

    def creature(self, cid: str) -> tuple[str, str, int, int, int, float]:
        for row in self.creatures:
            if row[0] == cid:
                return row
        raise ValueError(f"未登记潮灵：{cid}")

    def multiplier(self, attacker_type: str, defender_type: str) -> float:
        for atk_type, row in self.chart:
            if atk_type != attacker_type:
                continue
            for def_type, value in row:
                if def_type == defender_type:
                    return value
            break
        raise ValueError(f"克制矩阵缺少 {attacker_type}/{defender_type}")


def catch_probability(rules: Rules, cid: str, hp: int, max_hp: int,
                      statused: bool = False) -> float:
    """GDD-v0 §4：p = clamp(base_catch × (1 - hp_ratio) × ball_bonus × status_bonus, min, max)。

    全部因子来自 `Rules`；hp_ratio 来自状态，不在代码里写死任何平衡数值。
    """
    if max_hp <= 0:
        raise ValueError("max_hp 必须为正整数")
    row = rules.creature(cid)
    hp_ratio = min(1.0, max(0.0, hp / max_hp))
    bonus = rules.status_bonus if statused else 1.0
    raw = row[5] * (1.0 - hp_ratio) * rules.ball_bonus * bonus
    return min(rules.catch_max, max(rules.catch_min, raw))


def damage(rules: Rules, attacker_id: str, defender_id: str) -> int:
    """AI 占位公式（G2-01）：攻击力 × 克制倍率 − 防御的一半，至少 1 点。"""
    attacker = rules.creature(attacker_id)
    defender = rules.creature(defender_id)
    multiplier = rules.multiplier(attacker[1], defender[1])
    return max(1, int(attacker[3] * multiplier) - defender[4] // 2)
