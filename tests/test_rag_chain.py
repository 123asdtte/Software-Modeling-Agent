"""rag_chain 纯函数与空回答兜底测试（不初始化 LightRAG）。"""

import asyncio

from app.chains.rag_chain import build_qa_answer, extract_sources, truncate_context

CONTEXT = """## Document Chunks
-----Chunk 1-----
【来源：教材·智能问答｜任务二 用例图】
用例图内容。
-----Chunk 2-----
【来源：教材·智能问答｜任务二 用例图】
重复来源内容。
-----Chunk 3-----
【来源：教材·智能问答｜任务六 活动图】
活动图内容。
"""


def test_extract_sources_dedup_keeps_order():
    """来源提取应去重且保持首次出现顺序。"""
    sources = extract_sources(CONTEXT)
    assert sources == [
        "教材·智能问答｜任务二 用例图",
        "教材·智能问答｜任务六 活动图",
    ]


def test_extract_sources_empty():
    """无来源标注时返回空列表。"""
    assert extract_sources("没有任何标注的文本") == []


def test_truncate_noop_within_limit():
    """未超限时原样返回。"""
    assert truncate_context(CONTEXT, 10000) == CONTEXT


def test_truncate_cut_at_boundary():
    """超限时按块边界截断，且不超过预算。"""
    truncated = truncate_context(CONTEXT, 120)
    assert len(truncated) <= 120
    # 保留的是头部完整块（Chunk 1 的来源标注仍在）
    assert "【来源：教材·智能问答｜任务二 用例图】" in truncated
    # 尾部块被丢弃
    assert "活动图内容" not in truncated


def test_truncate_extreme_small_budget():
    """预算小于首个块时也要保证不超限。"""
    truncated = truncate_context(CONTEXT, 10)
    assert len(truncated) <= 10


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """按预设顺序返回 content 的假 LLM。"""

    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return _FakeMessage(self.contents[min(self.calls - 1, len(self.contents) - 1)])


def _patch(monkeypatch, llm: _FakeLLM, context: str = CONTEXT) -> None:
    import app.chains.rag_chain as rc

    async def fake_retrieve(question, top_k=None):
        return context

    monkeypatch.setattr(rc, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(rc, "get_llm", lambda: llm)


def test_build_qa_answer_retries_on_empty_content(monkeypatch):
    """首次空 content（reasoning 吃空预算）应重试并成功。"""
    llm = _FakeLLM(["", "正常回答"])
    _patch(monkeypatch, llm)
    result = asyncio.run(build_qa_answer("什么是用例图？"))
    assert llm.calls == 2
    assert result["reply"] == "正常回答"
    assert result["sources"]  # 来源来自检索上下文


def test_build_qa_answer_raises_when_all_empty(monkeypatch):
    """重试后仍为空应抛 RuntimeError（端点层转 502）。"""
    llm = _FakeLLM(["", ""])
    _patch(monkeypatch, llm)
    try:
        asyncio.run(build_qa_answer("什么是用例图？"))
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert llm.calls == 2  # 默认重试 1 次，共调用 2 次
