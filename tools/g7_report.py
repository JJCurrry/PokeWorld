"""G7 端到端机器事实报告：战斗 / 捕捉闭环 + 图鉴回写 + 存档 + 纯投影 + 零改表。

用法：`python tools/g7_report.py [world_seed]`（默认 `G7-a`，该种子可稳定演示捕捉成功闭环）。
`run(tables, world_seed)` 不改传入的表、不写文件、不读时钟；只有 `main()` 做
加载与打印。报告只写机器事实，不含手感 / 观感结论（B 级归人）。

五项 DoD 的证据：
- D1 战斗动作进会话层：`encounter / attack / catch / flee / item:<id>` 全部经
  G2 `step` 与 `ctx.advance()`；tick 同步、flag 校验由测试覆盖。
- D2 终局回写：`won / caught` 的野生潮灵经 `game.observe` 进图鉴（空册起可见
  增量），`lost / fled` 不登记；终局后 `battle` 清空。
- D3 端到端可玩：空册开局 → 遭遇 → 换网 / 上状态 → 捕捉 → 图鉴登记 → 存档 →
  读档（战斗运行时不入库、读档后重置），`frame_of` 战斗投影只读。
- D4 确定性 + 反证：同种子同策略逐字节一致、换种子不同；「无战斗时战斗动作
  抛错」「战斗中世界动作抛错」「空图鉴捕获增量」为反证 / 正证。
- D5 门控零改表：`gate.run` / manifest / golden 全绿、表未被改。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import gate  # noqa: E402
from src import schema  # noqa: E402
from src.view import deps  # noqa: E402
from src.view.layout import COMBAT_KEY_ACTIONS, KEY_ACTIONS, frame_of  # noqa: E402
from src.world import session as play  # noqa: E402
from src.world.save import FORBIDDEN_KEYS, SAVE_KEYS, decode, encode  # noqa: E402

DEFAULT_SEED = "G7-a"
# 捕捉策略：先换高级网、上凝霜状态，再重复捕捉直到终局（纯动作序列，无随机）。
_CATCH_SETUP = ("item:net_tide", "item:bell_calm")


def _capture_run(tables: dict, world_seed: str,
                 actions_bound: int = 48) -> tuple[object, tuple[str, ...], str]:
    """空册开局 → 遭遇 → 换网 / 上状态 → 反复捕捉到终局；返回会话 / 动作 / 野生 id。"""
    current = play.new_session(tables, world_seed)
    current = play.apply(current, "encounter", tables)
    wild = current.battle.wild.cid if current.battle is not None and current.battle.wild else ""
    actions = ["encounter"]
    for action in _CATCH_SETUP:
        if current.battle is None:
            break
        current = play.apply(current, action, tables)
        actions.append(action)
    while current.battle is not None and len(actions) < actions_bound:
        current = play.apply(current, "catch", tables)
        actions.append("catch")
    return current, tuple(actions), wild


def _raises(call) -> bool:
    """动作是否显式抛错（反证用；禁 assert 的生产代码路径）。"""
    try:
        call()
    except ValueError:
        return True
    return False


def run(tables: dict, world_seed: str = DEFAULT_SEED) -> dict:
    """纯函数：产出 G7 五项 DoD 的机器事实 JSON（不写手感 / 品味结论）。"""
    before = copy.deepcopy(tables)

    final, actions, wild = _capture_run(tables, world_seed)
    outcome_msg = final.messages[-1] if final.messages else ""
    captured = final.captures
    atlas_has_wild = final.state.atlas.contains(wild) if wild else False

    # 确定性：同种子同策略两次完全一致；换种子结果不同。
    replay, replay_actions, replay_wild = _capture_run(tables, world_seed)
    deterministic = (replay_actions == actions and replay_wild == wild
                     and replay.state.atlas == final.state.atlas
                     and replay.captures == captured)
    other, other_actions, other_wild = _capture_run(tables, f"{world_seed}-alt")
    seed_matters = (other_actions != actions or other_wild != wild
                    or other.state.atlas != final.state.atlas)

    # 反证：无战斗时战斗动作抛错；战斗中世界动作抛错；重复遭遇抛错。
    fresh = play.new_session(tables, world_seed)
    no_battle_rejected = _raises(lambda: play.apply(fresh, "attack", tables))
    in_battle = play.apply(fresh, "encounter", tables)
    world_rejected = _raises(lambda: play.apply(in_battle, "survey", tables))
    repeat_rejected = _raises(lambda: play.apply(in_battle, "encounter", tables))

    # 终局清空运行时战斗态（battle / battle_ctx 均不进存档）。
    battle_cleared = final.battle is None and final.battle_ctx is None
    text = play.serialize(final, tables)
    save_data = decode(text)
    roundtrip = encode(save_data) == text and encode(decode(text)) == text
    rejected = []
    for key in FORBIDDEN_KEYS:
        poisoned = json.loads(text)
        poisoned[key] = []
        try:
            decode(json.dumps(poisoned, ensure_ascii=False))
        except ValueError:
            rejected.append(key)
    restored = play.restore(text, tables)
    restored_clean = (restored.battle is None and restored.battle_ctx is None
                      and restored.captures == 0)

    # 帧纯投影：战斗中同参两次相等、combat 投影字段齐备；巡图帧不带战斗面板。
    battle_frame_session = play.apply(
        play.apply(fresh, "encounter", tables), "attack", tables)
    bf1 = frame_of(battle_frame_session, tables)
    bf2 = frame_of(battle_frame_session, tables)
    frame_pure = bf1 == bf2
    combat_projected = (bf1.combat and len(bf1.combat_lines) >= 3
                        and bool(bf1.combat_hint))
    walk_frame = frame_of(fresh, tables)
    walk_clean = not walk_frame.combat and walk_frame.combat_lines == ()

    tables_unchanged = tables == before
    try:
        schema.verify_manifest(ROOT)
        manifest_ok = True
    except (schema.SchemaError, OSError, ValueError):
        manifest_ok = False
    golden_ok = gate.check_golden_snapshot(ROOT) == []
    gate_ok = gate.run(ROOT) == []

    complete = bool(
        bool(actions) and actions[0] == "encounter"
        and captured >= 1 and atlas_has_wild and battle_cleared
        and deterministic and seed_matters
        and no_battle_rejected and world_rejected and repeat_rejected
        and roundtrip and len(rejected) == len(FORBIDDEN_KEYS)
        and restored_clean
        and frame_pure and combat_projected and walk_clean
        and len(KEY_ACTIONS) == 13 and len(COMBAT_KEY_ACTIONS) >= 6
        and tables_unchanged and manifest_ok and golden_ok and gate_ok
        and deps.dependency_facts()["headless_available"]
    )
    return {
        "world_seed": str(world_seed),
        "battle": {
            "actions": list(actions),
            "action_count": len(actions),
            "last_message": outcome_msg,
            "captures": captured,
            "wild_id": wild,
            "atlas_has_wild": atlas_has_wild,
            "atlas_entries": len(final.state.atlas.entries),
            "battle_cleared": battle_cleared,
        },
        "counter_proof": {
            "no_battle_action_rejected": no_battle_rejected,
            "world_action_in_battle_rejected": world_rejected,
            "repeat_encounter_rejected": repeat_rejected,
        },
        "determinism": {
            "same_seed_identical": deterministic,
            "different_seed_differs": seed_matters,
            "other_wild": other_wild,
        },
        "save": {
            "roundtrip": roundtrip,
            "bytes": len(text.encode("utf-8")),
            "keys": list(SAVE_KEYS),
            "rejected_generated_keys": rejected,
            "restored_battle_clean": restored_clean,
        },
        "view": {
            "frame_pure": frame_pure,
            "combat_projected": combat_projected,
            "walk_frame_clean": walk_clean,
            "combat_lines": list(bf1.combat_lines),
            "key_actions": len(KEY_ACTIONS),
            "combat_key_actions": len(COMBAT_KEY_ACTIONS),
        },
        "dependency": deps.dependency_facts(),
        "gate": {"ok": gate_ok, "golden_snapshot_ok": golden_ok,
                 "manifest_ok": manifest_ok, "tables_unchanged": tables_unchanged},
        "complete": complete,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    seed = args[0] if args else DEFAULT_SEED
    tables = schema.load_all(ROOT)
    report = run(tables, seed)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
