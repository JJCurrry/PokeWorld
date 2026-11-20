"""双击启动入口（发布工程，不改任何 G0–G7 已验收模块）。

职责：把「资源根目录」与「存档目录」从源码路径解耦，供 PyInstaller onefile 使用。
- 源码态：资源根 = 仓库根（本文件在 tools/ 下，parents[1] 即根）；存档 = 根/saves。
- 冻结态（exe）：资源根 = PyInstaller 解压目录 sys._MEIPASS（data/ 已打进包）；
  存档 = exe 所在目录/saves，保证双击用户能在自己看得见的地方找到存档。

本模块零游戏逻辑、零状态写入、零随机 / 时钟；校验一律显式抛错，禁 assert。
直接调用 src.main.main 的 --window 路径，沿用已验收的按键映射与唯一文件 I/O 边界。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN_ATTR = "_MEIPASS"
SAVE_DIR_NAME = "saves"
DEFAULT_SAVE_NAME = "slot1.json"


def resource_root() -> Path:
    """数据表所在根目录：冻结态取 PyInstaller 解压目录，源码态取仓库根。"""
    bundle = getattr(sys, FROZEN_ATTR, None)
    if isinstance(bundle, str) and bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[1]


def save_path() -> Path:
    """存档写入位置：exe 同目录（冻结态）或仓库根（源码态）下的 saves/。"""
    bundle = getattr(sys, FROZEN_ATTR, None)
    base = Path(sys.argv[0]).resolve().parent if isinstance(bundle, str) and bundle \
        else Path(__file__).resolve().parents[1]
    target = base / SAVE_DIR_NAME / DEFAULT_SAVE_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def main() -> int:
    """启动窗口模式；路径参数显式注入，避免依赖当前工作目录。"""
    root = resource_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # 已验收模块的 ROOT 均在模块级按 __file__ 计算，冻结态会指向临时目录而非资源根；
    # 在调用前逐个覆盖为资源根，使读表 / 报告自检从包内资源取数，零改这些模块源码。
    from src import main as app
    app.ROOT = root
    import gate
    import g5_report
    gate.ROOT = root
    g5_report.ROOT = root

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    return app.main(["--window", "--path", str(save_path())])


if __name__ == "__main__":
    raise SystemExit(main())
