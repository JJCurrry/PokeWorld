using System;
using System.Collections.Generic;

namespace PokeWorld.Core
{
    // @trace MECH-002
    public enum BattlePhase { Idle, Approach, Strike, Dodge, Capture, Result }

    public sealed class BattleState
    {
        public readonly BattlePhase Phase;
        public readonly int AllyHp;
        public readonly int WildHp;
        public readonly string Message;
        public BattleState(BattlePhase phase, int allyHp, int wildHp, string message)
        {
            Phase = phase; AllyHp = allyHp; WildHp = wildHp; Message = message;
        }
    }

    public static class BattleSystem
    {
        // 唯一状态转移入口；纯函数，不读时钟、不读全局随机。
        public static BattleState Apply(BattleState state, string action, int damage)
        {
            if (state == null) throw new ArgumentNullException(nameof(state));
            if (string.IsNullOrEmpty(action)) throw new ArgumentException("action 不可为空", nameof(action));
            switch (action)
            {
                case "approach":
                    return new BattleState(BattlePhase.Approach, state.AllyHp, state.WildHp, "接近目标");
                case "strike":
                    int left = Math.Max(0, state.WildHp - Math.Max(1, damage));
                    return new BattleState(BattlePhase.Strike, state.AllyHp, left, "命中");
                case "dodge":
                    return new BattleState(BattlePhase.Dodge, state.AllyHp, state.WildHp, "闪避");
                case "capture":
                    return new BattleState(BattlePhase.Capture, state.AllyHp, state.WildHp, "尝试捕捉");
                case "finish":
                    return new BattleState(BattlePhase.Result, state.AllyHp, state.WildHp, "结算");
                default:
                    return state;
            }
        }
    }
}
