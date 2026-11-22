"""G8/S8-01 美术资产加载器：按稳定名读取原创 PNG，缺图优雅降级。

- 顶层零 pygame import（G5 契约）：真正要画图时才由 overworld_view 传入 pygame 模块。
- 资源根：冻结态取 `sys._MEIPASS`（PyInstaller 解包目录，由 build_exe 纳入 assets/），
  源码态取本文件上溯两级即仓库根；与 tools/launcher.py::resource_root 同口径。
- 加载失败（缺文件 / 无 pygame / 图片损坏）返回 None，渲染层回退原几何绘制。
- 零 I/O 于状态层、零随机、零时钟；资产是静态只读资源，不进 RNG 流（R1）。
"""
from __future__ import annotations

import sys
from pathlib import Path

FROZEN_ATTR = "_MEIPASS"
ASSETS_DIR = Path("assets") / "sprites"


def resource_root() -> Path:
    """资产根目录（含 assets/ 的那一层）。"""
    bundle = getattr(sys, FROZEN_ATTR, None)
    if isinstance(bundle, str) and bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[2]


def asset_path(relative: str) -> Path:
    return resource_root() / ASSETS_DIR / relative


def available() -> bool:
    """资产目录是否就绪（供报告与测试核对，不做视觉结论）。"""
    return asset_path("player.png").is_file()


def load_image(pygame: object, relative: str) -> object | None:
    """加载单张 PNG 为 convert_alpha Surface；任何失败返回 None。"""
    path = asset_path(relative)
    if not path.is_file():
        return None
    try:
        image = pygame.image.load(str(path))
    except Exception:
        return None
    try:
        return image.convert_alpha()  # 需 display 已初始化；失败则回退带 alpha 的原图
    except Exception:
        return image  # PNG 自带 alpha，未 convert 也能正确 blit


def load_all(pygame: object) -> dict:
    """加载全套资产：player / 8 潮灵 / 7 地标；缺哪张就少哪项。"""
    out: dict = {
        "player": load_image(pygame, "player.png"),
        "creatures": {},
        "landmarks": {},
    }
    for index in range(1, 9):
        image = load_image(pygame, f"creatures/c{index:02d}.png")
        if image is not None:
            out["creatures"][f"c{index:02d}"] = image
    for index in range(1, 8):
        image = load_image(pygame, f"landmarks/r{index}.png")
        if image is not None:
            out["landmarks"][f"r{index}"] = image
    return out


def facts() -> dict:
    """机器事实：资产根目录、是否齐全、各资产文件数（不含观感判断）。"""
    return {
        "root": str(resource_root()),
        "available": available(),
        "creatures": len(list((resource_root() / ASSETS_DIR / "creatures").glob("c*.png"))),
        "landmarks": len(list((resource_root() / ASSETS_DIR / "landmarks").glob("r*.png"))),
        "player": (resource_root() / ASSETS_DIR / "player.png").is_file(),
    }
