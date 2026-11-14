"""优化模式防护（G0-R / 冷眼 F-16 回归）。

根因：旧版全部校验写在 assert 上，python -O 或 PYTHONOPTIMIZE=1 会剥离，
数据损坏时四道门照样输出 ALL GATES GREEN。本文件在真实子进程里复现该场景。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# verify_all.py 第 3 门会 discover 本文件；带此标记时只跳过「会再启动 verify_all」的两个用例，
# 防止「门 → 测试 → 门」无限递归；其余 -O 用例在门内照常运行。
NESTED_IN_GATE = os.environ.get("POKEWORLD_GATE_CHILD") == "1"


def run_py(args, env_patch=None):
    env = os.environ.copy()
    if env_patch:
        env.update(env_patch)
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


BAD_TOPOLOGY = {
    "schema_version": 1,
    "start": "r1",
    "abilities": [],
    "regions": [],
    "edges": [],
}


class TestOptimizeMode(unittest.TestCase):
    @unittest.skipIf(NESTED_IN_GATE, "会再启动 verify_all，嵌套时跳过；门内由第 0 道自检覆盖")
    def test_verify_all_refuses_python_O(self):
        r = run_py(["-O", "tools/verify_all.py"])
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("GATE 0 FAILED", r.stdout + r.stderr)
        self.assertNotIn("ALL GATES GREEN", r.stdout)

    @unittest.skipIf(NESTED_IN_GATE, "会再启动 verify_all，嵌套时跳过；门内由第 0 道自检覆盖")
    def test_verify_all_refuses_pythonoptimize_env(self):
        r = run_py(["tools/verify_all.py"], {"PYTHONOPTIMIZE": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("GATE 0 FAILED", r.stdout + r.stderr)
        self.assertNotIn("ALL GATES GREEN", r.stdout)

    def test_schema_still_raises_under_O(self):
        code = (
            "import sys, json; sys.path.insert(0, '.')\n"
            "from src import schema\n"
            "d = json.loads(sys.argv[1])\n"
            "try:\n"
            "    schema.validate_topology(d)\n"
            "except schema.SchemaError:\n"
            "    print('SCHEMA_ERROR_CAUGHT')\n"
            "else:\n"
            "    raise SystemExit('NOT_CAUGHT: 校验被优化模式剥离')\n"
        )
        r = run_py(["-O", "-c", code, json.dumps(BAD_TOPOLOGY)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SCHEMA_ERROR_CAUGHT", r.stdout)

    def test_manifest_still_checked_under_O(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            for name in ("topology.json", "species.json", "encounters.json"):
                (root / "data" / name).write_bytes((ROOT / "data" / name).read_bytes())
            (root / "data" / "MANIFEST.sha256").write_bytes(
                (ROOT / "data" / "MANIFEST.sha256").read_bytes())
            p = root / "data" / "topology.json"
            p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            code = (
                "import sys; sys.path.insert(0, r'{}')\n".format(ROOT.as_posix())
                + "from src import schema\n"
                + "try:\n"
                + "    schema.verify_manifest(r'{}')\n".format(root.as_posix())
                + "except schema.SchemaError:\n"
                + "    print('MANIFEST_MISMATCH_CAUGHT')\n"
                + "else:\n"
                + "    raise SystemExit('NOT_CAUGHT: hash 校验被优化模式剥离')\n"
            )
            r = run_py(["-O", "-c", code])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("MANIFEST_MISMATCH_CAUGHT", r.stdout)

    # 不在此处调用正常模式的 verify_all：它第 3 门会 discover 本文件并造成无限递归。
    # 正常模式全绿由外部单命令 `python tools/verify_all.py` 单独证明。


if __name__ == "__main__":
    unittest.main()
