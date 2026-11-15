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

    def test_full_hp_rows_follow_hp_base(self):
        """S2-03 采纳后满血不再恒等于下限；逐物种按 base_catch × catch_base 核对。"""
        catch = self.tables["encounters.json"]["catch_formula"]
        species = {c["id"]: c["base_catch"]
                   for c in self.tables["species.json"]["creatures"]}
        floor, cap, base = catch["min"], catch["max"], catch["catch_base"]
        rows = [row for row in self.report["catch_rows"] if row["hp_ratio"] == 1.0]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertAlmostEqual(
                row["theory"], min(cap, max(floor, species[row["creature"]] * base)),
                places=6)
        self.assertTrue(any(row["theory"] > floor for row in rows))

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

    def test_item_rows_are_sampled_and_match_theory(self):
        """道具 / 状态倍率真的接进 `step`，不是只改了字段。"""
        rows = self.report["item_rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(self.report["item_samples"], len(rows) * 2500)
        for row in rows:
            self.assertEqual(row["samples"], 2500)
        self.assertLess(self.report["item_max_abs_error"], 0.03)

    def test_full_hp_item_rows_scale_with_ball_and_status(self):
        """S2-03 采纳后，满血时换网 + 上状态必须真的拉开捕捉率（旧钳制回归锁已撤销）。"""
        floor = self.tables["encounters.json"]["catch_formula"]["min"]
        rows = [row for row in self.report["item_rows"] if row["hp_ratio"] == 1.0]
        self.assertEqual(len(rows), 2)
        plain = next(row for row in rows if row["ball"] == "net_plain")
        tide = next(row for row in rows if row["ball"] == "net_tide")
        self.assertGreater(tide["theory"], plain["theory"])
        self.assertGreaterEqual(plain["theory"], floor)

    def test_flee_is_not_always_successful(self):
        flee = self.report["flee"]
        self.assertEqual(flee["samples"], 20000)
        self.assertLess(flee["observed"], 1.0)
        self.assertLess(flee["abs_error"], 0.02)

    def test_rarity_report_covers_all_regions(self):
        rarity = self.report["rarity"]
        self.assertEqual(len(rarity["regions"]), 7)
        self.assertEqual(len(rarity["rarity"]), 8)
        for region in rarity["regions"]:
            if region["pool"]:
                self.assertAlmostEqual(sum(region["theory"].values()), 1.0, places=5)
        r1 = next(r for r in rarity["regions"] if r["region"] == "r1")
        values = [r1["theory"][cid] for cid in r1["pool"]]
        self.assertNotEqual(values[0], values[1])

    def test_damage_formula_is_proportional_and_floor_free(self):
        damage = self.report["damage"]
        self.assertEqual(damage["min"], 6)
        self.assertEqual(damage["max"], 48)
        self.assertEqual(damage["at_floor"], 0)
        self.assertEqual(damage["formula"]["atk_scale"], 0.55)

    def test_report_note_marks_human_judgement(self):
        self.assertIn("定稿", self.report["note"])
        self.assertIn("归人", self.report["note"])


if __name__ == "__main__":
    unittest.main()
