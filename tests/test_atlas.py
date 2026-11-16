"""G4 图鉴（DoD E1）：按出没条件登记、里程碑可达成且可反证。

证据方式：行为（frozen / 幂等 / 条件派生）+ AST（纯度 / 零能力名字面量）。
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
from src.gen.chunk import generate_chunk  # noqa: E402
from src.world.atlas import (  # noqa: E402
    Atlas, AtlasEntry, milestone, new_atlas, observe, observe_chunk,
    region_pool,
)
from src.world.progress import World  # noqa: E402

ATLAS_SOURCE = ROOT / "src" / "world" / "atlas.py"
G4_SOURCES = (
    "src/world/atlas.py", "src/world/evolution.py", "src/world/scripts.py",
    "src/world/save.py", "src/world/game.py", "tools/g4_report.py",
)


def _survey_atlas(tables: dict, seed: str = "atlas-test") -> tuple[World, Atlas]:
    world = World.from_tables(tables)
    atlas = new_atlas()
    for region in world.regions:
        atlas = observe_chunk(atlas, region,
                              generate_chunk(tables, seed, region, 0, 0))
    return world, atlas


class TestAtlasEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.world = World.from_tables(cls.tables)
        cls.chunk = generate_chunk(cls.tables, "atlas-test", "r1", 0, 0)

    def test_entry_and_atlas_are_frozen(self):
        entry = AtlasEntry("c01", "r1", "grass", "day")
        with self.assertRaises(FrozenInstanceError):
            entry.cid = "changed"
        atlas = observe(new_atlas(), "c01", "r1", "grass", "day")
        with self.assertRaises(FrozenInstanceError):
            atlas.entries = ()

    def test_observe_is_sorted_idempotent_and_leaves_original_untouched(self):
        empty = new_atlas()
        first = observe(empty, "c02", "r1", "shoal", "night")
        second = observe(first, "c01", "r1", "grass", "day")
        again = observe(second, "c01", "r1", "grass", "day")
        self.assertEqual(empty.entries, ())
        self.assertEqual(first.entries, (AtlasEntry("c02", "r1", "shoal", "night"),))
        self.assertEqual([e.cid for e in second.entries], ["c01", "c02"])
        self.assertEqual(again, second)

    def test_observe_rejects_empty_fields_and_wrong_atlas(self):
        for args in (("", "r1", "grass", "day"), ("c01", "", "grass", "day"),
                     ("c01", "r1", "", "day"), ("c01", "r1", "grass", "")):
            with self.assertRaises(ValueError):
                observe(new_atlas(), *args)
        with self.assertRaises(ValueError):
            observe("not-an-atlas", "c01", "r1", "grass", "day")

    def test_conditions_and_contains(self):
        atlas = observe(new_atlas(), "c01", "r1", "grass", "day")
        atlas = observe(atlas, "c01", "r2", "shoal", "night")
        self.assertTrue(atlas.contains("c01"))
        self.assertFalse(atlas.contains("c08"))
        self.assertEqual([e.region for e in atlas.conditions("c01")], ["r1", "r2"])
        self.assertEqual(atlas.regions(), ("r1", "r2"))

    def test_observe_chunk_derives_conditions_from_the_table(self):
        counts = self.chunk["terrain_counts"]
        dominant = min(counts, key=lambda name: (-counts[name], name))
        atlas = observe_chunk(new_atlas(), "r1", self.chunk)
        pool = region_pool(self.tables, "r1")
        phases = sorted(self.chunk["encounter_weights"])
        expected = {(cid, "r1", dominant, phase)
                    for phase in phases for cid in pool
                    if self.chunk["encounter_weights"][phase][cid] > 0}
        self.assertEqual({(e.cid, e.region, e.terrain, e.phase)
                          for e in atlas.entries}, expected)
        self.assertEqual(len(atlas.entries), len(expected))
        # 同一物种可按多个「时段 / 地形」条件登记，证明不是编号递增的收集册。
        self.assertEqual(len({e.phase for e in atlas.entries}), 2)
        self.assertTrue(all(isinstance(e, AtlasEntry) and all(
            (e.cid, e.region, e.terrain, e.phase)) for e in atlas.entries))
        self.assertGreater(len(atlas.conditions("c01")), 1)

    def test_observe_chunk_rejects_missing_terrain_counts(self):
        with self.assertRaises(ValueError):
            observe_chunk(new_atlas(), "r1", {"terrain_counts": {},
                                               "encounter_weights": {}})
        with self.assertRaises(KeyError):
            observe_chunk(new_atlas(), "r1", {"terrain_counts": {"grass": 1}})

    def test_region_pool_reads_table_and_r7_is_empty(self):
        self.assertEqual(region_pool(self.tables, "r1"), ("c01", "c02"))
        self.assertEqual(region_pool(self.tables, "r7"), ())
        with self.assertRaises(ValueError):
            region_pool(self.tables, "not-a-region")


class TestMilestone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.world, cls.atlas = _survey_atlas(cls.tables)

    def test_complete_true_after_all_regions_surveyed(self):
        facts = milestone(self.world, self.tables, self.atlas,
                          frozenset(self.world.regions))
        self.assertTrue(facts["complete"])
        self.assertEqual(facts["species_total"], 8)
        self.assertEqual(facts["species_covered"], 8)
        self.assertEqual(len(facts["regions"]), 7)
        self.assertTrue(all(row["achieved"] for row in facts["regions"]))
        self.assertEqual([row["region"] for row in facts["regions"]
                          if row["trivial"]], ["r7"])

    def test_dead_end_topology_counter_proof(self):
        """死端表副本：只有 start 可达 → complete=False，证明不是恒真。"""
        dead = copy.deepcopy(self.tables)
        dead["topology.json"]["edges"] = []
        dead_world = World.from_tables(dead)
        atlas = observe_chunk(new_atlas(), "r1",
                              generate_chunk(dead, "atlas-test", "r1", 0, 0))
        facts = milestone(dead_world, dead, atlas, frozenset(("r1",)))
        self.assertFalse(facts["complete"])
        self.assertFalse(all(row["surveyed"] for row in facts["regions"]))

    def test_atlas_entries_alone_cannot_fake_completion(self):
        """即使图鉴条目齐全，未巡查的区域仍不算达成。"""
        facts = milestone(self.world, self.tables, self.atlas,
                          frozenset(("r1",)))
        self.assertFalse(facts["complete"])

    def test_empty_atlas_never_completes(self):
        facts = milestone(self.world, self.tables, new_atlas(),
                          frozenset(self.world.regions))
        self.assertFalse(facts["complete"])
        self.assertEqual(facts["entries"], 0)

    def test_tables_are_not_mutated(self):
        before = copy.deepcopy(self.tables)
        milestone(self.world, self.tables, self.atlas,
                  frozenset(self.world.regions))
        self.assertEqual(self.tables, before)


class TestG4ProductionHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.abilities = tuple(cls.tables["topology.json"]["abilities"])

    def test_no_ability_literals_in_any_g4_source(self):
        for rel in G4_SOURCES:
            source = (ROOT / rel).read_text(encoding="utf-8")
            hits = [p for p in gate.check_source(source, rel, self.abilities)
                    if "R3" in p]
            self.assertEqual(hits, [], f"{rel} 撞 R3：{hits}")

    def test_atlas_module_is_pure(self):
        tree = ast.parse(ATLAS_SOURCE.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
