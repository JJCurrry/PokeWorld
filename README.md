# PokeWorld

> 原创生物收集 + 种子化群岛探索游戏，同时作为 AI Coding 门控式自治的演练项目。
> 游戏内标题：**PokeWorld**（2026-11-14 门控裁定沿用仓库名；名称商标高风险已知并接受，见 `docs/GDD-v0.md` 第 6、7 节）。

## 当前状态

2026-11-14 人裁决 **G0 / G1 均验收通过**并授权进入 G2。
**G1**：确定性 `rng(world_seed, region_id, cx, cy)`、8×8 区块地形与遭遇相对权重、golden seed 快照（**G1-v3**）与规则门 R7。
**G2 返工已实现（待人验收）**：按 2026-11-14 22:24 + 2026-11-15 两次人裁决完成 **比例型伤害公式**（结构常数入表）、**出没稀有度 `rarity`**、**道具 / 异常状态建模**（三档网 + 昏沉 / 僵麻 + 状态机 + 撤离判定）；`step(state, action, rng) -> state'` 签名不变、状态全 frozen。采样扩到 10 万次基础捕捉 + 1.5 万次道具 / 状态 + 10 万次遭遇 + 2 万次撤离，机器事实见 `docs/平衡采样报告.md`，**117 用例全绿**。
**S2-03 满血捕捉率仍归人**：hp 项未改，满血时道具 / 状态受公式下限钳制而失效，如实登记为已知限制（设计见 `docs/adr/ADR-002-战斗数值与出没稀有度建模.md` §5）。
G2 里程碑验收仍归人裁决，G3 未开始。**当前进度以 `docs/接力文件.md` 为唯一事实源**。

## 目录结构

唯一结构入口见 [`docs/地图.md`](docs/地图.md)；根入口（项目宪法）见 [`CLAUDE.md`](CLAUDE.md)。

## 快速开始

零第三方依赖，Python 3.13 标准库即可：

```bash
python tools/verify_all.py          # 四道门：规则 → 编译 → 测试 → 数据可加载
python -m unittest discover -s tests -v
python tools/gate.py                # 只看静态规则门 R0–R7
python tools/balance_check.py       # G2 平衡采样：23.5 万次动作，输出机器事实 JSON
```

`tests/golden_seed.json`（当前 **G1-v3**，SHA256 `3ab574e4…`）由规则门 R7 锁定：**不要直接改快照**。
仅当生成器或快照变更且**经人确认**后，才运行 `python tools/make_golden.py` 重建，
再把打印出的 SHA256 登记到 `tools/gate.py::GOLDEN_SNAPSHOT_SHA256` 并在工单变更记录留下新旧哈希与确认结论。
已发生过两次人确认变更：`c2dbd94d… → d18d1b85…`（G1-v2，S-02 拆通道）、`d18d1b85… → 3ab574e4…`（G1-v3，稀有度差异）；两次地形格逐格未变。
平衡手感、A11 数值定稿与 **S2-03 满血捕捉率**归人；`docs/平衡采样报告.md` 只归档机器事实。

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
