"""G5 会话层：把输入变成状态的**唯一**纯函数入口（`ADR-005` §决定 1）。

- 世界推进只调用 G3 `progress.step`；图鉴登记走 G4 `observe_chunk`；
  脚本效果走 G4 `game.apply_effects`；成长走 `game.train`。不开第二入口。
- 通关终点 `goal_region` 由**拓扑派生**（唯一无出边区域），不写死区域 id、
  不出现任何能力名字面量（R3a）；能力集合一律从 `World` 读。
- 存档复用 G4 `to_save / encode / decode / from_save` 三类字段投影，
  本模块不做任何文件 I/O（I/O 只在 `src/main.py`）。
- `Session` frozen；`apply` 用 `dataclasses.replace` 返回新对象，不改入参。

纯函数契约：不读时钟、不做 I/O、不改传入的表 / 状态；非法输入显式抛
`ValueError`（禁 assert，`python -O` 下同样生效）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..gen.chunk import generate_chunk
from .atlas import observe_chunk
from .game import GameState, apply_effects, from_save, new_game, to_save, train
from .progress import Progress, World, chunk_grid, edge_is_open, step
from .save import decode, encode
from .scripts import effects_of, select, texts_of

PHASES = ("day", "night")
DIRECTIONS = ("up", "down", "left", "right")
MOVE_PREFIX = "move:"
EDGE_PREFIX = "edge:"


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Session:
    """凝固会话快照：G4 聚合状态 + 只读视图字段（游标 / 时段 / 最近文案）。"""

    state: GameState
    cursor: tuple[int, int] = (0, 0)
    phase: str = "day"
    messages: tuple[str, ...] = ()
    chunks_seen: int = 0


def new_session(tables: dict, world_seed: str,
                state: GameState | None = None) -> Session:
    """从骨架表构造会话；可注入从存档还原的 GameState。"""
    return Session(new_game(tables, world_seed) if state is None else state)


def goal_region(world: World) -> str:
    """终点 = 唯一没有出边的区域（当前链式拓扑即联盟）。

    不读地标、不写死区域 id，避免把作者意图据为己有（原则 6）。
    多于一个或无出边时显式拒绝 —— 分叉 / 环路拓扑的局限如实暴露（S3-02）。
    """
    sources = frozenset(edge.source for edge in world.edges)
    sinks = tuple(region for region in world.regions if region not in sources)
    _require(len(sinks) == 1,
             f"拓扑须有唯一终点（无出边区域），实际 {len(sinks)} 个：{sinks}")
    return sinks[0]


def route_to_goal(progress: Progress, world: World) -> tuple[int, ...]:
    """BFS 在**开放的正向边**上找从当前区域到终点的边下标序列。

    门控复用 `edge_is_open`（`requires ⊆ abilities`），不硬编码能力名；
    已经站在终点时返回空元组。只走正向，不覆盖反向回退场景（S3-02）。
    """
    goal = goal_region(world)
    if progress.region == goal:
        return ()
    seen = {progress.region}
    queue = [(progress.region, ())]
    while queue:
        region, path = queue.pop(0)
        for index, edge in enumerate(world.edges):
            if edge.source != region or edge.target in seen:
                continue
            if not edge_is_open(world, index, progress.abilities):
                continue
            if edge.target == goal:
                return path + (index,)
            seen.add(edge.target)
            queue.append((edge.target, path + (index,)))
    return ()


def is_complete(session: Session) -> bool:
    """通关机器事实：到达终点 + 全区域到达 / 巡查 + 零受阻。

    刻意**不**要求「全 NPC 已访问」：G4 存档是投影，只存能力与语义 flags，
    不存 NPC 访问记录（`from_save` 的 visited_npcs 由已有能力派生）。若把它
    当硬条件，读档后永远无法重新通关 —— 这与 S4-02 是同一类投影限制。
    主通关序列的 NPC 覆盖（7/7）由 `tools/g5_report.py` 单独输出机器事实。
    """
    _require(isinstance(session, Session), "session 必须是 Session")
    world = session.state.world
    progress = session.state.progress
    return bool(
        progress.region == goal_region(world)
        and len(progress.visited_regions) == len(world.regions)
        and len(progress.surveyed_regions) == len(world.regions)
        and progress.blocked == 0
    )


def serialize(session: Session, tables: dict) -> str:
    """存档文本 = G4 三类字段投影；生成结果不入档（不变量 #6）。"""
    return encode(to_save(session.state, tables))


def restore(text: str, tables: dict) -> Session:
    """从存档文本还原会话；图鉴条件不还原（G4 已知限制 S4-02）。"""
    return Session(from_save(decode(text), tables))


def _next_phase(phase: str) -> str:
    _require(phase in PHASES, f"未登记的时段：{phase}")
    return PHASES[(PHASES.index(phase) + 1) % len(PHASES)]


def _move(session: Session, direction: str, world: World) -> Session:
    """只改视图游标，边界截断；不触碰任何世界状态。"""
    _require(direction in DIRECTIONS, f"未登记的移动方向：{direction}")
    width, height = chunk_grid(world, session.state.progress.region)
    cx, cy = session.cursor
    if direction == "up":
        cy = max(0, cy - 1)
    elif direction == "down":
        cy = min(height - 1, cy + 1)
    elif direction == "left":
        cx = max(0, cx - 1)
    else:
        cx = min(width - 1, cx + 1)
    return replace(session, cursor=(cx, cy))


def _register_chunks(state: GameState, tables: dict,
                     region: str) -> tuple[GameState, int]:
    """巡查一个区域时逐区块登记图鉴（与 `g4_report._walk` 同构，纯函数）。"""
    width, height = chunk_grid(state.world, region)
    atlas = state.atlas
    for cy in range(height):
        for cx in range(width):
            chunk = generate_chunk(tables, state.world_seed, region, cx, cy)
            atlas = observe_chunk(atlas, region, chunk)
    return replace(state, atlas=atlas), width * height


def _enter_region(state: GameState, region: str) -> tuple[GameState, tuple[str, ...]]:
    """跨入新区域时触发该区域的原创事件脚本；唯一解释器仍是 apply_effects。"""
    rows = select({"region": region})
    effects = effects_of(rows)
    return apply_effects(state, effects), texts_of(rows)


def apply(session: Session, action: str, tables: dict) -> Session:
    """唯一状态转移：动作 → 新 Session。不读时钟、不做 I/O、不改入参。"""
    _require(isinstance(session, Session), "session 必须是 Session")
    _require(isinstance(action, str) and bool(action), "动作必须是非空字符串")
    state = session.state
    world = state.world

    if action.startswith(MOVE_PREFIX):
        return _move(session, action[len(MOVE_PREFIX):], world)
    if action == "phase":
        return replace(session, phase=_next_phase(session.phase))
    if action == "train":
        return replace(session, state=train(state))

    world_action = action in ("survey", "npc") or action.startswith(EDGE_PREFIX)
    _require(world_action, f"未登记的动作：{action}")

    before = state.progress
    moved = step(before, action, world)
    new_state = replace(state, progress=moved)
    messages = session.messages
    cursor = session.cursor
    chunks_seen = session.chunks_seen
    if (action == "survey"
            and len(moved.surveyed_regions) > len(before.surveyed_regions)):
        new_state, counted = _register_chunks(new_state, tables, before.region)
        chunks_seen += counted
    if moved.region != before.region:
        new_state, messages = _enter_region(new_state, moved.region)
        cursor = (0, 0)
    return replace(session, state=new_state, cursor=cursor,
                   messages=messages, chunks_seen=chunks_seen)


def play_to_goal(session: Session, tables: dict, choose: object,
                 max_steps: int = 64) -> tuple[Session, tuple[str, ...]]:
    """确定性通关：先按注入的表序决策巡图，再按拓扑导航走到终点。

    `choose(progress, world)` 由调用方注入（现有 `autoplayer.choose_action`），
    使本模块不依赖 `tools/`，也不复制一份会分叉的决策逻辑。
    """
    _require(callable(choose), "choose 必须是可调用的决策函数")
    world = session.state.world
    actions: list[str] = []
    for _ in range(max_steps):
        action = choose(session.state.progress, world)
        if action is None:
            break
        session = apply(session, action, tables)
        actions.append(action)
    for index in route_to_goal(session.state.progress, world):
        action = f"{EDGE_PREFIX}{index}"
        session = apply(session, action, tables)
        actions.append(action)
    return session, tuple(actions)
