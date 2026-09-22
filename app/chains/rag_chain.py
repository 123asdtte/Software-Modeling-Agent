"""RAG 检索链：LightRAG 检索 → 四段式 QA 生成 → 来源标注。

职责划分：
- LightRAG 只负责检索（aquery + only_need_context 返回教材上下文，不生成回答）；
- QA 回答由自研 qa_prompt + DeepSeek 生成，保证四段式教学格式与引用标注可控。
- LightRAG 1.5 为异步 API，本模块提供 async 检索与问答；FastAPI 端点 async 调用。
"""

import asyncio
import logging
import re
from functools import lru_cache

from lightrag import LightRAG, QueryParam

from app.config.settings import get_settings
from app.knowledge_base.build import INDEX_DIR, build_llm_model_func
from app.knowledge_base.embeddings import get_embedding_func
from app.models.llm import get_llm
from app.prompts.qa_prompt import build_qa_prompt

logger = logging.getLogger(__name__)

# 检索返回文本中的来源标注：【来源：xxx｜yyy】
_SOURCE_RE = re.compile(r"【来源：([^｜]+)｜([^】]+)】")

# LightRAG 上下文的块边界（-----Chunk N----- / 段落标题行），用于按块截断
_SECTION_RE = re.compile(r"^(-----Chunk .+-----|# .+|## .+)$", re.MULTILINE)

_ready_lock = asyncio.Lock()
_rag_ready = False


@lru_cache(maxsize=1)
def get_rag() -> LightRAG:
    """加载已构建的知识库索引（未构建时抛错提示）。"""
    if not INDEX_DIR.is_dir():
        raise FileNotFoundError(
            "知识库索引不存在，请先执行：python -m app.knowledge_base.build"
        )
    return LightRAG(
        working_dir=str(INDEX_DIR),
        embedding_func=get_embedding_func(),
        llm_model_func=build_llm_model_func(),
        chunk_token_size=1200,
        chunk_overlap_token_size=120,
        entity_extraction_use_json=True,
    )


async def _ensure_ready() -> LightRAG:
    """确保实例已初始化（加载磁盘持久化索引），幂等、并发安全。"""
    global _rag_ready
    rag = get_rag()
    if not _rag_ready:
        async with _ready_lock:
            if not _rag_ready:
                await rag.initialize_storages()
                _rag_ready = True
    return rag


async def retrieve_context(question: str, top_k: int | None = None) -> str:
    """检索教材上下文（仅返回上下文，不生成回答）。

    使用 hybrid 三路召回（关键词 + 知识图谱 + 向量），图谱已由实体抽取补齐；
    若图谱缺失可临时切 mode="naive" 纯向量兜底。

    检索预算全部走 settings（LightRAG 默认 chunk_top_k=20 / max_total_tokens=30000，
    会返回 2 万字符上下文塞爆 prompt）；enable_rerank=False 消除未配置重排模型的告警。

    Args:
        question: 学生问题。
        top_k: 召回块数；缺省用 settings.qa_chunk_top_k。

    Returns:
        str: 带【来源】标注的教材上下文；无命中时返回空串。
    """
    s = get_settings()
    param = QueryParam(
        mode="hybrid",
        only_need_context=True,
        top_k=top_k or s.qa_chunk_top_k,
        chunk_top_k=top_k or s.qa_chunk_top_k,
        max_total_tokens=s.qa_max_total_tokens,
        max_entity_tokens=s.qa_max_entity_tokens,
        max_relation_tokens=s.qa_max_relation_tokens,
        enable_rerank=False,
    )
    return await (await _ensure_ready()).aquery(question, param=param) or ""


def extract_sources(context: str) -> list[str]:
    """从检索上下文中提取去重的来源标注。

    Args:
        context: 带【来源：…】标注的检索上下文。

    Returns:
        list[str]: 来源列表（如"教材·智能问答｜任务二 使用用例图进行需求分析建模"）。
    """
    return list(dict.fromkeys(f"{s}｜{h}" for s, h in _SOURCE_RE.findall(context)))


def truncate_context(context: str, max_chars: int) -> str:
    """按块边界截断上下文（应用层兜底，保头丢尾）。

    LightRAG 的 max_total_tokens 已在检索层控制预算；此函数防止
    极端情况（如 token 估算偏差）导致超长上下文进入 prompt。

    Args:
        context: 检索返回的上下文。
        max_chars: 最大字符数。

    Returns:
        str: 不超过 max_chars 的上下文；按块边界（Chunk/标题行）对齐截断。
    """
    if len(context) <= max_chars:
        return context
    # 找出所有块边界位置，保留完整块直到超出预算
    boundaries = [m.start() for m in _SECTION_RE.finditer(context)]
    cut = max_chars
    for pos in boundaries:
        if 0 < pos <= max_chars:
            cut = pos
        elif pos > max_chars:
            break
    logger.warning("上下文超长（%d 字符），截断至 %d 字符", len(context), cut)
    return context[:cut].rstrip()


async def build_qa_answer(question: str, top_k: int | None = None) -> dict:
    """完整 QA 链路（async）：检索 → 四段式生成 → 来源标注。

    Args:
        question: 学生问题。
        top_k: 召回块数；缺省用 settings.qa_chunk_top_k。

    Returns:
        dict: {"reply": 回答, "sources": 来源列表}。

    Raises:
        RuntimeError: 重试后仍拿到空回答（推理模型 content 被 reasoning 吃空时兜底）。
    """
    s = get_settings()
    context = await retrieve_context(question, top_k=top_k)
    context = truncate_context(context, s.qa_context_max_chars)
    sources = extract_sources(context)
    messages = build_qa_prompt(question, context)

    reply = ""
    # deepseek-flash 是推理模型：极端情况下 reasoning 消耗掉全部 max_tokens，
    # content 返回空串；此处重试一次，仍为空则报错走 502 而非返回空回答
    for attempt in range(1 + s.qa_answer_retries):
        reply = str(get_llm().invoke(messages).content)
        if reply.strip():
            break
        logger.warning("QA 第 %d 次生成返回空 content，重试", attempt + 1)
    if not reply.strip():
        raise RuntimeError("模型返回空回答（reasoning 耗尽 max_tokens），已重试仍失败")
    return {"reply": reply, "sources": sources}
