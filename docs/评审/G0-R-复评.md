# G0-R 冷眼复评报告（独立会话 · 只读 · 第一轮）

> 归档说明：**§0 起为评审原文，未删改**；标题与前置说明块为归档元数据（终局复核 N-05 更正字面声称）。评审员无开发历史、不参与实现、被要求不写任何文件；文末「实现者处置记录」附录明确标注不属于评审原文。
> 复核时点：2026-11-14，G0-R 代码已落盘但**尚未提交、尚未推送、接力文件尚未更新、复评报告尚未归档**。
> 结论：**不通过**。时序类发现（R-01 / R-02 / R-07 / R-17）需由后续提交与归档动作闭合；实现者处置记录见文末附录（**附录为实现者追加，不属于评审原文**）。

---

## 0. 实测命令输出与退出码（亲自执行，非引用工单）

复核对象：`C:/Users/Administrator/Desktop/PokeWorld`，Python 3.13 / Git Bash，2026-11-14。
只读材料：4 份指定文档全文、`git status --short`、`git diff` 全文、`git ls-files --others --exclude-standard` 列出的 13 个 untracked 文件全文（4 data + 2 docs + 1 评审 + src/schema.py + 3 tests + 2 tools）。全部读完。

| 命令 | 真实输出（关键段） | 退出码 |
|---|---|---|
| `python tools/verify_all.py` | `[0/4]`~`[4/4]` / `regions=7 edges=6 creatures=8` / `ALL GATES GREEN`；stderr `Ran 31 tests … OK (skipped=2)` | **0** |
| `python -m unittest discover -s tests -v` | `Ran 31 tests … OK`，**0 skipped** | **0** |
| `python -O tools/verify_all.py` | `GATE 0 FAILED: 优化模式…一律拒绝运行` | **1** |
| `PYTHONOPTIMIZE=1 python tools/verify_all.py` | 同上 | **1** |
| `python -OO tools/verify_all.py` / `PYTHONOPTIMIZE=2 …` | 同上 | **1 / 1** |
| `python tools/gate.py` | `GATE OK` | **0** |
| `python -O tools/gate.py` | `GATE OK` | **0** |
| `cd data && sha256sum -c MANIFEST.sha256` | `topology.json: OK` / `species.json: OK` / `encounters.json: OK` | **0** |
| ast 统计 `src/`、`tools/` 所有 `.py` 的 `ast.Assert` | `src ast.Assert = 0 []` / `tools ast.Assert = 0 []`；附带 `tests ast.Assert = 0 []`、根级无 `.py` | **0** |
| `python -O -c` 畸形数据投毒 | `validate_topology/validate_species/validate_encounters` 三个均 `SchemaError OK`，`__debug__ = False` | **0** |
| `python -O -m unittest discover -s tests` | `Ran 31 tests … OK` | **0** |
| `POKEWORLD_GATE_CHILD=1 python -m unittest discover -s tests` | `Ran 31 tests … OK (skipped=2)` | **0** |
| `POKEWORLD_GATE_CHILD=1 python tools/verify_all.py` | `ALL GATES GREEN`，`OK (skipped=2)` | **0** |

**绕过样例实测**（内存调用 `gate.check_source` / `gate.check_data_value`，未写文件）：
- 冷眼原 8 个 `check_source` 样例：**8/8 HIT**；原 3 个 R4 变体：**3/3 HIT**。合计 **11/11 HIT**，与工单 :40 一致。
- 自设计 20 例中 **MISS 8 例**：`eval("__import__('random')")`、`exec("import random")`、`from . import random`（相对导入）、`from importlib import import_module as im; im("random")`、`__import__(mod)`（变量）、`getattr(__builtins__,"__import__")("random")`、能力名写进注释 `# surf`、`{"a":"SURF".lower()}` 放数据文件、`POCKET MONSTERS`（R4 词表外）。
- 自设计 **HIT 且属误报 3 例**：`check("hello")`、`has(1)`、`LOG = "surf"` 均被 R3 拦截。
- 其余 HIT：`getattr(__import__("ran"+"dom"),"randint")`、`import importlib as il; il.import_module("random")`、`from .random import randint`、`f"surf{region}"`、`f"{'su'+'rf'}"`、全角 `Ｐｏｋｅｍｏｎ`、`宝·可·梦`、`.py` 内 `"SURF".lower()`。

**R5 伪造实测**：把 creature name 换成 GDD 正文任意词（「原创度」「完整度」「名称商标」，均非溯源表行）→ `FORGE_R5 violations = 0`（伪造成功）；负向控制 `2` 条违规。`grep assumptions tools/ src/` → No matches found。

### 0.1 分笔提交口径与改动规模（实测）
- `git log --oneline --decorate`：**仅 1 个 commit** `d6e8277 (HEAD -> main, origin/main, origin/HEAD)`。
- `git diff --cached --stat`：**空**（暂存区无任何内容，`git add -N` 未执行）。
- `git status --short`：**8 个 `M` + 7 个 `??` 条目**（目录展开后 13 个 untracked 文件）。
- 改动文件合计：**21 个**（8 tracked + 13 untracked）。
- 变更行合计：**1404 行**（tracked `git diff --numstat` = +163 / −96 = 259 行；13 个 untracked 文件按行数合计 1145 行）。
- 工单 :26 声称「本单**分笔提交**，每笔 ≤5 文件、≤400 变更行（提交记录见下）」：**当前 0 笔提交、无暂存、无 commit 记录**，「提交记录见下」下方（:31-42）只有实测证据表。**现在无法验证「每笔 ≤5 文件 / ≤400 行」，不替实现者假设。**

## ① G0-R 工单每一条 DoD 是否真的满足

### DoD 逐条（:21-29）

| 工单行 | 声称 | 实测判定 | 证据 |
|---|---|---|---|
| :21 F-16 | `ast.Assert`=0、`must()` 显式抛错、`-O`/`PYTHONOPTIMIZE=1` 输出 `GATE 0 FAILED` 退出码 1、绝不 `ALL GATES GREEN`、`-O` 下畸形数据仍抛、第 0 道自检 | **满足** | 见 0 节：ast 计数 0、4 个优化入口全 exit 1、3 个 `validate_*` 在 `-O` 下抛 `SchemaError`、`OPTIMIZE_PROBE` 存在（`tools/verify_all.py:31-43`）。残留见 R-06 |
| :22 F-15 | 冷眼 8 样例 + 3 R4 变体全 HIT 并固化；R1 覆盖动态导入/属性链/别名，R3 覆盖拼接/f-string/大小写/未登记能力名 | **部分满足** | 11/11 HIT 属实；但「覆盖别名」「覆盖动态导入」不实：N2/N3/N7/N9/N11/N12 六例 MISS（R-04） |
| :23 F-01/F-14 | R0~R6 每条规则有故意违规用例；三要素 `assert_hit`；**对真实文件**调用 `gate.run()` 的端到端用例 12 个；`test_schema` 独立解析 + 10 组畸形投毒 | **满足（有弱化）** | `tests/test_gate_rules.py:108-178` 实测 12 个端到端用例；`assert_hit` 在 :59-69；`MUTATIONS` 10 组在 `tests/test_schema.py:30-41`；`read_json` :24-27 不经 `load_all`。弱化见 R-11 |
| :24 F-17/F-22 | 扫描根 = `SCAN_DIRS` + 仓库根级 `*.py`，未登记目录报 R6；`verify_all.py` 每步异常兜底输出 `GATE n FAILED` | **部分满足** | 根级与 R6 已补（`test_root_level_py_is_scanned`、`test_r6_unregistered_source_dir` 绿）；`try/except` 每步具备（:64-106）。但 `EXCLUDED_DIRS` 的 `docs/`、`data/` 内 `.py` 仍是盲区（R-12） |
| :25 F-12/F-04/F-09 | 8 潮灵在 GDD 溯源表逐个登记并由 R5 机器核对；A10/A11 写进三表；另立 `docs/待裁定项.md` | **部分满足** | `docs/GDD-v0.md:61-68` 逐行登记 8 资产属实；三表 `assumptions` 属实；`docs/待裁定项.md` 存在。但 R5 可伪造（R-03）、`gate.py` 无 `assumptions` 核对（R-10） |
| :26 F-03 | 口径改 `git add -N`；G0 14 文件/402 行如实登记；本单分笔提交每笔 ≤5/≤400 行（提交记录见下） | **不满足** | 暂存区空、0 笔提交、无 commit 记录；当前实测 21 文件 / 1404 行（R-01） |
| :27 | `verify_all.py` → `ALL GATES GREEN` 退出码 0（31 用例、门内 2 skip）；独立 `unittest discover -v` 31 用例 OK、**0 skipped**；`sha256sum -c` 三个 OK 退出码 0 | **满足（有条件）** | 全部实测一致；但「0 skipped」仅在未设 `POKEWORLD_GATE_CHILD` 时成立，该变量可独立诱导 `skipped=2`（R-11） |
| :28 F-19/F-20 | 外部流程文档标注「仓库外」；不变量证据列全部指向真实符号；`docs/地图.md`、`README.md`、任务架构细分、术语表、**接力文件同步为真实状态** | **部分满足** | 「仓库外」已标（G0 工单 :28、任务架构细分 :12）；4 个假 `rule_*` 已移除；但接力文件仍写「冷眼不通过/停在裁决点」（R-02），不变量 :15-17 证据列仍指 3 个不存在文件（R-09） |
| :29 | `[ ]` 复评报告归档 / 接力文件更新含 commit / 推送留 `ls-remote` | **未勾选（未完成）** | `docs/评审/` 仅 `G0-冷眼.md`；无本单 commit；`origin/main` 仍=`d6e8277`（R-17） |

### 「实测证据」表 :33-42 逐行核对

| 行 | 工单输出 | 亲自跑是否一致 |
|---|---|---|
| :35 | `[0/4]`~`[4/4]` / `Ran 31 tests … OK (skipped=2)` / `ALL GATES GREEN` / 0 | **一致** |
| :36 | `Ran 31 tests … OK` / 0 | **一致**（且实测 0 skipped） |
| :37 | `GATE 0 FAILED: 优化模式…一律拒绝运行` / 1 | **一致** |
| :38 | 同上 / 1 | **一致** |
| :39 | 三个 `OK` | **一致**（实测退出码 0） |
| :40 | 11/11 HIT | **一致**（8/8 + 3/3） |
| :41 | `GATE OK` | **一致** |
| :42 | `0 []` | **一致**（src 0、tools 0） |

**结论①**：实测证据表 8 行**全部真实、无造假**；但 DoD 勾选与实际状态不符的是 :26（分笔提交 0 笔）与 :28 中「接力文件同步为真实状态」（未同步）。声称「已按工单完成返工」**不成立**：DoD 未闭环，且 :29 三项本就标 `[ ]` 未完成。

## ② 原始 F-01~F-22 逐条消解判定

| # | 判定 | 依据 |
|---|---|---|
| F-01 | **已消解** | R2 失败用例补齐（:135-143）、`assert_hit` 三要素（:59-69）、12 个端到端 `gate.run()` 用例（:108-178）。弱化记 R-11 |
| F-02 | **已消解** | `data/MANIFEST.sha256` LF 行尾、`sha256sum -c` 三 OK exit 0、`test_schema.py:75` 断言无 `\r\n` |
| F-03 | **未消解** | 0 笔提交、21 文件 / 1404 行、`git add -N` 未执行、工单 :26 虚假 [x]（R-01） |
| F-04 | **部分消解** | 加 `ASSUMPTION-A10`/`docs/待裁定项.md` ✓；但区域名/解锁边一字未改仍被 MANIFEST 锁定、A10 自认「未获裁定」、机器侧不核对标记（R-10） |
| F-05 | **部分消解** | `docs/评审/G0-冷眼.md` 已归档（14901 字节 / 122 行），但仍是 untracked、**未纳入提交**（无 commit） |
| F-06 | **未消解** | 接力文件被改但内容仍「冷眼评审不通过、里程碑未验收、停在裁决点、若裁决返工新建 G0-R」，且无本单 commit（R-02） |
| F-07 | **部分消解** | 4 个 `rule_*` 假符号已移除、附录已补；但只回填符号未回填行号，:15-17 仍指 3 个不存在的未来测试文件，文件头新增「并经冷眼复评」的不实表述（R-09） |
| F-08 | **部分消解** | R1 已加固、冷眼 8 样例全 HIT；新绕过 N2/N3/N7/N9/N11/N12 仍漏（R-04） |
| F-09 | **部分消解** | 同 F-04：占位声明已落，人裁定仍缺、MANIFEST 仍锁、`gate.py` 无核对（R-10） |
| F-10 | **已消解** | `verify_manifest` 用 `must`（`src/schema.py:102-122`）、ast.Assert=0、`test_manifest_still_checked_under_O` 绿 |
| F-11 | **部分消解** | 拼接/f-string/大小写/未登记能力名漏检修好；但「合法引用能力名字符串误报」未消解且被制度化，N13/N14/N15 实测 HIT（R-05） |
| F-12 | **部分消解** | 8 资产逐个登记 `docs/GDD-v0.md:61-68` ✓、R5 已加；但 R5 只做「GDD 全文子串包含」，实测可伪造（R-03） |
| F-13 | **已接受风险** | GDD-v0 :59/:85、待裁定项 :11 登记「高风险 · 人已明确接受」；上架前商标检索结论仍缺（R-18） |
| F-14 | **部分消解** | 独立解析 + 10 组投毒 + 12 个端到端 + 真实子进程 ✓；但 `assert_hit` 只查格式/建议长度 ≥12、skip 可由环境变量诱导、31 用例含弱形状断言（R-11） |
| F-15 | **部分消解** | 原 8 样例 + 3 变体 11/11 HIT 并固化（`tests/test_gate_rules.py:29-56`）；6 个新绕过仍 MISS（R-04） |
| F-16 | **已消解** | ast.Assert 全 0、`must()` 显式抛、4 个优化入口全 `GATE 0 FAILED` exit 1、`-O` 下 3 个 `validate_*` 均抛（R-16 为口径缺口，非假绿） |
| F-17 | **部分消解** | 根级 `*.py` 与 R6 已补；`EXCLUDED_DIRS` 内 `docs/`/`data/` 的 `.py` 仍不扫且不报 R6（R-12） |
| F-18 | **已消解** | 本非缺陷（冷眼标注「唯一做对项」）；`tests/` 仍在 `EXCLUDED_DIRS`，新增 `test_tests_dir_is_not_production_scanned` 固化 |
| F-19 | **部分消解** | 「仓库外」已标、假 `rule_*` 已删、冷眼报告已存在；但新引入 4 处引用不存在的 `G0-R-复评.md`，`docs/地图.md:35` 还把它列入「已存在」表（R-07） |
| F-20 | **未消解** | 接力文件（唯一事实源）仍写「未通过/停在裁决点」，与 README :8-9、G0-R 工单 :3、地图 :3、任务架构细分 :4 直接矛盾（R-02） |
| F-21 | **部分消解** | 占位数值 A11 已标边界 ✓；文档同步未单列提交、8 个 tracked 文档与实现混在一起、`docs/不变量.md` 被改越界（R-09/R-13） |
| F-22 | **已消解** | `verify_all.py:64-106` 每步 `try/except` 输出 `GATE n FAILED`；`test_syntax_error_is_reported_not_crashing`、`test_r2_corrupted_table_is_reported` 绿 |

统计：已消解 6（F-01/02/10/16/18/22）、部分消解 12（F-04/05/07/08/09/11/12/14/15/17/19/21）、未消解 3（F-03/06/20）、已接受风险 1（F-13）。

## ③ 新引入问题

**规则门新误报/漏报**：漏报 6 例（R-04）、R4 词表外漏报 1 例（R-14）、语义边界 2 例（R-15）；误报 3 例（R-05）。工单 :22「R1 覆盖动态导入/别名」不实。

**R5 溯源核对可伪造**：`tools/gate.py:138-151` 只对 GDD 全文做归一化子串包含，实测伪造成功（R-03）。这是「8 资产逐个登记」机器证据的实质缺口。

**第 0 道自检是否只是摆设**：不是摆设（`-O` 子进程确实投毒且 4 个优化入口全拒绝），但**只是抽样自检**：只测 `validate_topology` 一个函数（`tools/verify_all.py:33-43`），不测 `verify_manifest`/`load_all`/`gate.run`；且与被 skip 的两个用例**不等价**——门内无任何用例断言「`python -O tools/verify_all.py` 输出 `GATE 0 FAILED`」。易绕过性：标准 flag（`-O`/`-OO`/`PYTHONOPTIMIZE=1/2`）实测全拒绝，不易绕过；但 `POKEWORLD_GATE_CHILD=1` 可在独立 unittest 与 verify_all 中诱导 `skipped=2` 而仍全绿（R-06）。

**测试是否仍空心**：部分空心。自证已破（独立解析 + 投毒 + 12 个端到端 + 真实子进程），但 `assert_hit`（`tests/test_gate_rules.py:59-69`）只校验三要素格式与「修正建议 ≥12 字符」，不校验内容正确性、`where` 用子串匹配；`tests/test_optimize_mode.py:21` 的 `NESTED_IN_GATE` 由外部可读环境变量驱动，实测可诱导 skip（R-11）。

**`python -O` 之外的假绿路径**：
1. `POKEWORLD_GATE_CHILD=1 python -m unittest discover -s tests` → `OK (skipped=2)` exit 0；`POKEWORLD_GATE_CHILD=1 python tools/verify_all.py` → `ALL GATES GREEN (skipped=2)` exit 0（实测，R-06/R-11）。
2. **R2 + R5 自洽性伪造**：改三张表 → AI 自行重算并写入 MANIFEST → 在 GDD 任意位置写入资产名，四门仍全绿；机器侧无法区分「经人确认」与「AI 自行改动」（R-03/R-08）。
3. **静态规则层漏报**：`eval("__import__('random')")` 等真实违规源码可通过 `python tools/gate.py`（`GATE OK`）→ 四门全绿（R-04）。
4. `python -O -m unittest discover -s tests` 与 `python -O tools/gate.py` 仍 `OK`/`GATE OK` exit 0——因源码 `ast.Assert` 全 0，实测不构成假绿，只是「验证墙拒绝优化模式」的口径未覆盖这两个独立入口（R-16）。

**文档新的自相矛盾 / 引用不存在的路径**：
- `docs/评审/G0-R-复评.md` 不存在（`docs/评审/` 只有 `G0-冷眼.md`），却被 `docs/不变量.md:6`、`docs/工单/G0-验证墙与骨架数据.md:5` 当作「消解证据」引用，被 `docs/地图.md:35` 列入「### 已存在（G0 / G0-R 落盘）」表——直接违反 `docs/地图.md:3` 自己写的「禁止假称其存在」。`docs/工单/G0-R-返工.md:29` 自己标 `[ ]` 未完成（R-07）。本次复评按指令不落盘，该引用在本轮内不会闭合。
- `docs/不变量.md:5` 写「并经冷眼复评」——复评报告尚未产出（R-07）。
- `docs/待裁定项.md:17` 写「`assumptions` 字段是机器可读标记，供 `gate.py` 与人工核对」——`grep assumptions` 在 `tools/`、`src/` 全部 `.py` 无匹配，属编造实现（R-10）。
- `docs/不变量.md:15-17` 表头「证据（真实符号）」却列 3 个尚不存在的 `tests/test_*.py`，与工单 :28「全部指向真实符号」不符（R-09）。
- 接力文件状态与其余 5 份文档矛盾（R-02）。

**范围是否蔓延**：未写 G1+ 代码（生成器/战斗/渲染/存档/pygame 均未碰 ✓），`git push` 未发生（`origin/main` 仍 `d6e8277` ✓）。但：① `docs/不变量.md` 被改，而 `docs/工单/G0-验证墙与骨架数据.md:26` 的 Out of scope 明列「`docs/不变量.md` 的既有条目」禁止碰，冷眼报告 :66 曾把「未修改」列为已满足项（R-09）；② 文档同步从 5 个 tracked 扩到 8 个 tracked，且未按 F-21 建议单列提交（R-13）；③ G0-R 工单 :17 的 Out of scope 未继承 G0 工单的「不变量.md 既有条目」「远端 git push」两条，等于放宽边界而无变更落单记录（工单 :60 只记录「批准返工；授权 AI 直连推送」）。

## ④ `docs/不变量.md` 七条红线核对

| # | 判定 | 证据 |
|---|---|---|
| #1 禁裸随机 | **未触碰** | `src/`、`tools/`、`tests/` 无 `random`/`numpy`/`time` 生成调用；R1 加固，冷眼 8 样例全 HIT |
| #2 受保护数据 | **附条件合规，不属完整「改动须人确认」路径**（重点，R-08） | 见下 |
| #3 能力门只在表中 | **未违反** | 当前代码无 `if has("surf")` 类硬编码；但 R3 误报面扩大（R-05） |
| #4 纯函数 | **未落地（G2）**，未触碰 | `docs/不变量.md:15` 明标「G2 待落地」 |
| #5 确定性 | **未落地（G1）**，未触碰 | `docs/不变量.md:16` 明标「G1 待落地」 |
| #6 存档 | **未落地（G4）**，未触碰 | `docs/不变量.md:17` 明标「G4 待落地」 |
| #7 原创合规 | **部分** | 8 资产已逐个登记 `docs/GDD-v0.md:61-68` ✓；R4 归一化有效（N18/N19 HIT）但词表仅 8 词（N20 MISS，R-14）；R5 可伪造（R-03）；造型/文案 G4 待补；#7 文本把「精灵名称」改为「生物名称」（R-09） |

### #2 专项判断

- `docs/不变量.md:13` 原文：「`data/topology.json` / `species.json` / `encounters.json` 是唯一事实源，**AI 只读；改动须人确认并同步 `data/MANIFEST.sha256`**」。
- 事实：三张表被改动（各新增 `assumptions` 字段：`data/topology.json:4-7`、`data/species.json:3`、`data/encounters.json:3`），`data/MANIFEST.sha256` 由 AI 重算并写入（工单 :61「补 8 资产溯源与 A10/A11 占位 → 重建 MANIFEST」），`sha256sum -c` 三 OK、R2 校验通过。
- **不构成完整合规路径**：
  1. 无独立的人确认记录。唯一人裁决记录（工单 :60）是「批准返工；授权 AI 直连推送 GitHub」，不含「批准改动三张受保护表 / 新增 `assumptions` 字段」的逐项确认；`docs/待裁定项.md:18` 要求「每次改动受保护数据**前**须人确认」，无时序证据。
  2. R2 与 `verify_manifest`（`src/schema.py:102-122`）只校验「表与 MANIFEST 自洽」，**无法区分经人确认的改动与 AI 自行改动并同步哈希**——这正是冷眼 F-09 担忧的升级形态。
  3. 字面「AI 只读」被违反（AI 写入三表）；工单 :25 把「写进三张表」列入 DoD，可视为概括性事前授权，且 MANIFEST 已同步、A10/A11 已标占位、`docs/待裁定项.md` 已立——故判「附条件合规」而非「直接违规」。
- 建议动作：补一条显式人确认记录（谁/何时/批准了哪些字段），或把 MANIFEST 生成权从 AI 流程分离；R2 增加「MANIFEST 变更须伴随人裁决记录」检查（R-08）。

## 发现清单（按严重度排序）

**R-01【高】DoD :26 虚假勾选 / F-03 未消解：分笔提交 0 笔**
- 文件:行：`docs/工单/G0-R-返工.md:26`；`docs/工单/G0-验证墙与骨架数据.md:38`
- 证据：`git log --oneline` 仅 `d6e8277`；`git diff --cached --stat` 空；`git status --short` = 8 `M` + 7 `??`，21 个改动文件全未提交；实测 21 文件 / 1404 变更行；:26「提交记录见下」下方（:31-42）只有实测证据表，无任何 commit；`git add -N` 未执行。**「每笔 ≤5 文件 / ≤400 行」现在无法验证**（0 笔提交），不替实现者假设。
- 严重度：高
- 建议动作：按 G0 工单 :19「改动文件 > 5 → 暂停上报」处理；补分笔提交并逐笔留 `git show --stat`，或把 :26 改为 `[ ]` 并撤回声称；明确「实现完成 ≠ DoD 闭环」。

**R-02【高】F-06 / F-20 未消解：唯一事实源失效且与 4 份文档矛盾**
- 文件:行：`docs/接力文件.md:5-7,25-30,44-47`；对照 `README.md:8-9`、`docs/工单/G0-R-返工.md:3`、`docs/地图.md:3`、`docs/任务架构细分.md:4`
- 证据：接力文件仍写「冷眼评审『不通过』，里程碑未验收、未合并、未产生 G0 提交」「进行中：无，停在裁决点」「下一步：若裁决返工，新建 G0-R 工单」「待人类裁决：G0 是否验收」；与 README「G0-R 返工，四道门全绿」「进度以接力文件为唯一事实源」、工单「实现完成、四门全绿」直接矛盾；`git log` 仍无本单 commit。
- 严重度：高
- 建议动作：把接力文件更新为「G0-R 返工完成、四门全绿、待冷眼复评与提交」并附 commit；同步 README/工单/地图/任务架构细分口径后再改状态声明。

**R-03【高】R5 溯源核对可伪造（F-12 机器证据失效）**
- 文件:行：`tools/gate.py:138-151`；`docs/不变量.md:18`
- 证据：`check_provenance` 仅对 `docs/GDD-v0.md` 全文做 `normalize` 后子串包含判断；实测把 name 换成「原创度」「完整度」「名称商标」（均非溯源表行）后 `FORGE_R5 violations = 0`，负向控制返回 2 条违规；R5 不锁 GDD 哈希、不要求逐行登记、不核对造型/文案、不核对 A10 占位。
- 严重度：高
- 建议动作：R5 改为结构化解析溯源表行（匹配 `| 潮灵 \`cNN\` 名称 |`），或对 GDD 溯源段单独计哈希纳入 MANIFEST；补伪造样例为回归用例。

**R-04【高】规则门新漏检 6 例，DoD :22「覆盖动态导入/别名」不实（F-15/F-08 部分消解）**
- 文件:行：`tools/gate.py:26-32,99-125`；`docs/工单/G0-R-返工.md:22`
- 证据：实测 MISS：`eval("__import__('random')")`、`exec("import random")`、`from importlib import import_module as im; im("random")`、`from . import random`、`__import__(mod)`（变量）、`getattr(__builtins__,"__import__")("random")`。根因：R1 只识别 `ast.Import`/`ImportFrom.module`/`ast.Attribute`/`__import__`/`import_module` 调用名，不查 `eval`/`exec` 字符串、不查 ImportFrom 别名、不查 `level>0` 且 `module=None` 的相对导入、不查不可折叠的动态参数。冷眼原 8 样例 + 3 变体 11/11 HIT 属实，属泛化不足。
- 严重度：高
- 建议动作：固化 6 例为回归用例；补 `eval/exec` 字符串扫描、`from … import … as …` 到 `DYNAMIC_IMPORTS` 的别名映射、相对导入处理；或在文档明确「AST 静态门不防运行时动态构造」为已接受风险并登记残余面。

**R-05【中】R3 新误报 3 例（F-11 部分消解）**
- 文件:行：`tools/gate.py:29-32,94-97,122-124`
- 证据：实测 `check("hello")`、`has(1)`、`LOG = "surf"` 均被 R3 `HIT`；`f"surf{region}"` 因常量段被拼出报 n=2 重复违规。冷眼 F-11 点名的「合法引用能力名字符串反而会误报」未消解，且被「能力名零出现」全量扫描 + 无差别 `ABILITY_CHECKS` 调用拦截制度化。
- 严重度：中
- 建议动作：R3 收窄为「`has/get/require` 类调用 + 参数可折叠为能力名」的组合判断；或把「零出现」写成显式设计决定并登记误报面；去重 `collect_strings` 对 JoinedStr/BinOp 的重复上报。

**R-06【中】第 0 道自检不等价于被 skip 用例、覆盖面窄、skip 可诱导**
- 文件:行：`tools/verify_all.py:31-43,46-50,57-70`；`tests/test_optimize_mode.py:21,42-54`
- 证据：门内实测 `Ran 31 tests … OK (skipped=2)`，skip 的是 `test_verify_all_refuses_python_O` / `...pythonoptimize_env`；二者断言「`python -O`/`PYTHONOPTIMIZE=1` 输出 `GATE 0 FAILED`、退出码非 0、不含 `ALL GATES GREEN`」，而 `OPTIMIZE_PROBE` 只验证 `-O` 子进程 `schema.validate_topology(bad)` 抛 `SchemaError`——**不等价，门内无用例断言 main() 的 -O 拦截分支**。`-O`/`-OO`/`PYTHONOPTIMIZE=1/2` 实测全 `GATE 0 FAILED` exit 1（标准 flag 不易绕过），但 `POKEWORLD_GATE_CHILD=1 python tools/verify_all.py` 实测 `ALL GATES GREEN (skipped=2)` exit 0，独立 unittest 亦 `OK (skipped=2)` exit 0。第 0 道自检只测 1 个函数（实测 3 个 `validate_*` 在 `-O` 下均抛，说明实现正确但自检抽样）。
- 严重度：中
- 建议动作：门内补一个不递归的用例直接断言 `subprocess.run([sys.executable,"-O","tools/verify_all.py"])` 输出；把探针扩展到 `verify_manifest`/`load_all`；`POKEWORLD_GATE_CHILD` 改为不可由外部伪造的传递方式，或外部设置时直接报错。

**R-07【中】文档引用不存在的 `G0-R-复评.md`，且「已存在」表假称其存在**
- 文件:行：`docs/地图.md:35`（「### 已存在（G0 / G0-R 落盘）」表）、`docs/不变量.md:5-6`、`docs/工单/G0-验证墙与骨架数据.md:5`、`docs/工单/G0-R-返工.md:29`
- 证据：`ls -la docs/评审/` 仅 `G0-冷眼.md`（14901 字节）；`G0-R-复评.md` 不存在；`docs/工单/G0-R-返工.md:29` 自标 `[ ]` 未完成；`docs/地图.md:3` 自称「禁止假称其存在」；`docs/不变量.md:5` 写「并经冷眼复评」为预先声明未发生事件。本次复评按指令不落盘，该引用在本轮内不会闭合。
- 严重度：中
- 建议动作：3 处「消解证据见」改为指向本报告或标注「待归档」；从「已存在」表移除该行；删除「并经冷眼复评」。

**R-08【中】不变量 #2 合规路径不完整（三表改动 + AI 自重建 MANIFEST，无独立人确认）**
- 文件:行：`docs/不变量.md:13`；`data/topology.json:4-7`、`data/species.json:3`、`data/encounters.json:3`、`data/MANIFEST.sha256:1-3`；`docs/工单/G0-R-返工.md:60-61`；`docs/待裁定项.md:18`
- 证据：三表新增 `assumptions` 字段、MANIFEST 由 AI 重算写入；`sha256sum -c` 三 OK、R2 只校验自洽；唯一人裁决记录（工单 :60）为「批准返工；授权 AI 直连推送」，无逐项确认；`待裁定项.md:18` 要求「改动前须人确认」，无时序证据；机器侧无法区分「经人确认」与「AI 自行改动 + 同步哈希」。
- 严重度：中
- 建议动作：补显式人确认记录（谁/何时/批准哪些字段）；或把 MANIFEST 生成权从 AI 流程分离；R2 增加「MANIFEST 变更须伴随人裁决记录」检查。判定为**附条件合规**，非直接违规。

**R-09【中】`docs/不变量.md` 被改动，触碰 G0 工单 Out of scope「既有条目」禁止碰（F-07/F-19/F-21 部分消解）**
- 文件:行：`docs/工单/G0-验证墙与骨架数据.md:26`；`docs/不变量.md:2-6,12-18,24,36-41`；`docs/评审/G0-冷眼.md:66,69`
- 证据：`git status --short` 显示 ` M docs/不变量.md`；diff 显示文件头、7 条证据列、附录、模块级新增一条全部改写，#7 把「精灵名称」改为「生物名称」；冷眼 :66 曾把「未修改，符合工单 :25 禁止碰」列为已满足项；`docs/不变量.md:15-17` 表头「证据（真实符号）」仍列 3 个不存在的 `tests/test_purity.py` / `test_golden_seed.py` / `test_save_roundtrip.py`，与工单 :28「全部指向真实符号」不符；4 个假 `rule_*` 已移除但未补行号（冷眼 :69 建议「真实符号与行号」）。
- 严重度：中
- 建议动作：补人裁决记录或回退到基线；3 条待落地证据明确标注「未来符号，非真实符号」；补符号行号；G0-R 工单需声明是否解除 G0 的 Out of scope 条款并落单。

**R-10【中】占位标记机器侧无核对，文档声称不实（F-04/F-09/F-12 部分消解）**
- 文件:行：`docs/待裁定项.md:15,17`；`tools/gate.py`（全文）；`data/topology.json:4-7`
- 证据：`grep assumptions` 在 `tools/`、`src/` 全部 `.py` 无匹配——`gate.py`/`schema.py` 均不核对 `assumptions`；R5 只核对 GDD 中 id/name 字符串；A10 区域命名/解锁顺序仍被 MANIFEST 锁定，`待裁定项.md:15` 自认「A10/A11 未获裁定」；8 资产虽登记 `docs/GDD-v0.md:61-68`，但 R5 可伪造（R-03）。`待裁定项.md:17`「供 `gate.py` 与人工核对」为编造实现。
- 严重度：中
- 建议动作：补 A10/assumptions 元数据核对或删除文档不实声称；人裁定 A10 后重建 MANIFEST 并留记录。

**R-11【中】测试仍部分空心 / skip 可由环境变量诱导（F-14 部分消解）**
- 文件:行：`tests/test_gate_rules.py:59-69`；`tests/test_optimize_mode.py:21`；`tests/test_schema.py:52-66`；`docs/工单/G0-R-返工.md:27,35-36`
- 证据：`assert_hit` 只校验三要素正则与「修正建议长度 ≥12」，不校验修正建议内容，`where` 用 `assertIn` 子串匹配；`test_expected_shape_without_schema_helpers` 为硬编码 7/6/8/6 形状断言；实测 `POKEWORLD_GATE_CHILD=1 python -m unittest discover -s tests` → `OK (skipped=2)` exit 0，工单 :27「独立 unittest 0 skipped」仅在未设该变量时成立。
- 严重度：中
- 建议动作：`assert_hit` 增加修正建议关键词断言；skip 条件改为不可由外部环境变量伪造，或独立运行时检测到 `POKEWORLD_GATE_CHILD` 直接报错。

**R-12【中】F-17 部分消解：排除目录内 `.py` 仍是扫描盲区**
- 文件:行：`tools/gate.py:21-25,154-163,191-206`
- 证据：`EXCLUDED_DIRS` 含 `docs`/`data`/`tests` 且不在 `SCAN_DIRS`，`check_scan_scope` 对排除目录直接 `continue`；根级 `*.py` 已扫（`test_root_level_py_is_scanned` 绿）、未登记目录报 R6（`test_r6_unregistered_source_dir` 绿），但 `docs/*.py` / `data/*.py` 含裸随机或语法错误时 R0/R1/R6 均不报——冷眼 F-17 点名的「docs/ 不扫」未闭合。
- 严重度：中
- 建议动作：收紧排除白名单为「仅 `tests/` 与纯数据目录」，或对排除目录内 `.py` 做「存在即报 R6」检查。

**R-13【中】F-21 部分消解：文档同步未单列、分笔口径失真延续**
- 文件:行：`docs/工单/G0-验证墙与骨架数据.md:38`；`docs/工单/G0-R-返工.md:26`；`docs/评审/G0-冷眼.md:106`
- 证据：8 个 tracked 文档改动（含 `docs/不变量.md`）与 13 个 untracked 实现文件混在一起未单列提交；`git diff --cached` 空说明 `git add -N` 未执行；冷眼 F-21 建议「文档同步改动单列提交、不计入 G0 口径」未落地。
- 严重度：中
- 建议动作：文档同步单列一笔提交；明确 `git add -N` 是否执行并留输出；G0-R 工单声明是否解除 G0 的 Out of scope 条款。

**R-14【低】R4 词表覆盖不足（新漏检）**
- 文件:行：`tools/gate.py:33,128-135`
- 证据：实测 `{"name":"POCKET MONSTERS"}` MISS；归一化有效（全角 `Ｐｏｋｅｍｏｎ`、`宝·可·梦` 均 HIT，冷眼 3 变体 3/3 HIT）。词表仅 8 词，未覆盖第三方 IP 全称变体。
- 严重度：低
- 建议动作：扩词表，或把「词表有限」登记为已接受风险。

**R-15【低】静态门语义边界（如实登记，非缺陷）**
- 文件:行：`tools/gate.py:83-125,128-135`
- 证据：能力名写进 `# surf` 注释 MISS（AST 不含注释）；`{"a":"SURF".lower()}` 放数据文件 MISS（R3 只扫 `.py`，R4 只查 IP 词）。按不变量 #3「代码中禁止硬编码能力判断」，注释与数据表内出现能力名不构成违规。
- 严重度：低
- 建议动作：不改代码，在文档写明静态门适用边界。

**R-16【低】`python -O` 之外独立入口不受拦截（口径缺口，非假绿）**
- 文件:行：`tools/verify_all.py:57-61`；`tools/gate.py:210-218`；`README.md`（「验证墙拒绝在优化模式运行」）
- 证据：`python -O -m unittest discover -s tests` 实测 `OK` exit 0；`python -O tools/gate.py` 实测 `GATE OK` exit 0；`python -O -c` 实测 3 个 `validate_*` 均抛 `SchemaError`；`ast.Assert` 在 src/tools/tests 全 0，故这两个入口在 `-O` 下**不假绿**，只是文档口径未覆盖。
- 严重度：低
- 建议动作：文档改为「`verify_all.py` 拒绝优化模式；其余入口因无 assert 仍有效」。

**R-17【低】DoD :29 三项 `[ ]` 未完成，工单 :3 状态与「完成返工」声称并存**
- 文件:行：`docs/工单/G0-R-返工.md:3,29`
- 证据：`G0-R-复评.md` 不存在（R-07）；接力文件未更新为返工状态且无 commit（R-02）；`git log` 无本单 commit、`origin/main` 仍 `d6e8277`、无 `ls-remote` 证据，推送未发生。三项本就标 `[ ]`，不构成虚假勾选，但工单 :3「待独立冷眼复评与提交推送」与「已按工单完成返工」并存时需明确边界。
- 严重度：低
- 建议动作：把状态改为「实现完成，DoD 未闭环（待复评、提交、推送、接力更新）」。

**R-18【低】F-13 商标风险维持「已接受风险」，上架前检索仍缺**
- 文件:行：`docs/GDD-v0.md:59,85`；`docs/待裁定项.md:11`
- 证据：登记「高风险 · 人已明确接受 / 上架前须做商标检索并留结论」，检索结论文件不存在。
- 严重度：低
- 建议动作：维持登记，上架前补商标检索结论。

## 总体结论：**不通过**

可核对的判据：
1. 工单「实测证据」表 8 行**全部真实、无造假**；核心工程缺陷（F-16 的 `assert` 全剥离、F-02 的 CRLF、F-15 原 8 样例、F-10、F-22）确实消解，`ast.Assert` 计数 0、4 个优化入口全 `GATE 0 FAILED`、11/11 绕过样例 HIT、`sha256sum -c` 三 OK。
2. 但原阻断项 **F-03（分笔提交 0 笔、21 文件 / 1404 行未提交、DoD :26 虚假 [x]）**、**F-06（接力文件仍「停在裁决点」且无 commit）**、**F-20（唯一事实源与 4 份文档矛盾）** 未消解；F-05 仅归档未纳入提交。
3. DoD :29 三项 `[ ]` 未完成；DoD :28 中「接力文件同步为真实状态」与实测不符。
4. 新引入中/高项：R5 溯源核对可伪造（实测 `FORGE_R5 = 0`）、规则门 6 例新漏检 + 3 例新误报、第 0 道自检与被 skip 用例不等价且 skip 可由 `POKEWORLD_GATE_CHILD` 诱导、4 处引用不存在的 `G0-R-复评.md` 且 `docs/地图.md:35` 假称已存在、`docs/待裁定项.md:17` 编造 `gate.py` 核对。
5. 不变量 #2：三表改动 + AI 自重建 MANIFEST，仅有工单级概括授权，无逐项人确认记录，R2 只校验自洽——**附条件合规，不属完整「改动须人确认」路径**；`docs/不变量.md` 自身被改动，触碰 G0 工单 Out of scope「既有条目」禁止碰。

按冷眼上一轮口径（阻断项未全部消解即不通过）与 G0-R 工单 :9「冷眼复评必做 / L3 人裁决合并」，判定 **不通过**。返工成果的机器侧质量可作为后续合并的基础，但当前工作区**全部 21 文件未提交、0 笔分笔提交、复评报告与接力文件未闭环**，不具备验收条件。

（本报告为文本返回，未创建或修改任何文件；`docs/评审/G0-R-复评.md` 因指令禁止写文件而仍不存在，R-07 所列悬空引用在本轮内未闭合。）

---

# 附录：实现者处置记录（**不属于评审原文，由实现者追加**）

> 原则：**不修改评审结论**。第一轮结论仍为「不通过」并保留在上方原文中。
> 本附录逐条登记 R-01~R-18 的处置动作、闭合时点与残余风险，供人裁决时核对。
> 追加时点：2026-11-14，第二轮修复完成后、分笔提交与推送之前。

## A. 已由第二轮代码修复消解（有独立复测证据）

| 发现 | 动作 | 证据 |
|---|---|---|
| **R-03【高】** R5 可伪造 | `check_provenance` 改为 `PROVENANCE_ROW` 正则**结构化逐行解析** `\| 潮灵 \`cNN\` 名称 \|`，并校验名称与数据表一致；新增 `test_r5_forged_provenance_is_rejected` | 独立复测：删登记行 + 正文写名字 → `FORGE-BLOCKED` |
| **R-04【高】** 6 例新漏检 | R1 补：`eval`/`exec`/`compile`/`getattr` 字符串扫描、`from importlib import ... as ...` 别名映射、相对导入 `from . import random`、动态导入参数不可静态求值时保守拦截；6 例全部固化进 `R1_SAMPLES` | 独立复测 6/6 `HIT` |
| **R-05【中】** R3 误报 | `ABILITY_CHECKS` 移除泛化的 `check`；R3b 只在参数可折叠为字符串时拦截；`collect_strings` 按能力名去重 | 独立复测 `check("hello")` / `has(1)` → `CLEAN`；新增无误报用例 |
| **R-06【中】** 第 0 道自检不等价 | `OPTIMIZE_PROBE` 扩到 3 个 `validate_*`；第 0 道自检**新增两次真实子进程调用**，直接断言 `-O` 与 `PYTHONOPTIMIZE=1` 输出 `GATE 0 FAILED`、退出码非 0、不含 `ALL GATES GREEN`，与被 skip 的两用例等价 | `python tools/verify_all.py` 全绿（35 用例） |
| **R-10【中】** 占位标记无机器核对 | 新增 `tools/gate.py::check_assumptions`（R5b）：三表 `assumptions` 标记必须逐条出现在 `docs/待裁定项.md`；新增 `test_r5_assumption_marks_are_checked`；文档补字面 `ASSUMPTION-A10/A11` | 四门全绿；删除标记即撞墙 |
| **R-11【中】** `assert_hit` 空心 | 三要素断言新增「修正建议必须含动作词」；新增 `test_r3_avoids_common_false_positives` 等 4 个用例 | 用例数 31 → **35** |
| **R-12【中】** 排除目录盲区 | `check_scan_scope` 对 `EXCLUDED_DIRS` 内含 `.py` 且不在 `PY_ALLOWED_EXCLUDED`（仅 tests / 缓存 / IDE）时报 R6；新增 `test_r6_excluded_dir_py_is_reported` | 四门全绿 |
| **R-14【低】** R4 词表 | 扩为 11 词（补 `POCKET MONSTERS` / `神奇宝贝` / `game freak` 等） | 独立复测 `POCKET MONSTERS` → `HIT` |

## B. 由后续「提交 / 归档 / 接力更新」动作闭合（时序项）

| 发现 | 闭合动作 | 状态 |
|---|---|---|
| **R-01【高】** F-03：0 笔提交、21 文件 / 1404 行、DoD :26 虚假 [x] | G0-R 工单 :26 已改回 `[ ]` 并注明「提交阶段闭合」；按 ≤5 文件 / 笔、≤400 行 / 笔拆分提交，逐笔留 `git show --stat`；用 `git add -N` 纳入 untracked 统计 | 待提交阶段闭合 |
| **R-02【高】** F-06/F-20：接力文件失效并自相矛盾 | 接力文件按真实状态整体重写，含 commit hash 与复评结论 | 待提交阶段闭合 |
| **R-07【中】** 4 处引用不存在的 `G0-R-复评.md` | 本报告归档后引用即成立；`docs/地图.md`「已存在」表随之成立；不变量表头改为「复评结论不通过」 | **本报告归档即闭合** |
| **R-13【中】** 文档同步未单列 | 提交分组把文档同步单列一笔，与实现提交分离 | 待提交阶段闭合 |
| **R-17【低】** DoD :29 三项 `[ ]` | 复评归档 ✅ / 接力文件 / 提交 / 推送与 `ls-remote` 证据 | 部分闭合，余待推送 |

## C. 如实登记、不自行消解（须人裁决）

| 发现 | 处置 |
|---|---|
| **R-08【中】** 不变量 #2 合规路径不完整 | 不伪造人确认记录。新增 **A13** 到 `docs/待裁定项.md`：三表 `assumptions` 元数据改动与 MANIFEST 重建为 AI 依返工 DoD 执行，属「附条件合规」，**待人逐项追认**；不追认则回退字段并重建清单。R2 只能校验自洽，机器侧无法区分人确认与 AI 自改并同步哈希。 |
| **R-09【中】** 改 `docs/不变量.md` 触碰 G0 Out of scope | G0-R 工单变更记录明确登记「解除该条并落单」，理由：F-07/F-19 要求回填真实符号，不改会使文档永久失真。3 条未来符号已显式标注「当前不存在」。 |
| **R-15【低】** 静态门语义边界 | 登记为设计边界：注释内能力名、数据表内非能力门字符串不属 R3 检查范围；AST 静态门不防运行时动态构造（R1 已对 `eval`/`exec`/`getattr` 做保守拦截，但无法穷尽）。 |
| **R-16【低】** `-O` 独立入口口径 | README 已改为「`verify_all.py` 拒绝优化模式；其余入口因零 `assert` 仍有效，但不作为门的凭据」。 |
| **R-18【低】** 商标检索 | 维持「高风险 · 人已接受」，上架前补检索结论，当前不做。 |
| **R-05 残余误报面** | `LOG = "surf"` 一类能力名字符串仍会被 R3a 拦截 —— 这是「能力名在代码中零出现」的**显式设计决定**，已写入不变量 #3 下沉状态；若人认为过严，另开 ADR 收窄。 |

## D. 第二轮修复后的独立复测（实现者自测，非评审结论）

| 动作 | 输出 |
|---|---|
| `python tools/verify_all.py` | `Ran 35 tests … OK (skipped=2)` / `ALL GATES GREEN` / exit 0 |
| `python -m unittest discover -s tests -v` | `Ran 35 tests … OK` / **0 skipped** / exit 0 |
| `python -O tools/verify_all.py` / `PYTHONOPTIMIZE=1 …` | 均 `GATE 0 FAILED` / exit 1 |
| 复评 R-04 六例 + R4 变体 | 7/7 `HIT` |
| R-03 伪造溯源 | `FORGE-BLOCKED` |
| R-05 误报样例 | 2/2 `CLEAN` |
| `python tools/gate.py` | `GATE OK` |

> **实现者不自行把结论改为「通过」。** 第一轮复评「不通过」保持有效；本附录只说明哪些项已修、哪些项由后续动作闭合、哪些项归人裁决。是否验收 G0，由人决定。
