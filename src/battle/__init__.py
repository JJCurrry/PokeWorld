"""G2 战斗层：纯函数状态转移（不变量 #4）。

对外只暴露最小接口：构造状态、不可变随机上下文、状态转移。
规则快照 `Rules` 由 `src.battle.rules` 单独导出，供采样工具使用。
"""
from .context import RngContext
from .engine import step
from .rules import Rules
from .state import BattleState, Creature, new_state

__all__ = ("RngContext", "Rules", "BattleState", "Creature", "new_state", "step")
