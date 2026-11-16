"""G5 端到端机器事实报告：通关 / 反证 / 存档 / 纯投影 / 可选依赖 / 零改表。

用法：`python tools/g5_report.py [world_seed]`（默认 `G5-demo`）。
`run(tables, world_seed)` 不改传入的表、不写文件、不读时钟；只有 `main()` 做
加载与打印。报告只写机器事实，不含手感 / 观感结论（B 级归人）。

六项 DoD 的证据：
- F1 完整通关：`session.complete=true` + 20 步级动作序列逐个核对无跳关，
  图鉴里程碑 `atlas.complete=true`，另用「从不与 NPC 交谈」的序列反证为 False。
- F2 表现层只读：`frame_of` 同参两次逐字段相等、表未被改、键位映射可核对。
- F3 存档：`encode(decode(text)) == text`、生成结果键全数拒绝、读档后仍能通关。
- F4 依赖：`deps.dependency_facts()` 给出可选依赖状态（缺失分支由子进程实测）。
- F5 合规：UI 文案由 `tests/test_g5_layout.py` 做 R4 词表自检。
- F6 门控：`gate.run(ROOT)` 全绿、golden 快照与 manifest 未被改动。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import autoplayer  # noqa: E402
import gate  # noqa: E402
from src import schema  # noqa: E402
from src.view import deps  # noqa: E402
from src.view.layout import KEY_ACTIONS, frame_of  # noqa: E402
from src.world import session as play  # noqa: E402
from src.world.atlas import milestone  # noqa: E402
from src.world.progress import World, edge_is_open  # noqa: E402
from src.world.save import FORBIDDEN_KEYS, SAVE_KEYS, decode, encode  # noqa: E402

DEFAULT_SEED = "G5-demo"
EDGE_PREFIX = "edge:"


def _replay(tables: dict, world_seed: str,
            actions: tuple[str, ...]) -> tuple[object, tuple[dict, ...]]:
    """逐步重放动作序列，逐个 `edge:i` 核对 `requires ⊆ abilities`（无跳关）。"""
    current = play.new_session(tables, world_seed)
    events: list[dict] = []
    for action in actions:
        before = current.state.progress
        current = play.apply(current, action, tables)
        after = current.state.progress
        if action.startswith(EDGE_PREFIX):
            index = int(action[len(EDGE_PREFIX):])
            requires = tuple(current.state.world.edges[index].requires)
            events.append({
                "step": len(events),
                "action": action,
                "requires": list(requires),
                "satisfied": set(requires).issubset(before.abilities),
                "moved": after.region != before.region,
            })
    return current, tuple(events)


def _no_npc_walk(tables: dict, world_seed: str) -> object:
    """反证：从不与 NPC 交谈就拿不到能力，永远走不到联盟。"""
    world = World.from_tables(tables)
    current = play.new_session(tables, world_seed)
    for _ in range(40):
        progress = current.state.progress
        action = None
        if progress.region not in progress.surveyed_regions:
            action = "survey"
        else:
            for index, edge in enumerate(world.edges):
                if (edge.source == progress.region
                        and edge.target not in progress.visited_regions
                        and edge_is_open(world, index, progress.abilities)):
                    action = f"{EDGE_PREFIX}{index}"
                    break
        if action is None:
            break
        current = play.apply(current, action, tables)
    return current


def run(tables: dict, world_seed: str = DEFAULT_SEED) -> dict:
    """纯函数：产出 G5 六项 DoD 的机器事实 JSON（不写手感 / 品味结论）。"""
    before = copy.deepcopy(tables)
    initial = play.new_session(tables, world_seed)
    final, actions = play.play_to_goal(initial, tables,
                                       autoplayer.choose_action)
    replayed, edge_events = _replay(tables, world_seed, actions)
    world = final.state.world
    goal = play.goal_region(world)
    progress = final.state.progress

    atlas_facts = milestone(world, tables, final.state.atlas,
                            progress.surveyed_regions)
    expected_chunks = sum(width * height for _, width, height in world.grids)
    no_npc = _no_npc_walk(tables, world_seed)

    text = play.serialize(final, tables)
    save_data = decode(text)
    roundtrip = encode(save_data) == text and encode(decode(text)) == text
    rejected = []
    for key in FORBIDDEN_KEYS:
        poisoned = json.loads(text)
        poisoned[key] = []
        try:
            decode(json.dumps(poisoned, ensure_ascii=False))
        except ValueError:
            rejected.append(key)

    restored = play.restore(text, tables)
    resumed, resumed_actions = play.play_to_goal(
        restored, tables, autoplayer.choose_action)

    frame1 = frame_of(final, tables)
    frame2 = frame_of(final, tables)
    frame_pure = frame1 == frame2
    tables_unchanged = tables == before
    try:
        schema.verify_manifest(ROOT)
        manifest_ok = True
    except (schema.SchemaError, OSError, ValueError):
        manifest_ok = False
    golden_ok = gate.check_golden_snapshot(ROOT) == []
    gate_ok = gate.run(ROOT) == []

    no_jump = all(event["satisfied"] for event in edge_events)
    complete = bool(
        play.is_complete(final)
        and play.is_complete(replayed)
        and progress.blocked == 0
        and len(progress.visited_npcs) == len(world.npcs)
        and len(progress.surveyed_regions) == len(world.regions)
        and final.chunks_seen == expected_chunks
        and no_jump
        and atlas_facts["complete"]
        and atlas_facts["species_covered"] == atlas_facts["species_total"]
        and not play.is_complete(no_npc)
        and no_npc.state.progress.region != goal
        and roundtrip
        and len(rejected) == len(FORBIDDEN_KEYS)
        and play.is_complete(resumed)
        and resumed.state.progress.blocked == 0
        and frame_pure
        and tables_unchanged
        and manifest_ok and golden_ok and gate_ok
        and deps.dependency_facts()["headless_available"]
    )
    return {
        "world_seed": str(world_seed),
        "session": {
            "complete": play.is_complete(final),
            "steps": len(actions),
            "region": progress.region,
            "goal": goal,
            "visited_regions": len(progress.visited_regions),
            "visited_npcs": len(progress.visited_npcs),
            "surveyed_regions": len(progress.surveyed_regions),
            "chunks_seen": final.chunks_seen,
            "expected_chunks": expected_chunks,
            "abilities": len(progress.abilities),
            "blocked": progress.blocked,
            "edge_checks": len(edge_events),
            "no_jump": no_jump,
            "edge_events": [dict(event) for event in edge_events],
        },
        "atlas": {
            "complete": atlas_facts["complete"],
            "entries": atlas_facts["entries"],
            "species_total": atlas_facts["species_total"],
            "species_covered": atlas_facts["species_covered"],
            "trivial_regions": [row["region"] for row in atlas_facts["regions"]
                                if row["trivial"]],
        },
        "counter_proof": {
            "complete": play.is_complete(no_npc),
            "region": no_npc.state.progress.region,
            "goal": goal,
            "abilities": len(no_npc.state.progress.abilities),
        },
        "save": {
            "roundtrip": roundtrip,
            "bytes": len(text.encode("utf-8")),
            "flags": len(save_data.flags),
            "party": len(save_data.party),
            "keys": list(SAVE_KEYS),
            "rejected_generated_keys": rejected,
            "restored_region": restored.state.progress.region,
            "resumed_steps": len(resumed_actions),
            "resumed_complete": play.is_complete(resumed),
            "resumed_region": resumed.state.progress.region,
            "resumed_atlas_entries": len(resumed.state.atlas.entries),
        },
        "view": {
            "frame_pure": frame_pure,
            "grid": [len(frame1.grid), len(frame1.grid[0])],
            "palette": len(frame1.palette),
            "lines": len(frame1.lines),
            "key_actions": len(KEY_ACTIONS),
            "tables_unchanged": tables_unchanged,
            "frame_complete": frame1.complete,
        },
        "dependency": deps.dependency_facts(),
        "gate": {"ok": gate_ok, "golden_snapshot_ok": golden_ok,
                 "manifest_ok": manifest_ok},
        "complete": complete,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    seed = args[0] if args else DEFAULT_SEED
    tables = schema.load_all(ROOT)
    report = run(tables, seed)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
