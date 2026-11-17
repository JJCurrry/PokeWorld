"""G7 端到端报告（D4 / D5）：`run()` 纯函数、complete 合取、反证、零改表。

不读注释自称：报告 complete 由多条件合取、换种子差异、三类反证、存档 roundtrip、
门控 / manifest / golden 全绿共同支撑；`main()` 才做 I/O。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import g7_report  # noqa: E402
from src import schema  # noqa: E402


class TestG7Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_report_is_complete_and_pure(self):
        before = copy.deepcopy(self.tables)
        report = g7_report.run(self.tables, "G7-a")
        self.assertTrue(report["complete"], f"report not complete: {report}")
        self.assertEqual(self.tables, before)

    def test_complete_is_a_conjunction_not_a_literal(self):
        report = g7_report.run(self.tables, "G7-a")
        self.assertTrue(report["battle"]["captures"] >= 1)
        self.assertTrue(report["battle"]["atlas_has_wild"])
        self.assertTrue(report["battle"]["battle_cleared"])
        self.assertTrue(report["counter_proof"]["no_battle_action_rejected"])
        self.assertTrue(report["counter_proof"]["world_action_in_battle_rejected"])
        self.assertTrue(report["counter_proof"]["repeat_encounter_rejected"])
        self.assertTrue(report["determinism"]["same_seed_identical"])
        self.assertTrue(report["determinism"]["different_seed_differs"])
        self.assertTrue(report["save"]["roundtrip"])
        self.assertTrue(report["save"]["restored_battle_clean"])
        self.assertTrue(report["view"]["frame_pure"])
        self.assertTrue(report["view"]["combat_projected"])
        self.assertTrue(report["gate"]["tables_unchanged"])
        self.assertTrue(report["gate"]["ok"])
        self.assertTrue(report["gate"]["golden_snapshot_ok"])
        self.assertTrue(report["gate"]["manifest_ok"])

    def test_losing_seed_makes_complete_false(self):
        # 反证：战败种子没有捕获，complete 必须为假（合取而非恒定真）。
        report = g7_report.run(self.tables, "G7-demo")
        self.assertFalse(report["complete"])
        self.assertEqual(report["battle"]["captures"], 0)

    def test_run_is_deterministic(self):
        a = g7_report.run(self.tables, "G7-a")
        b = g7_report.run(self.tables, "G7-a")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
