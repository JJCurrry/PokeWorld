"""G3 自动玩家：确定性跑遍拓扑 / NPC / 区块，输出机器事实 JSON。

用法：`python tools/autoplayer.py [world_seed]`（默认 `G3-autoplayer`）。

`run(tables, world_seed)` 是纯函数：不读时钟、不写文件、不改传入表；
只有 `main()` 做加载与打印。决策按表序确定性推进（巡查 → NPC → 未访问
且开放的正向边 → 已访问子图上 BFS 回退），不引入随机 / 时钟（不变量 #1）。
区块地形由 G1 的 `rng(world_seed, region, cx, cy)` 生成，故**拓扑轨迹与
世界种子解耦**：换种子只变地形摘要，不变解锁顺序。

模块中不含任何能力名字面量，「谁在哪拿能力」全部由 `World` 从骨架表派生
（规则门 R3a / ADR-003）。报告只写机器事实，不含手感或平衡结论。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src import schema  # noqa: E402
from src.gen.chunk import encode_tiles, generate_chunk  # noqa: E402
from src.world.progress import (  # noqa: E402
    World, chunk_grid, coverage, edge_is_open, new_progress, npc_of, step,
)

DEFAULT_SEED = "G3-autoplayer"
MAX_STEPS_FACTOR = 8
STEP_MARGIN = 16


def survey_region(tables: dict, world_seed: str, region: str,
                  world: World) -> dict:
    """跑遍该区域全部区块；纯函数，只调用既有 G1 生成器（不改快照）。"""
    width, height = chunk_grid(world, region)
    codes = []
    totals: dict[str, int] = {}
    chunks = 0
    for cy in range(height):
        for cx in range(width):
            chunk = generate_chunk(tables, world_seed, region, cx, cy)
            codes.append(encode_tiles(chunk["tiles"]))
            for name, count in chunk["terrain_counts"].items():
                totals[name] = totals.get(name, 0) + int(count)
            chunks += 1
    digest = hashlib.sha256("|".join(codes).encode("utf-8")).hexdigest()
    return {"region": region, "grid": [width, height], "chunks": chunks,
            "terrain_totals": dict(sorted(totals.items())),
            "tiles_digest": digest}


def _shortest_edge_path(state, world: World, origin: str,
                        targets: set[str]) -> tuple[int, ...]:
    """在**已访问子图**上 BFS 找一条到待办区域的最短边序列。

    正向邻居须门控开放，反向邻居两端都已访问；因此路径首步一定能被
    `step` 真正走通，不会把自动玩家卡在 repeated blocked 上。
    """
    seen = {origin}
    queue = [(origin, ())]
    while queue:
        region, path = queue.pop(0)
        if region in targets and path:
            return path
        for index, edge in enumerate(world.edges):
            if (edge.source == region and edge.target in state.visited_regions
                    and edge_is_open(world, index, state.abilities)):
                nxt = edge.target
            elif edge.target == region and edge.source in state.visited_regions:
                nxt = edge.source
            else:
                continue
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, path + (index,)))
    return ()


def choose_action(state, world: World) -> str | None:
    """确定性策略；返回 None 表示已无待办（正常结束，不是卡死）。"""
    region = state.region
    if region not in state.surveyed_regions:
        return "survey"
    if npc_of(region) not in state.visited_npcs:
        return "npc"
    for index, edge in enumerate(world.edges):
        if (edge.source == region and edge.target not in state.visited_regions
                and edge_is_open(world, index, state.abilities)):
            return f"edge:{index}"
    pending = set()
    for candidate in world.regions:
        if candidate not in state.visited_regions:
            continue
        for index, edge in enumerate(world.edges):
            if (edge.source == candidate and edge.target not in state.visited_regions
                    and edge_is_open(world, index, state.abilities)):
                pending.add(candidate)
                break
    if not pending:
        return None
    path = _shortest_edge_path(state, world, region, pending)
    if path:
        return f"edge:{path[0]}"
    return None


def run(tables: dict, world_seed: str = DEFAULT_SEED) -> dict:
    """纯函数巡图，返回机器事实报告；complete=False 即判为卡死。"""
    world = World.from_tables(tables)
    state = new_progress(world)
    max_steps = (MAX_STEPS_FACTOR * len(world.regions)
                 + 4 * len(world.edges) + STEP_MARGIN)
    events: list[dict] = []
    surveys: list[dict] = []
    finished = False

    for _ in range(max_steps):
        action = choose_action(state, world)
        if action is None:
            finished = True
            break
        before = state
        state = step(state, action, world)
        event = {
            "step": state.tick,
            "action": action,
            "region_before": before.region,
            "region_after": state.region,
            "abilities_before": sorted(before.abilities),
            "blocked": state.blocked > before.blocked,
            "log_tail": state.log[-1] if state.log else "",
        }
        if action.startswith("edge:") and before.region != state.region:
            index = int(action[len("edge:"):])
            edge = world.edges[index]
            event.update({
                "edge": index,
                "edge_from": edge.source,
                "edge_to": edge.target,
                "requires": list(edge.requires),
                "entered_unvisited": state.region not in before.visited_regions,
            })
        events.append(event)
        if action == "survey" and state.region not in before.surveyed_regions:
            surveys.append(survey_region(tables, world_seed, state.region, world))

    cov = coverage(world)
    complete = bool(
        finished
        and len(state.visited_regions) == len(world.regions)
        and len(state.visited_npcs) == len(world.npcs)
        and len(state.surveyed_regions) == len(world.regions)
        and len(surveys) == len(world.regions)
    )
    return {
        "world_seed": str(world_seed),
        "regions_total": len(world.regions),
        "edges_total": len(world.edges),
        "npcs_total": len(world.npcs),
        "steps": len(events),
        "max_steps": max_steps,
        "complete": complete,
        "visited_regions": sorted(state.visited_regions),
        "visited_npcs": sorted(state.visited_npcs),
        "abilities": sorted(state.abilities),
        "surveyed_regions": sorted(state.surveyed_regions),
        "surveyed_chunks": sum(item["chunks"] for item in surveys),
        "surveys": surveys,
        "events": events,
        "blocked": state.blocked,
        "coverage": {
            "reachable": sorted(cov["reachable"]),
            "owned": sorted(cov["owned"]),
            "rounds": cov["rounds"],
            "complete": cov["complete"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    seed = args[0] if args else DEFAULT_SEED
    root = Path(__file__).resolve().parents[1]
    tables = schema.load_all(root)
    report = run(tables, seed)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
