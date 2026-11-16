"""G5 会话层（F1）：确定性完整通关、拓扑派生终点、纯函数与只读约束。

不靠注释自称「可通关」：动作序列逐条重放、能力门控逐边核对、表与入参
深拷贝比对，全部用行为给出机器事实。设计依据 `ADR-005` §决定 1 / §决定 2。
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import autoplayer  # noqa: E402
from src import schema  # noqa: E402
from src.world import session as play  # noqa: E402
from src.world.save import SAVE_KEYS, decode  # noqa: E402

SEED = "G5-session-test"


class TestG5Session(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)
        cls.initial = play.new_session(cls.tables, SEED)
        cls.initial_before = copy.deepcopy(cls.initial)
        cls.final, cls.actions = play.play_to_goal(
            cls.initial, cls.tables, autoplayer.choose_action)

    def test_full_run_reaches_topology_derived_goal(self):
        world = self.final.state.world
        progress = self.final.state.progress
        sources = {row["from"] for row in self.tables["topology.json"]["edges"]}
        sinks = [row["id"] for row in self.tables["topology.json"]["regions"]
                 if row["id"] not in sources]
        self.assertEqual(len(sinks), 1)
        self.assertEqual(play.goal_region(world), sinks[0])
        self.assertEqual(progress.region, sinks[0])
        self.assertTrue(play.is_complete(self.final))
        self.assertEqual(progress.blocked, 0)
        self.assertEqual(len(progress.visited_regions), len(world.regions))
        self.assertEqual(len(progress.surveyed_regions), len(world.regions))
        self.assertEqual(len(progress.visited_npcs), len(world.npcs))
        self.assertEqual(play.route_to_goal(progress, world), ())

    def test_run_is_deterministic_and_counts_every_chunk(self):
        again, actions = play.play_to_goal(
            self.initial, self.tables, autoplayer.choose_action)
        self.assertEqual(actions, self.actions)
        self.assertEqual(again, self.final)
        self.assertEqual(len(self.actions), 20)
        expected = sum(width * height for _, width, height
                       in self.final.state.world.grids)
        self.assertEqual(self.final.chunks_seen, expected)
        self.assertEqual(expected, 100)

    def test_no_jump_over_ability_gates(self):
        world = self.final.state.world
        current = self.initial
        for action in self.actions:
            if action.startswith(play.EDGE_PREFIX):
                index = int(action[len(play.EDGE_PREFIX):])
                requires = tuple(world.edges[index].requires)
                self.assertTrue(set(requires).issubset(
                    current.state.progress.abilities),
                    f"{action} 在能力未齐时通过")
            current = play.apply(current, action, self.tables)
        self.assertEqual(current, self.final)

    def test_apply_is_pure_and_session_is_frozen(self):
        probe = play.apply(self.initial, "survey", self.tables)
        self.assertEqual(self.initial, self.initial_before)
        self.assertIsNot(probe, self.initial)
        with self.assertRaises(FrozenInstanceError):
            probe.cursor = (9, 9)  # type: ignore[misc]
        self.assertEqual(self.tables, self.tables_before)

    def test_view_only_actions_do_not_touch_world_state(self):
        for action in ("move:right", "phase", "train"):
            probe = play.apply(self.initial, action, self.tables)
            self.assertEqual(probe.state.progress,
                             self.initial.state.progress)
        moved = play.apply(self.initial, "move:right", self.tables)
        self.assertEqual(moved.cursor, (1, 0))
        phased = play.apply(self.initial, "phase", self.tables)
        self.assertEqual(phased.phase, "night")

    def test_illegal_inputs_raise_explicit_value_error(self):
        for bad in ("", "warp:9", "move:sideways"):
            with self.assertRaises(ValueError):
                play.apply(self.initial, bad, self.tables)
        with self.assertRaises(ValueError):
            play.apply(object(), "survey", self.tables)  # type: ignore[arg-type]

    def test_restore_then_finish_is_still_completable(self):
        text = play.serialize(self.final, self.tables)
        self.assertEqual(sorted(json.loads(text)), sorted(SAVE_KEYS))
        self.assertEqual(decode(text).world_seed, SEED)
        restored = play.restore(text, self.tables)
        resumed, _ = play.play_to_goal(
            restored, self.tables, autoplayer.choose_action)
        self.assertTrue(play.is_complete(resumed))
        self.assertEqual(resumed.state.progress.blocked, 0)

    def test_g5_sources_contain_no_ability_name_literals(self):
        abilities = tuple(self.tables["topology.json"]["abilities"])
        for relative in ("src/world/session.py", "src/view/layout.py",
                         "src/view/window.py", "src/main.py",
                         "tools/g5_report.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for ability in abilities:
                self.assertNotIn(repr(ability), source,
                                 f"{relative} 出现能力名字面量 {ability}")


if __name__ == "__main__":
    unittest.main()
