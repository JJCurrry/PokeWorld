# PokeWorld

> 原创生物收集 + 种子化群岛探索游戏，同时作为 AI Coding 门控式自治的演练项目。
> 游戏内标题：**PokeWorld**（2026-11-14 门控裁定沿用仓库名；2026-11-15 22:02 人答「自己玩无所谓」→ 名称商标高风险由人接受、自用不上架、不做检索，见 `docs/GDD-v0.md` 第 6、7 节）。

## 当前状态

2026-11-16 人答复「**G4验收通过，开启G5的开发工作**」→ **G4 已由人裁决验收通过；G5 已获开工授权**（A9，两件事各自落单）。**G0 / G1 / G2 / G3 / G4 均已由人验收通过**；**G5 已按 `ADR-005` 实施完毕、F1–F6 按实测勾选，现按 A9 待人裁决验收**；当前工单 `docs/工单/G5-可玩闭环.md`。**AI 未自判 G5 通过、未开工 G6、未写任何 G6 代码**。当前进度以 `docs/接力文件.md` 为唯一事实源。

**G1**：确定性 `rng(world_seed, region_id, cx, cy)`、8×8 区块地形与遭遇相对权重、golden seed 快照（**G1-v3**）与规则门 R7。
**G2**：比例型伤害公式（结构常数入表）、出没稀有度 `rarity`、道具 / 异常状态建模（三档网 + 昏沉 / 僵麻 + 状态机 + 撤离判定）；`step(state, action, rng) -> state'` 签名不变、状态全 frozen。
**S2-03 已按人裁决「采纳」实施**：捕捉公式 hp 项改为带基数线性项 `catch_base + (1 - hp_ratio) × hp_weight`（0.12 / 0.88，常数入 `encounters.json::catch_formula`），满血时换网 / 上状态能拉开捕捉率；`MANIFEST.sha256` 按逐次确认重建（LF），**未重拍 golden 快照**（R7 仍 `3ab574e4…`）。采样 23.5 万次动作已重跑，机器事实见 `docs/平衡采样报告.md`（`G2-balance-v3`）。
**A11 数值已由人裁定「先定稿」**：全部数值（含新增两个 hp 常数）不再是候选占位；手感试玩复核作为非阻塞后续仍归人。
**G3 能力门与巡图**：`src/world/progress.py` 把拓扑凝固成 frozen `World`，门控只读 `edges[].requires`（代码零能力名字面量）；`tools/autoplayer.py` 确定性跑遍 **7 区域 / 7 NPC / 100 区块**，无卡死、无跳关。G3 实施期全程**零改表 / 零重建 MANIFEST / 零重拍快照**；设计见 `docs/adr/ADR-003-能力门与巡图表驱动实现.md`。

**G4 图鉴 / 成长 / 事件脚本 / 存档**：`src/world/atlas.py` 按出没条件登记图鉴（区域里程碑可达成、死端拓扑可反证）；`evolution.py` 成长刻度集中在单一常量、个体值由 `rng(..., stream="growth")` 派生；`scripts.py` 16 条纯字面量脚本只产出效果声明，唯一解释器 `game.apply_effects` 只改展示层字段；`save.py` 落地不变量 #6（只存 `world_seed + flags + 队伍状态`，生成结果全数拒绝、`-O` 下校验不失效）。`tools/g4_report.py` 输出三条 DoD 的机器事实 JSON。实施期全程**零改表 / 零重建 MANIFEST / 零重拍快照**；设计见 `ADR-004`，逐条证据见 `docs/工单/G4-图鉴进化事件脚本.md`。**B 级文案品味（16 条原创中文短句）仍归人复核**。

**G5 可玩闭环（已实施完毕，待人裁决验收）**：`src/world/session.py` 把输入变成唯一状态转移（拓扑派生终点，不写死 `r7`）；`src/view/{deps,layout,window}.py` 实现可选依赖探测、frozen `Frame` 纯投影与 pygame 2D 俯视窗口（表现层只读、不回写世界）；`src/main.py` 提供 `--headless` / `--window` / `--save` / `--load`，文件 I/O 只此一处；`tools/g5_report.py` 输出六项 DoD 的机器事实。`python tools/g5_report.py G5-demo` → `complete=true`（20 步到联盟 / 7 区域 / 7 NPC / 100 区块 / 6 条边无跳关 / 图鉴 8/8 物种 / 存档三字段且读档后仍通关 / 纯投影 / 门控全绿）。**依赖缺失时验证墙优雅跳过**：`POKEWORLD_NO_PYGAME=1 python tools/verify_all.py` 仍 `ALL GATES GREEN`（`skipped=9`）。全程零改表 / 零重建 MANIFEST / 零重拍快照；设计见 `ADR-005`（含「实施结论」）。**B 级手感与观感、以及 G4 遗留的 B 级文案品味仍归人裁决**；逐条证据见 `docs/工单/G5-可玩闭环.md`。

四道门 **233 用例全绿**（`ALL GATES GREEN`；G4 基线 201，G5 新增 32 条）。独立冷眼按人裁定维持 **G6**；G1 / G2 / G3 / G4 / G5 均只有实现者自审，不冒充「已通过评审」。**当前待人类裁决 4 项**：G5 验收 / G6 开工（阻塞）、B 级文案品味 / B 级手感观感（可延后）；完整清单见 `docs/接力文件.md`「待人类裁决的问题」。

## 目录结构

唯一结构入口见 [`docs/地图.md`](docs/地图.md)；根入口（项目宪法）见 [`CLAUDE.md`](CLAUDE.md)。

## 快速开始

零第三方依赖（G0–G4）：验证墙只用 Python 3.13 标准库即可跑；**G5 起 pygame 为可选依赖**（`pip install -r requirements.txt`），缺失时验证墙优雅跳过、headless 通关照常可用。

```bash
python tools/verify_all.py          # 四道门：规则 → 编译 → 测试 → 数据可加载
python -m unittest discover -s tests -v
python tools/gate.py                # 只看静态规则门 R0–R7
python tools/balance_check.py       # 平衡采样：23.5 万次动作，输出机器事实 JSON（G2-balance-v3）
python tools/autoplayer.py          # G3 巡图：7 区域 / 7 NPC / 100 区块，complete=true 表示无卡死
python tools/g4_report.py           # G4 端到端：图鉴里程碑 / 存档 roundtrip / 脚本不改世界状态
python tools/g5_report.py           # G5 端到端：完整通关 / 存档恢复后通关 / 纯投影 / 可选依赖
python -m src.main --headless       # 无显示器完整通关；--window 开窗口，--save/--load 读写 saves/
POKEWORLD_NO_PYGAME=1 python tools/verify_all.py   # 模拟依赖缺失：四道门仍应 ALL GATES GREEN
```

`tests/golden_seed.json`（当前 **G1-v3**，SHA256 `3ab574e4…`）由规则门 R7 锁定：**不要直接改快照**。
仅当生成器或快照变更且**经人逐次确认**后，才运行 `python tools/make_golden.py` 重建，
再把打印出的 SHA256 登记到 `tools/gate.py::GOLDEN_SNAPSHOT_SHA256` 并在工单变更记录留下新旧哈希与确认结论。
已发生过两次人确认变更：`c2dbd94d… → d18d1b85…`（G1-v2，S-02 拆通道）、`d18d1b85… → 3ab574e4…`（G1-v3，稀有度差异）；两次地形格逐格未变。
三张 `data/*.json` 与 `MANIFEST.sha256` 受保护，改动须逐次人确认并重建清单（LF）。**A11 数值已定稿、S2-03 已采纳**；平衡手感试玩复核仍归人（非阻塞）；`docs/平衡采样报告.md` 只归档机器事实。

`ALL GATES GREEN` 才算通过。`verify_all.py` **拒绝在优化模式运行**（`python -O` / `PYTHONOPTIMIZE`）；
第 0 道前置自检会在 `-O` 子进程投毒并直接验证两条拦截分支，与被跳过的用例等价。
其余入口（`gate.py` / `unittest`）因生产代码零 `assert`，在 `-O` 下仍有效，但不作为门的凭据。

## Git 与远端

- 本地仓库：分支 `main`；远端 `origin → https://github.com/JJCurrry/PokeWorld.git`。
- 2026-11-14 人裁定：**授权 AI 直接推送 GitHub**，AI 负责提交与项目更新（本条即 A5 的变更落单）。
- **推送优先直接 `git push origin main`**（2026-11-14 实测成功）。本机代理对 `github.com` 主域曾返回 `CONNECT tunnel failed, 502`；仅当直连遇 502 时，再尝试绕过代理环境变量：

```bash
git push origin main
# 仅当直连 502 时：
env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy -u ALL_PROXY git push origin main
```

- **无论用哪种方式，推送后必须 `git ls-remote origin HEAD` 核对**：曾出现绕代理命令 exit 0 却静默未更新 `origin/main` 的假成功，只看退出码会误判。
- 凭据由本机 Git Credential Manager 提供（`JJCurrry`），无需在仓库中存放 token；GCM 的 `... store: No such file or directory` 警告不影响推送，可忽略。

## 协作规范

按 `ai-coding-method` 的「1 人独立开发」裁剪基准运作：制品七件套齐备、宪法六条不裁（验收先行 / 小步提交 / 接力有棒 / 修复有规 / 熔断有线 / 变更落单）。
一次一个里程碑、分笔提交每笔 ≤5 文件且 diff ≤400 行，每个里程碑结束更新 `docs/接力文件.md`。
