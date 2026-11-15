"""G3 自动玩家的机器证明（DoD E4–E6）：无跳关 / 无卡死 / 确定性 / 纯度。

「无跳关」按事件逐条核对跨边前的已拥有能力；「无卡死」同时用静态
coverage 与动态轨迹，并用一条故意的死端拓扑证明 complete 不是恒真。
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import autoplayer  # noqa: E402
from src import schema  # noqa: E402


class TestAutoplayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.report = autoplayer.run(cls.tables, "G3-fixed")

    def test_complete_and_counts(self):
        r = self.report
        self.assertTrue(r["complete"])
        self.assertEqual(r["regions_total"], 7)
        self.assertEqual(r["edges_total"], 6)
        self.assertEqual(r["npcs_total"], 7)
        self.assertEqual(len(r["visited_regions"]), 7)
        self.assertEqual(len(r["visited_npcs"]), 7)
        self.assertEqual(len(r["abilities"]), 4)
        self.assertEqual(r["surveyed_chunks"], 100)
        self.assertEqual(r["blocked"], 0)
        self.assertLess(r["steps"], r["max_steps"])

    def test_no_skip_every_first_entry_has_its_gate_satisfied(self):
        r = self.report
        crossings = [e for e in r["events"] if e.get("entered_unvisited")]
        self.assertEqual(len(crossings), 6, "每条边各进入一个新区域")
        for event in crossings:
            self.assertFalse(event["blocked"], event)
            self.assertEqual(event["edge_from"], event["region_before"], event)
            self.assertEqual(event["edge_to"], event["region_after"], event)
            self.assertTrue(set(event["requires"]).issubset(
                set(event["abilities_before"])), event)
        for event in r["events"]:
            if "edge" in event:
                self.assertEqual(event["edge_from"], event["region_before"],
                                 "不得靠反向边绕进未解锁区域")

    def test_no_deadlock_static_and_dynamic(self):
        r = self.report
        self.assertTrue(r["coverage"]["complete"])
        self.assertEqual(set(r["coverage"]["reachable"]), set(r["visited_regions"]))
        self.assertEqual(set(r["coverage"]["owned"]), set(r["abilities"]))
        self.assertTrue(r["complete"] and r["steps"] < r["max_steps"])
        for region in r["visited_regions"]:
            self.assertIn(region, r["surveyed_regions"])
            self.assertIn(f"npc:{region}", r["visited_npcs"])

    def test_dead_end_topology_is_reported_incomplete(self):
        tables = copy.deepcopy(self.tables)
        tables["topology.json"]["start"] = "r7"  # 终局无正向出边，且反向只回已访问
        report = autoplayer.run(tables, "G3-dead-end")
        self.assertFalse(report["complete"])
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(report["visited_regions"], ["r7"])
        self.assertEqual(report["blocked"], 0)

    def test_survey_covers_every_chunk_of_every_region(self):
        r = self.report
        self.assertEqual(len(r["surveys"]), 7)
        self.assertEqual(sum(s["chunks"] for s in r["surveys"]), 100)
        for survey in r["surveys"]:
            self.assertEqual(survey["chunks"],
                             survey["grid"][0] * survey["grid"][1])
            self.assertEqual(len(survey["tiles_digest"]), 64)
            self.assertEqual(sum(survey["terrain_totals"].values()),
                             survey["chunks"] * 64)

    def test_same_seed_replays_byte_identically(self):
        first = json.dumps(self.report, sort_keys=True, ensure_ascii=False)
        second = json.dumps(autoplayer.run(self.tables, "G3-fixed"),
                            sort_keys=True, ensure_ascii=False)
        self.assertEqual(first, second)

    def test_topology_is_decoupled_from_world_seed(self):
        other = autoplayer.run(self.tables, "G3-other")
        self.assertEqual([e["action"] for e in other["events"]],
                         [e["action"] for e in self.report["events"]])
        self.assertEqual(other["visited_regions"], self.report["visited_regions"])
        self.assertEqual(other["abilities"], self.report["abilities"])
        self.assertNotEqual([s["tiles_digest"] for s in other["surveys"]],
                            [s["tiles_digest"] for s in self.report["surveys"]])

    def test_tables_are_not_mutated(self):
        before = copy.deepcopy(self.tables)
        autoplayer.run(self.tables, "G3-mutation-check")
        self.assertEqual(self.tables, before)

    def test_cli_prints_machine_facts_and_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, "tools/autoplayer.py", "G3-cli"],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["complete"])
        self.assertEqual(payload["world_seed"], "G3-cli")
        self.assertEqual(payload["surveyed_chunks"], 100)


if __name__ == "__main__":
    unittest.main()
