"""数据契约测试（G0-R）：独立解析 + 畸形数据注入。

冷眼 F-14 指出旧版 6 个断言只是把 schema.load_all 的逻辑重抄一遍（自证），
且全部建在 assert 上（F-16）。本版：① 用独立实现核对三表；② 主动投毒并
断言抛 SchemaError；③ 结构测试禁止生产代码出现 ast.Assert。
"""
from __future__ import annotations

import ast
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402


def read_json(name):
    """独立解析：刻意不经过 schema.load_all / validate_*。"""
    with (ROOT / "data" / name).open(encoding="utf-8") as f:
        return json.load(f)


MUTATIONS = (
    ("topology.json", lambda d: d["regions"].append(dict(d["regions"][0])), "区域 id 重复"),
    ("topology.json", lambda d: d.update(start="ghost"), "start 必须指向已存在区域"),
    ("topology.json", lambda d: d["edges"][0].update({"from": "ghost"}), "边引用了不存在的区域"),
    ("topology.json", lambda d: d["edges"][1].update(requires=["ghost_gate"]), "边声明了未登记能力"),
    ("topology.json", lambda d: d["regions"][0].update(pool=["c99"]), "pool 引用了未登记潮灵"),
    ("species.json", lambda d: d["creatures"][0].update(type="ghost"), "未知属性"),
    ("species.json", lambda d: d["creatures"][0].update(base_catch=1.5), "base_catch 越界"),
    ("species.json", lambda d: d["creatures"].append(dict(d["creatures"][0])), "潮灵 id 重复"),
    ("encounters.json", lambda d: d["type_chart"].pop("frost"), "克制矩阵必须覆盖全部 6 系"),
    ("encounters.json", lambda d: d["terrain_weight"].pop("grass"), "地形与权重不一致"),
)


class TestIndependentParse(unittest.TestCase):
    def test_tables_independently_parseable(self):
        for name in schema.PROTECTED:
            with self.subTest(name=name):
                data = read_json(name)
                self.assertIsInstance(data, dict)
                self.assertEqual(data["schema_version"], 1)

    def test_expected_shape_without_schema_helpers(self):
        topo = read_json("topology.json")
        species = read_json("species.json")
        encounters = read_json("encounters.json")
        self.assertEqual(len(topo["regions"]), 7)
        self.assertEqual(len(topo["edges"]), 6)
        self.assertEqual(len(species["creatures"]), 8)
        self.assertEqual(len(encounters["type_chart"]), 6)
        for row in encounters["type_chart"].values():
            self.assertEqual(len(row), 6)
        ids = {r["id"] for r in topo["regions"]}
        self.assertIn(topo["start"], ids)
        for edge in topo["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)

    def test_tables_load_through_schema(self):
        tables = schema.load_all(ROOT)
        self.assertEqual(set(tables), set(schema.PROTECTED))

    def test_manifest_matches_tables(self):
        schema.verify_manifest(ROOT)
        text = (ROOT / "data" / "MANIFEST.sha256").read_bytes()
        self.assertNotIn(b"\r\n", text, "MANIFEST 必须 LF 行尾，标准 sha256sum -c 才能消费")


class TestPoisonedData(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "data").mkdir()
        self.tables = {name: read_json(name) for name in schema.PROTECTED}

    def _write(self, tables):
        for name, data in tables.items():
            (self.root / "data" / name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_each_mutation_raises_schema_error(self):
        for name, mutate, fragment in MUTATIONS:
            with self.subTest(case=fragment):
                tables = copy.deepcopy(self.tables)
                mutate(tables[name])
                self._write(tables)
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.load_all(self.root)
                self.assertIn(fragment, str(ctx.exception))

    def test_verify_manifest_detects_tampering(self):
        self._write(self.tables)
        (self.root / "data" / "MANIFEST.sha256").write_text(
            (ROOT / "data" / "MANIFEST.sha256").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        p = self.root / "data" / "topology.json"
        p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(schema.SchemaError):
            schema.verify_manifest(self.root)

    def test_missing_table_raises_schema_error(self):
        self._write(self.tables)
        (self.root / "data" / "encounters.json").unlink()
        with self.assertRaises(schema.SchemaError):
            schema.load_all(self.root)

    def test_malformed_manifest_line_raises_schema_error(self):
        self._write(self.tables)
        (self.root / "data" / "MANIFEST.sha256").write_text("garbage line\n", encoding="utf-8")
        with self.assertRaises(schema.SchemaError):
            schema.verify_manifest(self.root)


class TestNoAssertInProduction(unittest.TestCase):
    def test_production_code_contains_no_assert(self):
        offenders = []
        for folder in ("src", "tools"):
            for path in (ROOT / folder).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assert):
                        offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
        self.assertEqual(offenders, [], "生产代码禁用 assert：python -O 会剥离全部校验")


if __name__ == "__main__":
    unittest.main()
