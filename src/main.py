"""G5 入口 CLI：headless 完整通关 / pygame 窗口 / 存档文件 I/O。

只有本模块做**文件读写**；会话层、投影层、窗口层全是纯函数 / 只读渲染
（`ADR-005` §决定 1 / §决定 4）。存档走 G4 `to_save / encode / decode / from_save`
三类字段投影，`saves/` 已被 `.gitignore` 排除（生成结果不入库）。

用法：
  python -m src.main --headless [--seed G5-demo]
  python -m src.main --window   [--path saves/slot1.json]
  python -m src.main --save saves/slot1.json
  python -m src.main --load saves/slot1.json
依赖缺失时 `--window` 打印明确提示并**降级 headless**（exit 0），不漏 traceback。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import autoplayer  # noqa: E402
import g5_report  # noqa: E402
from src import schema  # noqa: E402
from src.view import deps  # noqa: E402
from src.world import session as play  # noqa: E402

DEFAULT_SAVE = "saves/slot1.json"


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _save_report(tables: dict, seed: str, path: str) -> dict:
    """跑一遍完整通关，把三类字段投影写入存档文件。"""
    start = play.new_session(tables, seed)
    final, actions = play.play_to_goal(start, tables,
                                       autoplayer.choose_action)
    text = play.serialize(final, tables)
    _write(path, text)
    return {
        "mode": "save",
        "path": str(path),
        "bytes": len(text.encode("utf-8")),
        "steps": len(actions),
        "complete": play.is_complete(final),
    }


def _load_report(tables: dict, path: str) -> dict:
    """读存档 → 还原 → 继续推进到联盟（存档不破坏可通关性）。"""
    text = _read(path)
    restored = play.restore(text, tables)
    final, actions = play.play_to_goal(restored, tables,
                                       autoplayer.choose_action)
    return {
        "mode": "load",
        "path": str(path),
        "bytes": len(text.encode("utf-8")),
        "restored_region": restored.state.progress.region,
        "resumed_steps": len(actions),
        "resumed_complete": play.is_complete(final),
        "resumed_region": final.state.progress.region,
        "resumed_blocked": final.state.progress.blocked,
    }


def _window_report(tables: dict, seed: str, path: str) -> tuple[int, dict]:
    """开真实窗口；依赖缺失时降级 headless 并给出「怎么装 / 怎么绕」提示。"""
    if not deps.pygame_available():
        payload = {
            "mode": "window",
            "window": "unavailable",
            "hint": deps.INSTALL_HINT,
            "disable_env": deps.DISABLE_ENV,
            "fallback": "headless",
        }
        payload.update(_headless(tables, seed))
        return (0 if payload["complete"] else 1), payload

    # 抑制 pygame 的欢迎横幅，保证 stdout 只有一行可解析的 JSON 报告。
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    from src.view.window import run_window

    current = play.new_session(tables, seed)

    def do_save(state):
        _write(path, play.serialize(state, tables))
        return state

    def do_load(state):
        return play.restore(_read(path), tables)

    handlers = {
        "quit": lambda state: None,
        "auto": lambda state: play.play_to_goal(
            state, tables, autoplayer.choose_action)[0],
        "save": do_save,
        "load": do_load,
    }
    payload = run_window(current, tables, handlers=handlers)
    payload["mode"] = "window"
    return 0, payload


def _headless(tables: dict, seed: str) -> dict:
    return g5_report.run(tables, seed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PokeWorld G5 可玩闭环入口")
    parser.add_argument("--headless", action="store_true", help="无显示器完整通关并输出机器事实")
    parser.add_argument("--window", action="store_true", help="开 pygame 2D 俯视窗口")
    parser.add_argument("--seed", default="G5-demo", help="世界种子")
    parser.add_argument("--save", default="", help="跑通关并把投影写入该路径")
    parser.add_argument("--load", default="", help="从该存档还原并继续通关")
    parser.add_argument("--path", default=DEFAULT_SAVE, help="窗口 F5/F9 使用的存档路径")
    args = parser.parse_args(argv)

    tables = schema.load_all(ROOT)
    if args.load:
        payload = _load_report(tables, args.load)
        code = 0 if payload["resumed_complete"] else 1
    elif args.save:
        payload = _save_report(tables, args.seed, args.save)
        code = 0 if payload["complete"] else 1
    elif args.window:
        code, payload = _window_report(tables, args.seed, args.path)
    else:
        payload = _headless(tables, args.seed)
        code = 0 if payload["complete"] else 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
