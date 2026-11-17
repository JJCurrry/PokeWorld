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
- **G4 / G5 / G6 均已由人裁决验收通过；G7 已实施完毕、按 A9 待人裁决验收**（2026-11-17「G6验收通过，开发G7」+ 方向「核心循环可玩化」）。G7 把 G2 战斗 / 捕捉接进 G5 窗口、复用 A11 定稿公式与三表，**零改三表 / 零重建 `MANIFEST.sha256` / 零重拍 golden 快照**；`g7_report G7-a` `complete=true`、四道门 **253 用例**全绿、新增 S7-01~S7-03；「8 潮灵扩充 / 平衡调优」仍须逐次人确认才实施。当前工单 `docs/工单/G7-核心循环可玩化.md`，设计 `ADR-007`（含实施结论）；G6 工单已归档。**AI 不自判 G7 通过、不预支 G8**。当前待裁决 **5 项**（A 组 2 项阻塞：G7 验收 / G8 开工；B 组 3 项可延后），清单见 `docs/接力文件.md`「待人类裁决的问题」。

## 仲裁序（信息源冲突时谁先读）

任务工单 > 不变量清单 > 本文件原则 > 专项规范 > 代码现状

> 注意：仅排「信息源」先后，不排「权限」。真撞红线级冲突 → 停手并在接力文件上报，交人裁决，不自裁。
