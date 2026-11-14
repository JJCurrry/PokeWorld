"""单命令四道门：规则 -> 编译 -> 测试 -> 数据可加载。

四道门先行：门不绿，不写功能；功能每加一点立刻被门验收。
F-16：拒绝在优化模式运行（assert 会被剥离，验证墙可能假绿）。
F-22：每一步都有异常兜底，失败时输出 `GATE n FAILED: 原因`，绝不静默 traceback。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gate  # noqa: E402
from src import schema  # noqa: E402


def failed(n: int, message: str) -> int:
    print(f"GATE {n} FAILED: {message}")
    return 1


def step(n: int, label: str) -> None:
    print(f"[{n}/4] {label} ...", flush=True)


# 第 0 道前置自检：主动在 -O 子进程里投毒，证明显式校验没有被优化模式剥离。
# 复评 R-06：探针扩到 3 个 validate_*，并直接验证 main() 的 -O / PYTHONOPTIMIZE 拦截分支，
# 使门内证据与被 skip 的两个用例**等价**，而不是只测一个函数。
OPTIMIZE_PROBE = (
    "import sys; sys.path.insert(0, '.')\n"
    "from src import schema\n"
    "cases = (\n"
    "    (schema.validate_topology, {'schema_version': 1, 'start': 'r1', 'abilities': [], 'regions': [], 'edges': []}),\n"
    "    (schema.validate_species, {'schema_version': 2}),\n"
    "    (schema.validate_encounters, {'schema_version': 2}),\n"
    ")\n"
    "for fn, bad in cases:\n"
    "    try:\n"
    "        fn(bad)\n"
    "    except schema.SchemaError:\n"
    "        continue\n"
    "    raise SystemExit('校验被优化模式剥离')\n"
    "print('OPTIMIZE_SAFE')\n"
)


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["POKEWORLD_GATE_CHILD"] = "1"  # 让测试门跳过会再启动本脚本的用例，防递归
    env.pop("PYTHONOPTIMIZE", None)
    return env


def run_cmd(args: list[str]) -> int:
    return subprocess.run(args, cwd=ROOT, env=child_env()).returncode


def main() -> int:
    optimize = os.environ.get("PYTHONOPTIMIZE", "")
    if not __debug__ or optimize not in ("", "0"):
        return failed(0, "优化模式（python -O / PYTHONOPTIMIZE）下一律拒绝运行；"
                         "assert 会被剥离导致验证墙假绿，请用普通解释器重跑")

    step(0, "优化模式自检（-O 投毒 + 拦截分支等价验证）")
    env_optimize = child_env()
    env_optimize["PYTHONOPTIMIZE"] = "1"
    try:
        probe = subprocess.run([sys.executable, "-O", "-c", OPTIMIZE_PROBE], cwd=ROOT,
                               env=child_env(), capture_output=True, text=True, timeout=30)
        refusal = subprocess.run([sys.executable, "-O", "tools/verify_all.py"], cwd=ROOT,
                                 env=child_env(), capture_output=True, text=True, timeout=30)
        refusal_env = subprocess.run([sys.executable, "tools/verify_all.py"], cwd=ROOT,
                                     env=env_optimize, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return failed(0, f"无法执行优化模式自检：{exc}")
    if probe.returncode or "OPTIMIZE_SAFE" not in probe.stdout:
        return failed(0, f"优化模式下显式校验失效：{probe.stdout.strip()} {probe.stderr.strip()}")
    for label, result in (("-O", refusal), ("PYTHONOPTIMIZE=1", refusal_env)):
        if (result.returncode == 0 or "GATE 0 FAILED" not in result.stdout
                or "ALL GATES GREEN" in result.stdout):
            return failed(0, f"{label} 拦截分支失效：exit={result.returncode} {result.stdout.strip()}")

    step(1, "规则门 gate.run()")
    try:
        problems = gate.run(ROOT)
    except Exception as exc:  # 规则门自身异常也要会说话
        return failed(1, f"规则门自身异常 {type(exc).__name__}: {exc}")
    if problems:
        for item in problems:
            print(item)
        return failed(1, f"共 {len(problems)} 条违规，逐条见上方")

    step(2, "编译门 compileall")
    try:
        rc = run_cmd([sys.executable, "-m", "compileall", "-q", "src", "tools", "tests"])
    except OSError as exc:
        return failed(2, f"无法启动编译门：{exc}")
    if rc:
        return failed(2, "compileall 发现语法错误")

    step(3, "测试门 unittest")
    try:
        rc = run_cmd([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    except OSError as exc:
        return failed(3, f"无法启动测试门：{exc}")
    if rc:
        return failed(3, "unittest 有用例失败")

    step(4, "数据可加载门 load_all() + verify_manifest()")
    try:
        tables = schema.load_all(ROOT)
        schema.verify_manifest(ROOT)
        topo = tables["topology.json"]
        counts = f"regions={len(topo['regions'])} edges={len(topo['edges'])} " \
                 f"creatures={len(tables['species.json']['creatures'])}"
    except (schema.SchemaError, OSError, ValueError) as exc:
        return failed(4, f"数据表不可用：{exc}")
    print(f"  {counts}")

    print("ALL GATES GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
