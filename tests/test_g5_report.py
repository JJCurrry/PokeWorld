"""G5 端到端报告与 CLI 文件闭环（F1 / F3 / F6）：机器事实不靠注释自称。

`g5_report.run` 的 `complete` 由六项 DoD 的合取给出；本文件逐项复核其子事实，
并在真实子进程里跑 `--headless / --save / --load`，证明存档文件里只有三类字段、
生成结果键一个都不入库（不变量 #6）。
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import g5_report  # noqa: E402
from src import schema  # noqa: E402
from src.world.save import FORBIDDEN_KEYS, SAVE_KEYS  # noqa: E402


def run_py(args, timeout=90):
    env = os.environ.copy()
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


class TestG5Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.before = copy.deepcopy(cls.tables)
        cls.report = g5_report.run(cls.tables, "G5-report-test")

    def test_all_six_dod_machine_facts(self):
        report = self.report
        self.assertTrue(report["complete"])
        session = report["session"]
        self.assertTrue(session["complete"])
        self.assertEqual(session["region"], session["goal"])
        self.assertEqual(session["steps"], 20)
        self.assertEqual(session["blocked"], 0)
        self.assertEqual(session["visited_npcs"], 7)
        self.assertEqual(session["visited_regions"], 7)
        self.assertEqual(session["surveyed_regions"], 7)
        self.assertEqual(session["chunks_seen"], session["expected_chunks"])
        self.assertEqual(session["chunks_seen"], 100)
        self.assertTrue(session["no_jump"])
        self.assertEqual(session["edge_checks"], 6)
        self.assertTrue(all(item["satisfied"] and item["moved"]
                            for item in session["edge_events"]))

    def test_atlas_and_counter_proof(self):
        atlas = self.report["atlas"]
        self.assertTrue(atlas["complete"])
        self.assertEqual(atlas["species_covered"], atlas["species_total"])
        self.assertEqual(atlas["trivial_regions"], ["r7"])
        counter = self.report["counter_proof"]
        self.assertFalse(counter["complete"])
        self.assertNotEqual(counter["region"], counter["goal"])
        self.assertEqual(counter["abilities"], 0)

    def test_save_projection_and_resume(self):
        save = self.report["save"]
        self.assertTrue(save["roundtrip"])
        self.assertEqual(sorted(save["keys"]), sorted(SAVE_KEYS))
        self.assertEqual(sorted(save["rejected_generated_keys"]),
                         sorted(FORBIDDEN_KEYS))
        self.assertEqual(save["restored_region"], "r1")
        self.assertTrue(save["resumed_complete"])
        self.assertEqual(save["resumed_region"], "r7")
        # S4-02 已知限制：from_save 不还原图鉴条件，如实记录而非抹去。
        self.assertEqual(save["resumed_atlas_entries"], 0)

    def test_view_gate_and_zero_table_change(self):
        view = self.report["view"]
        self.assertTrue(view["frame_pure"])
        self.assertEqual(view["grid"], [8, 8])
        self.assertTrue(view["tables_unchanged"])
        self.assertTrue(view["frame_complete"])
        self.assertEqual(self.tables, self.before)
        self.assertTrue(self.report["gate"]["ok"])
        self.assertTrue(self.report["gate"]["golden_snapshot_ok"])
        self.assertTrue(self.report["gate"]["manifest_ok"])
        self.assertTrue(self.report["dependency"]["headless_available"])

    def test_different_seed_is_also_completable(self):
        report = g5_report.run(self.tables, "another-seed-for-g5")
        self.assertTrue(report["complete"])
        self.assertEqual(report["session"]["chunks_seen"], 100)

    def test_cli_headless_save_load_file_roundtrip(self):
        headless = run_py(["-m", "src.main", "--headless", "--seed", "G5-cli"])
        self.assertEqual(headless.returncode, 0,
                         headless.stdout + headless.stderr)
        self.assertTrue(json.loads(headless.stdout)["complete"])

        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "slot.json")
            saved = run_py(["-m", "src.main", "--save", path])
            self.assertEqual(saved.returncode, 0,
                             saved.stdout + saved.stderr)
            self.assertTrue(json.loads(saved.stdout)["complete"])
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(sorted(payload), sorted(SAVE_KEYS))
            for key in FORBIDDEN_KEYS:
                self.assertNotIn(key, payload)
            loaded = run_py(["-m", "src.main", "--load", path])
            self.assertEqual(loaded.returncode, 0,
                             loaded.stdout + loaded.stderr)
            report = json.loads(loaded.stdout)
            self.assertTrue(report["resumed_complete"])
            self.assertEqual(report["resumed_blocked"], 0)


if __name__ == "__main__":
    unittest.main()
