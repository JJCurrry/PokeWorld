"""G3 巡图：能力门与跨区域移动的纯函数状态转移（不变量 #3 / #4）。

门控唯一事实源是 `data/topology.json` 的 `edges[].requires`；本模块把表
凝固成 `World`（frozen），用 `step(state, action, world) -> state'` 推进：
- `npc`    —— 与当前区域的 NPC 交互，取得由该 NPC 授予的能力；
- `survey` —— 标记当前区域已巡查；
- `edge:i` —— 沿第 i 条有向边移动；不满足门控时记为 blocked，不移动。

设计见 `docs/adr/ADR-003-能力门与巡图表驱动实现.md`：
NPC 授予点由边机械派生（零改表），正向按 requires 判定，反向只允许回到
已访问区域。模块中不含任何能力名字面量（规则门 R3a），也不调用带字符串
参数的 `has/require/unlock/can_enter` 类判断（R3b）。

纯函数契约：不读时钟、不做 I/O、不改全局状态、不改传入的 state / World；
非法动作 / 越界边 / 不在当前区域的边显式抛 `ValueError`（不用 assert）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

NPC_PREFIX = "npc:"
EDGE_PREFIX = "edge:"


def _require(condition: object, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


def npc_of(region: str) -> str:
    """区域 → NPC 标识；用区域 id 命名，不新增需溯源的专名资产。"""
    return f"{NPC_PREFIX}{region}"


def npc_region(npc_id: str) -> str:
    """NPC 标识 → 区域 id；`coverage()` 用它判断授予点是否可达。"""
    _require(npc_id.startswith(NPC_PREFIX), f"NPC 标识格式非法：{npc_id}")
    return npc_id[len(NPC_PREFIX):]


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    requires: tuple[str, ...]


@dataclass(frozen=True)
class World:
    """三表拓扑的凝固快照；构造后不跟随原表变化（与 G2 `Rules` 同构）。"""

    start: str
    regions: tuple[str, ...]
    edges: tuple[Edge, ...]
    abilities: tuple[str, ...]
    npcs: tuple[str, ...]
    grants: tuple[tuple[str, str], ...]
    grids: tuple[tuple[str, int, int], ...]

    @classmethod
    def from_tables(cls, tables: dict) -> "World":
        topo = tables["topology.json"]
        regions = tuple(str(r["id"]) for r in topo["regions"])
        grids = tuple((str(r["id"]), int(r["chunks"][0]), int(r["chunks"][1]))
                      for r in topo["regions"])
        for _, width, height in grids:
            _require(width > 0 and height > 0, "区块网格宽高必须为正")
        start = str(topo["start"])
        _require(start in regions, "start 必须指向已存在区域")
        abilities = tuple(str(a) for a in topo["abilities"])
        known = set(abilities)
        edges = tuple(Edge(str(e["from"]), str(e["to"]),
                           tuple(str(a) for a in e["requires"]))
                      for e in topo["edges"])
        grants = set()
        for edge in edges:
            _require(edge.source in regions and edge.target in regions,
                     f"边引用了不存在的区域：{edge.source}->{edge.target}")
            for ability in edge.requires:
                _require(ability in known, f"边声明了未登记能力：{ability}")
                # 一条边的门控能力由其 source 区域的 NPC 授予（ADR-003）。
                grants.add((npc_of(edge.source), ability))
        return cls(start, regions, edges, abilities,
                   tuple(npc_of(r) for r in regions),
                   tuple(sorted(grants)), grids)


@dataclass(frozen=True)
class Progress:
    region: str
    abilities: frozenset[str]
    visited_regions: frozenset[str]
    visited_npcs: frozenset[str]
    surveyed_regions: frozenset[str]
    tick: int
    log: tuple[str, ...] = ()
    blocked: int = 0


def new_progress(world: World) -> Progress:
    """从 start 出发，零能力、零 NPC、零巡查；start 本身算已访问。"""
    return Progress(world.start, frozenset(), frozenset((world.start,)),
                    frozenset(), frozenset(), 0)


def chunk_grid(world: World, region: str) -> tuple[int, int]:
    for rid, width, height in world.grids:
        if rid == region:
            return width, height
    raise ValueError(f"未知区域：{region}")


def edge_is_open(world: World, index: int, abilities: frozenset[str]) -> bool:
    """表驱动门控：requires 是 abilities 的子集即可通行。"""
    _require(0 <= index < len(world.edges), f"边下标越界：{index}")
    return set(world.edges[index].requires).issubset(abilities)


def step(state: Progress, action: str, world: World) -> Progress:
    """纯函数：返回新状态；tick 递增 1，日志只追加不改写。"""
    _require(isinstance(state, Progress), "state 必须是 Progress")
    _require(isinstance(world, World), "world 必须是 World 凝固快照")
    base = replace(state, tick=state.tick + 1)

    if action == "npc":
        npc = npc_of(state.region)
        if npc in state.visited_npcs:
            return replace(base, log=state.log + (f"npc:{npc}:already",))
        gained = frozenset(ability for owner, ability in world.grants if owner == npc)
        return replace(base,
                       abilities=frozenset(state.abilities | gained),
                       visited_npcs=frozenset(state.visited_npcs | {npc}),
                       log=state.log + (f"npc:{npc}:+{len(gained)}",))

    if action == "survey":
        if state.region in state.surveyed_regions:
            return replace(base, log=state.log + (f"survey:{state.region}:already",))
        return replace(base,
                       surveyed_regions=frozenset(state.surveyed_regions | {state.region}),
                       log=state.log + (f"survey:{state.region}",))

    if action.startswith(EDGE_PREFIX):
        raw = action[len(EDGE_PREFIX):]
        _require(raw.isdigit(), f"动作需要非负整数边下标：{action}")
        index = int(raw)
        _require(0 <= index < len(world.edges), f"边下标越界：{index}")
        edge = world.edges[index]
        forward = edge.source == state.region
        backward = edge.target == state.region
        _require(forward or backward,
                 f"当前区域 {state.region} 不在边 {index} 上（{edge.source}->{edge.target}）")
        if forward:
            missing = tuple(a for a in edge.requires if a not in state.abilities)
            if missing:
                return replace(base, blocked=state.blocked + 1,
                               log=state.log + (f"blocked:{index}:{len(missing)}",))
            target, direction = edge.target, "forward"
        else:
            # 受限反向：只回已访问区域，杜绝绕过门控进入未解锁区域。
            if edge.source not in state.visited_regions:
                return replace(base, blocked=state.blocked + 1,
                               log=state.log + (f"blocked:{index}:back-unvisited",))
            target, direction = edge.source, "back"
        return replace(base, region=target,
                       visited_regions=frozenset(state.visited_regions | {target}),
                       log=state.log + (f"edge:{index}:{direction}:{state.region}->{target}",))

    raise ValueError(f"未知动作：{action}")


def _reachable(world: World, owned: frozenset[str]) -> frozenset[str]:
    """给定已拥有能力，从 start 沿开放的正向边做 BFS。"""
    seen = {world.start}
    queue = [world.start]
    while queue:
        region = queue.pop(0)
        for edge in world.edges:
            if edge.source != region or edge.target in seen:
                continue
            if set(edge.requires).issubset(owned):
                seen.add(edge.target)
                queue.append(edge.target)
    return frozenset(seen)


def coverage(world: World) -> dict:
    """静态可达性证明：能力闭包（可达区域内 NPC 授予能力）迭代到收敛。

    返回机器事实，不写「手感 / 设计好坏」结论。complete=True 表示全部
    区域在能力闭包后可达，是「无卡死」的静态证据；动态证据由自动玩家给出。
    """
    owned: frozenset[str] = frozenset()
    reachable: frozenset[str] = frozenset()
    rounds = 0
    while True:
        rounds += 1
        _require(rounds <= len(world.abilities) + 2, "能力闭包未收敛，拓扑可能自相矛盾")
        reachable = _reachable(world, owned)
        gained = frozenset(ability for npc, ability in world.grants
                           if npc_region(npc) in reachable)
        merged = owned | gained
        if merged == owned:
            break
        owned = merged
    return {"reachable": reachable, "owned": owned, "rounds": rounds,
            "complete": len(reachable) == len(world.regions)}


def edge_facts(world: World) -> tuple[dict, ...]:
    """逐边事实：source / target 可达性与门控可满足性，供 DoD E3 核对。"""
    cov = coverage(world)
    facts = []
    for index, edge in enumerate(world.edges):
        facts.append({
            "index": index,
            "source": edge.source,
            "target": edge.target,
            "requires": edge.requires,
            "source_reachable": edge.source in cov["reachable"],
            "target_reachable": edge.target in cov["reachable"],
            "gate_satisfiable": set(edge.requires).issubset(cov["owned"]),
        })
    return tuple(facts)
