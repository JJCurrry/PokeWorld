# PokeWorld 3D · Unity 工程骨架（G9）

> 本工程由 `tools/make_unity_skeleton.py` 确定性生成。
> **当前状态：结构骨架已落盘，未编译、未进入播放模式**（本机无 Unity，S9-01）。

## 打开步骤（需本机已装 Unity）

1. 用你的 Unity 版本打开本目录；首次打开会生成 `Library/` 等缓存。
2. 若 `ProjectSettings/ProjectVersion.txt` 的版本与本机不符，以 Hub 新建空工程覆盖本目录的 `ProjectSettings/` 与 `Packages/`，再重新运行生成器补齐脚本。
3. 菜单 `Tools/PokeWorld/Build Bootstrap Scene` → 生成 `Assets/Scenes/Main.unity` 并写入构建列表。
4. 播放模式确认 Console 出现 `[GameBootstrap] start`、`[GameBootstrap] ready`，场景可见地面 + 玩家 + 潮灵。

## 结构

- `Assets/Scripts/Core`：状态机 / 遭遇 / 能力门 / 图鉴 / 存档 / 玩家控制。
- `Assets/Scripts/View`：HUD / 音频 / 手绘色板。
- `Assets/Scripts/Editor`：场景生成入口（不手写场景 YAML）。
- `Assets/Settings`：JSON 配置（区域门 / 物种 / 色板）。
- `docs/design-freeze.json`：设计冻结清单（在仓库根 docs/）。
