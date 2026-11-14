"""确定性随机源（G1 · 血肉层 / 不变量 #1、#5）。

所有生成用随机必须来自 rng(world_seed, region_id, cx, cy)：同一四元组
在任意进程、任意平台都产生逐格一致的序列。实现用 hashlib.blake2b 对
「种子元组 + 流名 + 序号」派生字节，避开 random 模块与 Python 内置 hash
的进程随机化，也不依赖时钟。

本模块没有模块级可变状态。Stream 是每次调用新建的局部对象，不共享、
不逃逸；区块生成函数因此保持纯函数性质。
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence

DOMAIN = b"PokeWorld/G1"  # blake2b 的 person 参数上限 16 字节
_U64 = 1 << 64


def _block(digest: bytes, index: int) -> int:
    """由「绑定摘要 + 序号」派生一个 64 位无符号整数，纯函数。"""
    payload = digest + index.to_bytes(8, "big")
    return int.from_bytes(
        hashlib.blake2b(payload, digest_size=8, person=DOMAIN).digest(), "big")


class Stream:
    """绑定到单一四元组的确定性序列；只在本次生成内部推进游标。"""

    __slots__ = ("_digest", "_index")

    def __init__(self, digest: bytes) -> None:
        self._digest = digest
        self._index = 0

    def _next(self) -> int:
        value = _block(self._digest, self._index)
        self._index += 1
        return value

    def u64(self) -> int:
        return self._next()

    def unit(self) -> float:
        """[0, 1) 区间的浮点；分母固定为 2 的 64 次方，跨平台一致。"""
        return self._next() / _U64

    def below(self, upper: int) -> int:
        """[0, upper) 整数。64 位块对小上界的模偏差在 2 的 -64 次方量级。"""
        if upper <= 0:
            raise ValueError("上界必须为正整数")
        return self._next() % upper

    def pick(self, weights: Sequence[float]) -> int:
        """按非负权重返回索引；权重总和必须为正。"""
        total = sum(weights)
        if total <= 0:
            raise ValueError("权重总和必须为正")
        for w in weights:
            if w < 0:
                raise ValueError("权重不得为负")
        target = self.unit() * total
        acc = 0.0
        for index, weight in enumerate(weights):
            acc += weight
            if target < acc:
                return index
        return len(weights) - 1


def rng(world_seed: str | int, region_id: str, cx: int, cy: int,
        stream: str = "chunk") -> Stream:
    """把四元组（可选流名）绑定成一个确定性随机流。

    stream 用于隔离同一坐标下不同用途的序列，使后续新增用途时
    不会改变既有用途的逐格结果。
    """
    payload = f"{world_seed}|{region_id}|{cx}|{cy}|{stream}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=32, person=DOMAIN).digest()
    return Stream(digest)
