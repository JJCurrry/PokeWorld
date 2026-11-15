"""G2 状态转移：`step(state, action, rng) -> state'`（不变量 #4）。

纯函数契约：
- 不读时钟、不做 I/O、不改全局状态、不改传入的 state / rules；
- 随机只来自 `rng.stream(label)`，而 rng 是不可变的 `RngContext`；
- 同一份 (state, action, rng) 重跑得到逐字段相同的 state'；
- 非法状态 / 未知动作 / 空权重一律显式抛 `ValueError`，不用 `assert`。

动作（G2 返工 · ADR-002，签名仍为 `step(state, action, rng)`）：
- `encounter`：按 G1 相对权重抽样野生潮灵，初始无状态；
- `attack`：回合对战，野生必定反击；
- `item:<id>`：消耗背包里一件道具；ball 类设为本次捕捉的网，status 类按
  `apply_rate` 由 rng 判定施加异常状态并置 `status_ticks`；
- `catch`：用装备的网 + 野生当前状态计算捕捉率；未命中按 `counter_rate` 判定反击；
- `flee`：按 `flee` 表的基础率 + 敏捷差 + 状态加成判定，不再恒成功；失败同样按反击率判定。

状态机：`status_ticks` 在攻击 / 捕捉 / 撤离等回合动作后递减，归零清除状态；
施加状态的那一回合不递减。捕捉公式的 hp 项未改（S2-03 仍归人裁决）。
"""
from __future__ import annotations

from dataclasses import replace

from src.gen.rng import Stream

from .context import RngContext
from .rules import catch_probability, damage, flee_probability
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


def _decay(state: BattleState) -> BattleState:
    """异常状态持续回合递减，归零清除；施加当回合由调用方跳过本函数。"""
    wild = state.wild
    if wild is None or wild.status is None:
        return state
    ticks = wild.status_ticks - 1
    if ticks <= 0:
        return replace(state, wild=replace(wild, status=None, status_ticks=0))
    return replace(state, wild=replace(wild, status_ticks=ticks))


def _counter(rng: RngContext, state: BattleState, base: BattleState,
             prefix: str) -> BattleState:
    """捕捉未命中 / 撤离失败后的反击判定；无状态必定反击，僵麻反击率为 0。"""
    _require(state.wild is not None and state.ally is not None, "反击需要双方在场")
    rate = state.rules.counter_rate(state.wild.status)
    if rng.stream("counter").unit() >= rate:
        return replace(base, log=state.log + (prefix, "counter:avoided"))
    hit = damage(state.rules, state.wild.cid, state.ally.cid)
    ally = replace(state.ally, hp=max(0, state.ally.hp - hit))
    outcome = "lost" if ally.hp == 0 else "active"
    return replace(base, ally=ally, outcome=outcome,
                   log=state.log + (prefix, f"counter:{hit}"))


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

    if action.startswith("item:"):
        _require(state.outcome == "active", "仅 active 状态可使用道具")
        _require(state.wild is not None, "使用道具需要野生潮灵在场")
        item_id = action[len("item:"):]
        _require(bool(item_id), "道具 id 不得为空")
        _require(item_id in state.bag, f"背包中没有道具：{item_id}")
        item = state.rules.item(item_id)
        remaining = list(state.bag)
        remaining.remove(item_id)
        bag = tuple(remaining)
        if item[2] == "ball":
            return replace(base, bag=bag, equipped_ball=item_id,
                           log=state.log + (f"item:{item_id}:equip",))
        applied = rng.stream(f"item:{item_id}").unit() < item[5]
        if applied:
            duration = state.rules.status(item[4])[3]
            wild = replace(state.wild, status=item[4], status_ticks=duration)
            note = f"item:{item_id}:applied"
        else:
            wild = state.wild
            note = f"item:{item_id}:miss"
        # 施加当回合不递减 ticks，让 duration 覆盖其后完整 duration 个动作。
        return replace(base, bag=bag, wild=wild, log=state.log + (note,))

    if action == "attack":
        _require(state.outcome == "active", "仅 active 状态可攻击")
        _require(state.wild is not None and state.ally is not None,
                 "攻击需要双方在场")
        hit = damage(state.rules, state.ally.cid, state.wild.cid)
        wild = replace(state.wild, hp=max(0, state.wild.hp - hit))
        note = f"attack:{hit}"
        if wild.hp == 0:
            return _decay(replace(base, wild=wild, outcome="won",
                                  log=state.log + (note,)))
        counter = damage(state.rules, state.wild.cid, state.ally.cid)
        ally = replace(state.ally, hp=max(0, state.ally.hp - counter))
        outcome = "lost" if ally.hp == 0 else "active"
        return _decay(replace(base, wild=wild, ally=ally, outcome=outcome,
                              log=state.log + (note, f"counter:{counter}")))

    if action == "catch":
        _require(state.outcome == "active", "仅 active 状态可捕捉")
        _require(state.wild is not None and state.ally is not None,
                 "捕捉需要双方在场")
        ball_bonus = (state.rules.item(state.equipped_ball)[3]
                      if state.equipped_ball is not None else 1.0)
        status_bonus = (state.rules.status(state.wild.status)[2]
                        if state.wild.status is not None else 1.0)
        probability = catch_probability(state.rules, state.wild.cid,
                                        state.wild.hp, state.wild.max_hp,
                                        ball_bonus, status_bonus)
        if rng.stream("catch").unit() < probability:
            return _decay(replace(base, outcome="caught",
                                  log=state.log + ("catch:hit",)))
        return _decay(_counter(rng, state, base, "catch:miss"))

    if action == "flee":
        _require(state.outcome == "active", "仅 active 状态可撤离")
        _require(state.wild is not None and state.ally is not None,
                 "撤离需要双方在场")
        probability = flee_probability(state.rules, state.ally.cid,
                                       state.wild.cid, state.wild.status)
        if rng.stream("flee").unit() < probability:
            return _decay(replace(base, outcome="fled", log=state.log + ("flee",)))
        return _decay(_counter(rng, state, base, "flee:fail"))

    raise ValueError(f"未知动作：{action}")
