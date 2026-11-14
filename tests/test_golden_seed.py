"""G1 golden seed 快照测试（不变量 #1 / #5 / #6）。

逐 case 比对地形编码、地形计数与遭遇权重；另测确定性、参数敏感性、
纯函数性与边界显式报错。快照文件本身由 gate R7 锁定哈希，变更须人确认
（见 tools/make_golden.py 的操作路径与本工单变更记录）。
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.gen import CHUNK_SIZE, encode_tiles, generate_chunk  # noqa: E402
from src.gen.rng import rng  # noqa: E402

SNAPSHOT_PATH = ROOT / "tests" / "golden_seed.json"


class TestGoldenSeed(unittest.TestCase):
    """快照逐格锁定：生成器被悄悄改坏时必须红灯。"""

    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    def test_snapshot_header(self):
        self.assertEqual(self.snapshot["schema_version"], 1)
        self.assertEqual(self.snapshot["generator_version"], "G1-v2")
        self.assertEqual(self.snapshot["weights_kind"], "relative_terrain_time_only")
        self.assertEqual(self.snapshot["chunk_size"], CHUNK_SIZE)
        self.assertGreaterEqual(len(self.snapshot["cases"]), 8)

    def test_every_case_matches_tile_by_tile(self):
        for case in self.snapshot["cases"]:
            with self.subTest(seed=case["world_seed"], region=case["region"],
                              cx=case["cx"], cy=case["cy"]):
                chunk = generate_chunk(self.tables, case["world_seed"],
                                       case["region"], case["cx"], case["cy"])
                self.assertEqual(len(case["tiles"]), CHUNK_SIZE * CHUNK_SIZE)
                self.assertEqual(encode_tiles(chunk["tiles"]), case["tiles"])
                self.assertEqual(chunk["terrain_counts"], case["terrain_counts"])
                self.assertEqual(chunk["encounter_weights"], case["weights"])
                self.assertEqual(chunk["region"], case["region"])
                self.assertEqual(chunk["coord"], (case["cx"], case["cy"]))


class TestDeterminism(unittest.TestCase):
    """不变量 #1 / #5：单一随机源、同参逐格一致、参数敏感性。"""

    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def tiles(self, seed, region, cx, cy):
        return encode_tiles(generate_chunk(self.tables, seed, region, cx, cy)["tiles"])

    def test_same_arguments_reproduce_identically(self):
        a = generate_chunk(self.tables, "golden-a", "r1", 0, 0)
        b = generate_chunk(self.tables, "golden-a", "r1", 0, 0)
        self.assertEqual(a, b)
        self.assertEqual(encode_tiles(a["tiles"]), encode_tiles(b["tiles"]))

    def test_world_seed_changes_output(self):
        self.assertNotEqual(self.tiles("golden-a", "r1", 0, 0),
                            self.tiles("golden-b", "r1", 0, 0))

    def test_region_changes_output(self):
        self.assertNotEqual(self.tiles("golden-a", "r1", 0, 0),
                            self.tiles("golden-a", "r3", 0, 0))

    def test_coord_changes_output(self):
        self.assertNotEqual(self.tiles("golden-a", "r1", 0, 0),
                            self.tiles("golden-a", "r1", 1, 1))

    def test_rng_stream_is_stable(self):
        first = rng("seed", "r1", 0, 0)
        second = rng("seed", "r1", 0, 0)
        self.assertEqual([first.u64() for _ in range(8)],
                         [second.u64() for _ in range(8)])

    def test_rng_stream_separates_inputs(self):
        values = {
            rng(seed, region, cx, cy).u64()
            for seed, region, cx, cy in (
                ("seed", "r1", 0, 0), ("seed", "r1", 0, 1),
                ("seed", "r2", 0, 0), ("other", "r1", 0, 0),
            )
        }
        self.assertEqual(len(values), 4)

    def test_rng_stream_name_isolates_usages(self):
        self.assertNotEqual(rng("seed", "r1", 0, 0, "chunk").u64(),
                            rng("seed", "r1", 0, 0, "events").u64())


class TestPurityAndBounds(unittest.TestCase):
    """纯函数性与显式报错；生成结果不回写骨架表、不落盘。"""

    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_generate_chunk_does_not_mutate_tables(self):
        before = copy.deepcopy(self.tables)
        generate_chunk(self.tables, "golden-a", "r1", 2, 2)
        self.assertEqual(self.tables, before)

    def test_unknown_region_raises_value_error(self):
        with self.assertRaises(ValueError):
            generate_chunk(self.tables, "golden-a", "r99", 0, 0)

    def test_out_of_grid_coord_raises_value_error(self):
        with self.assertRaises(ValueError):
            generate_chunk(self.tables, "golden-a", "r1", 4, 0)
        with self.assertRaises(ValueError):
            generate_chunk(self.tables, "golden-a", "r7", 2, 0)

    def test_empty_pool_yields_empty_encounter_weights(self):
        chunk = generate_chunk(self.tables, "golden-a", "r7", 1, 1)
        self.assertEqual(chunk["encounter_weights"]["day"], {})
        self.assertEqual(len(encode_tiles(chunk["tiles"])), CHUNK_SIZE * CHUNK_SIZE)

    def test_all_terrains_are_registered(self):
        chunk = generate_chunk(self.tables, "golden-a", "r1", 0, 0)
        self.assertEqual(sum(chunk["terrain_counts"].values()),
                         CHUNK_SIZE * CHUNK_SIZE)
        self.assertEqual(set(chunk["terrain_counts"]),
                         set(self.tables["encounters.json"]["terrain"]))

    def test_weights_exclude_catch_rate(self):
        """人裁决 S-02 回归锁：改捕捉难度不得影响遭遇权重。"""
        altered = copy.deepcopy(self.tables)
        for creature in altered["species.json"]["creatures"]:
            creature["base_catch"] = 0.99
        a = generate_chunk(self.tables, "golden-a", "r1", 0, 0)
        b = generate_chunk(altered, "golden-a", "r1", 0, 0)
        self.assertEqual(a["encounter_weights"], b["encounter_weights"])

    def test_weights_equal_terrain_mean_times_phase(self):
        """权重 = 区块地形权重均值 × 时段权重；同 pool 内各物种相同。"""
        chunk = generate_chunk(self.tables, "golden-a", "r1", 0, 0)
        regions = self.tables["topology.json"]["regions"]
        pool = next(r["pool"] for r in regions if r["id"] == "r1")
        terrain_weight = self.tables["encounters.json"]["terrain_weight"]
        time_weight = self.tables["encounters.json"]["time_weight"]
        mean = sum(terrain_weight[k] * v for k, v in chunk["terrain_counts"].items()) \
            / (CHUNK_SIZE * CHUNK_SIZE)
        for phase, weights in chunk["encounter_weights"].items():
            self.assertEqual(set(weights), set(pool))
            self.assertEqual(set(weights.values()),
                             {round(mean * time_weight[phase], 6)})


if __name__ == "__main__":
    unittest.main()
