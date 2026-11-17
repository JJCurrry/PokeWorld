"""G5 只读投影：`Session` → frozen `Frame`（零 pygame / 零 I/O / 零时钟）。

设计依据 `ADR-005` §决定 1：表现层只读状态，不回写世界。`frame_of` 只从
`Session` 与骨架表读取数据，调用既有 `generate_chunk` 取当前区块地形，
产出「可画什么」的纯数据；真正画的是 `window.py`。同参两次调用逐字段相等。

模块级只放不可变字面量；校验一律显式抛 `ValueError`（禁 assert）。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..gen.chunk import generate_chunk
from ..world.progress import World
from ..world.session import Session, is_complete

# 地形配色按表内 terrain 顺序分配，代码零硬编码地形名 / 平衡数值。
PALETTE = (
    (96, 168, 104),
    (48, 112, 72),
    (116, 190, 208),
    (40, 88, 152),
)
PHASE_LABELS = (("day", "白昼"), ("night", "夜潮"))
HELP_TEXT = "方向键移动 · S 巡查 · N 交谈 · 数字键跨区 · A 自动通关 · P 时段 · T 成长 · Q 退出"
IDLE_TEXT = "潮声从远处传来，路还很长。"

# G7 战斗键位（单独一张表，不改 G5 的 13 条巡图键位，兼容既有测试）。
# 道具键（数字）在 `action_for_key` 里按 `items` 表的顺序派生，零道具 id 字面量。
COMBAT_KEY_ACTIONS = (
    ("b", "encounter"),
    ("j", "attack"),
    ("k", "catch"),
    ("l", "flee"),
    ("q", "quit"),
    ("escape", "quit"),
)
COMBAT_HELP = "B 遭遇 · J 攻击 · K 捕捉 · L 撤离 · 数字键道具 · Q 退出"

# pygame.key.name() 的名字 → 会话动作。数字键跨边在 action_for_key 里按表派生，
# 不把边数写死成常量。
KEY_ACTIONS = (
    ("up", "move:up"),
    ("down", "move:down"),
    ("left", "move:left"),
    ("right", "move:right"),
    ("s", "survey"),
    ("n", "npc"),
    ("a", "auto"),
    ("p", "phase"),
    ("t", "train"),
    ("q", "quit"),
    ("escape", "quit"),
    ("f5", "save"),
    ("f9", "load"),
)
CLI_ACTIONS = ("auto", "save", "load", "quit")


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Frame:
    """一帧可渲染数据；全部字段不可变，渲染层拿不到状态写入口。"""

    region: str
    region_name: str
    cursor: tuple[int, int]
    phase: str
    grid: tuple[tuple[str, ...], ...]
    palette: tuple[tuple[str, tuple[int, int, int]], ...]
    lines: tuple[str, ...]
    hint: str
    complete: bool
    # G7 战斗投影（带默认值，兼容 G5 位置构造与既有测试）。
    combat: bool = False
    combat_lines: tuple[str, ...] = ()
    combat_hint: str = ""


def _combat_projection(session: Session, tables: dict) -> tuple[bool, tuple[str, ...], str]:
    """从会话的运行时战斗状态派生只读战斗面板（不改状态、零 I/O）。"""
    battle = session.battle
    if battle is None:
        return False, (), ""
    ally = battle.ally
    wild = battle.wild
    ally_label = "—" if ally is None else f"{ally.cid} {ally.hp}/{ally.max_hp}"
    wild_label = "—" if wild is None else f"{wild.cid} {wild.hp}/{wild.max_hp}"
    tail = battle.log[-2:] if battle.log else ()
    lines = (
        f"战斗 · {battle.outcome}",
        f"我方 {ally_label}",
        f"野生 {wild_label}",
    ) + tail
    return True, tuple(lines), COMBAT_HELP


def _region_name(tables: dict, region: str) -> str:
    for row in tables["topology.json"]["regions"]:
        if row["id"] == region:
            return str(row["name"])
    raise ValueError(f"区域未在骨架表登记：{region}")


def _phase_label(phase: str) -> str:
    for key, label in PHASE_LABELS:
        if key == phase:
            return label
    raise ValueError(f"未登记的时段：{phase}")


def palette_of(tables: dict) -> tuple[tuple[str, tuple[int, int, int]], ...]:
    """地形 → 颜色；名字全部来自 `encounters.json::terrain`，按表序确定性分配。"""
    names = tuple(str(name) for name in tables["encounters.json"]["terrain"])
    _require(bool(names), "terrain 不得为空")
    return tuple((name, PALETTE[index % len(PALETTE)])
                 for index, name in enumerate(names))


def frame_of(session: Session, tables: dict) -> Frame:
    """纯投影：只读 Session / tables，返回可渲染的冻结快照。"""
    _require(isinstance(session, Session), "session 必须是 Session")
    state = session.state
    region = state.progress.region
    cx, cy = session.cursor
    chunk = generate_chunk(tables, state.world_seed, region, cx, cy)
    grid = tuple(tuple(str(cell) for cell in row) for row in chunk["tiles"])
    region_name = _region_name(tables, region)
    member = state.party[0]
    lines = (
        f"区域 {region} · {region_name}",
        f"区块 ({cx},{cy}) · 时段 {_phase_label(session.phase)}",
        f"巡查 {len(state.progress.surveyed_regions)}/{len(state.world.regions)}"
        f" · 能力 {len(state.progress.abilities)}/{len(state.world.abilities)}",
        f"图鉴 {len(state.atlas.entries)} 条 · 队伍 Lv.{member.level}",
        session.messages[-1] if session.messages else IDLE_TEXT,
    )
    combat, combat_lines, combat_hint = _combat_projection(session, tables)
    return Frame(region, region_name, (cx, cy), session.phase, grid,
                 palette_of(tables), lines, HELP_TEXT, is_complete(session),
                 combat, combat_lines, combat_hint)


def action_for_key(key: str, world: World, region: str, *,
                   combat: bool = False, items: tuple[str, ...] = ()) -> str | None:
    """键盘名 → 动作；数字键只对**当前区域相连**的边生效，避免非法边抛错。

    G7：战斗态（`combat=True`）改用 `COMBAT_KEY_ACTIONS`，数字键按 `items`
    表序派生 `item:<id>`，不写死道具名；巡图态行为与 G5 完全一致。
    """
    table = COMBAT_KEY_ACTIONS if combat else KEY_ACTIONS
    for name, action in table:
        if name == key:
            return action
    if key.isdigit():
        index = int(key) - 1
        if combat:
            if 0 <= index < len(items):
                return f"item:{items[index]}"
            return None
        if 0 <= index < len(world.edges):
            edge = world.edges[index]
            if edge.source == region or edge.target == region:
                return f"edge:{index}"
    return None
