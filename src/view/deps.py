"""可选依赖探测：只查 spec、不执行导入，供 CLI / 测试 / 验证墙共用。

设计依据 `ADR-005` §决定 3：pygame 是 G5 的首个第三方依赖，但必须是**可选**的。
`POKEWORLD_NO_PYGAME=1` 提供可复现的缺失模拟，使「依赖缺失时验证墙优雅跳过」
能在已装 pygame 的机器上被真实子进程实测，而不是靠注释自称。

本模块零 I/O、零时钟、零裸随机、零状态赋值；校验一律显式抛错（禁 assert）。
"""
from __future__ import annotations

import os
from importlib.util import find_spec

OPTIONAL_MODULE = "pygame"
DISABLE_ENV = "POKEWORLD_NO_PYGAME"
INSTALL_HINT = "pip install -r requirements.txt"


class ViewUnavailable(RuntimeError):
    """窗口模式不可用；报错自带「怎么装 / 怎么绕」提示。"""


def pygame_available() -> bool:
    """是否被允许且能够使用 pygame；不执行 `import pygame`。"""
    if os.environ.get(DISABLE_ENV) == "1":
        return False
    try:
        return find_spec(OPTIONAL_MODULE) is not None
    except (ImportError, ValueError):
        return False


def dependency_facts() -> dict:
    """机器事实：供报告与测试核对，不含手感 / 观感结论。"""
    return {
        "module": OPTIONAL_MODULE,
        "available": pygame_available(),
        "disable_env": DISABLE_ENV,
        "headless_available": True,
        "install_hint": INSTALL_HINT,
    }


def require_pygame() -> object:
    """真正要开窗口时才导入；缺失时抛带安装提示的明确错误，不漏 traceback。"""
    if not pygame_available():
        raise ViewUnavailable(
            f"{OPTIONAL_MODULE} 不可用（未安装或被 {DISABLE_ENV}=1 禁用）；"
            f"执行 `{INSTALL_HINT}` 安装，或改用 --headless 完整通关"
        )
    try:
        import pygame
    except ImportError as exc:
        raise ViewUnavailable(
            f"{OPTIONAL_MODULE} 导入失败；执行 `{INSTALL_HINT}` 安装，"
            f"或改用 --headless 完整通关"
        ) from exc
    return pygame
