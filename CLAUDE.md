# PokeWorld 项目规则（CLAUDE.md / AGENTS.md）

> 本文件是每个会话自动读取的「项目宪法 + 唯一根入口」。保持 ≤100 行。
> 只放两类东西：① 无法写成检查的「判断性原则」（≤15 条）；② 指向其他制品的「指针」+ 一条仲裁序。
> 能写成失败检查的规则，不要写在这里——去写 L1 检查。

## 一句话是什么

原创精灵收集 + 种子化群岛探索的 2D 单机游戏；Python 3.13 标准库优先，pygame 自 G5 起作为**可选**第三方依赖；按 ai-coding-method 的门控式自治推进。

## 常用命令

- `python tools/verify_all.py` —— 单命令四道门（含第 0 道优化模式自检）。
- `python tools/balance_check.py` —— 平衡采样（`G2-balance-v3`），输出机器事实；数值已于 2026-11-15 22:02 定稿，手感试玩复核归人（非阻塞）。
- `python tools/autoplayer.py [seed]` —— G3 巡图机器事实；`complete=true` 表示无卡死。
- `python tools/g4_report.py [seed]` —— G4 端到端机器事实（图鉴里程碑 / 存档 roundtrip / 脚本不改世界状态）；`complete=true` 表示三条 DoD 全通过。
- `python tools/g5_report.py [seed]` —— G5 端到端机器事实（完整通关 / 存档恢复后通关 / 表现层纯投影 / 可选依赖）；`complete=true` 表示六项 DoD 全通过。
- `python -m src.main --headless [seed]` —— 无显示器完整通关；`--window` 开 pygame 窗口（依赖缺失时降级 headless 并提示）；`--save` / `--load` 读写 `saves/`。
- G1 起：`tests/golden_seed.json` 由 R7 锁定（G1-v3 `3ab574e4…`）；变更须人**逐次**确认后才运行 `python tools/make_golden.py`。三张 `data/*.json` 与 `MANIFEST.sha256` 同样受保护，改动须逐次人确认 + 重建清单（LF）。
- G6 起：`python tools/gate.py`（R0–R7）、`docs/评审/G6-冷眼.md`（独立会话冷眼，实现者不改结论）、`docs/软著材料清单.md`（清单 + 对应制品路径 + 待补动作，非成品材料）。
- G7 起：`python tools/g7_report.py [seed]`（默认 `G7-a`）—— 战斗 / 捕捉端到端 JSON（遭遇 → 捕捉 → 图鉴 → 存档 → 读档 + 反证 + 确定性），`complete=true` 表示五项 DoD 机器可判定部分全通过。
- G8 起（开放世界）：`python -m src.ow_main --headless [seed]`（默认 `G8-demo`）——连续世界端到端机器事实；`--window` 开相机跟随窗口；`python tools/ow_report.py [seed]` 同报告。设计 `ADR-009`（显式推翻 ADR-001 无缝否决），工单 `docs/工单/G8-无缝开放世界.md`。旧 `python -m src.main --window` 仍可用（分区块原型）。
- P1 发布工程：双击 `dist/PokeWorld.exe` 开玩（自包含，无需 Python/pygame）；**G8 起双击入口已切到开放世界**（`tools/launcher.py` → `src.ow_main`）。重建 `python tools/build_exe.py`（需 `pip install pyinstaller`）。工单 `docs/工单/P1-双击可玩发行包.md`、`ADR-008`。
- 细节以 `docs/地图.md`「关键流程入口」为准；本文件不复制命令细节。

## 判断性原则（仅放无法自动化的；能写成检查的请下沉为 L1）

1. 不确定就停下问，不要猜测后硬上。
2. 发现工单 / 不变量 / 文档 / 代码信息冲突时，停手报告，不自行仲裁。
3. 计划阶段不写业务代码；门控未通过不进入执行。
4. 「没修好 + 清晰的现状报告」是合法且受欢迎的产出；禁止靠注释测试、加特判、删断言制造假完成。
5. 一个里程碑 = 一次提交，人保留合并裁决。
6. 骨架层的作者意图归人：区域命名、地标、解锁顺序由人定，AI 不得替人决定。
7. 原创合规优先：素材入库前先登记溯源表，拿不准就当不可用。
8. 涉及外部平台政策 / 法规，先核实再输出，并标注不确定性。
9. 每个里程碑结束必须更新接力文件，否则不算完成。

## 一张地图（指针，不是内容）

- 架构与模块索引：`docs/地图.md`
- 红线（不变量）：`docs/不变量.md`
- 术语（只收望文生义会错的词）：`docs/术语表.md`
- 设计决策（为什么这样）：`docs/adr/`
- 当前工单：`docs/工单/`
- 跨会话交接棒：`docs/接力文件.md`
- 整体里程碑拆解（当前计划）：`docs/任务架构细分.md`
- 游戏设计 / 原创溯源 / 合规自评：`docs/GDD-v0.md`
- 参考实现 / 黄金路径：G0 铸造 `src/schema.py` + `tools/gate.py`，G1 铸造 `src/gen/`，G2 铸造 `src/battle/`，G3 铸造 `src/world/progress.py` + `tools/autoplayer.py`，G4 铸造 `src/world/atlas.py` / `evolution.py` / `scripts.py` / `save.py` / `game.py` + `tools/g4_report.py`，G5 铸造 `src/world/session.py` + `src/view/` + `src/main.py` + `tools/g5_report.py`；清单见 `docs/地图.md`，**未落盘的模块不得假称其存在**。
- **G0–G7 全部已由人裁决验收通过**（G7 2026-11-19「G7验收通过」）。G7 把 G2 战斗 / 捕捉接进 G5 窗口、复用 A11 定稿公式与三表，**零改三表 / 零重建 `MANIFEST.sha256` / 零重拍 golden 快照**；`g7_report G7-a` `complete=true`、四道门 253 用例全绿、新增 S7-01~S7-03。G7 及以前工单均归档（含「人裁决记录」），设计 `ADR-007`。**验收是人的裁决（非 AI 自判、非独立冷眼）**。
- **G8 开放世界（2026-11-21 · 已实施；2026-11-27 人裁决验收不通过、归档，机器证据保留）**：人答「**3，我要做真正的开放世界！**」→ 开工 + 方向 + **明确推翻 ADR-001 无缝否决**，设计 `ADR-009`（supersede）。新增 `src/gen/overworld.py`（连续地形）、`src/world/explore.py`（纯函数探索）、`src/view/overworld_view.py`（相机窗口 + 键位提示折行）、`src/ow_main.py`（新入口）、`tools/ow_report.py`。`ow_report G8-demo` `complete=true`（64×64 连续世界 / 7 地标全部陆路连通 / 走到 r7 / 捕获入图鉴 / 确定性全真）；四道门 **263 用例**全绿（253 + G8 10 条）；**零改三表 / 清单 / golden**。工单 `docs/工单/G8-无缝开放世界.md`。**AI 不自判验收**；「8 潮灵扩充 / 平衡调优」仍须逐次人确认才实施。
- **P1 发布工程（2026-11-20 · 已实施，非 G8）**：`dist/PokeWorld.exe` 双击即玩（PyInstaller onefile，自包含 Python+pygame+三表，产物不入库），**G8 起双击入口已切到开放世界**；隔离 PATH 验证自包含、受保护数据 0 改动。工单 `docs/工单/P1-双击可玩发行包.md`、`ADR-008`，限制 P1-01~P1-05。历史制品，随旧工程冻结归档。
- **G8 结局（2026-11-27）**：人裁决 **验收不通过**（P2「游戏需要大改甚至是重建」），工单归档、机器证据保留、不回退。旧 Python 工程整体冻结：三表 / `MANIFEST.sha256` / golden / 268 用例保持原样全绿，**零改、零删、零迁移**。
- **G9 Unity 3D 可玩独立原型（2026-11-27 · 当前进行中）**：人答 P1–P6 → **选 C 路线 Unity 全量重建 + 明确 3D**（开工授权）+ **档位上调为可玩独立原型** + 手绘风 + P4/P6 授权 AI 快速处置。当前工单 `docs/工单/G9-Unity3D可玩独立原型.md`，设计 `ADR-011`（supersede `ADR-009` 引擎口径与 `ADR-001` 3D 否决）。阶段一 = 15 章策划案 + 设计冻结清单（`docs/design-freeze.json`，frozen 才准施工）；工程侧 `// @trace 编号`，自检统计覆盖率。**当前待裁决 0 项**；G9 验收按 A9 另裁、AI 不自判。⚠ 本机未检测到 Unity 安装（S9-01）→ 编译 / 播放验证阻塞，工程骨架版本字段为显式假设占位（S9-02），不得宣称可玩。

## 仲裁序（信息源冲突时谁先读）

任务工单 > 不变量清单 > 本文件原则 > 专项规范 > 代码现状

> 注意：仅排「信息源」先后，不排「权限」。真撞红线级冲突 → 停手并在接力文件上报，交人裁决，不自裁。
