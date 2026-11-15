"""G2 平衡采样（**只输出机器事实，不含手感结论**）。

不变量 #1 / #4：全部随机来自 `RngContext` → `src.gen.rng`，不使用裸随机、时钟或 I/O 之外的
副作用；同参重跑输出逐字节一致。采样覆盖：

- 捕捉率：8 潮灵 × 5 档 hp_ratio × 2500 次 = **100000 次**，实测成功率 vs 公式理论值；
- 道具 / 状态：6 组（球 × 状态 × hp_ratio）× 2500 次，验证 `step` 真的读到了装备球与异常状态；
- 遭遇分布：同一区块 **100000 次** encounter，按 wᵢ/Σw 加权抽样 vs 理论比例；
- 撤离：**20000 次** flee，验证成功率不再是恒定 100%；
- 伤害矩阵 / 稀有度分布：8×8 全组合与各区域理论比例（确定性计算，不采样）。

平衡手感、A11 数值定稿、S2-03 满血捕捉率均归人；本工具不写「良好 / 达标」一类结论。
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import schema  # noqa: E402
from src.battle import RngContext, Rules, new_state, step  # noqa: E402
from src.battle.rules import catch_probability, damage, flee_probability  # noqa: E402
from src.gen import generate_chunk  # noqa: E402

CATCH_PER_CASE = 2500
HP_RATIOS = (1.0, 0.75, 0.5, 0.25, 0.1)
ENCOUNTER_SAMPLES = 100000
FLEE_SAMPLES = 20000
SAMPLE_REGION = "r1"
ITEM_COMBOS = (
    ("c01", 1.0, "net_plain", None),
    ("c01", 0.5, "net_plain", None),
    ("c01", 0.5, "net_fine", "drowse"),
    ("c01", 0.5, "net_tide", "numb"),
    ("c01", 1.0, "net_tide", "numb"),
    ("c08", 0.5, "net_tide", "numb"),
)


def _catch_report(tables: dict) -> list[dict]:
    """每个 (物种, hp_ratio) 组合独立采样；world_seed 随序号变化，其余参数固定。

    默认装备表里第一个 ball 类道具（倍率 1.00）、野生无状态，因此与
    `catch_probability` 的两参数默认值一致。
    """
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


def _item_report(tables: dict) -> list[dict]:
    """直接构造「已装备某网 + 野生带某状态」的局面，验证道具 / 状态真的接进 `step`。

    这里不走 `item:<id>` 动作链（施加状态有 apply_rate 随机），只验证倍率消费路径。
    """
    rows = []
    for cid, ratio, ball, status in ITEM_COMBOS:
        state = new_state(tables, SAMPLE_REGION, 0, 0, "day", "c01",
                          wild_id=cid, wild_hp_ratio=ratio)
        rules = state.rules
        ball_bonus = rules.item(ball)[3]
        status_bonus = rules.status(status)[2] if status is not None else 1.0
        ticks = rules.status(status)[3] if status is not None else 0
        state = replace(state, equipped_ball=ball,
                        wild=replace(state.wild, status=status,
                                     status_ticks=ticks))
        theory = catch_probability(rules, cid, state.wild.hp,
                                   state.wild.max_hp, ball_bonus, status_bonus)
        hits = 0
        for index in range(CATCH_PER_CASE):
            seed = f"balance-item-{cid}-{ratio}-{ball}-{status}-{index}"
            ctx = RngContext(seed, SAMPLE_REGION, 0, 0, 0)
            if step(state, "catch", ctx).outcome == "caught":
                hits += 1
        observed = hits / CATCH_PER_CASE
        rows.append({
            "creature": cid,
            "hp_ratio": ratio,
            "ball": ball,
            "ball_bonus": ball_bonus,
            "status": status,
            "status_bonus": status_bonus,
            "samples": CATCH_PER_CASE,
            "theory": round(theory, 6),
            "observed": round(observed, 6),
            "abs_error": round(abs(observed - theory), 6),
        })
    return rows


def _encounter_report(tables: dict) -> dict:
    """消费 G1-v3 的相对权重（含 rarity）：加权抽样频率应与 wᵢ/Σw 一致。"""
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


def _flee_report(tables: dict) -> dict:
    """撤离不再恒成功：实测 `fled` 频率 vs `flee_probability` 理论值。"""
    state = new_state(tables, SAMPLE_REGION, 0, 0, "day", "c01", wild_id="c02")
    theory = flee_probability(state.rules, "c01", "c02", None)
    fled = 0
    for index in range(FLEE_SAMPLES):
        seed = f"balance-flee-{index}"
        ctx = RngContext(seed, SAMPLE_REGION, 0, 0, 0)
        if step(state, "flee", ctx).outcome == "fled":
            fled += 1
    observed = fled / FLEE_SAMPLES
    return {
        "samples": FLEE_SAMPLES,
        "ally": "c01",
        "wild": "c02",
        "theory": round(theory, 6),
        "observed": round(observed, 6),
        "abs_error": round(abs(observed - theory), 6),
    }


def _rarity_report(tables: dict) -> dict:
    """各区域 day 遭遇理论比例（确定性，由 G1-v3 权重算出），供人复核稀有度差异。"""
    rarity = {c["id"]: float(c["rarity"])
              for c in tables["species.json"]["creatures"]}
    regions = []
    for region in tables["topology.json"]["regions"]:
        chunk = generate_chunk(tables, "balance-rarity", region["id"], 0, 0)
        weights = chunk["encounter_weights"]["day"]
        total = sum(weights.values())
        regions.append({
            "region": region["id"],
            "name": region["name"],
            "pool": sorted(weights),
            "rarity": {cid: rarity[cid] for cid in sorted(weights)},
            "weights": {cid: round(weight, 6) for cid, weight in weights.items()},
            "theory": ({cid: round(weight / total, 6) for cid, weight in weights.items()}
                       if total else {}),
        })
    return {"rarity": rarity, "regions": regions}


def _damage_report(tables: dict) -> dict:
    """ADR-002 比例型伤害公式在 8×8 全属性组合下的取值，供人复核。"""
    rules = Rules.from_tables(tables)
    ids = [row[0] for row in rules.creatures]
    matrix = [[damage(rules, attacker, defender) for defender in ids]
              for attacker in ids]
    flat = [value for row in matrix for value in row]
    return {
        "ids": ids,
        "formula": dict(tables["encounters.json"]["damage_formula"]),
        "matrix": matrix,
        "pairs": len(flat),
        "min": min(flat),
        "max": max(flat),
        "mean": round(sum(flat) / len(flat), 4),
        "at_floor": sum(value == rules.damage_min for value in flat),
    }


def snapshot(root: str | Path | None = None) -> dict:
    """纯函数式采样入口：相同输入返回完全相同的 dict。"""
    tables = schema.load_all(root)
    schema.verify_manifest(root)
    catch_rows = _catch_report(tables)
    item_rows = _item_report(tables)
    return {
        "schema_version": 1,
        "generator_version": "G2-balance-v2",
        "catch_samples": len(catch_rows) * CATCH_PER_CASE,
        "catch_cases": len(catch_rows),
        "catch_max_abs_error": max(row["abs_error"] for row in catch_rows),
        "catch_rows": catch_rows,
        "item_samples": len(item_rows) * CATCH_PER_CASE,
        "item_max_abs_error": max(row["abs_error"] for row in item_rows),
        "item_rows": item_rows,
        "encounter": _encounter_report(tables),
        "flee": _flee_report(tables),
        "rarity": _rarity_report(tables),
        "damage": _damage_report(tables),
        "note": "机器事实；平衡手感、A11 数值定稿与 S2-03 满血捕捉率均归人；全部数值为候选占位",
    }


def main() -> int:
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
