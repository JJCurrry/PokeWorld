"""G2 采样确定性、规模与区间（DoD E5 / `docs/平衡采样报告.md`）。

`setUpClass` 真跑两次完整采样并比较序列化字节，证明「同参重跑逐字节一致」，
而不是只比较同一个对象的两次引用。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import balance_check  # noqa: E402
from src import schema  # noqa: E402


class TestBalanceSampling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = json.dumps(balance_check.snapshot(ROOT), ensure_ascii=False,
                               sort_keys=True, indent=2)
        cls.second = json.dumps(balance_check.snapshot(ROOT), ensure_ascii=False,
                                sort_keys=True, indent=2)
        cls.report = json.loads(cls.first)
        cls.tables = schema.load_all(ROOT)

    def test_snapshot_is_byte_identical_on_repeat(self):
        self.assertEqual(self.first, self.second)

    def test_catch_sample_count_is_one_hundred_thousand(self):
        self.assertEqual(self.report["catch_samples"], 100000)
        self.assertEqual(self.report["catch_cases"], 40)
        self.assertEqual(len(self.report["catch_rows"]), 40)
        for row in self.report["catch_rows"]:
            self.assertEqual(row["samples"], 2500)

    def test_catch_observed_matches_theory_within_tolerance(self):
        self.assertLess(self.report["catch_max_abs_error"], 0.03)

    def test_full_hp_rows_use_lower_clamp(self):
        floor = self.tables["encounters.json"]["catch_formula"]["min"]
        rows = [row for row in self.report["catch_rows"] if row["hp_ratio"] == 1.0]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertAlmostEqual(row["theory"], floor, places=6)

    def test_encounter_follows_weight_ratio(self):
        encounter = self.report["encounter"]
        self.assertEqual(encounter["samples"], 100000)
        self.assertEqual(sum(encounter["counts"].values()), 100000)
        self.assertLess(encounter["max_abs_error"], 0.01)
        for cid, theory in encounter["theory"].items():
            self.assertAlmostEqual(theory, encounter["observed"][cid], delta=0.01)

    def test_damage_matrix_shape_and_bounds(self):
        damage = self.report["damage"]
        self.assertEqual(damage["pairs"], 64)
        self.assertEqual(len(damage["matrix"]), 8)
        flat = [value for row in damage["matrix"] for value in row]
        self.assertEqual(len(flat), 64)
        self.assertEqual(damage["min"], min(flat))
        self.assertEqual(damage["max"], max(flat))
        self.assertGreaterEqual(damage["min"], 1)
        self.assertGreater(damage["max"], damage["min"])

    def test_report_note_marks_human_judgement(self):
        self.assertIn("归人", self.report["note"])


if __name__ == "__main__":
    unittest.main()
