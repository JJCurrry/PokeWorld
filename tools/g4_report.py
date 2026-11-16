"""G4 端到端机器事实报告：巡图 → 图鉴 → 脚本 → 效果 → 存档 roundtrip。

用法：`python tools/g4_report.py [world_seed]`（默认 `G4-demo`）。
`run(tables, world_seed)` 是纯函数：不读时钟、不写文件、不改传入的表；
只有 `main()` 做加载与打印。报告只写机器事实，不含手感 / 品味结论。

三条 DoD 的证据：
- E1 图鉴里程碑可达成：确定性巡图后 `atlas.complete=true`，8 潮灵按出没条件
  登记；另用「死端拓扑表副本」（edges=[]）反证 `counter_proof.complete=false`。
- E2 存档 roundtrip 绿：`save.roundtrip=true`，且生成结果键被 decode 全数拒绝。
- E3 事件脚本不直接改世界状态：`game.world_untouched=true`（Progress / World /
  Atlas / party 逐字段不动），只有 flags / notes / log 变化。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))
if str(ROOT_HINT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT_HINT / "tools"))

import autoplayer as player  # noqa: E402
from src import schema  # noqa: E402
from src.gen.chunk import generate_chunk  # noqa: E402
from src.world.atlas import milestone, new_atlas, observe_chunk  # noqa: E402
from src.world.evolution import stats_of  # noqa: E402
from src.world.game import (  # noqa: E402
    apply_effects, from_save, new_game, to_save, train,
)
from src.world.progress import World, chunk_grid, new_progress, step  # noqa: E402
from src.world.save import FORBIDDEN_KEYS, SAVE_KEYS, decode, encode  # noqa: E402
from src.world.scripts import (  # noqa: E402
    all_scripts, effects_of, select, texts_of,
)

DEFAULT_SEED = "G4-demo"
STEP_FACTOR = 8
EDGE_FACTOR = 4
STEP_MARGIN = 16
SCRIPT_LIMIT = 20


def _walk(tables: dict, world_seed: str) -> tuple:
    """确定性巡图 + 逐区块图鉴登记；复用 G3 自动玩家的表序决策，不改其代码。"""
    world = World.from_tables(tables)
    state = new_progress(world)
    atlas = new_atlas()
    max_steps = (STEP_FACTOR * len(world.regions)
                 + EDGE_FACTOR * len(world.edges) + STEP_MARGIN)
    steps = 0
    chunks = 0
    finished = False
    for _ in range(max_steps):
        action = player.choose_action(state, world)
        if action is None:
            finished = True
            break
        before = state
        state = step(state, action, world)
        steps += 1
        if (action == "survey"
                and len(state.surveyed_regions) > len(before.surveyed_regions)):
            width, height = chunk_grid(world, before.region)
            for cy in range(height):
                for cx in range(width):
                    chunk = generate_chunk(tables, world_seed,
                                           before.region, cx, cy)
                    atlas = observe_chunk(atlas, before.region, chunk)
                    chunks += 1
    return world, state, atlas, steps, chunks, finished


def _dead_end_tables(tables: dict) -> dict:
    """死端拓扑表副本：断开全部边，只有 start 可达；不改任何受保护文件。"""
    dead = copy.deepcopy(tables)
    dead["topology.json"]["edges"] = []
    return dead


def run(tables: dict, world_seed: str = DEFAULT_SEED) -> dict:
    """纯函数：产出 G4 三条 DoD 的机器事实 JSON。"""
    world, state, atlas, steps, chunks, finished = _walk(tables, world_seed)
    facts = milestone(world, tables, atlas, state.surveyed_regions)
    expected_chunks = sum(width * height for _, width, height in world.grids)

    dead = _dead_end_tables(tables)
    dead_world, dead_state, dead_atlas, _, dead_chunks, _ = _walk(dead, world_seed)
    dead_facts = milestone(dead_world, dead, dead_atlas,
                           dead_state.surveyed_regions)

    rows = all_scripts()
    contexts = tuple({row.key: row.match} for row in rows)
    chosen: list = []
    seen: set[str] = set()
    for context in contexts:
        for row in select(context):
            if row.sid not in seen:
                seen.add(row.sid)
                chosen.append(row)
    chosen_tuple = tuple(chosen)
    effects = effects_of(chosen_tuple)
    texts = texts_of(chosen_tuple)
    kinds = {kind: sum(1 for effect in effects if effect.kind == kind)
             for kind in ("flag", "note", "log")}

    initial = new_game(tables, world_seed, state, atlas)
    applied = apply_effects(initial, effects)
    world_untouched = (
        applied.world == initial.world
        and applied.progress == initial.progress
        and applied.atlas == initial.atlas
        and applied.party == initial.party
        and applied.world_seed == initial.world_seed
    )
    display_changed = (applied.flags != initial.flags
                       or applied.notes != initial.notes
                       or applied.log != initial.log)
    trained = train(applied, 0)
    before_member, after_member = initial.party[0], trained.party[0]

    save = to_save(trained, tables)
    text = encode(save)
    back = decode(text)
    roundtrip = back == save and encode(back) == text
    restored = from_save(back, tables)
    restored_ok = bool(
        restored.progress.surveyed_regions == state.surveyed_regions
        and restored.progress.abilities == state.abilities
        and restored.party == trained.party
        and restored.world_seed == str(world_seed)
        and not restored.atlas.entries
    )
    rejected = []
    for key in FORBIDDEN_KEYS:
        poisoned = json.loads(text)
        poisoned[key] = []
        try:
            decode(json.dumps(poisoned, ensure_ascii=False))
        except ValueError:
            rejected.append(key)

    complete = bool(
        finished
        and chunks == expected_chunks
        and facts["complete"]
        and facts["species_covered"] == facts["species_total"]
        and not dead_facts["complete"]
        and len(rows) <= SCRIPT_LIMIT
        and len(chosen_tuple) == len(rows)
        and len(effects) > 0
        and world_untouched
        and display_changed
        and after_member.level == before_member.level + 1
        and roundtrip
        and restored_ok
        and len(rejected) == len(FORBIDDEN_KEYS)
    )
    return {
        "world_seed": str(world_seed),
        "survey": {
            "finished": finished,
            "steps": steps,
            "chunks": chunks,
            "expected_chunks": expected_chunks,
            "surveyed_regions": sorted(state.surveyed_regions),
        },
        "atlas": {
            "complete": facts["complete"],
            "regions": len(facts["regions"]),
            "entries": facts["entries"],
            "species_total": facts["species_total"],
            "species_covered": facts["species_covered"],
            "registered_species": list(facts["registered_species"]),
            "trivial_regions": [row["region"] for row in facts["regions"]
                                if row["trivial"]],
            "per_region": [dict(row) for row in facts["regions"]],
        },
        "counter_proof": {
            "complete": dead_facts["complete"],
            "surveyed_regions": sorted(dead_state.surveyed_regions),
            "chunks": dead_chunks,
            "regions": len(dead_world.regions),
            "edges": len(dead_world.edges),
        },
        "scripts": {
            "total": len(rows),
            "selected": len(chosen_tuple),
            "effects": len(effects),
            "kinds": kinds,
            "texts": list(texts),
        },
        "game": {
            "world_untouched": world_untouched,
            "display_changed": display_changed,
            "flags": sorted(applied.flags),
            "notes": list(applied.notes),
            "log": list(applied.log),
        },
        "party": {
            "cid": after_member.cid,
            "level_before": before_member.level,
            "level_after": after_member.level,
            "stage": after_member.stage,
            "iv": after_member.iv,
            "stats": dict(stats_of(after_member, tables)),
        },
        "save": {
            "roundtrip": roundtrip,
            "restored_ok": restored_ok,
            "bytes": len(text.encode("utf-8")),
            "keys": list(SAVE_KEYS),
            "flags": len(save.flags),
            "party": len(save.party),
            "rejected_generated_keys": rejected,
        },
        "complete": complete,
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
