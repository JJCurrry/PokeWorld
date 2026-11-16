"""G4 事件脚本：**纯字面量数据 + 只读匹配**，绝不直接改世界状态。

设计依据 `docs/adr/ADR-004-图鉴成长事件脚本与存档.md`：
- `SCRIPT_ROWS` 是模块级 tuple-of-tuples（≤20 条），只含字符串，零可执行逻辑；
  文案为原创中文短句草案，B 级品味归人复核。
- `select` / `effects_of` 是纯函数，只产出 frozen `Effect` 意图声明；
  本模块**不 import** `progress` / `game` / `save`，也没有 `step(` / `replace(`
  / 状态赋值 / I/O / 时钟 / 裸随机 / `assert`。
- 唯一状态变更入口是 `src/world/game.py::apply_effects`；Effect 种类白名单
  只有 `flag` / `note` / `log`，只改展示层字段，不碰 Progress / World。

行格式：`(sid, key, match, kind, value, text)`
`key`/`match` 是只读上下文匹配条件；`kind`/`value` 是效果声明；`text` 是展示文案。
"""
from __future__ import annotations

from dataclasses import dataclass

SCRIPT_LIMIT = 20

# 原创中文短句（AI 草案，B 级品味归人复核）；无任何第三方 IP 词汇。
SCRIPT_ROWS = (
    ("s01", "region", "r1", "flag", "script:shore", "潮水退到石阶下，盐粒在风里发亮。"),
    ("s02", "region", "r2", "note", "浅滩的水声比脚步先到。", "石缝里有一枚被磨圆的贝壳。"),
    ("s03", "region", "r3", "flag", "script:ridge", "山脊把云切成两半，风从缺口漏下来。"),
    ("s04", "region", "r4", "note", "林间滴落的水带着松脂味。", "树根下留着一圈干爽的泥。"),
    ("s05", "region", "r5", "flag", "script:reed", "芦苇一齐弯向同一侧，像在指路。"),
    ("s06", "region", "r6", "log", "崖顶的回声数了三遍才散。", "碎石沿坡滚下，惊起一小片尘。"),
    ("s07", "region", "r7", "flag", "script:summit", "最后一段台阶没有脚印。"),
    ("s08", "terrain", "grass", "note", "草叶刚没过鞋面。", "露水在叶尖排成一列。"),
    ("s09", "terrain", "deep_grass", "flag", "script:thicket", "深草里传来细碎的响动。"),
    ("s10", "terrain", "shoal", "note", "浅水没过脚踝，凉得清醒。", "沙面下有一道缓缓移动的影子。"),
    ("s11", "terrain", "deep_water", "log", "深水把天光折成暗蓝。", "远处浮起一串细小的气泡。"),
    ("s12", "phase", "day", "flag", "script:daylight", "日光把潮线照得清清楚楚。"),
    ("s13", "phase", "night", "note", "夜色里只剩潮声和自己的脚步。", "磷光沿着湿痕一点点亮起来。"),
    ("s14", "milestone", "atlas", "flag", "script:atlas_done", "册子终于合得上，边角还沾着盐。"),
    ("s15", "milestone", "region", "note", "这一带的出没条件都记全了。", "回头看，来路已被雾抹平。"),
    ("s16", "party", "ready", "log", "同伴在前面停下等你。", "队伍的影子被拉得很长。"),
)

EFFECT_KINDS = ("flag", "note", "log")


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Script:
    """一条只读脚本行；字段全部是字符串。"""

    sid: str
    key: str
    match: str
    kind: str
    value: str
    text: str


@dataclass(frozen=True)
class Effect:
    """效果声明（意图），不含任何状态对象与副作用。"""

    kind: str
    value: str
    sid: str


def all_scripts() -> tuple[Script, ...]:
    """把字面量行转成 frozen 对象；顺带校验条数上限、sid 唯一与种类白名单。"""
    rows = tuple(Script(*row) for row in SCRIPT_ROWS)
    _require(len(rows) <= SCRIPT_LIMIT,
             f"事件脚本条数超过上限 {SCRIPT_LIMIT}")
    ids = tuple(row.sid for row in rows)
    _require(len(set(ids)) == len(ids), "事件脚本 sid 重复")
    for row in rows:
        _require(row.kind in EFFECT_KINDS, f"未登记的效果种类：{row.kind}")
        _require(bool(row.value) and bool(row.text), "效果值与文案不得为空")
    return rows


def select(context: dict) -> tuple[Script, ...]:
    """按声明顺序返回全部匹配行；只读 context，不修改任何对象。"""
    _require(isinstance(context, dict), "上下文必须是字典")
    return tuple(row for row in all_scripts()
                 if context.get(row.key) == row.match)


def effects_of(scripts: tuple[Script, ...]) -> tuple[Effect, ...]:
    """把脚本行折叠成效果声明；同参重放逐项一致。"""
    _require(isinstance(scripts, (tuple, list)), "scripts 必须是不可变序列")
    return tuple(Effect(row.kind, row.value, row.sid) for row in scripts)


def texts_of(scripts: tuple[Script, ...]) -> tuple[str, ...]:
    """展示文案；供报告输出，不参与状态变更。"""
    return tuple(row.text for row in scripts)
