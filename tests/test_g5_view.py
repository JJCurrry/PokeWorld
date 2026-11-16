"""G5 窗口层（F2）：真实 pygame 无头渲染冒烟 + 按键只经 session.apply。

用 `SDL_VIDEODRIVER=dummy` 开真实窗口，用假 KEYDOWN 事件确定性地证明
「键盘 → 动作 → 唯一状态转移」；未登记的 CLI 动作不得漏进 apply。缺依赖时
整类 skip，验证墙不因此变红（F4，设计见 `ADR-005` §决定 3）。
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
from src.view import deps, layout, window  # noqa: E402
from src.world.session import new_session  # noqa: E402


class _Event:
    def __init__(self, event_type, key=None):
        self.type = event_type
        self.key = key


@unittest.skipUnless(deps.pygame_available(), "pygame 不可用：窗口用例优雅跳过")
class TestG5Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pygame = deps.require_pygame()
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)

    def test_smoke_draws_real_frames(self):
        result = window.smoke(self.tables, "G5-window-smoke", max_frames=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["frames"], 2)
        self.assertEqual(result["cells_per_frame"], 64)
        self.assertEqual(result["cells_drawn"], 64)
        self.assertEqual(result["actions"], ())
        self.assertFalse(result["complete"])
        self.assertEqual(self.tables, self.tables_before)

    def test_zero_frame_limit_returns_well_formed_facts(self):
        # 覆盖「循环一次都不执行」时变量未绑定的早期缺陷，而不是只测正常路径。
        session = new_session(self.tables, "G5-window-zero")
        result = window.run_window(session, self.tables,
                                   max_frames=0, block=False, handlers={})
        self.assertTrue(result["ok"])
        self.assertEqual(result["frames"], 0)
        self.assertEqual(result["cells_drawn"], 0)
        self.assertEqual(result["actions"], ())

    def test_draw_returns_cell_count_without_touching_frame(self):
        pygame = self.pygame
        session = new_session(self.tables, "G5-window-draw")
        frame = layout.frame_of(session, self.tables)
        frame_before = copy.deepcopy(frame)
        pygame.init()
        surface = pygame.display.set_mode(window.WINDOW_SIZE)
        font = window._make_font(pygame)
        self.assertEqual(window.draw(surface, frame, pygame, font), 64)
        pygame.display.flip()
        self.assertEqual(frame, frame_before)

    def test_keydown_is_translated_into_the_single_state_transition(self):
        pygame = self.pygame
        session = new_session(self.tables, "G5-window-key")
        before = copy.deepcopy(session)
        events = [_Event(pygame.KEYDOWN, pygame.K_s)]
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=1,
                                       block=False, handlers={})
        self.assertEqual(result["actions"], ("survey",))
        self.assertTrue(result["ok"])
        self.assertEqual(session, before)
        self.assertEqual(self.tables, self.tables_before)

    def test_cli_actions_without_handler_are_ignored(self):
        pygame = self.pygame
        session = new_session(self.tables, "G5-window-cli")
        events = [_Event(pygame.KEYDOWN, pygame.K_a),
                  _Event(pygame.KEYDOWN, pygame.K_q)]
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=1,
                                       block=False, handlers={})
        self.assertEqual(result["actions"], ())
        self.assertTrue(result["ok"])

    def test_quit_event_stops_the_loop(self):
        pygame = self.pygame
        session = new_session(self.tables, "G5-window-quit")
        events = [_Event(pygame.QUIT)]
        with mock.patch.object(pygame.event, "get", return_value=events):
            result = window.run_window(session, self.tables, max_frames=5,
                                       block=False, handlers={})
        self.assertEqual(result["frames"], 1)
        self.assertEqual(result["actions"], ())


if __name__ == "__main__":
    unittest.main()
