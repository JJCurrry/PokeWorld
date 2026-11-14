"""G2 行为测试（不变量 #1 / #3 / #4）：状态机、确定性、公式来源与边界。

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
from src.battle.rules import catch_probability, damage  # noqa: E402
from src.gen import generate_chunk  # noqa: E402
from src.gen.rng import rng  # noqa: E402


class TestBattleActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.weights = generate_chunk(cls.tables, "battle-test", "r1", 0, 0)["encounter_weights"]["day"]

    def idle(self, tables=None):
        return new_state(tables or self.tables, "r1", 0, 0, "day", "c01", self.weights)

    def active(self, tables=None, wild_id="c02", hp_ratio=1.0):
        return new_state(tables or self.tables, "r1", 0, 0, "day", "c01",
                         wild_id=wild_id, wild_hp_ratio=hp_ratio)

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

    def test_flee_is_terminal(self):
        out = step(self.active(), "flee", self.ctx())
        self.assertEqual(out.outcome, "fled")
        self.assertEqual(out.log[-1], "flee")

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


class TestFormulasComeFromTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.rules = Rules.from_tables(cls.tables)
        cls.species = {c["id"]: c for c in cls.tables["species.json"]["creatures"]}
        cls.formula = cls.tables["encounters.json"]["catch_formula"]
        cls.chart = cls.tables["encounters.json"]["type_chart"]

    def test_full_hp_uses_lower_clamp_for_every_species(self):
        for creature in self.tables["species.json"]["creatures"]:
            with self.subTest(cid=creature["id"]):
                value = catch_probability(self.rules, creature["id"],
                                          creature["base"][0], creature["base"][0])
                self.assertEqual(value, self.formula["min"])

    def test_status_bonus_comes_from_table(self):
        base = catch_probability(self.rules, "c01", 22, 45)
        with_status = catch_probability(self.rules, "c01", 22, 45, True)
        self.assertAlmostEqual(with_status / base, self.formula["status_bonus"], places=6)

    def test_upper_clamp_is_effective(self):
        altered = copy.deepcopy(self.tables)
        altered["species.json"]["creatures"][0]["base_catch"] = 1.0
        rules = Rules.from_tables(altered)
        self.assertEqual(catch_probability(rules, "c01", 0, 45, True),
                         self.formula["max"])

    def test_damage_matches_table_values(self):
        attacker = self.species["c08"]
        defender = self.species["c05"]
        multiplier = self.chart[attacker["type"]][defender["type"]]
        expected = max(1, int(attacker["base"][1] * multiplier) - defender["base"][2] // 2)
        self.assertEqual(damage(self.rules, "c08", "c05"), expected)

    def test_type_chart_changes_damage(self):
        self.assertNotEqual(damage(self.rules, "c08", "c05"),
                            damage(self.rules, "c08", "c01"))

    def test_unknown_creature_raises(self):
        with self.assertRaises(ValueError):
            self.rules.creature("c99")


if __name__ == "__main__":
    unittest.main()
