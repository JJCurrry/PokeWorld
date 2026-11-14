"""G2 纯度证明（不变量 #4）：状态与表不被改、模块无副作用、可重放。

不靠注释自称纯函数，全部用行为 + AST 检查给出证据。
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

from src import schema  # noqa: E402
from src.battle import RngContext, Rules, new_state, step  # noqa: E402
from src.gen import generate_chunk  # noqa: E402

BATTLE_DIR = ROOT / "src" / "battle"


class TestPurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.weights = generate_chunk(cls.tables, "purity-test", "r1", 0, 0)["encounter_weights"]["day"]

    def test_tables_and_weights_are_not_mutated(self):
        before = copy.deepcopy(self.tables)
        weights_before = copy.deepcopy(self.weights)
        state = new_state(self.tables, "r1", 0, 0, "day", "c01", self.weights)
        ctx = RngContext("purity-test", "r1", 0, 0)
        step(state, "encounter", ctx)
        active = new_state(self.tables, "r1", 0, 0, "day", "c01", self.weights,
                           wild_id="c02")
        step(active, "attack", ctx)
        step(active, "catch", ctx)
        step(active, "flee", ctx)
        self.assertEqual(self.tables, before)
        self.assertEqual(self.weights, weights_before)

    def test_state_is_frozen(self):
        state = new_state(self.tables, "r1", 0, 0, "day", "c01", self.weights)
        with self.assertRaises(FrozenInstanceError):
            state.tick = 99

    def test_equivalent_context_replays_identically(self):
        state = new_state(self.tables, "r1", 0, 0, "day", "c01", self.weights)
        first = RngContext("same-seed", "r1", 0, 0, 0)
        second = RngContext("same-seed", "r1", 0, 0, 0)
        self.assertEqual(step(state, "encounter", first),
                         step(state, "encounter", second))

    def test_rules_snapshot_does_not_follow_table_changes(self):
        tables = copy.deepcopy(self.tables)
        state = new_state(tables, "r1", 0, 0, "day", "c01", self.weights)
        original = state.rules.creatures[0][5]
        tables["species.json"]["creatures"][0]["base_catch"] = 0.99
        self.assertEqual(state.rules.creatures[0][5], original)
        self.assertEqual(Rules.from_tables(tables).creatures[0][5], 0.99)

    def test_context_advance_changes_stream(self):
        ctx = RngContext("advance", "r1", 0, 0, 0)
        self.assertNotEqual(ctx.stream("catch").u64(),
                            ctx.advance().stream("catch").u64())


class TestModuleHygiene(unittest.TestCase):
    """静态证据：无 assert、无 I/O / 时钟、模块级只放不可变字面量。"""

    @classmethod
    def setUpClass(cls):
        cls.sources = sorted(BATTLE_DIR.glob("*.py"))
        cls.trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in cls.sources}

    def test_battle_modules_exist(self):
        self.assertGreaterEqual(len(self.sources), 4)

    def test_no_assert_statements(self):
        for path, tree in self.trees.items():
            hits = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]
            self.assertEqual(hits, [], f"{path.name}:{hits}")

    def test_no_io_or_dynamic_calls(self):
        banned = {"open", "print", "input", "eval", "exec", "compile", "getattr"}
        for path, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, banned,
                                     f"{path.name}:{node.lineno} 调用了 {node.func.id}")

    def test_no_clock_or_random_imports(self):
        banned = {"os", "time", "random", "numpy", "secrets", "datetime", "subprocess"}
        for path, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], banned,
                                         f"{path.name}:{node.lineno} 导入了 {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = (node.module or "").split(".")[0]
                    self.assertNotIn(module, banned,
                                     f"{path.name}:{node.lineno} 导入了 {node.module}")

    def test_module_level_values_are_immutable_literals(self):
        for path, tree in self.trees.items():
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    self.assertIsInstance(node.value, (ast.Tuple, ast.Constant),
                        f"{path.name}:{node.lineno} 模块级出现可变赋值")


if __name__ == "__main__":
    unittest.main()
