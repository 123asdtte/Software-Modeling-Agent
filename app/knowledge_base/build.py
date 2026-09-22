"""知识库构建脚本：教材源稿 → 分块 → LightRAG 索引（持久化）。

用法：
    python -m app.knowledge_base.build          # 全量重建
    python -m app.knowledge_base.build --force  # 强制重建（清空旧索引）

首批入库：`docs/02-需求文档PRD/_教材源稿提取/` 下的 4 份教材源稿。
"""

import argparse
import asyncio
import logging
import shutil
import sys
import time
from pathlib import Path

from lightrag import LightRAG, QueryParam

from app.knowledge_base.embeddings import get_embedding_func
from app.models.llm import get_llm
from app.tools.document_reader import DocumentChunk, parse_markdown_dir

logger = logging.getLogger(__name__)

# 教材源稿目录（文档体系已随仓库迁移到 docs/ 下；源稿内容在 .gitignore 中排除，
# 仅保留在本地，换机器时需手工补齐该目录）
DEFAULT_SOURCE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "02-需求文档PRD"
    / "_教材源稿提取"
)
# 索引持久化目录
INDEX_DIR = Path(__file__).resolve().parent / "lightrag_index"

SOURCE_PREFIX = "教材·"
# 块文本前缀，用于检索返回时定位引用
REF_PREFIX_TEMPLATE = "【来源：{source}｜{heading}】\n"


def build_llm_model_func():
    """LightRAG 内部 LLM 函数（实体抽取、关键词提取等），走 DeepSeek 工厂。

    - LightRAG 1.5 要求 llm_model_func 为 async 函数（会被并发包装层 await），
      且 role wrapper 会注入 hashing_kv 等参数，签名用 **kwargs 吸收。
    - 熔断降级：LLM 调用失败（如账户余额不足）时返回空实体抽取 JSON，
      保证纯向量索引仍可建成；充值后加 --force 重建即可补齐图谱。
    """

    llm = get_llm()
    degraded = {"n_calls": 0}

    async def _func(prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append(("system", system_prompt))
        messages.append(("user", prompt))
        try:
            reply = await asyncio.to_thread(llm.invoke, messages)
            return str(reply.content)
        except Exception as exc:  # noqa: BLE001
            degraded["n_calls"] += 1
            logger.warning(
                "LLM 调用失败（第 %d 次）：%s；降级返回空实体抽取结果",
                degraded["n_calls"],
                exc,
            )
            return '{"entities": [], "relationships": []}'

    return _func


def _chunks_with_ref(chunks: list[DocumentChunk]) -> list[str]:
    """给每个块加【来源：…】前缀，便于检索后提取引用标注。"""
    texts = []
    for chunk in chunks:
        prefix = REF_PREFIX_TEMPLATE.format(source=chunk.source, heading=chunk.heading)
        texts.append(prefix + chunk.text)
    return texts


def _build_kb_sync(source_dir: str | Path | None = None, force: bool = False) -> int:
    """构建知识库并持久化索引（LightRAG 1.5 需先异步初始化 storages）。

    Args:
        source_dir: 教材源稿目录；缺省用默认路径。
        force: 是否清空旧索引重建。

    Returns:
        int: 入库块数。
    """
    src_dir = Path(source_dir) if source_dir else DEFAULT_SOURCE_DIR
    if not src_dir.is_dir():
        logger.error("教材源稿目录不存在：%s", src_dir)
        raise FileNotFoundError(f"教材源稿目录不存在：{src_dir}")

    if INDEX_DIR.exists() and not force:
        logger.info("索引已存在（%s），跳过构建；如需重建加 --force", INDEX_DIR)
        return 0
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    chunks = parse_markdown_dir(src_dir, source_prefix=SOURCE_PREFIX)
    if not chunks:
        raise ValueError("教材源稿目录下未解析出任何文本块")

    texts = _chunks_with_ref(chunks)
    total = len(texts)

    async def _run() -> int:
        rag = LightRAG(
            working_dir=str(INDEX_DIR),
            embedding_func=get_embedding_func(),
            llm_model_func=build_llm_model_func(),
            chunk_token_size=1200,
            chunk_overlap_token_size=120,
            entity_extraction_use_json=True,
        )
        await rag.initialize_storages()

        logger.info("开始入库 %d 块（来源：%s）", total, src_dir.name)
        for i, text in enumerate(texts, start=1):
            await rag.ainsert(text)
            if i % 5 == 0 or i == total:
                logger.info("进度：%d/%d", i, total)

        # 构建完成后写一个探针查询验证索引可用（naive 纯向量检索，离线可用）
        probe = await rag.aquery(
            "什么是用例图",
            param=QueryParam(mode="naive", only_need_context=True, top_k=3),
        )
        logger.info("探针查询返回 %d 字符，索引可用", len(probe or ""))
        return total

    return asyncio.run(_run())


def build_kb(source_dir: str | Path | None = None, force: bool = False) -> int:
    """构建知识库（兼容同步入口，见 _build_kb_sync）。"""
    return _build_kb_sync(source_dir, force)


def main() -> None:
    """命令行入口。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="构建 v13 教材知识库")
    parser.add_argument("--source", type=str, default=None, help="教材源稿目录")
    parser.add_argument("--force", action="store_true", help="清空旧索引重建")
    args = parser.parse_args()

    start = time.time()
    try:
        count = build_kb(args.source, force=args.force)
    except Exception as exc:  # noqa: BLE001
        logger.error("构建失败：%s", exc)
        sys.exit(1)
    if count:
        logger.info("构建完成：入库 %d 块，耗时 %.1f 秒", count, time.time() - start)


if __name__ == "__main__":
    main()
