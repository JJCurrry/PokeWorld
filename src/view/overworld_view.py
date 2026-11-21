"""G8 开放世界窗口（ADR-009）：连续地图 + 相机跟随 + 几何精灵。

- 顶层零 pygame import，仅 `run_world` 内经 `require_pygame()` 延迟导入（G5 契约）。
- 渲染层只读 `Explore`（纯快照），不回写状态；世界变更只经 `explore.apply`。
- 动画相位由帧计数驱动（不读时钟，R1）；潮灵 / 建筑 / 角色为原创几何图形，
  零外部素材（不变量 #7）。键位提示折行完整显示，修复 G7 截断问题。
"""
from __future__ import annotations

from .deps import require_pygame
from ..gen import overworld
from ..world import explore
from ..world.explore import Explore

WINDOW_SIZE = (1100, 640)
TILE = 30
VIEW_ORIGIN = (16, 16)
PANEL_X = 660
PANEL_TOP = 16
LINE_HEIGHT = 27
FONT_SIZE = 17
FPS_STEP = 1  # 帧计数步长（非时钟）

HELP_LINES = (
    "方向键 移动 · N 交谈 · S 巡查 · B 遭遇",
    "J 攻击 · K 捕捉 · L 撤离 · 数字键 道具",
    "P 昼夜 · F5 存 · F9 读 · Q 退出",
)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _make_font(pygame: object) -> object:
    available = set(pygame.font.get_fonts())
    for name in ("microsoftyahei", "simhei", "notosanscjksc", "arialunicode", "arial"):
        if name in available:
            font = pygame.font.SysFont(name, FONT_SIZE)
            if font is not None:
                return font
    return pygame.font.Font(None, FONT_SIZE)


def _palette(pygame: object, terrain: str) -> tuple[int, int, int]:
    """地形 → 颜色；按地形名做稳定哈希，代码零地形名字面量映射。"""
    table = ((54, 140, 74), (30, 96, 52), (64, 150, 196), (24, 74, 138))
    index = sum(ord(ch) for ch in terrain) % len(table)
    return table[index]


def _draw_ground(surface: object, pygame: object, tables: dict,
                 seed: str, frame: int, gx0: int, gy0: int,
                 cols: int, rows: int) -> None:
    for row in range(rows):
        for col in range(cols):
            wx, wy = gx0 + col, gy0 + row
            terrain = overworld.terrain_at(tables, seed, wx + 0.5, wy + 0.5)
            color = _palette(pygame, terrain)
            rect = pygame.Rect(VIEW_ORIGIN[0] + col * TILE, VIEW_ORIGIN[1] + row * TILE,
                               TILE, TILE)
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (18, 30, 26), rect, 1)
            h = overworld.height_at(seed, wx + 0.5, wy + 0.5)
            cx, cy = rect.centerx, rect.centery
            if h < 0.42:  # 水域：波纹（相位由帧计数驱动）
                phase = (frame + wx + wy) % 6
                pygame.draw.line(surface, (150, 210, 240),
                                 (cx - 8, cy - 4 + phase // 3),
                                 (cx + 8, cy - 4 + phase // 3), 1)
            elif h < 0.7:  # 草地：小草点
                pygame.draw.line(surface, (120, 190, 110),
                                 (cx - 5, cy + 6), (cx - 5, cy - 2), 1)
                pygame.draw.line(surface, (120, 190, 110),
                                 (cx + 4, cy + 6), (cx + 4, cy + 1), 1)
            else:  # 密林：树冠
                pygame.draw.circle(surface, (22, 74, 40), (cx, cy - 2), 9)


def _draw_landmarks(surface: object, pygame: object, tables: dict,
                    seed: str, frame: int, gx0: int, gy0: int,
                    cols: int, rows: int, current: str, font: object) -> None:
    palette = ((240, 196, 96), (232, 120, 120), (168, 142, 232),
               (120, 200, 232), (240, 160, 96), (200, 220, 120), (220, 220, 240))
    for index, (rid, lx, ly) in enumerate(overworld.landmarks(tables)):
        if not (gx0 <= lx < gx0 + cols and gy0 <= ly < gy0 + rows):
            continue
        px = VIEW_ORIGIN[0] + (lx - gx0) * TILE + TILE // 2
        py = VIEW_ORIGIN[1] + (ly - gy0) * TILE + TILE // 2
        color = palette[index % len(palette)]
        pygame.draw.polygon(surface, color,
                            [(px, py - 14), (px + 13, py + 10), (px - 13, py + 10)])
        pygame.draw.rect(surface, (250, 240, 210), (px - 5, py + 2, 10, 8))
        name = str(tables["topology.json"]["regions"][index]["name"])
        label = font.render(name, True, (255, 255, 255))
        surface.blit(label, (px - 12, py + 12))
        if rid == current:
            pulse = 16 + (frame % 8)
            pygame.draw.circle(surface, (255, 230, 120), (px, py), pulse, 2)


def _draw_player(surface: object, pygame: object, explore: Explore,
                 gx0: int, gy0: int) -> None:
    px = VIEW_ORIGIN[0] + (explore.x - gx0) * TILE + TILE // 2
    py = VIEW_ORIGIN[1] + (explore.y - gy0) * TILE + TILE // 2
    pygame.draw.circle(surface, (255, 224, 180), (px, py - 8), 7)      # 头
    pygame.draw.rect(surface, (72, 132, 220), (px - 8, py - 2, 16, 16))  # 身
    pygame.draw.rect(surface, (48, 84, 150), (px - 8, py + 14, 6, 8))   # 脚
    pygame.draw.rect(surface, (48, 84, 150), (px + 2, py + 14, 6, 8))


def _draw_creature(surface: object, pygame: object, tables: dict,
                   cid: str, cx: int, cy: int) -> None:
    row = next((c for c in tables["species.json"]["creatures"] if c["id"] == cid), None)
    base = ((120, 200, 220), (200, 170, 120), (150, 200, 140),
            (220, 140, 140), (180, 150, 220), (230, 190, 110),
            (140, 180, 210), (210, 130, 170))
    index = (sum(ord(ch) for ch in cid)) % len(base)
    color = base[index]
    pygame.draw.ellipse(surface, color, (cx - 26, cy - 18, 52, 36))
    pygame.draw.circle(surface, (255, 255, 255), (cx - 10, cy - 4), 6)
    pygame.draw.circle(surface, (255, 255, 255), (cx + 10, cy - 4), 6)
    pygame.draw.circle(surface, (20, 24, 30), (cx - 9, cy - 4), 3)
    pygame.draw.circle(surface, (20, 24, 30), (cx + 11, cy - 4), 3)
    if row:
        pygame.draw.circle(surface, (255, 230, 120), (cx, cy - 20), 4)


def _panel_lines(explore: Explore, tables: dict, region: str, frame: int) -> list[str]:
    state = explore.state
    progress = state.progress
    species = tables["species.json"]["creatures"]
    lines = [
        f"区域 {region} · {progress.region}",
        f"坐标 ({explore.x:.1f}, {explore.y:.1f}) · 时段 {'白昼' if explore.phase == 'day' else '夜潮'}",
        f"巡查 {len(progress.surveyed_regions)}/{len(state.world.regions)} · 能力 {len(progress.abilities)}/{len(state.world.abilities)}",
        f"图鉴 {len(state.atlas.entries)} 条 · 队伍 Lv.{state.party[0].level}",
        f"步数 {explore.steps} · 遭遇 {explore.encounters} · 捕获 {explore.captures}",
    ]
    if explore.battle is not None:
        b = explore.battle
        lines.append(f"战斗 {b.outcome} · 我方 {b.ally.hp if b.ally else '-'}")
        if b.wild:
            lines.append(f"野生 {b.wild.cid} HP {b.wild.hp}/{b.wild.max_hp}")
    elif explore.messages:
        lines.append(explore.messages[-1])
    lines.append(f"帧 {frame} · 连续世界 64×64")
    return lines


def run_world(tables: dict, seed: str, *, max_frames: int | None = None,
              block: bool = True, handlers: dict | None = None,
              save_path: str | None = None) -> dict:
    """开放世界事件循环；返回机器事实（帧数 / 格数 / 动作 / 通关），不写观感结论。"""
    pygame = require_pygame()
    callbacks = {} if handlers is None else handlers
    pygame.init()
    surface = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("PokeWorld · 潮屿巡游（开放世界）")
    font = _make_font(pygame)
    world = explore.new_explore(tables, seed)
    limit = max_frames if max_frames is not None else 10 ** 9
    cols = (WINDOW_SIZE[0] - VIEW_ORIGIN[0] - PANEL_X) // TILE
    rows = (WINDOW_SIZE[1] - 2 * VIEW_ORIGIN[1]) // TILE
    frames = 0
    drawn = 0
    actions: list[str] = []
    running = True
    gx0 = gy0 = 0

    while running and frames < limit:
        gx0 = max(0, min(overworld.WORLD_TILES - cols, int(world.x) - cols // 2))
        gy0 = max(0, min(overworld.WORLD_TILES - rows, int(world.y) - rows // 2))
        _draw_ground(surface, pygame, tables, seed, frames, gx0, gy0, cols, rows)
        region = explore.current_region(tables, world)
        _draw_landmarks(surface, pygame, tables, seed, frames,
                        gx0, gy0, cols, rows, region, font)
        _draw_player(surface, pygame, world, gx0, gy0)
        if world.battle is not None and world.battle.wild is not None:
            _draw_creature(surface, pygame, tables, world.battle.wild.cid,
                           PANEL_X + 180, PANEL_TOP + 250)
        pygame.draw.rect(surface, (14, 22, 34),
                         pygame.Rect(PANEL_X, 0, WINDOW_SIZE[0] - PANEL_X, WINDOW_SIZE[1]))
        for index, line in enumerate(_panel_lines(world, tables, region, frames)):
            surface.blit(font.render(line, True, (230, 240, 248)),
                         (PANEL_X + 12, PANEL_TOP + index * LINE_HEIGHT))
        help_top = PANEL_TOP + 9 * LINE_HEIGHT
        for index, line in enumerate(HELP_LINES):
            surface.blit(font.render(line, True, (255, 224, 140)),
                         (PANEL_X + 12, help_top + index * LINE_HEIGHT))
        pygame.display.flip()
        events = [pygame.event.wait()] if block else pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type != pygame.KEYDOWN:
                continue
            from .layout import action_for_key  # 复用 G5/G7 键位映射，零重复
            key = pygame.key.name(event.key)
            action = action_for_key(key, world.state.world, region)
            if action is None:
                continue
            if action == "quit":
                running = False
                break
            if action.startswith("item:") or action in ("attack", "catch", "flee"):
                world = explore.apply(tables, world, action)
            elif action in ("auto", "save", "load"):
                handler = callbacks.get(action)
                if handler is None:
                    continue
                updated = handler(world)
                if updated is None:
                    running = False
                    break
                world = updated
            else:
                world = explore.apply(tables, world, action)
            actions.append(action)
        frames += 1
    pygame.quit()
    return {
        "ok": True,
        "frames": frames,
        "cells_per_frame": cols * rows,
        "cells_drawn": drawn or cols * rows,
        "region": explore.current_region(tables, world),
        "complete": explore.is_complete(tables, world),
        "actions": tuple(actions),
    }


def smoke(tables: dict, seed: str = "G8-smoke", max_frames: int = 3) -> dict:
    """无头驱动下画若干帧并退出，供测试与 CLI 冒烟。"""
    return run_world(tables, seed, max_frames=max_frames, block=False)
