"""G2 规则层：把三张受保护表凝固成不可变只读数据 + 纯函数公式。

不变量 #2：本模块只读表、不写回；不变量 #3：克制倍率只来自 `type_chart`，
代码中零硬编码。表数据在 `new_state` 时一次性凝固进 `Rules`（frozen），
使 `step(state, action, rng) -> state'` 不必再触碰磁盘或外部字典。

G2 返工（人裁决 2026-11-14 22:24 + 2026-11-15 确认，设计见 ADR-002）：
- 伤害公式由减法型占位改为比例型，结构常数全部来自 `damage_formula`；
- 道具倍率 / 状态倍率 / 撤离参数全部来自 `items` / `statuses` / `flee`，
  移除原单值 `ball_bonus` / `status_bonus`；
- **捕捉公式的 hp 项未改**（S2-03 仍归人裁决）：满血时 (1 - hp_ratio)=0，
  道具与状态倍率被乘成 0 后再被 min 抬回下限，属公式性质、不是实现缺陷。
全部数值属 A11 候选占位，不是最终平衡定稿。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    """凝固后的规则快照；全部字段为不可变 tuple / 数值。

    creatures 每行：(cid, 属性, hp, power, guard, base_catch, agility)
    chart 每行：(攻击方属性, ((防守方属性, 倍率), ...))
    items 每行：(id, name, kind, catch_bonus, status, apply_rate)
    statuses 每行：(id, name, catch_bonus, duration, counter_rate)
    """

    creatures: tuple[tuple[str, str, int, int, int, float, int], ...]
    chart: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    catch_min: float
    catch_max: float
    damage_atk_scale: float
    damage_guard_scale: float
    damage_min: int
    items: tuple[tuple[str, str, str, float, str, float], ...]
    statuses: tuple[tuple[str, str, float, int, float], ...]
    flee_base_rate: float
    flee_agility_scale: float
    flee_min: float
    flee_max: float
    flee_status_bonus: float

    @classmethod
    def from_tables(cls, tables: dict) -> "Rules":
        """只读构造；不缓存、不写回，调用方可安全传入深拷贝的表。"""
        encounters = tables["encounters.json"]
        creatures = tuple(
            (c["id"], c["type"], int(c["base"][0]), int(c["base"][1]),
             int(c["base"][2]), float(c["base_catch"]), int(c["base"][3]))
            for c in tables["species.json"]["creatures"]
        )
        chart = tuple(
            (atk, tuple((dfn, float(mult)) for dfn, mult in row.items()))
            for atk, row in encounters["type_chart"].items()
        )
        catch = encounters["catch_formula"]
        formula = encounters["damage_formula"]
        items = tuple(
            (key, str(item["name"]), item["kind"],
             float(item.get("catch_bonus", 0.0)), str(item.get("status", "")),
             float(item.get("apply_rate", 0.0)))
            for key, item in encounters["items"].items()
        )
        statuses = tuple(
            (key, str(st["name"]), float(st["catch_bonus"]),
             int(st["duration"]), float(st["counter_rate"]))
            for key, st in encounters["statuses"].items()
        )
        flee = encounters["flee"]
        return cls(
            creatures, chart,
            float(catch["min"]), float(catch["max"]),
            float(formula["atk_scale"]), float(formula["guard_scale"]),
            int(formula["min_damage"]),
            items, statuses,
            float(flee["base_rate"]), float(flee["agility_scale"]),
            float(flee["min"]), float(flee["max"]), float(flee["status_bonus"]),
        )

    def creature(self, cid: str) -> tuple[str, str, int, int, int, float, int]:
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

    def item(self, item_id: str) -> tuple[str, str, str, float, str, float]:
        for row in self.items:
            if row[0] == item_id:
                return row
        raise ValueError(f"未登记道具：{item_id}")

    def status(self, status_id: str) -> tuple[str, str, float, int, float]:
        for row in self.statuses:
            if row[0] == status_id:
                return row
        raise ValueError(f"未登记状态：{status_id}")

    def default_ball(self) -> str:
        """默认装备：表里第一个 ball 类道具，避免在代码里硬编码道具 id。"""
        for row in self.items:
            if row[2] == "ball":
                return row[0]
        raise ValueError("道具表缺少 ball 类道具")

    def counter_rate(self, status_id: str | None) -> float:
        """无状态视为必定反击；有状态按表里的 counter_rate（僵麻为 0）。"""
        return 1.0 if status_id is None else self.status(status_id)[4]


def catch_probability(rules: Rules, cid: str, hp: int, max_hp: int,
                      ball_bonus: float = 1.0, status_bonus: float = 1.0) -> float:
    """GDD-v0 §4：p = clamp(base_catch × (1 - hp_ratio) × 球倍率 × 状态倍率, min, max)。

    两个 1.0 是「无加成」的中性值，不是平衡常数；实际倍率由调用方从道具 / 状态表取。
    hp 项结构未改（S2-03 归人），满血恒落下限属公式性质。
    """
    if max_hp <= 0:
        raise ValueError("max_hp 必须为正整数")
    row = rules.creature(cid)
    hp_ratio = min(1.0, max(0.0, hp / max_hp))
    raw = row[5] * (1.0 - hp_ratio) * ball_bonus * status_bonus
    return min(rules.catch_max, max(rules.catch_min, raw))


def damage(rules: Rules, attacker_id: str, defender_id: str) -> int:
    """ADR-002 §2 比例型公式：power × 克制 × atk_scale / (1 + guard / guard_scale)。

    用「除以防御因子」替代减法，克制倍率不再被压成 1 点；结构常数全部来自表。
    """
    attacker = rules.creature(attacker_id)
    defender = rules.creature(defender_id)
    multiplier = rules.multiplier(attacker[1], defender[1])
    raw = attacker[3] * multiplier * rules.damage_atk_scale \
        / (1.0 + defender[4] / rules.damage_guard_scale)
    return max(rules.damage_min, round(raw))


def flee_probability(rules: Rules, ally_id: str, wild_id: str,
                     wild_status: str | None) -> float:
    """ADR-002 §4：撤离成功率 = 基础率 + 敏捷差 × 系数 + 野生状态加成，全部常数来自表。"""
    ally = rules.creature(ally_id)
    wild = rules.creature(wild_id)
    raw = (rules.flee_base_rate
           + (ally[6] - wild[6]) * rules.flee_agility_scale
           + (rules.flee_status_bonus if wild_status is not None else 0.0))
    return min(rules.flee_max, max(rules.flee_min, raw))
