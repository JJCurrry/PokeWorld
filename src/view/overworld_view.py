"""G8 开放世界窗口（ADR-009 + ADR-010）：连续地图 + 相机跟随 + 原创美术资产。

- 顶层零 pygame import，仅 `run_world` 内经 `require_pygame()` 延迟导入（G5 契约）。
- 渲染层只读 `Explore`（纯快照），不回写状态；世界变更只经 `explore.apply`。
- 动画相位由帧计数驱动（不读时钟，R1）；角色 / 潮灵 / 地标来自 `asset_atlas`
  加载的原创 PNG（不变量 #7，GDD §6 逐项登记），缺图自动回退原几何绘制。
- 地形在纯色底上叠加程序生成的纹理与光影（零外部素材、零随机、零时钟）。
- 键位提示折行完整显示，修复 G7 截断问题。
"""
from __future__ import annotations

from . import asset_atlas
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
CREATURE_DISPLAY = (92, 92)   # 战斗中潮灵面板显示尺寸
PLAYER_DISPLAY = (46, 62)     # 玩家在地图上的显示尺寸
LANDMARK_DISPLAY = (66, 66)   # 地标建筑显示尺寸

HELP_LINES = (
    "方向键 移动 · N 交谈 · S 巡查 · B 遭遇",
    "J 攻击 · K 捕捉 · L 撤离 · 数字键 道具",
    "P 昼夜 · F5 存 · F9 读 · Q 退出",
)

# 相机死区：玩家在视口中心 ±3 格内移动时地图不滚动，角色在屏幕上真实位移。
# 修复「按方向键只有背景微动、角色像没反应」的观感问题（纯渲染参数，不改逻辑坐标）。
CAMERA_DEADZONE = 3

# 最近操作回显：让每次按键都有肉眼可见的反馈，B 级文案为 AI 草案、归人复核。
ACTION_LABELS = {
    "move:up": "向上走", "move:down": "向下走",
    "move:left": "向左走", "move:right": "向右走",
    "npc": "交谈", "survey": "巡查", "phase": "切换昼夜",
    "encounter": "寻找野生潮灵", "attack": "攻击", "catch": "捕捉",
    "flee": "撤离", "save": "存档", "load": "读档", "quit": "退出",
}


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
    table = ((92, 158, 88), (46, 112, 66), (96, 178, 206), (36, 104, 164))
    index = sum(ord(ch) for ch in terrain) % len(table)
    return table[index]


def _shade(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """按亮度系数派生同色系明暗，用于程序光影（零随机、零外部素材）。"""
    return tuple(max(0, min(255, round(channel * amount))) for channel in color)


def _draw_ground(surface: object, pygame: object, tables: dict,
                 seed: str, frame: int, gx0: int, gy0: int,
                 cols: int, rows: int) -> None:
    """地形底图：纯色 + 棋盘微差 + 高度光影 + 草/水/林纹理（全确定性派生）。"""
    for row in range(rows):
        for col in range(cols):
            wx, wy = gx0 + col, gy0 + row
            terrain = overworld.terrain_at(tables, seed, wx + 0.5, wy + 0.5)
            base = _palette(pygame, terrain)
            rect = pygame.Rect(VIEW_ORIGIN[0] + col * TILE, VIEW_ORIGIN[1] + row * TILE,
                               TILE, TILE)
            pygame.draw.rect(surface, base, rect)
            # 相邻格微差 + 高度坡度光影：让连片地形显出层次而非一整块纯色
            checker = 1.0 if (wx + wy) % 2 == 0 else 0.94
            h = overworld.height_at(seed, wx + 0.5, wy + 0.5)
            h_right = overworld.height_at(seed, wx + 1.5, wy + 0.5)
            slope = max(-0.08, min(0.08, (h - h_right) * 0.4))
            pygame.draw.rect(surface, _shade(base, checker + slope), rect, 2)
            cx, cy = rect.centerx, rect.centery
            if h < 0.42:  # 水域：双层波纹（相位由帧计数驱动）
                phase = (frame + wx * 2 + wy) % 8
                light = _shade(base, 1.45)
                pygame.draw.line(surface, light, (cx - 9, cy - 5 + phase // 4),
                                 (cx + 3, cy - 5 + phase // 4), 2)
                pygame.draw.line(surface, light, (cx - 3, cy + 3 - phase // 4),
                                 (cx + 9, cy + 3 - phase // 4), 1)
            elif h < 0.7:  # 草地：成簇草叶 + 小花点
                grass = _shade(base, 0.62)
                bloom = (250, 214, 122)
                for dx, dy in ((-7, 4), (0, 7), (6, 3)):
                    pygame.draw.line(surface, grass, (cx + dx, cy + dy),
                                     (cx + dx - 1, cy + dy - 5), 1)
                if (wx * 3 + wy * 7) % 9 == 0:
                    pygame.draw.circle(surface, bloom, (cx + 4, cy - 4), 2)
            else:  # 密林：层叠树冠 + 高光
                dark = _shade(base, 0.66)
                light = _shade(base, 1.28)
                pygame.draw.circle(surface, dark, (cx - 4, cy + 1), 10)
                pygame.draw.circle(surface, base, (cx + 4, cy - 2), 9)
                pygame.draw.circle(surface, light, (cx + 1, cy - 6), 4)


def _blit_centered(surface: object, image: object, px: int, py: int,
                   size: tuple[int, int], pygame: object, bob: int = 0) -> None:
    scaled = pygame.transform.smoothscale(image, size)
    surface.blit(scaled, (px - size[0] // 2, py - size[1] // 2 + bob))


def _draw_landmarks(surface: object, pygame: object, tables: dict,
                    seed: str, frame: int, gx0: int, gy0: int,
                    cols: int, rows: int, current: str, font: object,
                    atlas: dict) -> None:
    palette = ((240, 196, 96), (232, 120, 120), (168, 142, 232),
               (120, 200, 232), (240, 160, 96), (200, 220, 120), (220, 220, 240))
    for index, (rid, lx, ly) in enumerate(overworld.landmarks(tables)):
        if not (gx0 <= lx < gx0 + cols and gy0 <= ly < gy0 + rows):
            continue
        px = VIEW_ORIGIN[0] + (lx - gx0) * TILE + TILE // 2
        py = VIEW_ORIGIN[1] + (ly - gy0) * TILE + TILE // 2
        image = atlas.get("landmarks", {}).get(rid)
        if image is not None:
            # 建筑略上移，使站在地标中心的玩家像在建筑门前而非被压在屋顶下
            _blit_centered(surface, image, px, py - 20, LANDMARK_DISPLAY, pygame)
        else:  # 缺图降级：原几何房顶
            color = palette[index % len(palette)]
            pygame.draw.polygon(surface, color,
                                [(px, py - 26), (px + 13, py - 2), (px - 13, py - 2)])
            pygame.draw.rect(surface, (250, 240, 210), (px - 5, py - 10, 10, 8))
        name = str(tables["topology.json"]["regions"][index]["name"])
        label = font.render(name, True, (255, 255, 255))
        surface.blit(label, (px - 12, py + 22))
        if rid == current:
            pulse = 38 + (frame % 10)
            pygame.draw.circle(surface, (255, 230, 120), (px, py), pulse, 2)


def _draw_player(surface: object, pygame: object, explore: Explore,
                 gx0: int, gy0: int, atlas: dict, frame: int,
                 landmarks: tuple = ()) -> None:
    px = VIEW_ORIGIN[0] + (explore.x - gx0) * TILE + TILE // 2
    py = VIEW_ORIGIN[1] + (explore.y - gy0) * TILE + TILE // 2
    image = atlas.get("player")
    if image is not None:
        bob = -2 if frame % 8 < 4 else 0  # 帧计数驱动的轻微踏步（零时钟）
        # 站在地标中心时向脚下偏移，露出身后建筑；纯渲染，不改逻辑坐标
        on_landmark = any(abs(explore.x - lx) < 1 and abs(explore.y - ly) < 1
                          for _, lx, ly in landmarks)
        offset = 12 if on_landmark else -6
        _blit_centered(surface, image, px, py + offset, PLAYER_DISPLAY, pygame, bob)
        return
    pygame.draw.circle(surface, (255, 224, 180), (px, py - 8), 7)      # 头
    pygame.draw.rect(surface, (72, 132, 220), (px - 8, py - 2, 16, 16))  # 身
    pygame.draw.rect(surface, (48, 84, 150), (px - 8, py + 14, 6, 8))   # 脚
    pygame.draw.rect(surface, (48, 84, 150), (px + 2, py + 14, 6, 8))


def _draw_creature(surface: object, pygame: object, tables: dict,
                   cid: str, cx: int, cy: int, atlas: dict, frame: int) -> None:
    image = atlas.get("creatures", {}).get(cid)
    if image is not None:
        bob = -3 if frame % 10 < 5 else 0
        _blit_centered(surface, image, cx, cy, CREATURE_DISPLAY, pygame, bob)
        return
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


def _panel_lines(explore: Explore, tables: dict, region: str, frame: int,
                 last_action: str = "") -> list[str]:
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
    if last_action:
        lines.append("最近操作 " + ACTION_LABELS.get(last_action, last_action))
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
    atlas = asset_atlas.load_all(pygame)
    world = explore.new_explore(tables, seed)
    limit = max_frames if max_frames is not None else 10 ** 9
    cols = (WINDOW_SIZE[0] - VIEW_ORIGIN[0] - PANEL_X) // TILE
    rows = (WINDOW_SIZE[1] - 2 * VIEW_ORIGIN[1]) // TILE
    frames = 0
    drawn = 0
    actions: list[str] = []
    running = True
    last_action = ""
    # 开局居中，之后按死区增量跟随：角色在屏幕内真实位移，走够 3 格地图才滚动。
    gx0 = max(0, min(overworld.WORLD_TILES - cols, int(world.x) - cols // 2))
    gy0 = max(0, min(overworld.WORLD_TILES - rows, int(world.y) - rows // 2))

    while running and frames < limit:
        target_x = int(world.x) - cols // 2
        target_y = int(world.y) - rows // 2
        if target_x > gx0 + CAMERA_DEADZONE:
            gx0 = target_x - CAMERA_DEADZONE
        elif target_x < gx0 - CAMERA_DEADZONE:
            gx0 = target_x + CAMERA_DEADZONE
        if target_y > gy0 + CAMERA_DEADZONE:
            gy0 = target_y - CAMERA_DEADZONE
        elif target_y < gy0 - CAMERA_DEADZONE:
            gy0 = target_y + CAMERA_DEADZONE
        gx0 = max(0, min(overworld.WORLD_TILES - cols, gx0))
        gy0 = max(0, min(overworld.WORLD_TILES - rows, gy0))
        _draw_ground(surface, pygame, tables, seed, frames, gx0, gy0, cols, rows)
        region = explore.current_region(tables, world)
        _draw_landmarks(surface, pygame, tables, seed, frames,
                        gx0, gy0, cols, rows, region, font, atlas)
        _draw_player(surface, pygame, world, gx0, gy0, atlas, frames,
                     overworld.landmarks(tables))
        if world.battle is not None and world.battle.wild is not None:
            _draw_creature(surface, pygame, tables, world.battle.wild.cid,
                           PANEL_X + 180, PANEL_TOP + 250, atlas, frames)
        # 侧栏：深色渐变底 + 顶部高光条 + 分隔线，替代原纯色块
        panel = pygame.Rect(PANEL_X, 0, WINDOW_SIZE[0] - PANEL_X, WINDOW_SIZE[1])
        pygame.draw.rect(surface, (18, 30, 46), panel)
        pygame.draw.rect(surface, (42, 78, 112),
                         pygame.Rect(PANEL_X, 0, panel.width, 4))
        status_lines = _panel_lines(world, tables, region, frames, last_action)
        help_top = PANEL_TOP + (len(status_lines) + 1) * LINE_HEIGHT
        pygame.draw.line(surface, (58, 96, 132),
                         (PANEL_X + 8, help_top - 8),
                         (WINDOW_SIZE[0] - 12, help_top - 8), 1)
        for index, line in enumerate(status_lines):
            surface.blit(font.render(line, True, (230, 240, 248)),
                         (PANEL_X + 12, PANEL_TOP + index * LINE_HEIGHT))

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
            combat = world.battle is not None
            # 战斗态走 COMBAT_KEY_ACTIONS；道具键按 encounters.json 表序派生（R3 零字面量）。
            item_ids = tuple(str(key_id) for key_id in tables["encounters.json"]["items"])
            action = action_for_key(key, world.state.world, region,
                                    combat=combat, items=item_ids)
            if action is None:
                continue
            if action == "quit":
                running = False
                break
            if action in ("auto", "save", "load"):
                handler = callbacks.get(action)
                if handler is None:
                    continue
                updated = handler(world)
                if updated is None:
                    running = False
                    break
                world = updated
            elif action.startswith("edge:") or action == "train":
                continue  # G5 遗留动作：开放世界不用数字跨区 / 训练，避免异常中断窗口
            elif action == "encounter" and combat:
                continue  # 战斗中 B 无意义，忽略而不是让 _start_battle 抛错
            else:
                world = explore.apply(tables, world, action)
                # 陆地行走按确定性触发值进入遭遇（状态层 _move 不触发，autoplay 不受影响）。
                if action.startswith("move:") and world.battle is None and explore.should_encounter(world):
                    world = explore.apply(tables, world, "encounter")
                    actions.append("encounter")
            actions.append(action)
            last_action = action
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
        "last_action": last_action,
        "combat": world.battle is not None,
        "art": {
            "player": atlas.get("player") is not None,
            "creatures": len(atlas.get("creatures", {})),
            "landmarks": len(atlas.get("landmarks", {})),
        },
    }


def smoke(tables: dict, seed: str = "G8-smoke", max_frames: int = 3) -> dict:
    """无头驱动下画若干帧并退出，供测试与 CLI 冒烟。"""
    return run_world(tables, seed, max_frames=max_frames, block=False)
