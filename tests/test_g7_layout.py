"""G7 战斗投影（D3 / B 级合规）：Frame 带只读战斗字段、战斗键位表驱动。

证明：frame_of 战斗中同参相等且只读、巡图帧不带战斗面板、键位映射来自表、
新增文案过 R4 第三方 IP 词表（机器只证明合规，不证明好看）。
"""
from __future__ import annotations

import ast
import copy
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import gate  # noqa: E402
from src import schema  # noqa: E402
from src.view import layout  # noqa: E402
from src.world import session as play  # noqa: E402

SEED = "G7-a"


class TestG7Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)

    def test_walk_frame_has_no_combat_panel(self):
        session = play.new_session(self.tables, SEED)
        frame = layout.frame_of(session, self.tables)
        self.assertFalse(frame.combat)
        self.assertEqual(frame.combat_lines, ())
        self.assertEqual(frame.combat_hint, "")
        self.assertEqual(len(frame.lines), 5)  # G5 既有契约不回退

    def test_combat_frame_is_a_pure_read_only_projection(self):
        session = play.apply(play.new_session(self.tables, SEED),
                             "encounter", self.tables)
        before = copy.deepcopy(session)
        frame1 = layout.frame_of(session, self.tables)
        frame2 = layout.frame_of(session, self.tables)
        self.assertEqual(frame1, frame2)
        self.assertEqual(session, before)
        self.assertEqual(self.tables, self.tables_before)
        with self.assertRaises(FrozenInstanceError):
            frame1.combat = False  # type: ignore[misc]

    def test_combat_projection_fields(self):
        session = play.apply(play.new_session(self.tables, SEED),
                             "encounter", self.tables)
        frame = layout.frame_of(session, self.tables)
        self.assertTrue(frame.combat)
        self.assertGreaterEqual(len(frame.combat_lines), 3)
        self.assertTrue(frame.combat_hint)
        self.assertIn("战斗", frame.combat_lines[0])

    def test_combat_key_mapping_is_table_derived(self):
        world = play.new_session(self.tables, SEED).state.world
        region = play.new_session(self.tables, SEED).state.progress.region
        self.assertEqual(layout.action_for_key("b", world, region,
                                               combat=True), "encounter")
        self.assertEqual(layout.action_for_key("j", world, region,
                                               combat=True), "attack")
        self.assertEqual(layout.action_for_key("k", world, region,
                                               combat=True), "catch")
        self.assertEqual(layout.action_for_key("l", world, region,
                                               combat=True), "flee")
        items = tuple(sorted(self.tables["encounters.json"]["items"]))
        self.assertEqual(layout.action_for_key("1", world, region,
                                               combat=True, items=items),
                         f"item:{items[0]}")
        self.assertIsNone(layout.action_for_key("9", world, region,
                                                combat=True, items=items))
        # 巡图态行为完全不变（G5 契约）
        self.assertEqual(layout.action_for_key("s", world, region), "survey")
        self.assertEqual(len(layout.KEY_ACTIONS), 13)

    def test_combat_ui_text_passes_r4_wordlist(self):
        literals = [layout.COMBAT_HELP]
        for name, _ in layout.COMBAT_KEY_ACTIONS:
            literals.append(name)
        for relative in ("src/view/layout.py", "src/view/window.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            literals += [text for text, _ in gate.collect_strings(ast.parse(source))
                         if text]
        for word in gate.BANNED_WORDS:
            for text in literals:
                self.assertNotIn(gate.normalize(word), gate.normalize(text),
                                 f"战斗 UI 文案出现第三方 IP 词汇「{word}」：{text}")


if __name__ == "__main__":
    unittest.main()
