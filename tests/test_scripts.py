"""G4 事件脚本（DoD E3）：纯数据 + 只读匹配，绝不直接改世界状态。

AST 证据：无 assert / I/O / 时钟 / 裸随机、无状态赋值、不 import
progress / game / save、模块级只放不可变字面量。
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

import gate  # noqa: E402
from src import schema  # noqa: E402
from src.world.game import new_game  # noqa: E402
from src.world.scripts import (  # noqa: E402
    EFFECT_KINDS, SCRIPT_LIMIT, SCRIPT_ROWS, Effect, Script, all_scripts,
    effects_of, select, texts_of,
)

SCRIPTS_SOURCE = ROOT / "src" / "world" / "scripts.py"


class TestScriptRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = all_scripts()

    def test_rows_are_within_limit_unique_and_well_typed(self):
        self.assertLessEqual(len(SCRIPT_ROWS), SCRIPT_LIMIT)
        self.assertLessEqual(len(SCRIPT_ROWS), 20)
        self.assertEqual(len(self.rows), len(SCRIPT_ROWS))
        self.assertTrue(all(len(row) == 6 for row in SCRIPT_ROWS))
        self.assertTrue(all(all(isinstance(field, str) for field in row)
                            for row in SCRIPT_ROWS))
        ids = [row.sid for row in self.rows]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(self.rows, all_scripts())

    def test_effects_are_whitelisted_and_texts_original(self):
        for row in self.rows:
            self.assertIn(row.kind, EFFECT_KINDS)
            self.assertTrue(row.value.strip())
            self.assertTrue(row.text.strip())
            self.assertTrue(row.value.strip())
        normalized = gate.normalize(SCRIPTS_SOURCE.read_text(encoding="utf-8"))
        for word in gate.BANNED_WORDS:
            self.assertNotIn(gate.normalize(word), normalized, word)

    def test_select_is_deterministic_and_does_not_mutate_context(self):
        context = {"region": "r1", "phase": "day"}
        before = copy.deepcopy(context)
        first = select(context)
        self.assertEqual(first, select(context))
        self.assertEqual(context, before)
        self.assertTrue(all(row.key in context
                            and row.match == context[row.key]
                            for row in first))
        self.assertEqual(select({"region": "not-a-region"}), ())

    def test_effects_of_returns_frozen_declarations(self):
        chosen = select({"terrain": "shoal"})
        effects = effects_of(chosen)
        self.assertEqual(len(effects), len(chosen))
        self.assertTrue(all(isinstance(effect, Effect) for effect in effects))
        self.assertEqual(effects, effects_of(chosen))
        with self.assertRaises(FrozenInstanceError):
            effects[0].kind = "flag"
        self.assertEqual(texts_of(chosen),
                         tuple(row.text for row in chosen))

    def test_select_and_effects_leave_game_state_untouched(self):
        tables = schema.load_all(ROOT)
        game = new_game(tables, "scripts-test")
        before = copy.deepcopy(game)
        chosen = select({"region": "r1"})
        effects = effects_of(chosen)
        self.assertEqual(game, before)
        self.assertEqual(game.progress, before.progress)
        self.assertEqual(game.world, before.world)


class TestScriptsModuleHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SCRIPTS_SOURCE.read_text(encoding="utf-8"))

    def test_no_assert_no_io_no_clock_no_dynamic_calls(self):
        self.assertEqual([n.lineno for n in ast.walk(self.tree)
                          if isinstance(n, ast.Assert)], [])
        banned_calls = {"open", "print", "input", "eval", "exec", "compile",
                        "getattr", "step", "replace", "apply_effects",
                        "observe", "encode", "decode"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, banned_calls,
                                 f"{node.lineno}: {node.func.id}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     {"os", "time", "random", "numpy",
                                      "secrets", "datetime", "subprocess"})
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],
                                 {"os", "time", "random", "numpy",
                                  "secrets", "datetime", "subprocess"})

    def test_does_not_import_world_state_modules(self):
        banned = {"progress", "game", "save", "evolution"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[-1], banned)
            elif isinstance(node, ast.ImportFrom):
                parts = (node.module or "").split(".")
                self.assertFalse(set(parts) & banned, node.module)
                for alias in node.names:
                    self.assertNotIn(alias.name, banned)

    def test_no_state_assignment_and_only_literal_module_values(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
                    node.ctx, (ast.Store, ast.Del)):
                self.fail(f"{node.lineno}: 出现了状态赋值 {ast.dump(node)[:60]}")
        for node in self.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                self.assertIsInstance(node.value, (ast.Tuple, ast.Constant),
                                      f"scripts.py:{node.lineno} 模块级出现可变赋值")

    def test_script_and_effect_are_frozen_value_objects(self):
        row = Script(*SCRIPT_ROWS[0])
        with self.assertRaises(FrozenInstanceError):
            row.kind = "note"
        effect = Effect("flag", "script:x", "s01")
        with self.assertRaises(FrozenInstanceError):
            effect.value = "changed"


if __name__ == "__main__":
    unittest.main()
