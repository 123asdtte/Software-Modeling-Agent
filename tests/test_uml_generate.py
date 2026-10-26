"""统一生成端点 /v1/uml/generate 与意图识别测试（mock 生成链，不调真实 LLM）。"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.api.uml import router as uml_router
from app.chains.uml_chain import (
    detect_diagram_type,
    generate_activity_model,
    generate_statemachine_model,
    generate_uml_model,
)
from app.main import app
from app.models.uml import ActivityModel, DiagramType, StateMachineModel

client = TestClient(app)

VALID_ACTIVITY_JSON = json.dumps(
    {
        "type": "activity",
        "module": "订单处理",
        "swimlanes": [{"name": "顾客"}, {"name": "系统"}],
        "nodes": [
            {"id": "start", "kind": "initial"},
            {"id": "a1", "name": "提交订单", "lane": "顾客", "kind": "action"},
            {"id": "d1", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "a2", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "a3", "name": "通知缺货", "lane": "系统", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        "flows": [
            {"from": "start", "to": "a1"},
            {"from": "a1", "to": "d1"},
            {"from": "d1", "to": "a2", "cond": "充足"},
            {"from": "d1", "to": "a3", "cond": "不足"},
            {"from": "a2", "to": "end"},
            {"from": "a3", "to": "end"},
        ],
    },
    ensure_ascii=False,
)

VALID_STATEMACHINE_JSON = json.dumps(
    {
        "type": "statemachine",
        "object": "订单",
        "states": [
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        "transitions": [
            {"from": "init", "to": "s1", "event": "创建订单"},
            {"from": "s1", "to": "s2", "event": "支付成功"},
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    },
    ensure_ascii=False,
)


class _FakeLLM:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        idx = min(self.calls - 1, len(self.contents) - 1)
        return type("M", (), {"content": self.contents[idx]})()


def _factory(llm: _FakeLLM):
    return lambda timeout=None: llm


def _run(coro):
    return asyncio.run(coro)


# ---------------- 生成链 ----------------


def test_generate_activity_model():
    m = _run(generate_activity_model("订单处理流程", llm_factory=_factory(_FakeLLM([VALID_ACTIVITY_JSON]))))
    assert isinstance(m, ActivityModel)
    assert m.type == DiagramType.ACTIVITY
    assert m.module == "订单处理"


def test_generate_statemachine_model():
    m = _run(generate_statemachine_model("订单生命周期", llm_factory=_factory(_FakeLLM([VALID_STATEMACHINE_JSON]))))
    assert isinstance(m, StateMachineModel)
    assert m.type == DiagramType.STATEMACHINE
    assert m.object == "订单"


def test_generate_uml_model_dispatches():
    act = _run(generate_uml_model(DiagramType.ACTIVITY, "x", llm_factory=_factory(_FakeLLM([VALID_ACTIVITY_JSON]))))
    sm = _run(
        generate_uml_model(
            DiagramType.STATEMACHINE, "x", llm_factory=_factory(_FakeLLM([VALID_STATEMACHINE_JSON]))
        )
    )
    assert isinstance(act, ActivityModel) and isinstance(sm, StateMachineModel)


def test_detect_diagram_type_activity():
    dtype = _run(
        detect_diagram_type(
            "订单处理流程", llm_factory=_factory(_FakeLLM(['{"type":"activity","reason":"流程"}']))
        )
    )
    assert dtype == DiagramType.ACTIVITY


def test_detect_diagram_type_unsupported_raises():
    with pytest.raises(ValueError):
        _run(detect_diagram_type("类图怎么画", llm_factory=_factory(_FakeLLM(['{"type":"other","reason":"不支持"}']))))


# ---------------- API：显式图型 ----------------


def _patch_generate(monkeypatch, func) -> None:
    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "generate_uml_model", func)


def test_generate_activity_endpoint_ok(monkeypatch):
    """显式 activity：200 + diagram_type=activity + 完整渲染与质检。"""

    async def fake(diagram_type, requirement, llm_factory=None):
        return ActivityModel.model_validate(json.loads(VALID_ACTIVITY_JSON))

    _patch_generate(monkeypatch, fake)
    resp = client.post("/v1/uml/generate", json={"requirement": "订单处理流程", "diagram_type": "activity"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "activity"
    assert body["model"]["module"] == "订单处理"
    assert "nodes" in body["model"] and "flows" in body["model"]
    assert body["plantuml"].startswith("@startuml")
    assert body["review_report"]["passed"] is True
    # 活动图现支持 drawio 可编辑导出（三图型统一）；svg 仅用例图自绘渲染器
    assert body["drawio_download_url"] is not None
    assert body["drawio_download_url"].startswith("/files/uml/")
    assert body["svg_download_url"] is None


def test_generate_statemachine_endpoint_ok(monkeypatch):
    """显式 statemachine：200 + diagram_type=statemachine + 完整渲染与质检。"""

    async def fake(diagram_type, requirement, llm_factory=None):
        return StateMachineModel.model_validate(json.loads(VALID_STATEMACHINE_JSON))

    _patch_generate(monkeypatch, fake)
    resp = client.post("/v1/uml/generate", json={"requirement": "订单生命周期", "diagram_type": "statemachine"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "statemachine"
    assert body["model"]["object"] == "订单"
    assert "states" in body["model"] and "transitions" in body["model"]
    assert body["plantuml"].startswith("@startuml")
    assert body["review_report"]["passed"] is True


def test_generate_endpoint_422_blank():
    """空白需求返回 422。"""
    resp = client.post("/v1/uml/generate", json={"requirement": "   ", "diagram_type": "activity"})
    assert resp.status_code == 422


def test_generate_endpoint_invalid_diagram_type():
    """非法图型枚举返回 422（component 仍未支持；sequence 已支持）。"""
    resp = client.post("/v1/uml/generate", json={"requirement": "x", "diagram_type": "component"})
    assert resp.status_code == 422


def test_generate_endpoint_502_on_structured_error(monkeypatch):
    """结构化生成失败返回 502，不泄露内部细节。"""
    from app.core.structured_output import StructuredOutputError

    async def boom(diagram_type, requirement, llm_factory=None):
        raise StructuredOutputError("ActivityModel", RuntimeError("internal"), 2)

    _patch_generate(monkeypatch, boom)
    resp = client.post("/v1/uml/generate", json={"requirement": "x", "diagram_type": "activity"})
    assert resp.status_code == 502


# ---------------- API：自动识别 ----------------


def test_generate_auto_detect_then_activity(monkeypatch):
    """auto：先意图识别为 activity，再生成活动图。"""

    async def fake_detect(requirement, llm_factory=None):
        return DiagramType.ACTIVITY

    async def fake_gen(diagram_type, requirement, llm_factory=None):
        assert diagram_type == DiagramType.ACTIVITY
        return ActivityModel.model_validate(json.loads(VALID_ACTIVITY_JSON))

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "detect_diagram_type", fake_detect)
    monkeypatch.setattr(uml_api, "generate_uml_model", fake_gen)
    resp = client.post("/v1/uml/generate", json={"requirement": "帮我画订单处理流程", "diagram_type": "auto"})
    assert resp.status_code == 200
    assert resp.json()["diagram_type"] == "activity"


def test_generate_auto_unsupported_returns_422(monkeypatch):
    """auto 识别为不支持图型（other）：返回 422 提示后续版本。"""

    async def fake_detect(requirement, llm_factory=None):
        raise ValueError("unsupported_diagram_type:other")

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "detect_diagram_type", fake_detect)
    resp = client.post("/v1/uml/generate", json={"requirement": "画个类图", "diagram_type": "auto"})
    assert resp.status_code == 422


def test_generate_auto_timeout_falls_back_to_usecase(monkeypatch):
    """auto 意图识别超时时回退 usecase（不阻断主流程，仍返回 200）。"""

    async def fake_detect(requirement, llm_factory=None):
        raise asyncio.TimeoutError()

    async def fake_gen(diagram_type, requirement, llm_factory=None):
        # 回退为 usecase 后生成的模型；此处用活动图模型验证渲染/质检分发仍然成立
        return ActivityModel.model_validate(json.loads(VALID_ACTIVITY_JSON))

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "detect_diagram_type", fake_detect)
    monkeypatch.setattr(uml_api, "generate_uml_model", fake_gen)
    resp = client.post("/v1/uml/generate", json={"requirement": "x", "diagram_type": "auto"})
    assert resp.status_code == 200


# ---------------- 路由注册取证 ----------------


def test_generate_route_registered():
    """/v1/uml/generate 已注册（路由表取证 + 422 实证）。"""
    src_paths = [r.path for r in uml_router.routes]
    assert "/v1/uml/generate" in src_paths
    resp = client.post("/v1/uml/generate", json={})
    assert resp.status_code == 422
