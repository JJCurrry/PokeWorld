"""G2 状态转移：`step(state, action, rng) -> state'`（不变量 #4）。

纯函数契约：
- 不读时钟、不做 I/O、不改全局状态、不改传入的 state / rules；
- 随机只来自 `rng.stream(label)`，而 rng 是不可变的 `RngContext`；
- 同一份 (state, action, rng) 重跑得到逐字段相同的 state'；
- 非法状态 / 未知动作 / 空权重一律显式抛 `ValueError`，不用 `assert`。

动作：encounter（遭遇）/ attack（回合对战）/ catch（捕捉）/ flee（撤离）。
撤离在原型级恒成功，不引入额外数值（G2-03 登记）。
"""
from __future__ import annotations

from dataclasses import replace

from src.gen.rng import Stream

from .context import RngContext
from .rules import catch_probability, damage
from .state import BattleState, Creature


def _require(condition: bool, message: str) -> None:
    """显式校验；`python -O` 下同样生效（不依赖 assert）。"""
    if not condition:
        raise ValueError(message)


def _pick(stream: Stream, weights: tuple[tuple[str, float], ...]) -> str:
    """按 wᵢ/Σw 加权抽样消费 G1 的相对权重；不把相对量当概率直接比较。"""
    if not weights:
        raise ValueError("当前区块的遭遇权重为空，无法触发遭遇")
    cids = [cid for cid, _ in weights]
    values = [weight for _, weight in weights]
    return cids[stream.pick(values)]


def step(state: BattleState, action: str, rng: RngContext) -> BattleState:
    """纯函数：返回新状态；tick 递增 1，日志只追加不改写。"""
    _require(isinstance(state, BattleState), "state 必须是 BattleState")
    _require(isinstance(rng, RngContext), "rng 必须是不可变 RngContext（不得传 Stream）")
    _require(rng.tick == state.tick,
             f"随机上下文 tick={rng.tick} 与状态 tick={state.tick} 不一致；请用 advance() 同步")
    _require(state.region == rng.region_id and state.coord == (rng.cx, rng.cy),
             "随机上下文的区域 / 坐标与状态不一致")

    base = replace(state, tick=state.tick + 1)

    if action == "encounter":
        _require(state.outcome == "idle", "仅 idle 状态可触发遭遇")
        cid = _pick(rng.stream("encounter"), state.weights)
        row = state.rules.creature(cid)
        wild = Creature(cid, row[2], row[2])
        return replace(base, wild=wild, outcome="active",
                       log=state.log + (f"encounter:{cid}",))

    if action == "attack":
        _require(state.outcome == "active", "仅 active 状态可攻击")
        _require(state.wild is not None and state.ally is not None,
                 "攻击需要双方在场")
        hit = damage(state.rules, state.ally.cid, state.wild.cid)
        wild = replace(state.wild, hp=max(0, state.wild.hp - hit))
        note = f"attack:{hit}"
        if wild.hp == 0:
            return replace(base, wild=wild, outcome="won",
                           log=state.log + (note,))
        counter = damage(state.rules, state.wild.cid, state.ally.cid)
        ally = replace(state.ally, hp=max(0, state.ally.hp - counter))
        outcome = "lost" if ally.hp == 0 else "active"
        return replace(base, wild=wild, ally=ally, outcome=outcome,
                       log=state.log + (note, f"counter:{counter}"))

    if action == "catch":
        _require(state.outcome == "active", "仅 active 状态可捕捉")
        _require(state.wild is not None and state.ally is not None,
                 "捕捉需要双方在场")
        probability = catch_probability(state.rules, state.wild.cid,
                                        state.wild.hp, state.wild.max_hp,
                                        state.wild.statused)
        if rng.stream("catch").unit() < probability:
            return replace(base, outcome="caught",
                           log=state.log + ("catch:hit",))
        counter = damage(state.rules, state.wild.cid, state.ally.cid)
        ally = replace(state.ally, hp=max(0, state.ally.hp - counter))
        outcome = "lost" if ally.hp == 0 else "active"
        return replace(base, ally=ally, outcome=outcome,
                       log=state.log + ("catch:miss", f"counter:{counter}"))

    if action == "flee":
        _require(state.outcome == "active", "仅 active 状态可撤离")
        return replace(base, outcome="fled", log=state.log + ("flee",))

    raise ValueError(f"未知动作：{action}")
