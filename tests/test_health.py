"""/health 健康检查接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    """健康检查应返回 200 与就绪状态。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "AI-Education-Agent"
    assert "model" in body


def test_health_api_key_flag() -> None:
    """健康检查应暴露 api_key 是否已配置（不返回密钥本身）。"""
    resp = client.get("/health")
    body = resp.json()
    assert "api_key_configured" in body
    assert isinstance(body["api_key_configured"], bool)
    assert "deepseek_api_key" not in body
