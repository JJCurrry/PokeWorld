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

    @unittest.skipUnless(deps.pygame_available(), "pygame 不可用：窗口用例优雅跳过")
    def test_real_keypress_drives_whole_loop(self):
        """真实按键事件走通：移动→遭遇→战斗动作→图鉴；侧栏回显最近操作。"""
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        from src.view import overworld_view as ov
        from src.view.overworld_view import ACTION_LABELS

        pygame.init()
        for key in (pygame.K_RIGHT, pygame.K_k, pygame.K_k, pygame.K_k, pygame.K_k):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        result = ov.run_world(self.tables, SEED, max_frames=5, block=False)
        self.assertIn("move:right", result["actions"])
        self.assertIn("encounter", result["actions"])  # 走路自动触发遭遇
        self.assertIn("catch", result["actions"])      # 战斗态 K 键生效
        self.assertEqual(result["last_action"], "catch")
        self.assertIn(result["last_action"], ACTION_LABELS)  # 侧栏回显有中文标签

    def test_action_labels_cover_all_controls(self):
        from src.view.overworld_view import ACTION_LABELS
        for action in ("move:up", "move:down", "move:left", "move:right",
                       "npc", "survey", "phase", "encounter", "attack",
                       "catch", "flee", "save", "load", "quit"):
            self.assertIn(action, ACTION_LABELS)


class ArtAssets(unittest.TestCase):
    """G8/S8-01 原创美术资产：文件就位、真透明、稳定名、缺图降级。"""

    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_all_assets_present_with_alpha(self):
        from src.view import asset_atlas
        self.assertTrue(asset_atlas.available())
        facts = asset_atlas.facts()
        self.assertEqual(facts["creatures"], 8)
        self.assertEqual(facts["landmarks"], 7)
        self.assertTrue(facts["player"])
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL 不可用：alpha 检查优雅跳过")
        for index in range(1, 9):
            path = asset_atlas.asset_path(f"creatures/c{index:02d}.png")
            image = Image.open(path).convert("RGBA")
            self.assertEqual(image.getchannel("A").getextrema()[0], 0,
                             f"c{index:02d} 背景未透明")
        for index in range(1, 8):
            path = asset_atlas.asset_path(f"landmarks/r{index}.png")
            image = Image.open(path).convert("RGBA")
            self.assertEqual(image.getchannel("A").getextrema()[0], 0,
                             f"r{index} 背景未透明")

    def test_provenance_registered_for_each_asset(self):
        gdd = (ROOT / "docs" / "GDD-v0.md").read_text(encoding="utf-8")
        for index in range(1, 9):
            self.assertIn(f"潮灵美术 `c{index:02d}`", gdd)
        self.assertIn("地标美术 r1–r7", gdd)
        self.assertIn("玩家角色美术", gdd)

    @unittest.skipUnless(deps.pygame_available(), "pygame 不可用：窗口用例优雅跳过")
    def test_smoke_reports_art_loaded(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from src.view.overworld_view import smoke
        result = smoke(self.tables, SEED, max_frames=2)
        self.assertTrue(result["ok"])
        art = result["art"]
        self.assertTrue(art["player"])
        self.assertEqual(art["creatures"], 8)
        self.assertEqual(art["landmarks"], 7)


if __name__ == "__main__":
    unittest.main()
