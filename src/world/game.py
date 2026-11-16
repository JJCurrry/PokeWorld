"""G4 游戏状态聚合：**唯一**状态变更入口 `apply_effects`。

设计依据 `docs/adr/ADR-004-图鉴成长事件脚本与存档.md`：
- `GameState` 是 frozen，聚合 G3 的 `World` / `Progress`、G4 的 `Atlas` / 队伍
  与展示层字段（flags / notes / log）。
- 事件脚本只产出 `Effect` 声明；`apply_effects` 是**唯一**把 Effect 转成状态的
  入口，且**只改 flags / notes / log**，Progress / World / Atlas / party 逐字段不动；
  于是 G3 门控的唯一入口仍是 `progress.step`，脚本无法形成跳关路径。
- 成长 / 形态阶段由 `train` 这条独立纯函数推进，不走效果通道。
- `to_save` 把语义标记投影成 flags（不存 tick / log / blocked，更不存生成结果）；
  `from_save` 从三类持久化信息重建起点状态。

纯函数契约：不改传入的表 / 状态，非法输入显式抛 `ValueError`（禁 assert）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import evolution
from .atlas import Atlas, milestone, new_atlas, observe as observe_entry
from .progress import Progress, World, new_progress
from .save import SaveData
from .scripts import Effect

EFFECT_KINDS = ("flag", "note", "log")


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class GameState:
    """凝固聚合快照；展示层字段与骨架层字段分离。"""

    world_seed: str
    world: World
    progress: Progress
    atlas: Atlas
    party: tuple[evolution.PartyMember, ...]
    flags: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()
    log: tuple[str, ...] = ()


def new_game(tables: dict, world_seed: str, progress: Progress | None = None,
             atlas: Atlas | None = None) -> GameState:
    """从骨架表构造状态；可注入已巡查的 Progress / Atlas 供报告与存档投影使用。

    队伍首位取表内第一个登记物种（不写死 id）。
    """
    _require(bool(world_seed), "world_seed 不得为空")
    _require(progress is None or isinstance(progress, Progress),
             "progress 必须是 Progress")
    _require(atlas is None or isinstance(atlas, Atlas), "atlas 必须是 Atlas")
    world = World.from_tables(tables)
    creatures = tables["species.json"]["creatures"]
    _require(bool(creatures), "物种表为空")
    first = str(creatures[0]["id"])
    member = evolution.new_member(tables, world_seed, first)
    return GameState(world_seed, world,
                     new_progress(world) if progress is None else progress,
                     new_atlas() if atlas is None else atlas,
                     (member,))


def apply_effects(state: GameState,
                  effects: tuple[Effect, ...]) -> GameState:
    """唯一解释器：只把白名单 Effect 折叠进 flags / notes / log。

    返回的 `progress` / `world` / `atlas` / `party` / `world_seed` 与原状态
    **同一对象或逐字段相等**，脚本因此不可能直接改世界状态。
    """
    _require(isinstance(state, GameState), "state 必须是 GameState")
    _require(isinstance(effects, (tuple, list)), "effects 必须是不可变序列")
    flags = set(state.flags)
    notes = list(state.notes)
    lines = list(state.log)
    for effect in effects:
        _require(isinstance(effect, Effect), "effects 元素必须是 Effect")
        _require(effect.kind in EFFECT_KINDS,
                 f"未登记的效果种类：{effect.kind}")
        _require(bool(effect.value), "效果值不得为空")
        if effect.kind == "flag":
            flags.add(effect.value)
        elif effect.kind == "note":
            notes.append(effect.value)
        else:
            lines.append(effect.value)
    return replace(state, flags=frozenset(flags),
                   notes=tuple(notes), log=tuple(lines))


def train(state: GameState, index: int = 0) -> GameState:
    """成长 / 形态阶段推进；只改 party，其余字段不动。"""
    _require(isinstance(state, GameState), "state 必须是 GameState")
    _require(type(index) is int and 0 <= index < len(state.party),
             f"队伍下标越界：{index!r}")
    members = list(state.party)
    members[index] = evolution.train(members[index])
    return replace(state, party=tuple(members))


def observe(state: GameState, cid: str, region: str, terrain: str,
            phase: str) -> GameState:
    """图鉴登记的聚合入口（调用 atlas.observe，只改 atlas 字段）。"""
    return replace(state, atlas=observe_entry(state.atlas, cid, region,
                                              terrain, phase))


def to_save(state: GameState, tables: dict) -> SaveData:
    """投影：语义标记 → 排序去重 flags；队伍 → 四元组。生成结果不入档。"""
    _require(isinstance(state, GameState), "state 必须是 GameState")
    flags = set(state.flags)
    for region in sorted(state.progress.surveyed_regions):
        flags.add(f"region:{region}")
    for ability in sorted(state.progress.abilities):
        flags.add(f"ability:{ability}")
    for cid in sorted({entry.cid for entry in state.atlas.entries}):
        flags.add(f"atlas:{cid}")
    facts = milestone(state.world, tables, state.atlas,
                      state.progress.surveyed_regions)
    if facts["complete"]:
        flags.add("milestone:atlas")
    return SaveData(state.world_seed, tuple(sorted(flags)),
                    tuple(member.row() for member in state.party))


def from_save(save: SaveData, tables: dict) -> GameState:
    """从三类持久化信息重建起点状态；运行时过程量一律归零（ADR-004 已知限制）。

    region / ability flags 可还原巡查与门控语义；图鉴的「地形 / 时段」条件
    不在存档三类信息里，故 atlas 从空册开始，需重新巡查才能重建完整条件记录。
    """
    _require(isinstance(save, SaveData), "save 必须是 SaveData")
    world = World.from_tables(tables)
    regions = frozenset(item[len("region:"):] for item in save.flags
                        if item.startswith("region:"))
    abilities = frozenset(item[len("ability:"):] for item in save.flags
                          if item.startswith("ability:"))
    script_flags = frozenset(item for item in save.flags
                             if item.startswith("script:"))
    _require(regions.issubset(set(world.regions)), "存档含未登记区域")
    _require(abilities.issubset(set(world.abilities)), "存档含未登记能力")
    visited = frozenset(regions | {world.start})
    npcs = frozenset(owner for owner, ability in world.grants
                     if ability in abilities)
    progress = Progress(world.start, abilities, visited, npcs, regions, 0)
    party = tuple(evolution.member_from_row(tables, row) for row in save.party)
    return GameState(save.world_seed, world, progress, new_atlas(), party,
                     script_flags)
