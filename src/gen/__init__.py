"""血肉层：由世界种子确定性生成区块（ADR-001 B 层）。

禁止 import 渲染层、禁止模块级可变状态；对外只暴露纯函数入口。
"""
from .chunk import CHUNK_SIZE, encode_tiles, generate_chunk
from .rng import Stream, rng

__all__ = ("Stream", "rng", "CHUNK_SIZE", "encode_tiles", "generate_chunk")
