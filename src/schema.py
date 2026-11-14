"""骨架层数据契约（G0-R 参考实现）：只读加载 + 结构校验 + 完整性校验。

F-16 修复：全部校验经 `must()` 显式抛 `SchemaError`，**绝不使用 assert**——
`python -O` / `PYTHONOPTIMIZE` 会剥离 assert，使验证墙在数据损坏时假绿。
禁止在此模块写生成逻辑、全局可变状态或任何隐藏副作用。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROTECTED = ("topology.json", "species.json", "encounters.json")
TYPES = ("tide", "rock", "forest", "flame", "thunder", "frost")
BASE_LEN = 5


class SchemaError(ValueError):
    """数据表违反契约。可被 gate / verify_all 捕获并转成会说话的失败。"""


def must(condition: object, message: str) -> None:
    """显式校验；不依赖 `__debug__`，优化模式下同样生效。"""
    if not condition:
        raise SchemaError(message)


def root_of(path: str | Path | None = None) -> Path:
    return Path(path) if path is not None else Path(__file__).resolve().parents[1]


def load_table(root: Path, name: str) -> dict:
    path = root / "data" / name
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except OSError as exc:
        raise SchemaError(f"{name} 无法读取：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{name} 不是合法 JSON：{exc}") from exc


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SchemaError(f"{path.name} 无法计算哈希：{exc}") from exc


def validate_topology(d: dict) -> None:
    must(d.get("schema_version") == 1, "topology.schema_version 必须为 1")
    regions = d.get("regions")
    must(isinstance(regions, list), "topology.regions 必须是列表")
    ids = [r["id"] for r in regions]
    must(len(ids) == len(set(ids)), "区域 id 重复")
    must(d.get("start") in ids, "start 必须指向已存在区域")
    abilities = set(d.get("abilities", []))
    for e in d.get("edges", []):
        must(e["from"] in ids and e["to"] in ids, f"边引用了不存在的区域: {e}")
        must(set(e["requires"]) <= abilities, f"边声明了未登记能力: {e}")
    for r in regions:
        must(len(r["chunks"]) == 2, f"chunks 必须是 [w, h]: {r['id']}")


def validate_species(d: dict) -> None:
    must(d.get("schema_version") == 1, "species.schema_version 必须为 1")
    must(tuple(d.get("types", ())) == TYPES, "types 必须与契约一致")
    must(tuple(d.get("base_keys", ())) == ("hp", "power", "guard", "agility", "spirit"),
         "base_keys 必须与契约一致")
    creatures = d.get("creatures", [])
    ids = [c["id"] for c in creatures]
    must(len(ids) == len(set(ids)), "潮灵 id 重复")
    for c in creatures:
        must(c["type"] in TYPES, f"未知属性: {c['type']}")
        must(len(c["base"]) == BASE_LEN and all(isinstance(x, int) for x in c["base"]),
             f"base 必须是 {BASE_LEN} 个整数: {c['id']}")
        must(0 < c["base_catch"] <= 1, f"base_catch 越界: {c['id']}")


def validate_encounters(d: dict) -> None:
    must(d.get("schema_version") == 1, "encounters.schema_version 必须为 1")
    chart = d.get("type_chart", {})
    must(set(chart) == set(TYPES), "克制矩阵必须覆盖全部 6 系")
    for row in chart.values():
        must(set(row) == set(TYPES), "克制矩阵必须是 6x6 方阵")
    must(set(d.get("terrain", [])) == set(d.get("terrain_weight", {})), "地形与权重不一致")


def load_all(root: str | Path | None = None) -> dict:
    root = root_of(root)
    tables = {name: load_table(root, name) for name in PROTECTED}
    validate_topology(tables["topology.json"])
    validate_species(tables["species.json"])
    validate_encounters(tables["encounters.json"])
    species_ids = {c["id"] for c in tables["species.json"]["creatures"]}
    for r in tables["topology.json"]["regions"]:
        unknown = set(r["pool"]) - species_ids
        must(not unknown, f"区域 {r['id']} 的 pool 引用了未登记潮灵: {unknown}")
    return tables


def verify_manifest(root: str | Path | None = None) -> None:
    root = root_of(root)
    path = root / "data" / "MANIFEST.sha256"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaError(f"MANIFEST.sha256 无法读取：{exc}") from exc
    recorded: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        must(len(parts) == 2 and parts[1].strip(),
             f"MANIFEST 行格式非法：{line!r}；应为 '<sha256>  <文件名>'")
        digest, name = parts[0].strip(), parts[1].strip()
        must(len(digest) == 64, f"MANIFEST 中 {name} 的哈希长度非法")
        recorded[name] = digest
    must(set(recorded) == set(PROTECTED), "MANIFEST 覆盖的表不完整")
    for name in PROTECTED:
        must(recorded[name] == sha256(root / "data" / name),
             f"{name} 与 MANIFEST 不符：受保护数据改动须人确认后重建（不变量 #2）")
