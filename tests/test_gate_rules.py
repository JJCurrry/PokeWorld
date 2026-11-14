"""规则门失败用例（G0-R）：每条规则都有故意违规输入，撞墙报错含三要素。

复现自 docs/评审/G0-冷眼.md 的 F-01 / F-14 / F-15：旧版只有 5 个用例、
缺 R2、只断言规则名子串、且从不调用 gate.run() 扫描真实文件。
本文件位于 tests/，按 gate.SCAN_DIRS 设计不参与生产扫描（违规字符串是测试数据）。
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gate  # noqa: E402
from src import schema  # noqa: E402

ABILITIES = ("rock_smash", "surf", "strength", "league_pass")

# 规则名 + 文件路径(:行号) + 修正建议 —— 缺一不可
VIO = re.compile(r"^\[(R\d+) ([a-z_]+)\] (\S+?)(?::(\d+))? -> (\S.*)$")

# 冷眼 F-15 实测 6 个绕过 + 2 个原本命中的样例，全部固化
R1_SAMPLES = (
    "import random\n",
    "from random import randint\n",
    "from numpy.random import randint\n",
    "import numpy as np\nx = np.random.rand()\n",
    '__import__("random")\n',
    'import importlib\nimportlib.import_module("random")\n',
    "import time\nt = time.time()\n",
    "import secrets\ns = secrets.randbelow(10)\n",
    # 复评 R-04 新发现的 6 个绕过，全部固化为回归用例
    'eval("__import__(\'random\')")\n',
    'exec("import random")\n',
    'from importlib import import_module as im\nim("random")\n',
    "from . import random\n",
    "__import__(mod)\n",
    'getattr(__builtins__, "__import__")("random")\n',
)
R3_SAMPLES = (
    'key = "surf"\n',
    'key = "su" + "rf"\n',
    'key = "SURF".lower()\n',
    'key = f"sur" f"f"\n',
    'key = "rock" + "_" + "smash"\n',
    'if has("cut"): pass\n',
    'if require("unknown_gate"): pass\n',
)
R4_SAMPLES = (
    '{"name": "皮卡丘"}',
    '{"name": "pokemon"}',
    '{"name": "Pokemon"}',
    '{"name": "Pokémon"}',
    '{"name": "宝 可 梦"}',
    '{"name": "口袋妖怪"}',
    '{"name": "精灵宝可梦"}',
)


def assert_hit(testcase, items, rule, where=None):
    """三要素断言：规则名、文件(:行号)、修正建议。"""
    hits = [v for v in items if v.startswith(f"[{rule} ")]
    testcase.assertTrue(hits, f"未撞上 {rule}：{items}")
    for v in hits:
        m = VIO.match(v)
        testcase.assertIsNotNone(m, f"报错格式缺三要素：{v}")
        testcase.assertGreaterEqual(len(m.group(5)), 12, f"修正建议过短：{v}")
        # 复评 R-11：不只验长度，还要验「怎么改」确实带动作词
        testcase.assertTrue(
            any(k in m.group(5) for k in ("不变量", "禁止", "改用", "须", "请", "修复")),
            f"修正建议缺动作词：{v}")
        if where:
            testcase.assertIn(where, m.group(3), v)
    return hits


class TestRuleStrings(unittest.TestCase):
    """纯函数层：每条规则的绕过样例必须命中，报错必须会说话。"""

    def test_r1_bypass_samples(self):
        for src in R1_SAMPLES:
            with self.subTest(src=src.strip()):
                out = gate.check_source(src, "src/gen/probe.py", ABILITIES)
                assert_hit(self, out, "R1", "src/gen/probe.py")

    def test_r3_bypass_samples(self):
        for src in R3_SAMPLES:
            with self.subTest(src=src.strip()):
                out = gate.check_source(src, "src/world/probe.py", ABILITIES)
                assert_hit(self, out, "R3", "src/world/probe.py")

    def test_r4_normalized_variants(self):
        for text in R4_SAMPLES:
            with self.subTest(text=text):
                out = gate.check_data_value(text, "data/species.json")
                assert_hit(self, out, "R4", "data/species.json")

    def test_clean_source_passes(self):
        out = gate.check_source("def f(x):\n    return x + 1\n", "src/gen/ok.py", ABILITIES)
        self.assertEqual(out, [])

    def test_r3_avoids_common_false_positives(self):
        """复评 R-05：`check` / 非字符串参数的能力判断不应误报。"""
        for src in ('check("hello")\n', "has(1)\n", "def f(x):\n    return x + 1\n"):
            with self.subTest(src=src.strip()):
                out = gate.check_source(src, "src/gen/ok.py", ABILITIES)
                self.assertFalse(any(v.startswith("[R3 ") for v in out), (src, out))

    def test_r4_clean_table_passes(self):
        for name in schema.PROTECTED:
            text = (ROOT / "data" / name).read_text(encoding="utf-8")
            self.assertEqual(gate.check_data_value(text, f"data/{name}"), [], name)

    def test_violation_reports_line_number(self):
        out = gate.check_source("x = 1\nimport random\n", "src/gen/x.py", ABILITIES)
        m = VIO.match(assert_hit(self, out, "R1")[0])
        self.assertEqual(m.group(4), "2")


class TestGateEndToEnd(unittest.TestCase):
    """端到端：真实文件 + gate.run()，证明墙拦得住真实仓库而非自造字符串。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "data").mkdir()
        for name in schema.PROTECTED:
            shutil.copyfile(ROOT / "data" / name, self.root / "data" / name)
        shutil.copyfile(ROOT / "data" / "MANIFEST.sha256", self.root / "data" / "MANIFEST.sha256")
        for folder in ("src", "tools", "docs"):
            (self.root / folder).mkdir()
        (self.root / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
        shutil.copyfile(ROOT / "docs" / "GDD-v0.md", self.root / "docs" / "GDD-v0.md")
        shutil.copyfile(ROOT / "docs" / "待裁定项.md", self.root / "docs" / "待裁定项.md")

    def test_clean_repo_passes(self):
        self.assertEqual(gate.run(self.root), [])

    def test_r1_real_file_is_scanned(self):
        (self.root / "src" / "bad.py").write_text("import random\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R1", "src/bad.py")

    def test_root_level_py_is_scanned(self):
        (self.root / "stray.py").write_text("import random\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R1", "stray.py")

    def test_r2_manifest_mismatch(self):
        p = self.root / "data" / "topology.json"
        p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R2", "MANIFEST.sha256")

    def test_r2_corrupted_table_is_reported(self):
        p = self.root / "data" / "species.json"
        p.write_text("{ broken json", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R2", "data/")

    def test_r3_real_file_is_scanned(self):
        (self.root / "src" / "gate.py").write_text('if has("cut"): pass\n', encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R3", "src/gate.py")

    def test_r4_real_table_is_scanned(self):
        p = self.root / "data" / "species.json"
        p.write_text(p.read_text(encoding="utf-8").replace("汐芽", "皮卡丘"), encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R4", "data/species.json")

    def test_r5_unregistered_asset(self):
        gdd = self.root / "docs" / "GDD-v0.md"
        gdd.write_text(gdd.read_text(encoding="utf-8").replace("汐芽", "已移除"), encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R5", "GDD-v0.md")

    def test_r5_missing_provenance_doc(self):
        (self.root / "docs" / "GDD-v0.md").unlink()
        assert_hit(self, gate.run(self.root), "R5", "GDD-v0.md")

    def test_r5_forged_provenance_is_rejected(self):
        """复评 R-03：把资产名写进 GDD 正文任意位置不得冒充溯源登记行。"""
        gdd = self.root / "docs" / "GDD-v0.md"
        lines = [ln for ln in gdd.read_text(encoding="utf-8").splitlines()
                 if not ln.startswith("| 潮灵 `c01`")]
        lines.append("正文提及 c01 汐芽（但不是溯源表行）")
        gdd.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R5", "GDD-v0.md")

    def test_r5_assumption_marks_are_checked(self):
        """复评 R-10：占位标记必须在待裁定项清单中有对应条目。"""
        doc = self.root / "docs" / "待裁定项.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("ASSUMPTION-A10", "已删除"),
                       encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R5", "待裁定项.md")

    def test_r6_unregistered_source_dir(self):
        d = self.root / "rogue"
        d.mkdir()
        (d / "x.py").write_text("import random\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R6", "rogue")

    def test_r6_excluded_dir_py_is_reported(self):
        """复评 R-12：`docs/` 等排除目录内出现 .py 时不得静默形成扫描盲区。"""
        (self.root / "docs" / "helper.py").write_text("import random\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R6", "docs/")

    def test_syntax_error_is_reported_not_crashing(self):
        (self.root / "src" / "broken.py").write_text("def oops(\n", encoding="utf-8")
        assert_hit(self, gate.run(self.root), "R0", "src/broken.py")

    def test_tests_dir_is_not_production_scanned(self):
        d = self.root / "tests"
        d.mkdir()
        (d / "fixture.py").write_text("import random\n", encoding="utf-8")
        out = gate.run(self.root)
        self.assertFalse(any("tests/fixture.py" in v for v in out), out)


if __name__ == "__main__":
    unittest.main()
