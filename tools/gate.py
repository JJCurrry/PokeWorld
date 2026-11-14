"""G0-R2 质量门（会说话的墙）：基于 AST 的静态规则 + 数据完整性检查。

撞墙格式：`[R# rule] 文件:行 -> 怎么改`（规则名 + 位置 + 修正建议，三要素）。
扫描 `SCAN_DIRS` 与仓库根级 `*.py`；`tests/` 是测试数据不参与生产扫描，但其余排除目录
内出现 `.py` 会由 R6 报盲区。规则：R0 语法 / R1 裸随机 / R2 受保护数据 / R3 能力门 /
R4 第三方 IP / R5 资产与占位登记 / R6 扫描范围 / R7 golden seed 快照锁定。
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402

SCAN_DIRS = ("src", "tools")
EXCLUDED_DIRS = frozenset({
    ".git", "__pycache__", "tests", "docs", "data", ".venv", "venv",
    "build", "dist", ".workbuddy", ".idea", ".vscode",
})
# 只有这些排除目录允许含 .py（测试夹具 / 工具缓存），其余出现 .py 即报 R6 盲区
PY_ALLOWED_EXCLUDED = frozenset({
    ".git", "__pycache__", "tests", ".venv", "venv", "build", "dist",
    ".workbuddy", ".idea", ".vscode",
})
BANNED_ROOTS = frozenset({"random", "numpy", "time", "secrets", "datetime"})
BANNED_ATTRS = frozenset({"random", "randint", "randrange", "choice", "shuffle", "uniform", "gauss", "randbelow"})
DYNAMIC_IMPORTS = frozenset({"__import__", "import_module"})
DYNAMIC_EVAL = frozenset({"eval", "exec", "compile", "getattr"})
# 危险表达式用完整词 / 模式匹配，不用 "import"/"random" 裸子串，
# 否则 `getattr(cfg, "import_path")`、`compile("important", ...)` 会误报（终局复核 N-01）。
DANGEROUS_EVAL = re.compile(
    r"__import__|import_module|\bimport\s+(?:random|numpy|time|secrets|datetime)\b|\brandom\b|\btime\s*\.",
    re.IGNORECASE)
EXACT_DANGEROUS_ATTRS = frozenset({"__import__", "import_module", "random", "randint", "time"})
ABILITY_CHECKS = frozenset({
    "has", "has_ability", "require", "requires", "check_ability",
    "unlock", "is_unlocked", "can_enter",
})
BANNED_WORDS = (
    "宝可梦", "pokemon", "皮卡丘", "口袋妖怪", "精灵宝可梦", "神奇宝贝",
    "pocket monsters", "nintendo", "任天堂", "game freak", "pokeball",
)
PROVENANCE_ROW = re.compile(r"^\|\s*潮灵\s*`?(c\d+)`?\s+(\S+?)\s*\|", re.MULTILINE)
# R7：golden seed 快照哈希由人确认后登记于此（不变量 #5 / ADR-001 §后果）。
# 改快照必须同时改本常量并在 G1 工单变更记录留痕，禁止 AI 顺手更新快照把测试「修绿」。
GOLDEN_SNAPSHOT_PATH = "tests/golden_seed.json"
# G1-v2 快照变更（2026-11-14 17:56 人裁决 S-02 拆通道，确认记录见 G1 工单「人裁决记录」）：
# 旧 c2dbd94dc16e237a7de9af7ba8af75f9167f602715f97c3fe7fa3baf652605d6
# 新 d18d1b85fb0d557ccbe8dcb7bad42d8cd1d071d9e9f3c6fcf84d3e548b9ca454
GOLDEN_SNAPSHOT_SHA256 = "d18d1b85fb0d557ccbe8dcb7bad42d8cd1d071d9e9f3c6fcf84d3e548b9ca454"


def violation(rule: str, where: str, hint: str) -> str:
    return f"[{rule}] {where} -> {hint}"


def normalize(text: str) -> str:
    """NFKC + NFKD 去变音符 + 大小写折叠 + 去所有非字母数字（含中文）。"""
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def _fold(node: ast.AST) -> str | None:
    """字符串常量折叠：常量 / 字符串加法 / f-string 常量段。

    不能直接用 ast.literal_eval —— 它拒绝字符串相加（防 DoS），
    会漏掉 `"su" + "rf"` 这类绕过（冷眼 F-15）。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _fold(node.left), _fold(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = [_fold(part) for part in node.values if isinstance(part, ast.Constant)]
        return "".join(parts) if parts and all(p is not None for p in parts) else None
    return None


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def collect_strings(tree: ast.AST) -> list[tuple[str, int]]:
    """收集可直接判定的字符串：常量、字符串加法拼接、f-string 常量段。"""
    pool: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.BinOp, ast.JoinedStr)):
            value = _fold(node)
            if value is not None:
                pool.append((value, getattr(node, "lineno", 0)))
    return pool


def _dynamic_aliases(tree: ast.AST) -> set[str]:
    """`from importlib import import_module as im` 这类别名，后续 `im("random")` 也算动态导入。"""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in DYNAMIC_IMPORTS:
                    aliases.add(alias.asname or alias.name)
    return aliases


def check_source(source: str, filename: str, abilities: tuple[str, ...] = ()) -> list[str]:
    """纯函数：给一段源码返回违规列表，供规则门与失败用例共用。"""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [violation("R0 syntax", f"{filename}:{exc.lineno or 0}",
                          f"Python 语法错误：{exc.msg}；修复后重跑验证墙")]
    out: list[str] = []
    ability_norm = {normalize(a) for a in abilities}
    banned_norm = {normalize(m) for m in BANNED_ROOTS}
    aliases = _dynamic_aliases(tree)

    # R3a：能力名在代码中零出现（每个能力名只报一次，避免 f-string 重复）
    seen: set[str] = set()
    for value, line in collect_strings(tree):
        key = normalize(value)
        if key in ability_norm and key not in seen:
            seen.add(key)
            out.append(violation("R3 gate_in_table", f"{filename}:{line}",
                "能力门只在 topology.json 的 edges[].requires 声明，代码里禁止写死能力名（不变量 #3）"))

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        where = f"{filename}:{line}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] in BANNED_ROOTS or "random" in parts:
                    out.append(violation("R1 no_bare_random", where,
                        f"禁止裸随机/时钟模块「{alias.name}」；改用 rng(world_seed, region_id, cx, cy)（不变量 #1）"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in BANNED_ROOTS:
                out.append(violation("R1 no_bare_random", where,
                    f"禁止从「{module}」导入随机/时钟；改用单一随机源（不变量 #1）"))
            for alias in node.names:
                # 覆盖 `from . import random`（module=None, level>0）
                if alias.name in BANNED_ROOTS or "random" in alias.name.split("."):
                    out.append(violation("R1 no_bare_random", where,
                        f"禁止相对/具名导入随机模块「{alias.name}」；改用 rng(...)（不变量 #1）"))
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
            out.append(violation("R1 no_bare_random", where,
                f"禁止随机属性「.{node.attr}」；所有随机必须来自 rng(...)（不变量 #1）"))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in DYNAMIC_IMPORTS or name in aliases:
                suspicious = [v for v in (_fold(a) for a in node.args)
                              if v is None or normalize(v) in banned_norm or "random" in v.casefold()]
                if suspicious:
                    shown = next((v for v in suspicious if v), "<参数不可静态求值>")
                    out.append(violation("R1 no_bare_random", where,
                        f"禁止动态导入「{shown}」或不可静态判定的导入参数；改用 rng(...)（不变量 #1）"))
            # 只查内建函数调用；`re.compile(pattern)` 这类方法调用不是代码构造，
            # 否则规则门会扫到自己的正则字面量而自撞墙。
            if name in DYNAMIC_EVAL and isinstance(node.func, ast.Name):
                for arg in node.args:
                    value = _fold(arg)
                    if not value:
                        continue
                    dangerous = (value in EXACT_DANGEROUS_ATTRS if name == "getattr"
                                 else bool(DANGEROUS_EVAL.search(value)))
                    if dangerous:
                        out.append(violation("R1 no_bare_random", where,
                            f"禁止通过 {name}() 动态构造随机/导入；改用 rng(...)（不变量 #1）"))
            if name in ABILITY_CHECKS and any(_fold(a) is not None for a in node.args):
                out.append(violation("R3 gate_in_table", where,
                    "能力判断必须查 topology.json 的 edges[].requires，禁止硬编码 has/require 类调用（不变量 #3）"))
    return out


def check_data_value(text: str, filename: str) -> list[str]:
    """R4：数据表禁止出现第三方 IP 词汇（不变量 #7 的机器可判定部分）。"""
    folded = normalize(text)
    return [
        violation("R4 no_third_party_ip", f"{filename}:1",
                  f"出现第三方 IP 词汇「{word}」；资产须全部原创（不变量 #7）")
        for word in BANNED_WORDS if normalize(word) in folded
    ]


def check_provenance(root: Path, tables: dict) -> list[str]:
    """R5a：溯源表必须**逐行**登记 `| 潮灵 `cNN` 名称 |`，且名称与数据表一致。

    全文子串包含会被伪造（复评 R-03：把名字写成 GDD 正文任意词即可通过）。
    """
    gdd = root / "docs" / "GDD-v0.md"
    if not gdd.is_file():
        return [violation("R5 asset_provenance", "docs/GDD-v0.md:0",
                          "缺少原创性溯源表；每个潮灵须逐行登记后才可入库（不变量 #7）")]
    rows = {normalize(m.group(1)): normalize(m.group(2))
            for m in PROVENANCE_ROW.finditer(gdd.read_text(encoding="utf-8"))}
    out: list[str] = []
    for creature in tables["species.json"]["creatures"]:
        cid, name = normalize(creature["id"]), normalize(creature["name"])
        if cid not in rows:
            out.append(violation("R5 asset_provenance", "docs/GDD-v0.md:0",
                f"潮灵 {creature['id']} 缺少溯源登记行；须按 '| 潮灵 `cNN` 名称 |' 逐行登记（不变量 #7）"))
        elif rows[cid] != name:
            out.append(violation("R5 asset_provenance", "docs/GDD-v0.md:0",
                f"潮灵 {creature['id']} 的溯源表名称与数据表不一致；禁止在正文任意位置冒充登记（不变量 #7）"))
    return out


def check_assumptions(root: Path, tables: dict) -> list[str]:
    """R5b：三表的 `assumptions` 占位标记必须在 `docs/待裁定项.md` 有对应条目。"""
    doc = root / "docs" / "待裁定项.md"
    if not doc.is_file():
        return [violation("R5 asset_provenance", "docs/待裁定项.md:0",
                          "缺少待裁定项清单；占位字段须集中登记并待人追认（冷眼 F-04/F-09）")]
    folded = normalize(doc.read_text(encoding="utf-8"))
    out: list[str] = []
    for name, data in tables.items():
        marks = data.get("assumptions", [])
        if not marks:
            out.append(violation("R5 asset_provenance", f"data/{name}:0",
                f"{name} 缺少 assumptions 占位标记；未裁定字段须显式标记（不变量 #2）"))
        for mark in marks:
            mark_id = mark["id"] if isinstance(mark, dict) else mark
            if normalize(mark_id) not in folded:
                out.append(violation("R5 asset_provenance", "docs/待裁定项.md:0",
                    f"占位标记 {mark_id} 未登记到待裁定项清单；补登记后再入库（不变量 #2）"))
    return out


def check_scan_scope(root: Path) -> list[str]:
    """R6：含 .py 的顶层目录必须登记；排除目录内出现 .py 也要报盲区。"""
    out: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name in SCAN_DIRS:
            continue
        if not any(path.rglob("*.py")):
            continue
        if path.name in EXCLUDED_DIRS:
            if path.name not in PY_ALLOWED_EXCLUDED:
                out.append(violation("R6 scan_scope", f"{path.name}/:0",
                    f"排除目录 {path.name}/ 内含 .py 但不参与生产扫描；请移走或显式登记，避免盲扫"))
            continue
        out.append(violation("R6 scan_scope", f"{path.name}/:0",
            "新目录含 .py 但不在 gate.SCAN_DIRS；请登记扫描根或加入排除白名单，避免盲扫"))
    return out


def check_golden_snapshot(root: Path) -> list[str]:
    """R7：锁定快照哈希；变更须人确认（不变量 #5 / ADR-001 §后果）。

    行尾归一化后再算哈希：Git 在 Windows 检出可能把 LF 转成 CRLF，
    不得因此误报「快照被人改过」。内容任何改动仍会改变哈希。
    """
    path = root / GOLDEN_SNAPSHOT_PATH
    if not path.is_file():
        return [violation("R7 golden_seed", f"{GOLDEN_SNAPSHOT_PATH}:0",
            "缺少 golden seed 快照；须由人确认后运行 tools/make_golden.py 重建并登记哈希（不变量 #5 / ADR-001）")]
    try:
        raw = path.read_bytes().replace(b"\r\n", b"\n")
    except OSError as exc:
        return [violation("R7 golden_seed", f"{GOLDEN_SNAPSHOT_PATH}:0",
            f"快照无法读取：{exc}；请重新生成后再跑验证墙")]
    digest = hashlib.sha256(raw).hexdigest()
    if digest != GOLDEN_SNAPSHOT_SHA256:
        return [violation("R7 golden_seed", f"{GOLDEN_SNAPSHOT_PATH}:0",
            f"快照哈希 {digest[:12]}… 与登记值不符；生成器或快照变更须人确认后运行 tools/make_golden.py，"
            "并把新哈希登记到 gate.GOLDEN_SNAPSHOT_SHA256 且在工单变更记录留痕（不变量 #5 / ADR-001）")]
    return []


def run(root: str | Path | None = None) -> list[str]:
    root = schema.root_of(root)
    out: list[str] = []
    try:
        schema.verify_manifest(root)
    except (schema.SchemaError, OSError) as exc:
        out.append(violation("R2 protected_files", "data/MANIFEST.sha256:0",
            f"{exc}；改动受保护数据须人确认后重建 manifest（不变量 #2）"))
    try:
        tables = schema.load_all(root)
    except (schema.SchemaError, OSError, ValueError) as exc:
        out.append(violation("R2 protected_files", "data/:0",
            f"表加载或结构校验失败：{exc}；修复三张表后重跑（不变量 #2）"))
        out += check_scan_scope(root)
        return out

    for name in schema.PROTECTED:
        try:
            text = (root / "data" / name).read_text(encoding="utf-8")
        except OSError as exc:
            out.append(violation("R2 protected_files", f"data/{name}:0", f"无法读取：{exc}"))
            continue
        out += check_data_value(text, f"data/{name}")
    out += check_provenance(root, tables)
    out += check_assumptions(root, tables)

    abilities = tuple(tables["topology.json"]["abilities"])
    targets: list[Path] = []
    for folder in SCAN_DIRS:
        folder_path = root / folder
        if folder_path.is_dir():
            targets.extend(folder_path.rglob("*.py"))
    targets.extend(root.glob("*.py"))
    for path in sorted(set(targets)):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append(violation("R0 syntax", f"{rel}:0", f"无法读取源码：{exc}"))
            continue
        out += check_source(source, rel, abilities)
    out += check_scan_scope(root)
    out += check_golden_snapshot(root)
    return out


def main() -> int:
    problems = run()
    if problems:
        for item in problems:
            print(item)
        print(f"GATE FAILED: {len(problems)} violation(s)")
        return 1
    print("GATE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
