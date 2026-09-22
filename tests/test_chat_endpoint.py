"""/v1/chat 端点行为测试（mock LLM，不耗 token）。

工程基线验收要求：/health、/v1/chat、/v1/qa 行为不变。
/health、/v1/qa 已有测试；此处锁定 /v1/chat 的成功与失败路径。
"""

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app

client = TestClient(app)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def invoke(self, messages):
        return _FakeMessage("收到：你好")


def test_chat_ok(monkeypatch):
    """正常路径：返回 reply 与 model 字段。"""
    monkeypatch.setattr(main_module, "get_llm", lambda: _FakeLLM())
    resp = client.post("/v1/chat", json={"message": "你好"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "收到：你好"
    assert body["model"]  # model 名随配置返回


def test_chat_rejects_empty_message():
    """空消息应被请求校验拦截（422），不进入模型调用。"""
    resp = client.post("/v1/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_502_on_model_error(monkeypatch):
    """模型异常统一 502，不暴露堆栈。"""

    class _Boom:
        def invoke(self, messages):
            raise RuntimeError("上游模型错误")

    monkeypatch.setattr(main_module, "get_llm", lambda: _Boom())
    resp = client.post("/v1/chat", json={"message": "你好"})
    assert resp.status_code == 502
