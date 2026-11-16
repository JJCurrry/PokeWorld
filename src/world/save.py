"""G4 存档：不变量 #6 的落地证据（只存 world_seed + flags + 队伍状态）。

设计依据 `docs/adr/ADR-004-图鉴成长事件脚本与存档.md`：
- `SaveData` 只有三个字段；**区块生成结果禁止入库**，由 world_seed 重建。
- `encode` 用 `sort_keys=True` + 固定分隔符 + 排序去重 flags，保证确定性字节；
  `decode` 走字段白名单 + flag 前缀白名单 + 逐字段类型 / 越界校验，
  显式抛 `SchemaError`（禁 assert，`python -O` 下同样生效）。
- 存档是**投影不是快照**：progress / atlas 的语义标记压成排序去重的 flags，
  tick / log / blocked 是运行时过程量，不持久化（限制见 ADR-004 §后果）。

本模块无 I/O（不读写文件，只做字符串编解码）、不读时钟、无裸随机。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..schema import SchemaError, must
from .evolution import EVOLVE_LEVELS, IV_SPAN, MAX_LEVEL

SAVE_KEYS = ("world_seed", "flags", "party")
FLAG_PREFIXES = ("ability:", "atlas:", "milestone:", "region:", "script:")
# 生成结果键：出现任何一个都直接拒绝，并给出可读原因（不变量 #6）。
FORBIDDEN_KEYS = ("tiles", "terrain_counts", "encounter_weights",
                  "chunks", "surveys", "events", "terrain_totals")
MAX_FLAG_LENGTH = 120


@dataclass(frozen=True)
class SaveData:
    """可持久化的三类信息；队伍行是 `(cid, level, stage, iv)` 四元组。"""

    world_seed: str
    flags: tuple[str, ...]
    party: tuple[tuple[str, int, int, int], ...]


def encode(save: SaveData) -> str:
    """确定性字节：同一存档两次调用逐字节一致。"""
    must(isinstance(save, SaveData), "encode 只接受 SaveData")
    must(isinstance(save.world_seed, str) and bool(save.world_seed),
         "world_seed 必须是非空字符串")
    must(isinstance(save.flags, (tuple, list)), "flags 必须是不可变序列")
    must(isinstance(save.party, (tuple, list)), "party 必须是不可变序列")
    payload = {
        "world_seed": save.world_seed,
        "flags": sorted(set(save.flags)),
        "party": [list(row) for row in save.party],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _decode_flags(raw: object) -> tuple[str, ...]:
    must(isinstance(raw, list), "flags 必须是列表")
    flags = []
    for item in raw:
        must(isinstance(item, str), f"flag 必须是字符串：{item!r}")
        must(any(item.startswith(prefix) for prefix in FLAG_PREFIXES),
             f"flag 前缀不在白名单：{item!r}")
        must(0 < len(item) <= MAX_FLAG_LENGTH and "\n" not in item,
             f"flag 长度或内容非法：{item!r}")
        flags.append(item)
    return tuple(sorted(set(flags)))


def _decode_party(raw: object) -> tuple[tuple[str, int, int, int], ...]:
    must(isinstance(raw, list), "party 必须是列表")
    max_stage = len(EVOLVE_LEVELS)
    rows = []
    for item in raw:
        must(isinstance(item, list) and len(item) == 4,
             f"队伍成员必须是四元素列表：{item!r}")
        cid, level, stage, iv = item
        must(isinstance(cid, str) and bool(cid), f"队伍 cid 非法：{cid!r}")
        must(type(level) is int and 1 <= level <= MAX_LEVEL,
             f"队伍等级越界：{level!r}")
        must(type(stage) is int and 0 <= stage <= max_stage,
             f"形态阶段越界：{stage!r}")
        must(type(iv) is int and 0 <= iv < IV_SPAN, f"个体值越界：{iv!r}")
        rows.append((cid, level, stage, iv))
    return tuple(rows)


def decode(text: str) -> SaveData:
    """白名单反序列化；任何多余键 / 生成结果键 / 畸形值都显式拒绝。"""
    must(isinstance(text, str), "存档必须是字符串")
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"存档不是合法 JSON：{exc}") from exc
    must(isinstance(payload, dict), "存档顶层必须是对象")
    for key in FORBIDDEN_KEYS:
        must(key not in payload,
             f"存档禁止写入生成结果键「{key}」；生成结果须由 world_seed 重建（不变量 #6）")
    missing = tuple(key for key in SAVE_KEYS if key not in payload)
    extra = tuple(sorted(key for key in payload if key not in SAVE_KEYS))
    must(not missing and not extra,
         f"存档字段必须恰好为 {SAVE_KEYS}；缺 {missing}，多 {extra}")
    seed = payload["world_seed"]
    must(isinstance(seed, str) and bool(seed), "world_seed 必须是非空字符串")
    return SaveData(seed, _decode_flags(payload["flags"]),
                    _decode_party(payload["party"]))
