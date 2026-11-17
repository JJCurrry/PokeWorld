"""G7 战斗窗口（D3）：真实 pygame 无头下战斗键只经 session.apply。

假 KEYDOWN 证明「战斗键 → 战斗动作 → 唯一状态转移」，入参不被改、表不被改；
战斗中数字键按表序派生道具动作。缺依赖时整类 skip，验证墙不因此变红。
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src import schema  # noqa: E402
from src.view import deps, window  # noqa: E402
from src.world import session as play  # noqa: E402


class _Event:
    def __init__(self, event_type, key=None):
        self.type = event_type
        self.key = key


@unittest.skipUnless(deps.pygame_available(), "pygame 不可用：窗口用例优雅跳过")
class TestG7Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pygame = deps.require_pygame()
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)

    def test_combat_key_goes_through_single_transition(self):
        pygame = self.pygame
        session = play.apply(play.new_session(self.tables, "G7-a"),
                             "encounter", self.tables)
        before = copy.deepcopy(session)
        events = [_Event(pygame.KEYDOWN, pygame.K_j)]  # attack
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=1,
                                       block=False, handlers={})
        self.assertEqual(result["actions"], ("attack",))
        self.assertTrue(result["ok"])
        self.assertEqual(session, before)
        self.assertEqual(self.tables, self.tables_before)

    def test_combat_item_key_is_table_derived(self):
        pygame = self.pygame
        session = play.apply(play.new_session(self.tables, "G7-a"),
                             "encounter", self.tables)
        events = [_Event(pygame.KEYDOWN, pygame.K_1)]
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=1,
                                       block=False, handlers={})
        items = tuple(sorted(self.tables["encounters.json"]["items"]))
        self.assertEqual(result["actions"], (f"item:{items[0]}",))

    def test_walk_key_still_survey(self):
        pygame = self.pygame
        session = play.new_session(self.tables, "G7-a")
        events = [_Event(pygame.KEYDOWN, pygame.K_s)]
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=1,
                                       block=False, handlers={})
        self.assertEqual(result["actions"], ("survey",))

    def test_combat_frame_draws_without_touching_session(self):
        pygame = self.pygame
        session = play.apply(play.new_session(self.tables, "G7-a"),
                             "encounter", self.tables)
        before = copy.deepcopy(session)
        result = window.run_window(session, self.tables, max_frames=2,
                                   block=False, handlers={})
        self.assertTrue(result["ok"])
        self.assertEqual(result["cells_drawn"], 64)
        self.assertEqual(session, before)
        self.assertEqual(self.tables, self.tables_before)


if __name__ == "__main__":
    unittest.main()
