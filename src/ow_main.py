"""G8 开放世界入口：headless 报告 / 连续窗口 / 存档 I/O（ADR-009）。

只有本模块做文件 I/O；世界 / 探索 / 投影层全是纯函数 / 只读渲染。
依赖缺失时 `--window` 优雅降级 headless，不漏 traceback（G5 契约沿用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from src import schema                       # noqa: E402
from src.view import deps                    # noqa: E402
from src.view.overworld_view import run_world  # noqa: E402
from src.world import explore                # noqa: E402
from src.world.game import from_save, to_save  # noqa: E402
from src.world.save import decode, encode    # noqa: E402
import ow_report                             # noqa: E402（tools 已在 sys.path）
from dataclasses import replace              # noqa: E402

DEFAULT_SEED = "G8-demo"
DEFAULT_SAVE = "saves/ow_slot1.json"


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _do_save(tables: dict, world: explore.Explore, path: str) -> dict:
    text = encode(to_save(world.state, tables))
    _write(path, text)
    return {"mode": "save", "path": path, "bytes": len(text.encode("utf-8")),
            "region": explore.current_region(tables, world)}


def _do_load(tables: dict, text: str, seed: str, path: str) -> explore.Explore:
    state = from_save(decode(text), tables)
    base = explore.new_explore(tables, seed)
    return replace(base, state=state)


def _window(tables: dict, seed: str, path: str) -> tuple[int, dict]:
    if not deps.pygame_available():
        payload = {"mode": "window", "window": "unavailable",
                   "hint": deps.INSTALL_HINT, "disable_env": deps.DISABLE_ENV,
                   "fallback": "headless"}
        payload.update(ow_report.run(tables, seed))
        return (0 if payload["complete"] else 1), payload

    def do_save(world: explore.Explore) -> explore.Explore:
        _do_save(tables, world, path)
        return world

    def do_load(world: explore.Explore) -> explore.Explore | None:
        if not Path(path).is_file():
            return world
        return _do_load(tables, _read(path), seed, path)

    payload = run_world(tables, seed, handlers={"save": do_save, "load": do_load})
    payload["mode"] = "window"
    return 0, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PokeWorld G8 开放世界入口")
    parser.add_argument("--headless", action="store_true", help="无显示器端到端报告")
    parser.add_argument("--window", action="store_true", help="开连续世界 pygame 窗口")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="世界种子")
    parser.add_argument("--save", default="", help="跑通并把存档写入该路径")
    parser.add_argument("--load", default="", help="读档并输出机器事实")
    parser.add_argument("--path", default=DEFAULT_SAVE, help="窗口 F5/F9 存档路径")
    args = parser.parse_args(argv)

    tables = schema.load_all(ROOT)
    if args.save:
        payload = _do_save(tables, explore.autoplay(tables, explore.new_explore(tables, args.seed)), args.save)
        code = 0
    elif args.load:
        payload = {"mode": "load", "path": args.load,
                   **ow_report.run(tables, args.seed)}
        code = 0 if Path(args.load).is_file() else 1
    elif args.window:
        code, payload = _window(tables, args.seed, args.path)
    else:
        payload = ow_report.run(tables, args.seed)
        code = 0 if payload["complete"] else 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
