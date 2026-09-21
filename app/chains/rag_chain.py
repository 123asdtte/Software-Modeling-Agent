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

from app.knowledge_base.build import INDEX_DIR, build_llm_model_func
from app.knowledge_base.embeddings import get_embedding_func
from app.models.llm import get_llm
from app.prompts.qa_prompt import build_qa_prompt

logger = logging.getLogger(__name__)

# 检索返回文本中的来源标注：【来源：xxx｜yyy】
_SOURCE_RE = re.compile(r"【来源：([^｜]+)｜([^】]+)】")

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


async def retrieve_context(question: str, top_k: int = 5) -> str:
    """检索教材上下文（仅返回上下文，不生成回答）。

    使用 naive 纯向量检索：离线稳定、不依赖图谱与关键词 LLM；
    等知识库图谱补齐后可切 mode="hybrid" 获得更强召回。

    Args:
        question: 学生问题。
        top_k: 召回块数。

    Returns:
        str: 带【来源】标注的教材上下文；无命中时返回空串。
    """
    param = QueryParam(mode="naive", only_need_context=True, top_k=top_k)
    return await (await _ensure_ready()).aquery(question, param=param) or ""


def extract_sources(context: str) -> list[str]:
    """从检索上下文中提取去重的来源标注。

    Args:
        context: 带【来源：…】标注的检索上下文。

    Returns:
        list[str]: 来源列表（如"教材·智能问答｜任务二 使用用例图进行需求分析建模"）。
    """
    return list(dict.fromkeys(f"{s}｜{h}" for s, h in _SOURCE_RE.findall(context)))


async def build_qa_answer(question: str, top_k: int = 5) -> dict:
    """完整 QA 链路（async）：检索 → 四段式生成 → 来源标注。

    Args:
        question: 学生问题。
        top_k: 召回块数。

    Returns:
        dict: {"reply": 回答, "sources": 来源列表}。
    """
    context = await retrieve_context(question, top_k=top_k)
    sources = extract_sources(context)
    messages = build_qa_prompt(question, context)
    reply = str(get_llm().invoke(messages).content)
    return {"reply": reply, "sources": sources}
