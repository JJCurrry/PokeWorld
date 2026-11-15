"""G3 门控与巡图状态的机器证明（不变量 #3 / #4；DoD E1–E3、E7）。

不靠注释自称纯函数或表驱动：凝固快照用「改原表看是否跟随」证明，
门控用「改表副本看行为是否变化」证明，纯度用行为 + AST 双重证据。
"""
from __future__ import annotations

import ast
import copy
import sys
import unittest
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import gate  # noqa: E402
from src import schema  # noqa: E402
from src.world.progress import (  # noqa: E402
    Progress, World, coverage, edge_facts, edge_is_open, new_progress,
    npc_of, npc_region, step,
)

PROGRESS_SOURCE = ROOT / "src" / "world" / "progress.py"


class TestWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.world = World.from_tables(cls.tables)
        cls.topo = cls.tables["topology.json"]

    def test_world_and_edges_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.world.start = "changed"
        with self.assertRaises(FrozenInstanceError):
            self.world.edges[0].source = "changed"

    def test_world_is_snapshot_not_live_view(self):
        tables = copy.deepcopy(self.tables)
        world = World.from_tables(tables)
        before = copy.deepcopy(world)
        tables["topology.json"]["edges"][1]["requires"] = []
        tables["topology.json"]["regions"][0]["id"] = "changed"
        tables["topology.json"]["abilities"][0] = "changed"
        self.assertEqual(world, before)

    def test_shapes_match_the_table(self):
        self.assertEqual(self.world.start, self.topo["start"])
        self.assertEqual(self.world.regions,
                         tuple(r["id"] for r in self.topo["regions"]))
        self.assertEqual(len(self.world.edges), len(self.topo["edges"]))
        self.assertEqual(len(self.world.npcs), len(self.topo["regions"]))
        self.assertEqual(self.world.abilities, tuple(self.topo["abilities"]))
        self.assertEqual(sum(w * h for _, w, h in self.world.grids), 100)

    def test_grants_are_derived_from_edges(self):
        expected = {(npc_of(e["from"]), a)
                    for e in self.topo["edges"] for a in e["requires"]}
        self.assertEqual(set(self.world.grants), expected)
        self.assertEqual(len(self.world.grants), len(expected))
        counts = Counter(a for _, a in self.world.grants)
        self.assertEqual(set(counts.values()), {1}, "当前表每个能力恰有一个授予来源")
        self.assertEqual(set(counts), {a for _, a in expected})
        for npc, _ in self.world.grants:
            self.assertIn(npc_region(npc), self.world.regions)
            self.assertIn(npc, self.world.npcs)

    def test_no_ability_literals_in_g3_production_code(self):
        for rel in ("src/world/progress.py", "tools/autoplayer.py"):
            source = (ROOT / rel).read_text(encoding="utf-8")
            problems = gate.check_source(source, rel, self.world.abilities)
            hits = [p for p in problems if "R3" in p]
            self.assertEqual(hits, [], f"{rel} 撞 R3：{hits}")

    def test_gate_follows_the_table_without_code_changes(self):
        tables = copy.deepcopy(self.tables)
        tables["topology.json"]["edges"][1]["requires"] = []
        changed = World.from_tables(tables)
        at_r2 = step(new_progress(changed), "edge:0", changed)
        self.assertEqual(at_r2.region, "r2")
        self.assertEqual(step(at_r2, "edge:1", changed).region, "r3")
        original = step(new_progress(self.world), "edge:0", self.world)
        self.assertEqual(step(original, "edge:1", self.world).region, "r2")
        self.assertEqual(step(original, "edge:1", self.world).blocked, 1)


class TestGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.world = World.from_tables(cls.tables)

    def _at(self, region, abilities=(), visited=None):
        return Progress(region, frozenset(abilities),
                        frozenset(visited or (region,)), frozenset(),
                        frozenset(), 0)

    def test_every_gated_edge_blocked_without_and_open_with_abilities(self):
        for index, edge in enumerate(self.world.edges):
            if not edge.requires:
                continue
            blocked = step(self._at(edge.source), f"edge:{index}", self.world)
            self.assertEqual(blocked.region, edge.source, f"边 {index} 缺能力却通行")
            self.assertEqual(blocked.blocked, 1)
            opened = step(self._at(edge.source, edge.requires),
                          f"edge:{index}", self.world)
            self.assertEqual(opened.region, edge.target, f"边 {index} 齐备却不通")
            self.assertEqual(opened.blocked, 0)
            self.assertIn(edge.target, opened.visited_regions)

    def test_open_edges_without_gate_are_traversable(self):
        for index, edge in enumerate(self.world.edges):
            if edge.requires:
                continue
            self.assertTrue(edge_is_open(self.world, index, frozenset()))
            self.assertEqual(step(self._at(edge.source), f"edge:{index}",
                                  self.world).region, edge.target)

    def test_backward_move_only_returns_to_visited_regions(self):
        index = next(i for i, e in enumerate(self.world.edges) if e.requires)
        edge = self.world.edges[index]
        cold = self._at(edge.target)
        blocked = step(cold, f"edge:{index}", self.world)
        self.assertEqual(blocked.region, edge.target)
        self.assertEqual(blocked.blocked, 1)
        warmed = replace(cold, visited_regions=frozenset((edge.target, edge.source)))
        back = step(warmed, f"edge:{index}", self.world)
        self.assertEqual(back.region, edge.source)
        self.assertEqual(back.blocked, 0)

    def test_coverage_proves_all_regions_reachable(self):
        cov = coverage(self.world)
        self.assertTrue(cov["complete"])
        self.assertEqual(set(cov["reachable"]), set(self.world.regions))
        self.assertEqual(set(cov["owned"]), set(self.world.abilities))
        self.assertGreaterEqual(cov["rounds"], 2)

    def test_every_edge_is_reachable_and_gate_satisfiable(self):
        facts = edge_facts(self.world)
        self.assertEqual(len(facts), len(self.world.edges))
        for fact in facts:
            self.assertTrue(fact["source_reachable"], fact)
            self.assertTrue(fact["target_reachable"], fact)
            self.assertTrue(fact["gate_satisfiable"], fact)


class TestStepPurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.world = World.from_tables(cls.tables)

    def test_state_is_frozen_and_tables_untouched(self):
        before = copy.deepcopy(self.tables)
        state = new_progress(self.world)
        for action in ("survey", "npc", "edge:0"):
            state = step(state, action, self.world)
        self.assertEqual(self.tables, before)
        with self.assertRaises(FrozenInstanceError):
            state.region = "changed"

    def test_same_arguments_replay_identically(self):
        state = new_progress(self.world)
        self.assertEqual(step(state, "edge:0", self.world),
                         step(state, "edge:0", self.world))
        self.assertEqual(state.tick, 0)

    def test_invalid_actions_raise_explicitly(self):
        state = new_progress(self.world)
        for action in ("unknown", "edge:x", "edge:-1", "edge:99", "edge:1"):
            with self.assertRaises(ValueError, msg=action):
                step(state, action, self.world)
        with self.assertRaises(ValueError):
            step("not-a-state", "survey", self.world)

    def test_npc_action_grants_only_that_npcs_abilities(self):
        world = self.world
        state = step(new_progress(world), "edge:0", world)  # 走到 r2
        state = step(state, "survey", world)
        first = step(state, "npc", world)
        expected = frozenset(a for owner, a in world.grants
                             if owner == npc_of(state.region))
        self.assertTrue(expected, "r2 的 NPC 应有派生授予")
        self.assertEqual(first.abilities, expected)
        self.assertEqual(step(first, "npc", world).abilities, expected)

    def test_module_hygiene(self):
        tree = ast.parse(PROGRESS_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual([n.lineno for n in ast.walk(tree)
                          if isinstance(n, ast.Assert)], [])
        banned_calls = {"open", "print", "input", "eval", "exec", "compile", "getattr"}
        banned_imports = {"os", "time", "random", "numpy", "secrets",
                          "datetime", "subprocess"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, banned_calls)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], banned_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], banned_imports)
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                self.assertIsInstance(node.value, (ast.Tuple, ast.Constant),
                                      f"progress.py:{node.lineno} 模块级出现可变赋值")


if __name__ == "__main__":
    unittest.main()
