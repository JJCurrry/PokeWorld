"""G5 只读投影（F2 / F5）：`frame_of` 纯函数、表驱动配色、键位映射与合规词表。

不靠注释自称「表现层只读」：深拷贝比对 Session / tables、frozen 写入报错、
AST 检查零 pygame 顶层导入、UI 字面量逐条过 R4 第三方 IP 词表。
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
from src.gen.chunk import CHUNK_SIZE, generate_chunk  # noqa: E402
from src.view import layout  # noqa: E402
from src.world.progress import chunk_grid  # noqa: E402
from src.world.session import new_session, is_complete  # noqa: E402

G5_VIEW_SOURCES = (
    "src/view/__init__.py", "src/view/deps.py",
    "src/view/layout.py", "src/view/window.py",
    "src/world/session.py", "src/main.py",
)


def _imports_pygame_at_top_level(source: str) -> bool:
    """只查模块级 import；函数体内的延迟导入不算（ADR-005 §决定 3）。"""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "pygame" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "pygame":
                return True
    return False


class TestG5Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.tables_before = copy.deepcopy(cls.tables)
        cls.session = new_session(cls.tables, "G5-layout-test")

    def test_frame_of_is_a_pure_read_only_projection(self):
        before = copy.deepcopy(self.session)
        frame1 = layout.frame_of(self.session, self.tables)
        frame2 = layout.frame_of(self.session, self.tables)
        self.assertEqual(frame1, frame2)
        self.assertEqual(self.session, before)
        self.assertEqual(self.tables, self.tables_before)
        with self.assertRaises(FrozenInstanceError):
            frame1.region = "somewhere-else"  # type: ignore[misc]

    def test_frame_fields_come_from_tables_and_session(self):
        frame = layout.frame_of(self.session, self.tables)
        world = self.session.state.world
        region = self.session.state.progress.region
        # 游标遍历的是「区块网格」，每格再展开成 CHUNK_SIZE × CHUNK_SIZE 地形格。
        width, height = chunk_grid(world, region)
        region_row = next(row for row in self.tables["topology.json"]["regions"]
                          if row["id"] == region)
        self.assertEqual((width, height), tuple(region_row["chunks"]))
        chunk = generate_chunk(self.tables, self.session.state.world_seed,
                               region, *self.session.cursor)
        self.assertGreaterEqual(width, 1)
        self.assertGreaterEqual(height, 1)
        self.assertEqual(frame.grid,
                         tuple(tuple(str(cell) for cell in row)
                               for row in chunk["tiles"]))
        self.assertEqual((len(frame.grid), len(frame.grid[0])),
                         (CHUNK_SIZE, CHUNK_SIZE))
        names = tuple(str(name) for name
                      in self.tables["encounters.json"]["terrain"])
        self.assertEqual(tuple(name for name, _ in frame.palette), names)
        self.assertEqual(len(frame.palette), len(names))
        self.assertEqual(frame.region, region)
        self.assertEqual(frame.cursor, self.session.cursor)
        self.assertEqual(frame.phase, self.session.phase)
        self.assertEqual(frame.complete, is_complete(self.session))
        self.assertEqual(len(frame.lines), 5)
        self.assertTrue(frame.hint)

    def test_key_mapping_is_table_derived_and_bounded(self):
        world = self.session.state.world
        region = self.session.state.progress.region
        self.assertEqual(layout.action_for_key("s", world, region), "survey")
        self.assertEqual(layout.action_for_key("n", world, region), "npc")
        self.assertEqual(layout.action_for_key("p", world, region), "phase")
        self.assertEqual(layout.action_for_key("q", world, region), "quit")
        self.assertEqual(layout.action_for_key("F5", world, region), None)
        self.assertIsNone(layout.action_for_key("unknown", world, region))
        for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            action = layout.action_for_key(key, world, region)
            if action is None:
                continue
            index = int(action.split(":")[1])
            edge = world.edges[index]
            self.assertIn(region, (edge.source, edge.target))
        self.assertEqual(len(layout.KEY_ACTIONS), 13)
        self.assertEqual(set(layout.CLI_ACTIONS),
                         {"auto", "save", "load", "quit"})

    def test_invalid_inputs_raise_explicit_value_error(self):
        with self.assertRaises(ValueError):
            layout.frame_of(object(), self.tables)  # type: ignore[arg-type]
        bad = copy.deepcopy(self.tables)
        bad["topology.json"]["regions"] = []
        with self.assertRaises(ValueError):
            layout.frame_of(self.session, bad)
        with self.assertRaises(ValueError):
            layout._phase_label("twilight")

    def test_view_sources_have_no_top_level_pygame_import(self):
        for relative in G5_VIEW_SOURCES:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertFalse(_imports_pygame_at_top_level(source),
                             f"{relative} 在顶层导入了 pygame")

    def test_ui_text_passes_r4_third_party_ip_wordlist(self):
        frame = layout.frame_of(self.session, self.tables)
        literals = [frame.hint, frame.region_name, *frame.lines]
        for relative in ("src/view/layout.py", "src/view/window.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            literals += [text for text, _ in gate.collect_strings(ast.parse(source))
                         if text]
        for word in gate.BANNED_WORDS:
            for text in literals:
                self.assertNotIn(gate.normalize(word), gate.normalize(text),
                                 f"UI 文案出现第三方 IP 词汇「{word}」：{text}")


if __name__ == "__main__":
    unittest.main()
