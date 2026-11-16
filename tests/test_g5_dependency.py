"""G5 可选依赖（F4）：缺失模拟、`ViewUnavailable` 明确提示、验证墙优雅跳过。

关键证据来自**真实子进程**：装了 pygame 的机器用 `POKEWORLD_NO_PYGAME=1`
模拟缺失，跑 `tools/verify_all.py` 与 `-m src.main --window`，断言仍全绿且不漏
traceback；不是靠注释自称「会优雅跳过」。设计依据 `ADR-005` §决定 3。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.view import deps  # noqa: E402

NESTED_IN_GATE = os.environ.get("POKEWORLD_GATE_CHILD") == "1"


def run_py(args, env_patch=None, timeout=120):
    env = os.environ.copy()
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    if env_patch:
        env.update(env_patch)
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


class TestG5Dependency(unittest.TestCase):
    def test_dependency_facts_are_machine_readable(self):
        facts = deps.dependency_facts()
        self.assertEqual(facts["module"], "pygame")
        self.assertEqual(facts["disable_env"], "POKEWORLD_NO_PYGAME")
        self.assertTrue(facts["headless_available"])
        self.assertIn("requirements.txt", facts["install_hint"])

    def test_disable_env_switches_availability_and_require_raises(self):
        with mock.patch.dict(os.environ, {deps.DISABLE_ENV: "1"}):
            self.assertFalse(deps.pygame_available())
            self.assertFalse(deps.dependency_facts()["available"])
            with self.assertRaises(deps.ViewUnavailable) as caught:
                deps.require_pygame()
        message = str(caught.exception)
        self.assertIn(deps.INSTALL_HINT, message)
        self.assertIn("--headless", message)
        self.assertIn(deps.DISABLE_ENV, message)

    def test_probe_never_imports_pygame_at_module_level(self):
        source = (ROOT / "src/view/deps.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Import)
                   and any(alias.name.split(".")[0] == "pygame"
                           for alias in node.names)]
        self.assertEqual(len(imports), 1, "只允许 require_pygame 内一处延迟导入")
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "require_pygame"]
        self.assertEqual(len(functions), 1)
        self.assertLess(functions[0].lineno, imports[0].lineno)
        self.assertGreater(functions[0].end_lineno, imports[0].lineno)
        self.assertFalse(any(
            isinstance(node, ast.Import)
            and any(alias.name.split(".")[0] == "pygame"
                    for alias in node.names)
            for node in tree.body))

    def test_window_cli_degrades_to_headless_without_dependency(self):
        result = run_py(["-m", "src.main", "--window"],
                        {deps.DISABLE_ENV: "1"}, timeout=90)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["window"], "unavailable")
        self.assertEqual(payload["fallback"], "headless")
        self.assertEqual(payload["hint"], deps.INSTALL_HINT)
        self.assertTrue(payload["complete"])

    def test_headless_cli_works_without_dependency(self):
        result = run_py(["-m", "src.main", "--headless"],
                        {deps.DISABLE_ENV: "1"}, timeout=90)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["complete"])

    @unittest.skipIf(NESTED_IN_GATE, "会再启动 verify_all，门内由外层调用覆盖，避免递归")
    def test_verify_all_is_green_when_dependency_is_missing(self):
        result = run_py(["tools/verify_all.py"],
                        {deps.DISABLE_ENV: "1"}, timeout=180)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("ALL GATES GREEN", output)
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
