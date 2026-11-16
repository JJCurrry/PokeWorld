"""G5 pygame 窗口适配：按 `Frame` 画 2D 俯视区块，把键盘翻译成动作。

设计依据 `ADR-005` §决定 1 / §决定 3：
- **顶层零 pygame import**，只有 `run_window` 内经 `require_pygame()` 延迟导入；
- 渲染层只拿 `Frame` 纯数据，绝不持有或修改 `GameState` / `Progress`；
- 世界状态变更只经 `session.apply` 或由 CLI 注入的 handler，窗口不自己写状态；
- 事件驱动（`event.wait`），不读时钟、不引入裸随机，保持不变量 #1。

模块级只放不可变字面量；字体查询失败回退内置字体，不抛异常给玩家。
"""
from __future__ import annotations

from .deps import require_pygame
from .layout import CLI_ACTIONS, Frame, frame_of, action_for_key
from ..world.session import Session, apply, is_complete

WINDOW_SIZE = (960, 600)
CELL_SIZE = 48
GRID_ORIGIN = (24, 24)
PANEL_ORIGIN = (440, 40)
LINE_HEIGHT = 34
BG_COLOR = (18, 26, 38)
TEXT_COLOR = (232, 240, 246)
CURSOR_COLOR = (246, 210, 112)
FONT_SIZE = 20
FONT_CANDIDATES = ("microsoftyahei", "simhei", "notosanscjksc", "arialunicode", "arial")
DEFAULT_FRAMES = 240


def _make_font(pygame: object) -> object:
    """按本机可用字体挑一个；没有就回退内置字体（中文显示归 B 级观感）。"""
    available = set(pygame.font.get_fonts())
    for candidate in FONT_CANDIDATES:
        if candidate in available:
            font = pygame.font.SysFont(candidate, FONT_SIZE)
            if font is not None:
                return font
    return pygame.font.Font(None, FONT_SIZE)


def draw(surface: object, frame: Frame, pygame: object, font: object) -> int:
    """把一帧画到 Surface；返回画出的地形格数（机器可核对，不看像素）。"""
    pygame.draw.rect(surface, BG_COLOR,
                     pygame.Rect(0, 0, WINDOW_SIZE[0], WINDOW_SIZE[1]))
    colors = dict(frame.palette)
    drawn = 0
    for row_index, row in enumerate(frame.grid):
        for col_index, terrain in enumerate(row):
            rect = pygame.Rect(
                GRID_ORIGIN[0] + col_index * CELL_SIZE,
                GRID_ORIGIN[1] + row_index * CELL_SIZE,
                CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(surface, colors[terrain], rect)
            pygame.draw.rect(surface, BG_COLOR, rect, 1)
            drawn += 1
    cx, cy = frame.cursor
    cursor_rect = pygame.Rect(
        GRID_ORIGIN[0] + cx * CELL_SIZE + CELL_SIZE // 4,
        GRID_ORIGIN[1] + cy * CELL_SIZE + CELL_SIZE // 4,
        CELL_SIZE // 2, CELL_SIZE // 2)
    pygame.draw.rect(surface, CURSOR_COLOR, cursor_rect, 3)

    for index, line in enumerate(frame.lines):
        surface.blit(font.render(line, True, TEXT_COLOR),
                     (PANEL_ORIGIN[0], PANEL_ORIGIN[1] + index * LINE_HEIGHT))
    hint_y = PANEL_ORIGIN[1] + (len(frame.lines) + 1) * LINE_HEIGHT
    surface.blit(font.render(frame.hint, True, TEXT_COLOR),
                 (PANEL_ORIGIN[0], hint_y))
    surface.blit(font.render("通关" if frame.complete else "巡游中", True, CURSOR_COLOR),
                 (PANEL_ORIGIN[0], hint_y + LINE_HEIGHT))
    return drawn


def run_window(session: Session, tables: dict, *,
               max_frames: int | None = None,
               block: bool = True,
               handlers: dict | None = None) -> dict:
    """事件循环；返回机器事实（帧数 / 动作 / 是否通关），不写手感结论。

    `handlers` 由 CLI 注入，处理需要文件 I/O 或自动通关的动作；未登记的
    CLI 动作被忽略，绝不传给 `session.apply` 造成异常。
    """
    pygame = require_pygame()
    callbacks = {} if handlers is None else handlers
    pygame.init()
    surface = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("PokeWorld · 潮屿巡游")
    font = _make_font(pygame)
    limit = DEFAULT_FRAMES if max_frames is None else max_frames
    frames = 0
    cells = 0
    frame = frame_of(session, tables)
    actions: list[str] = []
    running = True

    while running and frames < limit:
        frame = frame_of(session, tables)
        cells = draw(surface, frame, pygame, font)
        pygame.display.flip()
        events = [pygame.event.wait()] if block else pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type != pygame.KEYDOWN:
                continue
            key = pygame.key.name(event.key)
            action = action_for_key(key, session.state.world,
                                    session.state.progress.region)
            if action is None:
                continue
            if action in CLI_ACTIONS:
                handler = callbacks.get(action)
                if handler is None:
                    continue
                updated = handler(session)
                if updated is None:
                    running = False
                    break
                session = updated
            else:
                session = apply(session, action, tables)
            actions.append(action)
        frames += 1
        # block=False（smoke）时即使没有事件也按帧数上限退出，不依赖时钟。

    pygame.quit()
    return {
        "ok": True,
        "frames": frames,
        "cells_per_frame": len(frame.grid) * len(frame.grid[0]) if frame.grid else 0,
        "cells_drawn": cells,
        "actions": tuple(actions),
        "complete": is_complete(session),
    }


def smoke(tables: dict, world_seed: str = "G5-smoke",
          max_frames: int = 2) -> dict:
    """无头驱动下画若干帧并退出，供测试与 CLI 做真实窗口冒烟。"""
    from ..world.session import new_session

    return run_window(new_session(tables, world_seed), tables,
                      max_frames=max_frames, block=False,
                      handlers={"quit": lambda current: None})
