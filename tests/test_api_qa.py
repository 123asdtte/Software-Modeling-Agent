"""/v1/qa 端点测试（mock 掉 RAG 链路，不依赖真实索引与模型）。"""

import asyncio

from fastapi.testclient import TestClient

import app.main as main_module
from app.config.settings import get_settings
from app.main import app

client = TestClient(app)


def _patch_chain(monkeypatch, func) -> None:
    """把端点引用的 build_qa_answer 替换为给定函数。"""
    monkeypatch.setattr(main_module, "build_qa_answer", func)


def test_qa_ok(monkeypatch):
    """正常链路返回 200 与回答 + 来源。"""

    async def fake(question, top_k=None):
        return {"reply": "四段式回答", "sources": ["教材·智能问答｜任务二 用例图"]}

    _patch_chain(monkeypatch, fake)
    resp = client.post("/v1/qa", json={"question": "什么是用例图？"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "四段式回答"
    assert body["sources"] == ["教材·智能问答｜任务二 用例图"]


def test_qa_503_when_index_missing(monkeypatch):
    """索引未构建（FileNotFoundError）应返回 503。"""

    async def fake(question, top_k=None):
        raise FileNotFoundError("知识库索引不存在，请先执行：python -m app.knowledge_base.build")

    _patch_chain(monkeypatch, fake)
    resp = client.post("/v1/qa", json={"question": "什么是用例图？"})
    assert resp.status_code == 503
    assert "python -m app.knowledge_base.build" in resp.json()["detail"]


def test_qa_504_on_timeout(monkeypatch):
    """超过整体墙钟应返回 504（快速失败，不挂死请求）。"""

    async def slow(question, top_k=None):
        await asyncio.sleep(5)
        return {"reply": "不会返回", "sources": []}

    monkeypatch.setattr(get_settings(), "qa_timeout", 0.05)
    _patch_chain(monkeypatch, slow)
    resp = client.post("/v1/qa", json={"question": "什么是用例图？"})
    assert resp.status_code == 504
    assert "超时" in resp.json()["detail"]


def test_qa_502_on_unexpected_error(monkeypatch):
    """其他异常统一转 502，不暴露堆栈。"""

    async def boom(question, top_k=None):
        raise ValueError("模型调用失败：余额不足")

    _patch_chain(monkeypatch, boom)
    resp = client.post("/v1/qa", json={"question": "什么是用例图？"})
    assert resp.status_code == 502


def test_qa_rejects_empty_question():
    """空问题应被请求校验拦截（422），不进入链路。"""
    resp = client.post("/v1/qa", json={"question": ""})
    assert resp.status_code == 422


def test_qa_respects_concurrency_limit(monkeypatch):
    """并发上限应生效：超出 qa_max_concurrency 的请求被闸门串行化。"""
    import httpx

    monkeypatch.setattr(get_settings(), "qa_max_concurrency", 1)
    # 重建端点模块级信号量（模块级 Semaphore 在 import 时创建）
    monkeypatch.setattr(main_module, "_qa_semaphore", asyncio.Semaphore(1))

    active = 0
    peak = 0

    async def tracked(question, top_k=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {"reply": "ok", "sources": []}

    _patch_chain(monkeypatch, tracked)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            responses = await asyncio.gather(*[ac.post("/v1/qa", json={"question": "并发测试"}) for _ in range(3)])
        assert all(r.status_code == 200 for r in responses)

    asyncio.run(run())
    assert peak == 1  # 信号量把并发压到 1
