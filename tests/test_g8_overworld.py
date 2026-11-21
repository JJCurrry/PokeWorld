"""G8 开放世界（ADR-009）：连续地形确定性 / 地标连通 / 探索闭环 / 报告。

纯逻辑用例不依赖 pygame；窗口冒烟单独用 dummy 驱动并在缺依赖时优雅 skip。
"""
from __future__ import annotations

import os
import sys
import unittest
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from src import schema                      # noqa: E402
from src.gen import overworld               # noqa: E402
from src.view import deps                   # noqa: E402
from src.world import explore               # noqa: E402
import ow_report                            # noqa: E402

SEED = "G8-demo"


class WorldGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_matrix_deterministic_and_seed_sensitive(self):
        a = overworld.matrix(self.tables, SEED)
        self.assertEqual(a, overworld.matrix(self.tables, SEED))
        self.assertNotEqual(a, overworld.matrix(self.tables, SEED + "-x"))

    def test_continuous_height_bounded(self):
        for x, y in ((0, 0), (10.5, 3.2), (63.5, 63.5), (31.25, 47.75)):
            value = overworld.height_at(SEED, x, y)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_landmarks_derived_and_walkable(self):
        places = overworld.landmarks(self.tables)
        self.assertEqual(len(places), len(self.tables["topology.json"]["regions"]))
        for _, lx, ly in places:
            self.assertTrue(overworld.walkable(self.tables, SEED, lx, ly))

    def test_landmarks_connected_by_land(self):
        places = overworld.landmarks(self.tables)
        start = (int(places[0][1]), int(places[0][2]))
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if (nxt in seen or not (0 <= nxt[0] < overworld.WORLD_TILES
                                         and 0 <= nxt[1] < overworld.WORLD_TILES)):
                    continue
                if overworld.walkable(self.tables, SEED, nxt[0] + 0.5, nxt[1] + 0.5):
                    seen.add(nxt)
                    queue.append(nxt)
        for _, lx, ly in places:
            self.assertIn((int(lx), int(ly)), seen)

    def test_generate_chunk_untouched(self):
        from src.gen.chunk import generate_chunk
        first = generate_chunk(self.tables, "G1-v3", "r1", 0, 0)
        self.assertEqual(first, generate_chunk(self.tables, "G1-v3", "r1", 0, 0))


class ExploreFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_move_is_pure_and_in_bounds(self):
        before = explore.new_explore(self.tables, SEED)
        after = explore.apply(self.tables, before, "move:right")
        self.assertNotEqual((before.x, before.steps), (after.x, after.steps))
        self.assertEqual((before.x, before.y), (explore.new_explore(self.tables, SEED).x,
                                                 explore.new_explore(self.tables, SEED).y))

    def test_encounter_and_battle_action(self):
        started = explore.apply(self.tables, explore.new_explore(self.tables, SEED), "encounter")
        self.assertIsNotNone(started.battle)
        self.assertTrue(started.battle.weights)

    def test_autoplay_completes_default_seed(self):
        finished = explore.autoplay(self.tables, explore.new_explore(self.tables, SEED))
        self.assertEqual(explore.current_region(self.tables, finished), "r7")
        self.assertGreater(finished.captures, 0)
        self.assertTrue(explore.is_complete(self.tables, finished))

    def test_report_complete(self):
        payload = ow_report.run(self.tables, SEED)
        self.assertTrue(payload["complete"])
        self.assertTrue(payload["determinism"]["same_seed_identical"])
        self.assertTrue(payload["gates"]["coverage_complete"])


class WindowSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    @unittest.skipUnless(deps.pygame_available(), "pygame 不可用：窗口用例优雅跳过")
    def test_world_smoke_draws(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from src.view.overworld_view import smoke
        result = smoke(self.tables, SEED, max_frames=3)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["cells_drawn"], 1)


if __name__ == "__main__":
    unittest.main()
