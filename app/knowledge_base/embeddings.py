"""Embedding 适配层：fastembed（ONNX，无需 torch/GPU）。

模型：BAAI/bge-small-zh-v1.5（轻量中文向量模型，512 维，~100MB）。
如需更强效果可换 BAAI/bge-m3（需更大内存），修改 get_embedding_model 即可。

LightRAG 1.5 要求 embedding_func 为 EmbeddingFunc 包装对象（带 .func 属性），
且 .func 必须是 async 函数（会被并发包装层 await）。
"""

import asyncio
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding
from lightrag.utils import EmbeddingFunc

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIM = 512  # bge-small-zh-v1.5 维度
EMBEDDING_MAX_TOKENS = 8192


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    """返回全局单例 Embedding 模型（首次调用会下载模型文件）。"""
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def _embed_sync(texts: list[str]) -> np.ndarray:
    """同步实现：把文本列表转成单个 2D 向量数组（n_texts × 512）。

    LightRAG 的 EmbeddingFunc 契约要求 func 返回一个 numpy 数组
    （内部用 .size 校验维度与数量），不能返回 list。
    """
    model = get_embedding_model()
    return np.vstack(list(model.embed(list(texts))))


async def embed_texts(texts: list[str]) -> np.ndarray:
    """把文本列表转成 2D 向量数组（async，供 LightRAG EmbeddingFunc 使用）。"""
    return await asyncio.to_thread(_embed_sync, texts)


@lru_cache(maxsize=1)
def get_embedding_func() -> EmbeddingFunc:
    """返回 LightRAG 兼容的 EmbeddingFunc 包装对象。"""
    return EmbeddingFunc(
        embedding_dim=EMBEDDING_DIM,
        func=embed_texts,
        max_token_size=EMBEDDING_MAX_TOKENS,
        model_name=EMBEDDING_MODEL,
    )
