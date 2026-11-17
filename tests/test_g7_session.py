"""G7 会话战斗编排（D1 / D2）：动作经 G2 纯函数、tick 同步、终局回写图鉴。

不靠注释自称：frozen 不变式、入参不被改、显式抛错、终局清空运行时字段、
图鉴增量、零改表，全部用机器断言。继承 A9：本文件是自测，不是独立冷眼。
"""
from __future__ import annotations

import copy
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.battle.context import RngContext  # noqa: E402
from src.battle.state import BattleState  # noqa: E402
from src.world import session as play  # noqa: E402

SEED = "G7-a"


class TestG7BattleSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)

    def setUp(self):
        self.session = play.new_session(self.tables, SEED)

    def test_battle_fields_default_and_session_is_frozen(self):
        self.assertIsNone(self.session.battle)
        self.assertIsNone(self.session.battle_ctx)
        with self.assertRaises(FrozenInstanceError):
            self.session.encounters = 99  # type: ignore[misc]

    def test_encounter_builds_battle_from_chunk_weights(self):
        before = copy.deepcopy(self.session)
        started = play.apply(self.session, "encounter", self.tables)
        self.assertIsInstance(started.battle, BattleState)
        self.assertIsInstance(started.battle_ctx, RngContext)
        self.assertEqual(started.battle_ctx.tick, started.battle.tick)
        self.assertEqual(started.battle.outcome, "active")
        self.assertTrue(started.battle.weights)
        self.assertEqual(started.encounters, 1)
        # 入参不被改写
        self.assertEqual(self.session, before)
        self.assertEqual(self.tables, self.tables_before)

    def test_battle_actions_advance_tick_and_clear_on_terminal(self):
        current = play.apply(self.session, "encounter", self.tables)
        current = play.apply(current, "item:net_tide", self.tables)
        current = play.apply(current, "item:bell_calm", self.tables)
        steps = 0
        while current.battle is not None and steps < 48:
            prev = current
            current = play.apply(current, "catch", self.tables)
            if current.battle is not None:
                self.assertEqual(current.battle.tick, prev.battle.tick + 1)
                self.assertEqual(current.battle_ctx.tick, current.battle.tick)
            steps += 1
        self.assertIsNone(current.battle)
        self.assertIsNone(current.battle_ctx)
        self.assertLess(steps, 48)

    def test_capture_writes_cid_into_empty_atlas(self):
        self.assertEqual(len(self.session.state.atlas.entries), 0)
        current = play.apply(self.session, "encounter", self.tables)
        wild = current.battle.wild.cid
        for action in ("item:net_tide", "item:bell_calm"):
            current = play.apply(current, action, self.tables)
        steps = 0
        while current.battle is not None and steps < 48:
            current = play.apply(current, "catch", self.tables)
            steps += 1
        self.assertEqual(current.messages[-1], "战斗结束：caught")
        self.assertTrue(current.state.atlas.contains(wild))
        self.assertEqual(current.captures, 1)

    def test_lost_outcome_does_not_register_atlas(self):
        # G7-demo 稳定战败：验证败北不写图鉴、不增 captures。
        current = play.new_session(self.tables, "G7-demo")
        current = play.apply(current, "encounter", self.tables)
        steps = 0
        while current.battle is not None and steps < 48:
            current = play.apply(current, "attack", self.tables)
            steps += 1
        self.assertEqual(current.messages[-1], "战斗结束：lost")
        self.assertEqual(current.captures, 0)
        self.assertEqual(len(current.state.atlas.entries), 0)

    def test_illegal_actions_raise_explicit_value_error(self):
        # 无战斗时不允许战斗动作
        with self.assertRaises(ValueError):
            play.apply(self.session, "attack", self.tables)
        # 战斗中不允许世界动作 / 重复遭遇
        in_battle = play.apply(self.session, "encounter", self.tables)
        for bad in ("survey", "npc", "edge:0", "move:up", "encounter"):
            with self.assertRaises(ValueError):
                play.apply(in_battle, bad, self.tables)
        with self.assertRaises(ValueError):
            play.apply(self.session, "item:not_a_real_id", self.tables)

    def test_determinism_same_seed_same_actions(self):
        def run_once():
            current = play.new_session(self.tables, SEED)
            current = play.apply(current, "encounter", self.tables)
            for action in ("item:net_tide", "item:bell_calm"):
                current = play.apply(current, action, self.tables)
            steps = 0
            while current.battle is not None and steps < 48:
                current = play.apply(current, "catch", self.tables)
                steps += 1
            return current
        self.assertEqual(run_once(), run_once())
        self.assertEqual(self.tables, self.tables_before)


if __name__ == "__main__":
    unittest.main()
