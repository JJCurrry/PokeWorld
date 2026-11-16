"""G4 存档 roundtrip（DoD E2 / 不变量 #6 的未来符号在此落地）。

证据：确定性字节、白名单拒绝、生成结果不入档、同 seed 可重建、`-O` 下校验不失效。
"""
from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.gen.chunk import generate_chunk  # noqa: E402
from src.schema import SchemaError  # noqa: E402
from src.world.save import (  # noqa: E402
    FLAG_PREFIXES, FORBIDDEN_KEYS, SAVE_KEYS, SaveData, decode, encode,
)

SAVE_SOURCE = ROOT / "src" / "world" / "save.py"

OPTIMIZE_PROBE = (
    "import sys, json; sys.path.insert(0, '.')\n"
    "from src.world.save import SaveData, decode, encode\n"
    "from src.schema import SchemaError\n"
    "raw = json.loads(encode(SaveData('w', ('region:r1',), (('c01', 1, 0, 0),))))\n"
    "for key in ('tiles', 'chunks'):\n"
    "    bad = dict(raw); bad[key] = []\n"
    "    try:\n"
    "        decode(json.dumps(bad))\n"
    "    except SchemaError:\n"
    "        continue\n"
    "    raise SystemExit('校验被优化模式剥离')\n"
    "print('OPTIMIZE_SAFE')\n"
)


def _canonical_save() -> SaveData:
    return SaveData(
        "save-test",
        ("ability:league_pass", "atlas:c01", "milestone:atlas",
         "region:r1", "region:r2", "script:shore"),
        (("c01", 2, 0, 3), ("c03", 16, 2, 1)),
    )


class TestRoundtrip(unittest.TestCase):
    def test_save_data_has_exactly_three_fields(self):
        self.assertEqual(tuple(f.name for f in dataclasses.fields(SaveData)),
                         SAVE_KEYS)
        self.assertEqual(set(SAVE_KEYS),
                         {"world_seed", "flags", "party"})

    def test_encode_bytes_are_deterministic_and_canonical(self):
        save = _canonical_save()
        text = encode(save)
        self.assertEqual(text, encode(save))
        self.assertEqual(text, encode(decode(text)))
        payload = json.loads(text)
        self.assertEqual(set(payload), set(SAVE_KEYS))
        self.assertEqual(payload["flags"], sorted(set(save.flags)))
        # 排序键 + 固定分隔符，无多余空白。
        self.assertNotIn(", ", text)
        self.assertNotIn(": ", text)

    def test_decode_encode_roundtrip(self):
        save = _canonical_save()
        self.assertEqual(decode(encode(save)), save)

    def test_encode_is_pure(self):
        save = _canonical_save()
        before = (save.world_seed, save.flags, save.party)
        encode(save)
        self.assertEqual((save.world_seed, save.flags, save.party), before)


class TestDecodeWhitelist(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(encode(_canonical_save()))

    def _decode(self, payload) -> SaveData:
        return decode(json.dumps(payload, ensure_ascii=False))

    def test_every_generated_result_key_is_rejected(self):
        for key in FORBIDDEN_KEYS:
            bad = dict(self.raw)
            bad[key] = []
            with self.assertRaises(SchemaError, msg=key):
                self._decode(bad)
            self.assertIn(key, str(self._get_error(bad)))

    def _get_error(self, payload) -> Exception:
        try:
            self._decode(payload)
        except SchemaError as exc:
            return exc
        self.fail("应当抛出 SchemaError")

    def test_extra_and_missing_keys_are_rejected(self):
        bad = dict(self.raw)
        bad["tick"] = 9
        with self.assertRaises(SchemaError):
            self._decode(bad)
        for key in SAVE_KEYS:
            missing = dict(self.raw)
            del missing[key]
            with self.assertRaises(SchemaError, msg=key):
                self._decode(missing)

    def test_unknown_flag_prefix_and_flag_shape_are_rejected(self):
        for flag in ("unknown:x", "", "region:" + "x" * 200, "region:a\nb"):
            bad = dict(self.raw)
            bad["flags"] = [flag]
            with self.assertRaises(SchemaError, msg=repr(flag)):
                self._decode(bad)
        bad = dict(self.raw)
        bad["flags"] = "region:r1"
        with self.assertRaises(SchemaError):
            self._decode(bad)
        for prefix in FLAG_PREFIXES:
            good = dict(self.raw)
            good["flags"] = [prefix + "x"]
            self.assertEqual(len(self._decode(good).flags), 1)

    def test_malformed_party_is_rejected(self):
        bad_rows = (
            ("c01", 1, 0),                 # 长度
            ("c01", 0, 0, 0),             # 等级
            ("c01", 999, 0, 0),           # 等级上界
            ("c01", True, 0, 0),          # bool 冒充 int
            ("c01", 1, 9, 0),             # 阶段
            ("c01", 1, 0, 999),           # 个体值
            "c01",                        # 非列表
            [1, 2, 3, 4],                 # cid 非字符串
        )
        for row in bad_rows:
            bad = dict(self.raw)
            bad["party"] = [row]
            with self.assertRaises(SchemaError, msg=str(row)):
                self._decode(bad)

    def test_bad_json_and_non_string_are_rejected(self):
        for text in ("{", "[]", "null", "123", ""):
            with self.assertRaises(SchemaError, msg=text):
                decode(text)
        with self.assertRaises(SchemaError):
            decode(b'{"world_seed":"w"}')
        with self.assertRaises(SchemaError):
            encode("not-a-save")


class TestNoGeneratedResultsInSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_encoded_bytes_contain_no_generated_result_key(self):
        text = encode(_canonical_save())
        for key in FORBIDDEN_KEYS:
            self.assertNotIn(key, text)

    def test_chunk_is_rebuildable_from_world_seed(self):
        first = generate_chunk(self.tables, "save-test", "r1", 2, 1)
        second = generate_chunk(self.tables, "save-test", "r1", 2, 1)
        self.assertEqual(first, second)
        save = _canonical_save()
        self.assertEqual(decode(encode(save)), save)
        self.assertNotIn("tiles_digest", encode(save))

    def test_validation_survives_optimize_mode(self):
        result = subprocess.run([sys.executable, "-O", "-c", OPTIMIZE_PROBE],
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=30)
        self.assertEqual(result.returncode, 0,
                         f"{result.stdout} {result.stderr}")
        self.assertIn("OPTIMIZE_SAFE", result.stdout)

    def test_save_module_has_no_assert_or_io(self):
        tree = ast.parse(SAVE_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual([n.lineno for n in ast.walk(tree)
                          if isinstance(n, ast.Assert)], [])
        banned = {"open", "print", "input", "eval", "exec", "compile", "getattr"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, banned)


if __name__ == "__main__":
    unittest.main()
