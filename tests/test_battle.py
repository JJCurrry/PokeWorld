"""G2 行为测试（不变量 #1 / #3 / #4）：状态机、确定性、公式来源与边界。

G2 返工（ADR-002）后新增：道具消耗 / 装备、异常状态施加与衰减、反击率、
撤离判定、比例型伤害公式、表驱动倍率。
S2-03（2026-11-15 22:02 人裁决「采纳」）后：原「满血恒落下限」回归锁改为
「hp 基数生效 + 满血时球 / 状态倍率可拉开差距」，并补 hp 常数表驱动用例。
全部断言用 unittest 方法，不使用裸 `assert` 语句（优化模式会剥离）。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.battle import RngContext, Rules, new_state, step  # noqa: E402
from src.battle.rules import catch_probability, damage, flee_probability  # noqa: E402
from src.gen import generate_chunk  # noqa: E402
from src.gen.rng import rng  # noqa: E402


class TestBattleActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.weights = generate_chunk(cls.tables, "battle-test", "r1", 0, 0)["encounter_weights"]["day"]

    def idle(self, tables=None):
        return new_state(tables or self.tables, "r1", 0, 0, "day", "c01", self.weights)

    def active(self, tables=None, wild_id="c02", hp_ratio=1.0, bag=()):
        return new_state(tables or self.tables, "r1", 0, 0, "day", "c01",
                         wild_id=wild_id, wild_hp_ratio=hp_ratio, bag=bag)

    @staticmethod
    def ctx(seed="battle-test", tick=0, region="r1", cx=0, cy=0):
        return RngContext(seed, region, cx, cy, tick)

    def test_same_arguments_reproduce_identically(self):
        state = self.idle()
        self.assertEqual(step(state, "encounter", self.ctx()),
                         step(state, "encounter", self.ctx()))

    def test_original_state_is_unchanged(self):
        state = self.idle()
        before = copy.deepcopy(state)
        step(state, "encounter", self.ctx())
        self.assertEqual(state, before)

    def test_encounter_result_comes_from_weight_keys(self):
        state = self.idle()
        for index in range(50):
            out = step(state, "encounter", self.ctx(f"enc-{index}"))
            self.assertIn(out.wild.cid, self.weights)
            self.assertEqual(out.wild.hp, out.wild.max_hp)
            self.assertIsNone(out.wild.status)
            self.assertEqual(out.outcome, "active")

    def test_empty_weights_raise_value_error(self):
        state = new_state(self.tables, "r7", 1, 1, "day", "c01", {})
        with self.assertRaises(ValueError):
            step(state, "encounter", self.ctx(region="r7", cx=1, cy=1))

    def test_state_machine_rejects_wrong_phase(self):
        with self.assertRaises(ValueError):
            step(self.active(), "encounter", self.ctx())

    def test_unknown_action_raises_value_error(self):
        with self.assertRaises(ValueError):
            step(self.idle(), "dance", self.ctx())

    def test_tick_mismatch_raises_value_error(self):
        with self.assertRaises(ValueError):
            step(self.idle(), "encounter", self.ctx(tick=7))

    def test_region_mismatch_raises_value_error(self):
        with self.assertRaises(ValueError):
            step(self.idle(), "encounter", self.ctx(region="r2"))

    def test_mutable_stream_is_rejected(self):
        with self.assertRaises(ValueError):
            step(self.idle(), "encounter", rng("battle-test", "r1", 0, 0))

    def test_attack_reduces_hp_and_allows_counter(self):
        state = self.active()
        out = step(state, "attack", self.ctx())
        self.assertLess(out.wild.hp, state.wild.hp)
        self.assertLessEqual(out.ally.hp, state.ally.hp)
        self.assertIn(out.outcome, ("active", "won", "lost"))
        self.assertEqual(out.tick, state.tick + 1)

    def test_flee_success_when_rate_is_certain(self):
        """撤离不再恒成功：把 flee 上下界都改成 1.0 才能得到确定的 fled。"""
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["flee"]["min"] = 1.0
        altered["encounters.json"]["flee"]["max"] = 1.0
        out = step(self.active(altered), "flee", self.ctx())
        self.assertEqual(out.outcome, "fled")
        self.assertEqual(out.log[-1], "flee")

    def test_flee_fails_when_rate_is_zero(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["flee"]["min"] = 0.0
        altered["encounters.json"]["flee"]["max"] = 0.0
        out = step(self.active(altered), "flee", self.ctx())
        self.assertNotEqual(out.outcome, "fled")
        self.assertIn("flee:fail", out.log)

    def test_chain_is_replayable(self):
        def chain():
            state = self.idle()
            ctx = self.ctx()
            state = step(state, "encounter", ctx)
            ctx = ctx.advance()
            state = step(state, "attack", ctx)
            ctx = ctx.advance()
            return step(state, "catch", ctx)
        self.assertEqual(chain(), chain())

    def test_catch_hit_when_probability_is_certain(self):
        """把公式上下界都改成 1.0，命中就是确定事件，不依赖抽样运气。"""
        altered = copy.deepcopy(self.tables)
        altered["species.json"]["creatures"][0]["base_catch"] = 1.0
        altered["encounters.json"]["catch_formula"]["min"] = 1.0
        altered["encounters.json"]["catch_formula"]["max"] = 1.0
        state = self.active(altered, wild_id="c01", hp_ratio=0.1)
        self.assertEqual(step(state, "catch", self.ctx()).outcome, "caught")

    def test_catch_miss_when_probability_is_zero(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["catch_formula"]["min"] = 0.0
        altered["encounters.json"]["catch_formula"]["max"] = 0.0
        state = self.active(altered, wild_id="c01", hp_ratio=0.1)
        self.assertEqual(step(state, "catch", self.ctx()).outcome, "active")

    # ---- G2 返工：道具 / 异常状态 / 状态机 ----

    def test_item_ball_is_consumed_and_equipped(self):
        state = self.active(bag=("net_tide",))
        out = step(state, "item:net_tide", self.ctx())
        self.assertEqual(out.bag, ())
        self.assertEqual(out.equipped_ball, "net_tide")
        self.assertEqual(state.bag, ("net_tide",))
        self.assertEqual(out.log[-1], "item:net_tide:equip")

    def test_item_not_in_bag_raises(self):
        with self.assertRaises(ValueError):
            step(self.active(bag=()), "item:net_tide", self.ctx())

    def test_unknown_item_id_raises(self):
        with self.assertRaises(ValueError):
            step(self.active(bag=("ghost",)), "item:ghost", self.ctx())

    def test_item_empty_id_raises(self):
        with self.assertRaises(ValueError):
            step(self.active(bag=("item:",)), "item:", self.ctx())

    def test_item_on_idle_state_raises(self):
        with self.assertRaises(ValueError):
            step(self.idle(), "item:net_tide", self.ctx())

    def test_status_item_applies_when_rate_is_certain(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["items"]["seal_frost"]["apply_rate"] = 1.0
        state = self.active(altered, bag=("seal_frost",))
        out = step(state, "item:seal_frost", self.ctx())
        self.assertEqual(out.wild.status, "numb")
        self.assertEqual(out.wild.status_ticks, out.rules.status("numb")[3])
        self.assertEqual(out.bag, ())
        self.assertEqual(out.log[-1], "item:seal_frost:applied")

    def test_status_item_misses_when_rate_is_zero(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["items"]["seal_frost"]["apply_rate"] = 0.0
        state = self.active(altered, bag=("seal_frost",))
        out = step(state, "item:seal_frost", self.ctx())
        self.assertIsNone(out.wild.status)
        self.assertEqual(out.bag, ())
        self.assertEqual(out.log[-1], "item:seal_frost:miss")

    def test_status_ticks_decay_and_clear(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["items"]["seal_frost"]["apply_rate"] = 1.0
        state = self.active(altered, bag=("seal_frost",))
        ctx = self.ctx()
        applied = step(state, "item:seal_frost", ctx)
        ctx = ctx.advance()
        self.assertGreater(applied.wild.status_ticks, 0)
        first = step(applied, "attack", ctx)
        ctx = ctx.advance()
        self.assertEqual(first.wild.status_ticks, applied.wild.status_ticks - 1)
        second = step(first, "attack", ctx)
        self.assertIsNone(second.wild.status)
        self.assertEqual(second.wild.status_ticks, 0)

    def test_numb_status_avoids_counter_after_catch_miss(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["catch_formula"]["min"] = 0.0
        altered["encounters.json"]["catch_formula"]["max"] = 0.0
        altered["encounters.json"]["items"]["seal_frost"]["apply_rate"] = 1.0
        state = self.active(altered, bag=("seal_frost",))
        ctx = self.ctx()
        applied = step(state, "item:seal_frost", ctx)
        out = step(applied, "catch", ctx.advance())
        self.assertIn("counter:avoided", out.log)
        self.assertEqual(out.ally.hp, state.ally.hp)

    def test_equipped_ball_changes_catch_probability(self):
        """同一局面换网，命中率必须真的变（不是只改了字段）。

        用真实表值且取半血，两个概率都落在 [min, max] 内、不被 clamp 抹平。
        """
        state = self.active(wild_id="c01", hp_ratio=0.5, bag=("net_tide",))
        plain = catch_probability(state.rules, "c01", state.wild.hp,
                                  state.wild.max_hp, 1.0)
        tide = catch_probability(state.rules, "c01", state.wild.hp,
                                 state.wild.max_hp,
                                 state.rules.item("net_tide")[3])
        self.assertGreater(tide, plain)
        equipped = step(state, "item:net_tide", self.ctx())
        self.assertEqual(equipped.equipped_ball, "net_tide")


class TestFormulasComeFromTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.rules = Rules.from_tables(cls.tables)
        cls.species = {c["id"]: c for c in cls.tables["species.json"]["creatures"]}
        cls.formula = cls.tables["encounters.json"]["catch_formula"]
        cls.chart = cls.tables["encounters.json"]["type_chart"]
        cls.damage_formula = cls.tables["encounters.json"]["damage_formula"]
        cls.items = cls.tables["encounters.json"]["items"]
        cls.statuses = cls.tables["encounters.json"]["statuses"]
        cls.flee = cls.tables["encounters.json"]["flee"]

    def test_full_hp_uses_hp_base_not_zero(self):
        """S2-03 已裁决采纳：满血 hp_factor = catch_base，不再恒落下限。

        低 base_catch 的物种仍可能落到 min，但高 base_catch 的物种必须高于下限；
        逐物种按 min/max clamp 后的理论值核对，防止把公式写死成常数。
        """
        base = self.formula["catch_base"]
        floor, cap = self.formula["min"], self.formula["max"]
        above = 0
        for creature in self.tables["species.json"]["creatures"]:
            with self.subTest(cid=creature["id"]):
                value = catch_probability(self.rules, creature["id"],
                                          creature["base"][0], creature["base"][0])
                expected = min(cap, max(floor, creature["base_catch"] * base))
                self.assertAlmostEqual(value, expected, places=6)
                if value > floor:
                    above += 1
        self.assertGreater(above, 0)

    def test_full_hp_ball_and_status_now_take_effect(self):
        """S2-03 采纳后满血不再被钳死：换网 / 上状态必须真的拉开捕捉率。

        旧回归锁断言「满血恒等于下限」已随人裁决撤销；本用例反过来证明
        道具与状态在满血场景生效，且倍率比例与表一致。
        """
        ball = self.items["net_tide"]["catch_bonus"]
        status = self.statuses["numb"]["catch_bonus"]
        plain = catch_probability(self.rules, "c01", 45, 45)
        boosted = catch_probability(self.rules, "c01", 45, 45, ball, status)
        self.assertGreater(plain, self.formula["min"])
        self.assertGreater(boosted, plain)
        self.assertAlmostEqual(boosted / plain, ball * status, places=6)

    def test_hp_base_constants_come_from_table(self):
        """S2-03 的两个常数必须来自 catch_formula，不能在代码里写死。"""
        raised = copy.deepcopy(self.tables)
        raised["encounters.json"]["catch_formula"]["catch_base"] = 0.30
        self.assertGreater(
            catch_probability(Rules.from_tables(raised), "c01", 45, 45),
            catch_probability(self.rules, "c01", 45, 45))
        lowered = copy.deepcopy(self.tables)
        lowered["encounters.json"]["catch_formula"]["hp_weight"] = 0.40
        self.assertLess(
            catch_probability(Rules.from_tables(lowered), "c01", 22, 45),
            catch_probability(self.rules, "c01", 22, 45))

    def test_ball_and_status_bonus_come_from_table(self):
        base = catch_probability(self.rules, "c01", 22, 45)
        ball = self.items["net_tide"]["catch_bonus"]
        status = self.statuses["numb"]["catch_bonus"]
        with_ball = catch_probability(self.rules, "c01", 22, 45, ball_bonus=ball)
        with_status = catch_probability(self.rules, "c01", 22, 45, status_bonus=status)
        self.assertAlmostEqual(with_ball / base, ball, places=6)
        self.assertAlmostEqual(with_status / base, status, places=6)

    def test_upper_clamp_is_effective(self):
        altered = copy.deepcopy(self.tables)
        altered["species.json"]["creatures"][0]["base_catch"] = 1.0
        rules = Rules.from_tables(altered)
        self.assertEqual(catch_probability(rules, "c01", 0, 45),
                         self.formula["max"])

    def test_damage_matches_table_values(self):
        attacker = self.species["c08"]
        defender = self.species["c05"]
        multiplier = self.chart[attacker["type"]][defender["type"]]
        expected = max(self.damage_formula["min_damage"],
                       round(attacker["base"][1] * multiplier
                             * self.damage_formula["atk_scale"]
                             / (1 + defender["base"][2]
                                / self.damage_formula["guard_scale"])))
        self.assertEqual(damage(self.rules, "c08", "c05"), expected)

    def test_damage_constants_are_table_driven(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["damage_formula"]["atk_scale"] = 0.30
        rules = Rules.from_tables(altered)
        self.assertLess(damage(rules, "c08", "c05"),
                        damage(self.rules, "c08", "c05"))

    def test_type_chart_changes_damage(self):
        self.assertNotEqual(damage(self.rules, "c08", "c05"),
                            damage(self.rules, "c08", "c01"))

    def test_flee_probability_comes_from_table(self):
        altered = copy.deepcopy(self.tables)
        altered["encounters.json"]["flee"]["base_rate"] = 0.1
        rules = Rules.from_tables(altered)
        self.assertLess(flee_probability(rules, "c01", "c02", None),
                        flee_probability(self.rules, "c01", "c02", None))

    def test_flee_status_bonus_raises_probability(self):
        base = flee_probability(self.rules, "c01", "c02", None)
        with_status = flee_probability(self.rules, "c01", "c02", "numb")
        self.assertAlmostEqual(with_status - base, self.flee["status_bonus"],
                               places=6)

    def test_items_and_statuses_are_registered(self):
        self.assertEqual(self.rules.default_ball(), "net_plain")
        self.assertEqual(self.rules.item("net_tide")[3],
                         self.items["net_tide"]["catch_bonus"])
        self.assertEqual(self.rules.status("numb")[4], 0.0)
        with self.assertRaises(ValueError):
            self.rules.item("ghost")
        with self.assertRaises(ValueError):
            self.rules.status("ghost")

    def test_unknown_creature_raises(self):
        with self.assertRaises(ValueError):
            self.rules.creature("c99")


if __name__ == "__main__":
    unittest.main()
