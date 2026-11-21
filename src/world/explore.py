"""G8 开放世界探索：连续坐标状态转移（ADR-009 · 纯函数）。

- `Explore` frozen；`apply` 用 dataclasses.replace 返回新状态，不改入参。
- 世界推进复用 G3 `progress.step`（能力门查 edges[].requires，R3 合规）、
  G4 `game.observe`（图鉴唯一写入口）、G2 `battle.engine.step`（战斗纯函数）。
- 连续坐标 / 遭遇触发只走 `rng(world_seed, ...)`；无裸随机 / 无时钟（R1）。
- 零 I/O、零能力名字面量、不改三表 / golden（R2 / R3 / R7）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..battle.context import RngContext
from ..battle.engine import step as battle_step
from ..battle.state import BattleState
from ..battle.state import new_state as new_battle_state
from ..gen import overworld
from ..gen.rng import rng
from . import game
from .game import GameState, observe as observe_game
from .progress import World, edge_is_open, step as progress_step
from .session import BATTLE_TERMINAL, BATTLE_ACTIONS, EDGE_PREFIX, ITEM_PREFIX

MOVE_PREFIX = "move:"
TERRAIN_BATTLE_TRIGGER = 0.18  # 陆地每步遭遇触发阈值（确定性比较，非概率随机数）


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Explore:
    """开放世界凝固快照：连续位置 + G4 聚合状态 + 战斗运行时（不进存档）。"""

    state: GameState
    x: float
    y: float
    phase: str = "day"
    steps: int = 0
    encounters: int = 0
    captures: int = 0
    battle: BattleState | None = None
    battle_ctx: RngContext | None = None
    messages: tuple[str, ...] = ()
    last_trigger: float = -1.0  # 上一块陆地触发用的确定性采样值


def new_explore(tables: dict, world_seed: str) -> Explore:
    """从起点地标的陆地位置开局；起点由表序派生，不写死区域 id / 座标。"""
    start = game.new_game(tables, world_seed)
    region = start.progress.region
    for rid, lx, ly in overworld.landmarks(tables):
        if rid == region:
            return Explore(start, lx, ly)
    raise ValueError(f"起点区域无地标：{region}")


def current_region(tables: dict, explore: Explore) -> str:
    """当前所在区域 = 最近地标（半径内）；离开地标群时保留最后所在区域。"""
    region, _, _, distance = overworld.nearest_landmark(tables, explore.x, explore.y)
    if distance <= overworld.LANDMARK_RADIUS:
        return region
    return explore.state.progress.region


def _bag_from_tables(tables: dict) -> tuple[str, ...]:
    items = tables["encounters.json"]["items"]
    return tuple(sorted(str(key) for key in items))


def _start_battle(tables: dict, explore: Explore) -> Explore:
    """在连续坐标处开局：权重来自该地标点位，状态由 G2 纯函数构造。"""
    _require(explore.battle is None, "已有战斗进行中")
    region = current_region(tables, explore)
    weights = overworld.encounter_weights(tables, region, explore.phase,
                                          explore.state.world_seed, explore.x, explore.y)
    if not weights:
        return replace(explore, messages=explore.messages + ("此处无可遭遇潮灵",))
    ally_id = explore.state.party[0].cid
    gx, gy = int(explore.x), int(explore.y)
    battle = new_battle_state(tables, region, gx, gy, explore.phase, ally_id,
                              weights=weights, bag=_bag_from_tables(tables))
    ctx = RngContext(explore.state.world_seed, region, gx, gy)
    battle = battle_step(battle, "encounter", ctx)
    return replace(explore, battle=battle, battle_ctx=ctx.advance(),
                   encounters=explore.encounters + 1,
                   messages=explore.messages + (f"遭遇潮灵于 {region}",))


def _finish_battle(tables: dict, explore: Explore, battle: BattleState) -> Explore:
    """终局：caught / won 经 game.observe 入图鉴（唯一写入口），清运行时态。"""
    state = explore.state
    captures = explore.captures
    if battle.outcome in ("caught", "won") and battle.wild is not None:
        region = battle.region
        terrain = overworld.terrain_at(tables, state.world_seed, *battle.coord)
        state = observe_game(state, battle.wild.cid, region, terrain, battle.time_phase)
        captures += 1
    return replace(explore, state=state, battle=None, battle_ctx=None,
                   captures=captures,
                   messages=explore.messages + (f"战斗结束：{battle.outcome}",))


def _battle_action(tables: dict, explore: Explore, action: str) -> Explore:
    battle, ctx = explore.battle, explore.battle_ctx
    _require(battle is not None and ctx is not None, "当前没有战斗")
    _require(ctx.tick == battle.tick, "战斗随机上下文与状态不同步")
    next_battle = battle_step(battle, action, ctx)
    advanced = replace(explore, battle=next_battle, battle_ctx=ctx.advance())
    if next_battle.outcome in BATTLE_TERMINAL:
        return _finish_battle(tables, advanced, next_battle)
    return advanced


def _enter_landmark(tables: dict, explore: Explore, region: str) -> Explore:
    """走到地标：沿拓扑边推进进度（查表门控）；门未开则记受阻、不改区域。"""
    world: World = explore.state.world
    progress = explore.state.progress
    if region == progress.region:
        return explore
    for index, edge in enumerate(world.edges):
        if edge.source == progress.region and edge.target == region:
            if not edge_is_open(world, index, progress.abilities):
                return replace(explore, messages=explore.messages + (f"前方 {region} 尚未解锁",))
            moved = progress_step(progress, f"{EDGE_PREFIX}{index}", world)
            state = replace(explore.state, progress=moved)
            return replace(explore, state=state,
                           messages=explore.messages + (f"抵达 {region}",))
    return explore  # 非相邻地标：开放世界可自由走动，但进度只沿表内边推进


def _move(tables: dict, explore: Explore, direction: str) -> Explore:
    """连续移动一格；水域不可进入；踩到地标推进区域；陆地触发确定性遭遇判定。"""
    _require(direction in ("up", "down", "left", "right"), f"未知方向：{direction}")
    x, y = explore.x, explore.y
    if direction == "up":
        y -= 1
    elif direction == "down":
        y += 1
    elif direction == "left":
        x -= 1
    else:
        x += 1
    x = max(0.0, min(float(overworld.WORLD_TILES), x))
    y = max(0.0, min(float(overworld.WORLD_TILES), y))
    if not overworld.walkable(tables, explore.state.world_seed, x, y):
        return replace(explore, messages=explore.messages + ("前方是水域，无法通行",))
    moved = replace(explore, x=x, y=y, steps=explore.steps + 1)
    moved = _enter_landmark(tables, moved, current_region(tables, moved))
    seed = explore.state.world_seed
    trigger = rng(seed, "explore", int(x), int(y)).unit()
    return replace(moved, last_trigger=trigger)


def apply(tables: dict, explore: Explore, action: str) -> Explore:
    """唯一状态转移：动作 → 新 Explore；战斗态只接受战斗动作。"""
    _require(isinstance(explore, Explore), "explore 必须是 Explore")
    _require(isinstance(action, str) and bool(action), "动作必须是非空字符串")
    if explore.battle is not None:
        if action in BATTLE_ACTIONS or action.startswith(ITEM_PREFIX):
            return _battle_action(tables, explore, action)
        return explore  # 战斗中忽略世界动作
    if action.startswith(MOVE_PREFIX):
        return _move(tables, explore, action[len(MOVE_PREFIX):])
    if action == "encounter":
        return _start_battle(tables, explore)
    if action == "npc":
        progress = progress_step(explore.state.progress, "npc", explore.state.world)
        return replace(explore, state=replace(explore.state, progress=progress),
                       messages=explore.messages + ("与地标 NPC 交谈",))
    if action == "survey":
        progress = progress_step(explore.state.progress, "survey", explore.state.world)
        return replace(explore, state=replace(explore.state, progress=progress),
                       messages=explore.messages + ("巡查完成",))
    if action == "phase":
        return replace(explore, phase="night" if explore.phase == "day" else "day")
    raise ValueError(f"未登记的动作：{action}")


def should_encounter(explore: Explore) -> bool:
    """确定性遭遇判定：陆地步且触发值低于阈值（无随机、无时钟）。"""
    return explore.battle is None and 0.0 <= explore.last_trigger < TERRAIN_BATTLE_TRIGGER


def is_complete(tables: dict, explore: Explore) -> bool:
    """通关机器事实：到达拓扑终点地标 + 图鉴非空 + 至少一次捕获。"""
    world: World = explore.state.world
    goal_region = next((r for r in world.regions
                        if not any(e.source == r for e in world.edges)), "")
    region = current_region(tables, explore)
    return bool(region == goal_region and len(explore.state.atlas.entries) > 0
                and explore.captures > 0)


def _route(tables: dict, seed: str | int, sx: int, sy: int,
           tx: int, ty: int) -> tuple[tuple[int, int], ...]:
    """网格 BFS 最短路（四邻、固定方向序，确定性）；只走可步行地形。"""
    from collections import deque

    start, goal = (sx, sy), (tx, ty)
    if start == goal:
        return ()
    queue = deque([start])
    parents: dict[tuple[int, int], tuple[int, int]] = {}
    while queue:
        cell = queue.popleft()
        for neighbor in ((cell[0] + 1, cell[1]), (cell[0], cell[1] + 1),
                         (cell[0] - 1, cell[1]), (cell[0], cell[1] - 1)):
            nx, ny = neighbor
            if neighbor in parents or not (0 <= nx < overworld.WORLD_TILES
                                           and 0 <= ny < overworld.WORLD_TILES):
                continue
            if not overworld.walkable(tables, seed, nx + 0.5, ny + 0.5):
                continue
            parents[neighbor] = cell
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parents:
        return ()
    path = []
    cell = goal
    while cell != start:
        path.append(cell)
        cell = parents[cell]
    path.reverse()
    return tuple(path)


def _walk_toward(tables: dict, explore: Explore, tx: float, ty: float,
                 limit: int = 512) -> Explore:
    """沿 BFS 最短路走到目标地标（绕过水域），逐格走 apply。"""
    seed = explore.state.world_seed
    path = _route(tables, seed, int(explore.x), int(explore.y), int(tx), int(ty))
    for gx, gy in path[:limit]:
        dx, dy = gx - explore.x, gy - explore.y
        if abs(dx) >= abs(dy) and dx:
            direction = "right" if dx > 0 else "left"
        elif dy:
            direction = "down" if dy > 0 else "up"
        else:
            continue
        explore = apply(tables, explore, f"{MOVE_PREFIX}{direction}")
    return explore


def _catch_wild(tables: dict, explore: Explore, limit: int = 24) -> Explore:
    """确定性捕捉（复用 G2 纯函数）：装备最强网 → 上状态压制反击 → 削血 → 抓。

    ball / status 道具从表里按 `catch_bonus` 最大者派生，代码零道具 id 字面量。
    """
    items = tables["encounters.json"]["items"]
    statuses = tables["encounters.json"]["statuses"]
    balls = [key for key, row in items.items() if row["kind"] == "ball"]
    states = [key for key, row in items.items() if row["kind"] == "status"]
    best_ball = max(balls, key=lambda key: (float(items[key]["catch_bonus"]), key))
    best_status = max(states, key=lambda key: (
        float(statuses[items[key]["status"]]["catch_bonus"]), key))
    equipped = False
    statused = False
    for _ in range(limit):
        battle = explore.battle
        if battle is None or battle.outcome in BATTLE_TERMINAL:
            break
        if not equipped and best_ball in battle.bag:
            explore = apply(tables, explore, f"{ITEM_PREFIX}{best_ball}")
            equipped = True
            continue
        if not statused and best_status in battle.bag:
            explore = apply(tables, explore, f"{ITEM_PREFIX}{best_status}")
            statused = True
            continue
        wild = explore.battle.wild if explore.battle else None
        if wild is None:
            break
        # 磨到半血再抓（捕捉率随失血上升）；僵麻期间 catch 失败不反击。
        # attack 必被反击，故仅在野生血量仍高且我方血量充裕时才攻击。
        ally = explore.battle.ally
        can_attack = bool(ally and ally.hp > 12 and wild.hp / wild.max_hp > 0.45)
        explore = apply(tables, explore, "attack" if can_attack else "catch")
    if explore.battle is not None and explore.battle.outcome not in BATTLE_TERMINAL:
        explore = apply(tables, explore, "flee")  # 限定回合未抓到则撤离，不卡死
    return explore


def autoplay(tables: dict, explore: Explore, *, catch_at: str | None = None,
             max_rounds: int = 32) -> Explore:
    """确定性开放世界通关：逐地标交谈→巡查→走到下一地标；沿途可捕捉一次。

    `catch_at` 指定在哪个区域触发一次遭遇 + 捕捉（None 表示不捕捉）。
    进度推进全部经 `progress_step`（查表门控），捕捉经 G2 + `game.observe`。
    """
    caught = False
    for _ in range(max_rounds):
        region = current_region(tables, explore)
        explore = apply(tables, explore, "npc")     # 取得该区域授予的能力
        explore = apply(tables, explore, "survey")  # 标记巡查
        want_catch = (catch_at is None and not caught) or (
            catch_at is not None and region == catch_at)
        if want_catch and not caught:
            for attempt in range(4):
                if explore.battle is None:
                    explore = apply(tables, explore, "encounter")
                explore = _catch_wild(tables, explore)
                caught = explore.captures > 0
                if caught:
                    break
        progress = explore.state.progress
        world = explore.state.world
        next_index = None
        for index, edge in enumerate(world.edges):
            if edge.source != progress.region:
                continue
            if edge_is_open(world, index, progress.abilities):
                next_index = index
                break
        if next_index is None:
            break
        target = world.edges[next_index].target
        for rid, lx, ly in overworld.landmarks(tables):
            if rid == target:
                explore = _walk_toward(tables, explore, lx, ly)
                break
        if current_region(tables, explore) != target:
            break
    return explore
