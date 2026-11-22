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
import traceback
from pathlib import Path

FROZEN_ATTR = "_MEIPASS"
SAVE_DIR_NAME = "saves"
DEFAULT_SAVE_NAME = "slot1.json"
DIAG_NAME = "启动诊断.log"


def base_dir() -> Path:
    """exe 所在目录（冻结态）或仓库根（源码态）；诊断与存档都落这里。"""
    bundle = getattr(sys, FROZEN_ATTR, None)
    return Path(sys.argv[0]).resolve().parent if isinstance(bundle, str) and bundle \
        else Path(__file__).resolve().parents[1]


def log(message: str) -> None:
    """追加一行诊断；写失败也不影响游戏。"""
    try:
        target = base_dir() / SAVE_DIR_NAME / DIAG_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def show_error(text: str) -> None:
    """无控制台 exe 里用系统弹窗显示错误，避免静默闪退。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text[:1800], "PokeWorld 启动失败", 0x10)
    except Exception:
        pass


def resource_root() -> Path:
    """数据表所在根目录：冻结态取 PyInstaller 解压目录，源码态取仓库根。"""
    bundle = getattr(sys, FROZEN_ATTR, None)
    if isinstance(bundle, str) and bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[1]


def save_path() -> Path:
    """存档写入位置：exe 同目录（冻结态）或仓库根（源码态）下的 saves/。"""
    target = base_dir() / SAVE_DIR_NAME / DEFAULT_SAVE_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _boot() -> int:
    """真正的启动流程，独立成函数以便统一捕获异常。"""
    log("启动：begin")
    root = resource_root()
    log("资源根：" + str(root))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # 已验收模块的 ROOT 均在模块级按 __file__ 计算，冻结态会指向临时目录而非资源根；
    # 在调用前逐个覆盖为资源根，使读表 / 报告自检从包内资源取数，零改这些模块源码。
    # G8 起双击入口改为 src.ow_main（连续开放世界）；旧 src.main 入口仍保留可命令行调用。
    from src import ow_main as app
    app.ROOT = root
    import ow_report
    ow_report.ROOT = root
    import gate
    import g5_report
    gate.ROOT = root
    g5_report.ROOT = root
    log("模块导入：ok（开放世界入口）")

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    # G8/S8-01：资产目录是否随包解出（机器事实，不含观感结论）
    from src.view import asset_atlas
    log("资产目录：" + str(asset_atlas.asset_path("player.png")) +
        " 就绪=" + str(asset_atlas.available()))
    path = save_path()
    log("存档路径：" + str(path))
    log("进入开放世界窗口循环")
    code = app.main(["--window", "--path", str(path)])
    log("窗口循环返回：code=" + str(code))
    return code


def main() -> int:
    """启动窗口模式；任何异常都落日志并弹窗，避免无控制台 exe 静默闪退。"""
    try:
        return _boot()
    except Exception as exc:  # 无控制台下必须兜底；SystemExit 等正常退出不当崩溃
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log("崩溃：\n" + detail)
        show_error("启动时出错，详情已写入 saves/启动诊断.log：\n\n" + str(exc)[:600])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
