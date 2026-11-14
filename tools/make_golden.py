"""重建 golden seed 快照（G1 · **人确认后方可运行**）。

不变量 #5 / ADR-001 §后果：生成器或快照变更须人确认，禁止 AI 顺手更新
快照把测试「修绿」。G1-v1 → G1-v2 的口径变更由 2026-11-14 17:56 人裁决
（S-02 拆通道）确认，记录见 `docs/工单/G1-区块生成器.md`。人确认后的操作路径：
  1. 在 `docs/工单/G1-区块生成器.md`「变更记录」写明人确认结论；
  2. `python tools/make_golden.py` 重建 `tests/golden_seed.json`；
  3. 把打印出的 SHA256 登记到 `tools/gate.py::GOLDEN_SNAPSHOT_SHA256`；
  4. `python tools/verify_all.py` 全绿，并把新旧哈希一并留在工单变更记录里。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.gen import CHUNK_SIZE, encode_tiles, generate_chunk  # noqa: E402

SNAPSHOT_PATH = ROOT / "tests" / "golden_seed.json"
GENERATOR_VERSION = "G1-v2"  # 人裁决 S-02 后：遭遇权重不含捕捉难度

# 覆盖：多世界种子、多区域、多坐标、字符串 / 整数种子、空 pool 的边界区域。
CASES = (
    ("golden-a", "r1", 0, 0),
    ("golden-a", "r1", 3, 3),
    ("golden-a", "r3", 1, 2),
    ("golden-a", "r7", 1, 1),
    ("golden-b", "r1", 0, 0),
    ("golden-b", "r5", 2, 1),
    (20261114, "r2", 0, 3),
    ("golden-b", "r7", 0, 0),
)


def build(tables: dict) -> dict:
    """由骨架表 + 生成器构造快照内容，纯函数、无 I/O。"""
    cases = []
    for seed, region, cx, cy in CASES:
        chunk = generate_chunk(tables, seed, region, cx, cy)
        cases.append({
            "world_seed": seed,
            "region": region,
            "cx": cx,
            "cy": cy,
            "tiles": encode_tiles(chunk["tiles"]),
            "terrain_counts": chunk["terrain_counts"],
            "weights": chunk["encounter_weights"],
        })
    return {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "chunk_size": CHUNK_SIZE,
        "weights_kind": "relative_terrain_time_only",
        "note": "由 tools/make_golden.py 重建；变更须人确认（不变量 #5 / ADR-001）；G1-v2 起权重不含捕捉难度",
        "cases": cases,
    }


def main() -> int:
    tables = schema.load_all(ROOT)
    schema.verify_manifest(ROOT)  # 生成前确认骨架表未被改动
    payload = json.dumps(build(tables), ensure_ascii=False, indent=2) + "\n"
    SNAPSHOT_PATH.write_bytes(payload.encode("utf-8"))  # 固定 UTF-8 + LF
    digest = hashlib.sha256(SNAPSHOT_PATH.read_bytes()).hexdigest()
    print(f"WROTE {SNAPSHOT_PATH.relative_to(ROOT).as_posix()}")
    print(f"CASES {len(CASES)}  SIZE {SNAPSHOT_PATH.stat().st_size}")
    print(f"SHA256 {digest}")
    print("把该哈希登记到 tools/gate.py::GOLDEN_SNAPSHOT_SHA256（须人确认）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
