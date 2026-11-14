# PokeWorld

> 原创精灵收集 + 种子化群岛探索游戏，同时作为 AI Coding 门控式自治的演练项目。
> 游戏内标题：**潮屿图鉴 / Tide Atlas**。仓库名 `PokeWorld` 仅作工程代号，名称商标风险见 `docs/GDD-v0.md`。

## 当前状态

七步工作循环的**第 3 步（计划）**，等待第 4 步门控评审。
仓库内**尚无任何业务代码**——按「计划只出计划，不写一行代码」与「四道门先行」，G0 才点亮验证墙。

## 目录结构

唯一结构入口见 [`docs/地图.md`](docs/地图.md)；根入口（项目宪法）见 [`CLAUDE.md`](CLAUDE.md)。

## 快速开始

当前阶段无运行命令。G0 交付后，单命令验证墙：

```bash
python tools/verify_all.py
```

## Git 与远端

- 本地仓库：分支 `main`；远端 `origin → https://github.com/JJCurrry/PokeWorld.git`（已配置，探测为空仓库）
- 按项目所有者习惯，**推送由本人在本机终端执行**，AI 不代推：

```bash
git push -u origin main
```

## 协作规范

按 `ai-coding-method` 的「1 人独立开发」裁剪基准运作：制品七件套齐备、宪法六条不裁（验收先行 / 小步提交 / 接力有棒 / 修复有规 / 熔断有线 / 变更落单）。
一次一个里程碑、一次提交、diff ≤ 400 行，每个里程碑结束更新 `docs/接力文件.md`。
