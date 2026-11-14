"""G2 随机上下文（不变量 #1 / #4）。

`step` 的 rng 参数是**不可变上下文**，不是会推进游标的流对象：
若把 `Stream` 直接传进 step，同一份 state+action 会因为游标位置不同而
得到不同结果，「同参重跑逐字段一致」就无法证明，采样也失去意义。

本模块只放不可变类型与纯函数；模块级无可变状态。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.gen.rng import Stream, rng


@dataclass(frozen=True)
class RngContext:
    """绑定四元组与回合序号；每次动作由 step 校验与 state.tick 一致。"""

    world_seed: str | int
    region_id: str
    cx: int
    cy: int
    tick: int = 0

    def stream(self, label: str) -> Stream:
        """按用途名 + tick 派生隔离流；新增用途不会改变既有用途的结果。"""
        return rng(self.world_seed, self.region_id, self.cx, self.cy,
                   f"{label}:{self.tick}")

    def advance(self) -> "RngContext":
        """返回下一回合的上下文，供链式调用与 state.tick 同步。"""
        return RngContext(self.world_seed, self.region_id, self.cx, self.cy,
                          self.tick + 1)
