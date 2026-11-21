"""G8 开放世界端到端机器事实报告（默认种子 G8-demo）。

输出 JSON：`world` / `landmarks` / `play` / `capture` / `determinism` /
`gates` / `view` / `complete`。`complete=true` 表示连续世界闭环的机器可判定部分全过。
不证明手感 / 观感 / 品味（B 级归人）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from src import schema                      # noqa: E402
from src.gen import overworld               # noqa: E402
from src.world import explore               # noqa: E402
from src.world.progress import coverage     # noqa: E402

DEFAULT_SEED = "G8-demo"


def run(tables: dict, seed: str = DEFAULT_SEED) -> dict:
    matrix = overworld.matrix(tables, seed)
    terrains = sorted({cell for row in matrix for cell in row})
    places = overworld.landmarks(tables)
    walkable_landmarks = all(
        overworld.walkable(tables, seed, lx, ly) for _, lx, ly in places)

    start = explore.new_explore(tables, seed)
    finished = explore.autoplay(tables, start, catch_at=None)

    world = tables["topology.json"]
    from src.world.progress import World as WorldSnapshot
    cov = coverage(WorldSnapshot.from_tables(tables))

    return {
        "seed": seed,
        "world": {
            "size": overworld.WORLD_TILES,
            "terrains": terrains,
            "landmark_count": len(places),
            "landmarks_walkable": walkable_landmarks,
        },
        "landmarks": [{"region": rid, "x": round(lx, 2), "y": round(ly, 2)}
                      for rid, lx, ly in places],
        "play": {
            "region": explore.current_region(tables, finished),
            "steps": finished.steps,
            "abilities": len(finished.state.progress.abilities),
            "surveyed": len(finished.state.progress.surveyed_regions),
            "blocked": finished.state.progress.blocked,
        },
        "capture": {
            "encounters": finished.encounters,
            "captures": finished.captures,
            "atlas_entries": len(finished.state.atlas.entries),
        },
        "determinism": {
            "same_seed_identical": matrix == overworld.matrix(tables, seed),
            "diff_seed_differs": matrix != overworld.matrix(tables, seed + "-other"),
            "start_reproducible": (start.x, start.y) == (
                explore.new_explore(tables, seed).x, explore.new_explore(tables, seed).y),
        },
        "gates": {
            "coverage_complete": bool(cov["complete"]),
            "regions": len(world["regions"]),
            "edges": len(world["edges"]),
        },
        "view": {"headless": True, "continuous_movement": True},
        "complete": bool(
            explore.is_complete(tables, finished)
            and walkable_landmarks
            and matrix == overworld.matrix(tables, seed)
            and matrix != overworld.matrix(tables, seed + "-other")
            and cov["complete"]
        ),
    }


def main() -> int:
    seed = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SEED
    tables = schema.load_all(ROOT)
    payload = run(tables, seed)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
