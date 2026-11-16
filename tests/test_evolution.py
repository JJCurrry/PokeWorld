"""G4 成长 / 形态阶段（DoD E4）：单一随机源、单一刻度常量、纯函数。"""
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
from src.gen.chunk import generate_chunk  # noqa: E402
from src.gen.rng import rng  # noqa: E402
from src.world import evolution  # noqa: E402

EVOLUTION_SOURCE = ROOT / "src" / "world" / "evolution.py"
SCALE_NAMES = {"MAX_LEVEL", "PER_LEVEL", "IV_SPAN",
               "EVOLVE_LEVELS", "STAGE_BONUS"}


class TestGrowth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_individual_value_is_deterministic_and_seed_bound(self):
        first = evolution.individual_value("seed-A", "c01")
        second = evolution.individual_value("seed-A", "c01")
        self.assertEqual(first, second)
        self.assertTrue(0 <= first < evolution.IV_SPAN)
        self.assertEqual(first, rng("seed-A", "c01", 0, 0,
                                    stream=evolution.GROWTH_STREAM)
                         .below(evolution.IV_SPAN))
        values = {evolution.individual_value("seed-A", cid)
                  for cid in ("c01", "c02", "c03", "c04")}
        self.assertGreater(len(values), 1, "不同潮灵应有不同个体值")

    def test_growth_stream_is_isolated_from_chunk_stream(self):
        growth = rng("seed-A", "c01", 0, 0,
                     stream=evolution.GROWTH_STREAM).u64()
        chunk = rng("seed-A", "c01", 0, 0).u64()
        self.assertNotEqual(growth, chunk)
        # 成长流不参与区块生成 → golden 快照哈希保持 G1-v3 登记值。
        self.assertEqual(gate.check_golden_snapshot(ROOT), [])

    def test_stats_read_base_from_table_and_grow_linearly(self):
        tables = copy.deepcopy(self.tables)
        member = evolution.new_member(tables, "seed-A", "c01")
        base = dict(evolution.stats_of(member, tables))
        grown = evolution.train(member)
        after = dict(evolution.stats_of(grown, tables))
        for key in base:
            self.assertEqual(after[key] - base[key], evolution.PER_LEVEL, key)
        tables["species.json"]["creatures"][0]["base"] = [10, 10, 10, 10, 10]
        changed = dict(evolution.stats_of(member, tables))
        self.assertNotEqual(changed, base)
        self.assertEqual(set(changed), set(tables["species.json"]["base_keys"]))

    def test_stage_thresholds_and_stage_bonus(self):
        member = evolution.new_member(self.tables, "seed-A", "c01")
        expected = {1: 0, 7: 0, 8: 1, 15: 1, 16: 2, 20: 2}
        for level, stage in expected.items():
            self.assertEqual(evolution.stage_of(level), stage)
            self.assertEqual(evolution.train_to(member, level).stage, stage)
        low = evolution.train_to(member, 7)
        high = evolution.train_to(member, 8)
        low_stats = dict(evolution.stats_of(low, self.tables))
        high_stats = dict(evolution.stats_of(high, self.tables))
        for key in low_stats:
            self.assertEqual(high_stats[key] - low_stats[key],
                             evolution.PER_LEVEL
                             + evolution.STAGE_BONUS[1]
                             - evolution.STAGE_BONUS[0], key)

    def test_member_is_frozen_and_train_is_pure(self):
        member = evolution.new_member(self.tables, "seed-A", "c01")
        grown = evolution.train(member)
        self.assertEqual(member.level, 1)
        self.assertEqual(grown.level, 2)
        self.assertEqual(grown.iv, member.iv)
        self.assertIsNot(member, grown)
        with self.assertRaises(FrozenInstanceError):
            grown.level = 99
        self.assertEqual(evolution.train(member), evolution.train(member))

    def test_explicit_validation(self):
        member = evolution.new_member(self.tables, "seed-A", "c01")
        for bad in (0, 21, True, 1.5, "2"):
            with self.assertRaises(ValueError):
                evolution.stage_of(bad)
        with self.assertRaises(ValueError):
            evolution.new_member(self.tables, "seed-A", "not-a-cid")
        with self.assertRaises(ValueError):
            evolution.train(evolution.train_to(member, evolution.MAX_LEVEL))
        with self.assertRaises(ValueError):
            evolution.train_to(member, 0)

    def test_member_from_row_validates_every_field(self):
        row = evolution.new_member(self.tables, "seed-A", "c01").row()
        self.assertEqual(evolution.member_from_row(self.tables, row).row(), row)
        bad_rows = (
            ("c01", 1, 0),                 # 长度不对
            ("nope", 1, 0, 0),            # 未登记物种
            ("c01", 0, 0, 0),             # 等级越界
            ("c01", 2, 1, 0),             # 阶段与等级不符
            ("c01", 2, 0, evolution.IV_SPAN),  # 个体值越界
            ("c01", True, 0, 0),          # bool 不得冒充 int
        )
        for bad in bad_rows:
            with self.assertRaises(ValueError, msg=str(bad)):
                evolution.member_from_row(self.tables, bad)


class TestSingleScaleSource(unittest.TestCase):
    def test_growth_scales_are_defined_only_in_evolution(self):
        owners: dict[str, set[str]] = {}
        for folder in ("src", "tools"):
            for path in (ROOT / folder).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"),
                                 filename=str(path))
                for node in tree.body:
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        targets = (node.targets if isinstance(node, ast.Assign)
                                   else [node.target])
                        for target in targets:
                            if isinstance(target, ast.Name) and target.id in SCALE_NAMES:
                                owners.setdefault(target.id, set()).add(
                                    path.relative_to(ROOT).as_posix())
        self.assertEqual(set(owners), SCALE_NAMES)
        for name, paths in owners.items():
            self.assertEqual(paths, {"src/world/evolution.py"}, name)

    def test_evolution_module_is_pure(self):
        tree = ast.parse(EVOLUTION_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual([n.lineno for n in ast.walk(tree)
                          if isinstance(n, ast.Assert)], [])
        banned = {"open", "print", "input", "eval", "exec", "compile", "getattr"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, banned)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     {"os", "time", "random", "numpy",
                                      "secrets", "datetime", "subprocess"})
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                self.assertIsInstance(node.value, (ast.Tuple, ast.Constant))

    def test_chunk_generation_is_unchanged_by_growth_module(self):
        chunk = generate_chunk(schema.load_all(ROOT), "growth-probe", "r1", 0, 0)
        evolution.new_member(schema.load_all(ROOT), "growth-probe", "c01")
        again = generate_chunk(schema.load_all(ROOT), "growth-probe", "r1", 0, 0)
        self.assertEqual(chunk, again)


if __name__ == "__main__":
    unittest.main()
