"""对话式修正链（架构增量重构）三图型统一测试（mock LLM，不调真实服务）。"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.chains.uml_adjust import AdjustedOutput, adjust_uml_model
from app.main import app
from app.models.uml import ActivityModel, StateMachineModel, UseCaseModel

client = TestClient(app)


VALID_ACTIVITY_JSON = json.dumps(
    {
        "type": "activity",
        "module": "订单处理",
        "swimlanes": [{"name": "顾客"}, {"name": "系统"}],
        "nodes": [
            {"id": "A0", "kind": "initial"},
            {"id": "A-01", "name": "下单", "lane": "顾客", "kind": "action"},
            {"id": "D-01", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "A-02", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "A-03", "name": "通知缺货", "lane": "系统", "kind": "action"},
            {"id": "A9", "kind": "final"},
        ],
        "flows": [
            {"from": "A0", "to": "A-01"},
            {"from": "A-01", "to": "D-01"},
            {"from": "D-01", "to": "A-02", "cond": "充足"},
            {"from": "D-01", "to": "A-03", "cond": "不足"},
            {"from": "A-02", "to": "A9"},
            {"from": "A-03", "to": "A9"},
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


def _activity_model() -> ActivityModel:
    return ActivityModel.model_validate(json.loads(VALID_ACTIVITY_JSON))


def _statemachine_model() -> StateMachineModel:
    return StateMachineModel.model_validate(json.loads(VALID_STATEMACHINE_JSON))


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, messages):
        return type("M", (), {"content": self.content})()


def _factory(llm: _FakeLLM):
    return lambda timeout=None: llm


def _adjusted_json(model_obj, reply="已按指令修正", diff="变更1处") -> str:
    return json.dumps(
        {"model": json.loads(model_obj.model_dump_json(by_alias=True)), "reply": reply, "diff_summary": diff},
        ensure_ascii=False,
    )


def test_adjust_activity_moves_node_to_lane():
    """活动图修正：指令要求把动作换泳道 → 返回修正后模型 + 重质检。"""
    m = _activity_model()
    m.swimlanes[0].name = "顾客"
    adjusted = _activity_model()
    adjusted.nodes[1].lane = "系统"  # A-01 下单 → 系统（示例修正）
    out = asyncio.run(
        adjust_uml_model(
            m,
            "把「下单」动作移到系统泳道",
            "png",
            llm_factory=_factory(_FakeLLM(_adjusted_json(adjusted))),
        )
    )
    assert out["success"] is True
    assert out["model"]["type"] == "activity"
    assert out["model"]["nodes"][1]["name"] == "下单"
    assert out["plantuml"].startswith("@startuml")
    assert "|定时" not in out["plantuml"]
    assert out["passed"] in (True, False)  # 质检已执行
    assert isinstance(out["issues"], list)


def test_adjust_statemachine_adds_event():
    """状态机修正：返回修正后模型 + 质检 + 渲染。"""
    m = _statemachine_model()
    adjusted = _statemachine_model()
    adjusted.transitions[1].event = "支付完成"
    out = asyncio.run(
        adjust_uml_model(
            m,
            "把「支付成功」事件改名为「支付完成」",
            "png",
            llm_factory=_factory(_FakeLLM(_adjusted_json(adjusted))),
        )
    )
    assert out["success"] is True
    assert out["model"]["type"] == "statemachine"
    assert out["model"]["transitions"][1]["event"] == "支付完成"
    assert "[*] --> st_1" in out["plantuml"]


def test_adjust_rejects_type_change():
    """LLM 改动了 model.type（联合类型校验成另一模型）→ 拒绝并抛 ValueError。"""
    m = _activity_model()
    # 用状态机 JSON 冒充活动图修正结果 → type 不一致
    sm = _statemachine_model()
    with pytest.raises(ValueError):
        asyncio.run(
            adjust_uml_model(m, "x", "png", llm_factory=_factory(_FakeLLM(_adjusted_json(sm))))
        )


def test_adjusted_output_union_by_type():
    """AdjustedOutput 联合类型按 type 字段精确匹配三图型。"""
    a = AdjustedOutput.model_validate_json(_adjusted_json(_activity_model()))
    assert isinstance(a.model, ActivityModel)
    s = AdjustedOutput.model_validate_json(_adjusted_json(_statemachine_model()))
    assert isinstance(s.model, StateMachineModel)
    u = AdjustedOutput.model_validate_json(
        _adjusted_json(UseCaseModel(system="学籍系统"))
    )
    assert isinstance(u.model, UseCaseModel)


# ---------------- API 层 ----------------


def test_chat_adjust_activity_endpoint(monkeypatch):
    """/chat-adjust 传活动图模型：按 type 分派，返回修正结果。"""

    async def fake_adjust(current_model, instruction, output_format, llm_factory=None):
        return {
            "success": True,
            "reply": "已修正",
            "model": json.loads(VALID_ACTIVITY_JSON),
            "plantuml": "@startuml\nstart\nstop\n@enduml",
            "issues": [],
            "passed": True,
            "diff_summary": "无",
            "render": {"status": "source_only", "format": None, "download_url": None, "reason": None},
        }

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "adjust_uml_model", fake_adjust)
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "修改动作名称", "current_model": json.loads(VALID_ACTIVITY_JSON), "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["model"]["type"] == "activity"


def test_chat_adjust_statemachine_endpoint(monkeypatch):
    """/chat-adjust 传状态机模型：按 type 分派。"""

    async def fake_adjust(current_model, instruction, output_format, llm_factory=None):
        return {
            "success": True,
            "reply": "已修正",
            "model": json.loads(VALID_STATEMACHINE_JSON),
            "plantuml": "@startuml\n@enduml",
            "issues": [],
            "passed": True,
            "diff_summary": "无",
            "render": {"status": "source_only", "format": None, "download_url": None, "reason": None},
        }

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "adjust_uml_model", fake_adjust)
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "修改事件名", "current_model": json.loads(VALID_STATEMACHINE_JSON), "format": "png"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"]["type"] == "statemachine"


def test_chat_adjust_invalid_type_422():
    """未知 model.type → 422（sequence 已支持，用 component 验证未支持类型）。"""
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "x", "current_model": {"type": "component", "system": "s"}, "format": "png"},
    )
    assert resp.status_code == 422
