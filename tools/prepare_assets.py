"""一次性资产加工：把 AI 生成的白底精灵表转成透明 PNG 并按稳定名落盘。

用途（G8/S8-01 原创美术返工）：
- 输入 assets/sprites/_raw/ 下的三张源图（AI 生成、白底、右下角带工具水印）。
- 输出 assets/sprites/creatures/cNN.png、landmarks/rN.png、player.png（真透明、去水印、统一尺寸）。
- 消费方 src/view/asset_atlas.py 只按稳定名加载，不关心源图长啥样。

算法：从四角 flood fill 连通的浅灰白背景像素置为全透明；角色内部浅色（如霜绒白毛）
不与边缘连通故保留。随后按 4x2 网格切分、裁到非透明包围盒、等比缩放到目标尺寸居中。
本脚本不进四道门扫描范围之外的目录（tools/ 是已登记扫描根），无需新增 py 目录。
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "sprites" / "_raw"
OUT = ROOT / "assets" / "sprites"

BG_MAX_DIFF = 26          # 背景近似中性浅灰白的通道差阈值
BG_MIN_LUMA = 205         # 亮度下限：低于此值视为内容
CELL = (256, 256)         # 1024x512 的 4x2 网格每格尺寸
CREATURE_SIZE = (96, 96)
LANDMARK_SIZE = (112, 112)
PLAYER_SIZE = (72, 96)


def _is_bg(px: tuple[int, int, int]) -> bool:
    r, g, b = px[:3]
    return min(r, g, b) >= BG_MIN_LUMA and max(r, g, b) - min(r, g, b) <= BG_MAX_DIFF


def transparentize(im: Image.Image) -> Image.Image:
    """flood fill 从四边沿连通浅色背景置透明；返回 RGBA。"""
    src = im.convert("RGBA")
    w, h = src.size
    px = src.load()
    seen = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        if not _is_bg(px[x, y]):
            continue
        px[x, y] = (0, 0, 0, 0)
        if x > 0:
            queue.append((x - 1, y))
        if x < w - 1:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y < h - 1:
            queue.append((x, y + 1))
    return src


def _bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    return im.getchannel("A").getbbox()


def fit(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """裁到非透明包围盒后等比缩放并居中到目标画布。"""
    box = _bbox(im)
    if box is None:
        raise ValueError("资产裁切后为空（alpha 全 0）")
    crop = im.crop(box)
    max_w, max_h = size
    ratio = min(max_w / crop.width, max_h / crop.height)
    new = (max(1, round(crop.width * ratio)), max(1, round(crop.height * ratio)))
    crop = crop.resize(new, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(crop, ((max_w - new[0]) // 2, (max_h - new[1]) // 2))
    return canvas


def split_sheet(im: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    cw, ch = CELL
    out: list[Image.Image] = []
    for row in range(rows):
        for col in range(cols):
            out.append(im.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)))
    return out


def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    print(f"  {path.relative_to(ROOT)}  {im.size}")


def main() -> None:
    creature_src = next((RAW / "creatures").glob("*.png"))
    landmark_src = next((RAW / "landmarks").glob("*.png"))
    player_src = next((RAW / "player").glob("*.png"))

    print("加工潮灵表 ...")
    creatures = split_sheet(transparentize(Image.open(creature_src)), 4, 2)
    for index, cell in enumerate(creatures[:8], start=1):
        save(fit(cell, CREATURE_SIZE), OUT / "creatures" / f"c{index:02d}.png")

    print("加工地标表 ...")
    landmarks = split_sheet(transparentize(Image.open(landmark_src)), 4, 2)
    for index, cell in enumerate(landmarks[:7], start=1):
        save(fit(cell, LANDMARK_SIZE), OUT / "landmarks" / f"r{index}.png")

    print("加工玩家角色 ...")
    save(fit(transparentize(Image.open(player_src)), PLAYER_SIZE), OUT / "player.png")
    print("完成：资产按稳定名落盘，源图保留在 _raw/ 仅供溯源。")


if __name__ == "__main__":
    main()
