"""G2 平衡采样（**只输出机器事实，不含手感结论**）。

不变量 #1 / #4：全部随机来自 `RngContext` → `src.gen.rng`，不使用裸随机、时钟或 I/O 之外的
副作用；同参重跑输出逐字节一致。采样覆盖：

- 捕捉率：8 潮灵 × 5 档 hp_ratio × 2500 次 = **100000 次**，实测成功率 vs 公式理论值；
- 遭遇分布：同一区块 **100000 次** encounter，按 wᵢ/Σw 加权抽样 vs 理论比例；
- 伤害矩阵：8×8 全组合（确定性计算，不采样）。

平衡手感、A11 数值定稿与伤害公式（G2-01）均归人；本工具不写「良好 / 达标」一类结论。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.battle import RngContext, Rules, new_state, step  # noqa: E402
from src.battle.rules import catch_probability, damage  # noqa: E402
from src.gen import generate_chunk  # noqa: E402

CATCH_PER_CASE = 2500
HP_RATIOS = (1.0, 0.75, 0.5, 0.25, 0.1)
ENCOUNTER_SAMPLES = 100000
SAMPLE_REGION = "r1"


def _catch_report(tables: dict) -> list[dict]:
    """每个 (物种, hp_ratio) 组合独立采样；world_seed 随序号变化，其余参数固定。"""
    species = [c["id"] for c in tables["species.json"]["creatures"]]
    rows = []
    for cid in species:
        for ratio in HP_RATIOS:
            state = new_state(tables, SAMPLE_REGION, 0, 0, "day", species[0],
                              wild_id=cid, wild_hp_ratio=ratio)
            theory = catch_probability(state.rules, cid, state.wild.hp,
                                       state.wild.max_hp)
            hits = 0
            for index in range(CATCH_PER_CASE):
                seed = f"balance-catch-{cid}-{ratio}-{index}"
                ctx = RngContext(seed, SAMPLE_REGION, 0, 0, 0)
                if step(state, "catch", ctx).outcome == "caught":
                    hits += 1
            observed = hits / CATCH_PER_CASE
            rows.append({
                "creature": cid,
                "hp_ratio": ratio,
                "hp": state.wild.hp,
                "samples": CATCH_PER_CASE,
                "theory": round(theory, 6),
                "observed": round(observed, 6),
                "abs_error": round(abs(observed - theory), 6),
            })
    return rows


def _encounter_report(tables: dict) -> dict:
    """消费 G1-v2 的相对权重：加权抽样频率应与 wᵢ/Σw 一致。"""
    chunk = generate_chunk(tables, "balance-encounter", SAMPLE_REGION, 0, 0)
    weights = chunk["encounter_weights"]["day"]
    state = new_state(tables, SAMPLE_REGION, 0, 0, "day", "c01", weights)
    total = sum(weights.values())
    theory = {cid: weight / total for cid, weight in weights.items()}
    counts = {cid: 0 for cid in weights}
    for index in range(ENCOUNTER_SAMPLES):
        seed = f"balance-enc-{index}"
        ctx = RngContext(seed, SAMPLE_REGION, 0, 0, 0)
        counts[step(state, "encounter", ctx).wild.cid] += 1
    observed = {cid: count / ENCOUNTER_SAMPLES for cid, count in counts.items()}
    errors = {cid: round(abs(observed[cid] - theory[cid]), 6) for cid in weights}
    return {
        "samples": ENCOUNTER_SAMPLES,
        "weights": weights,
        "theory": {k: round(v, 6) for k, v in theory.items()},
        "observed": {k: round(v, 6) for k, v in observed.items()},
        "counts": counts,
        "abs_error": errors,
        "max_abs_error": max(errors.values()),
    }


def _damage_report(tables: dict) -> dict:
    """AI 占位伤害公式（G2-01）在 8×8 全属性组合下的取值，供人复核。"""
    rules = Rules.from_tables(tables)
    ids = [row[0] for row in rules.creatures]
    matrix = [[damage(rules, attacker, defender) for defender in ids]
              for attacker in ids]
    flat = [value for row in matrix for value in row]
    return {
        "ids": ids,
        "matrix": matrix,
        "pairs": len(flat),
        "min": min(flat),
        "max": max(flat),
    }


def snapshot(root: str | Path | None = None) -> dict:
    """纯函数式采样入口：相同输入返回完全相同的 dict。"""
    tables = schema.load_all(root)
    schema.verify_manifest(root)
    catch_rows = _catch_report(tables)
    return {
        "schema_version": 1,
        "generator_version": "G2-balance-v1",
        "catch_samples": len(catch_rows) * CATCH_PER_CASE,
        "catch_cases": len(catch_rows),
        "catch_max_abs_error": max(row["abs_error"] for row in catch_rows),
        "catch_rows": catch_rows,
        "encounter": _encounter_report(tables),
        "damage": _damage_report(tables),
        "note": "机器事实；平衡手感、A11 数值定稿与 G2-01 伤害公式均归人",
    }


def main() -> int:
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
