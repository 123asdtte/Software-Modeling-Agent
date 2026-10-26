"""活动图 / 状态机图领域模型测试（纯模型校验，不调 LLM、不渲染）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import ActivityModel, DiagramType, StateMachineModel

# ---------------- 活动图 ----------------


def _valid_activity() -> dict:
    return {
        "type": "activity",
        "module": "订单处理",
        "swimlanes": [{"name": "顾客"}, {"name": "系统"}],
        "nodes": [
            {"id": "start", "kind": "initial"},
            {"id": "a1", "name": "提交订单", "lane": "顾客", "kind": "action"},
            {"id": "d1", "name": "库存充足?", "lane": "系统", "kind": "decision",
             "branches": [{"cond": "充足", "to": "a2"}, {"cond": "不足", "to": "a3"}]},
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
    }


def test_activity_model_valid():
    """合法活动图模型正常构造，类型锁定 activity。"""
    m = ActivityModel.model_validate(_valid_activity())
    assert m.type == DiagramType.ACTIVITY
    assert len(m.swimlanes) == 2 and len(m.nodes) == 6


def test_activity_action_requires_name():
    """action/decision 节点必须有 name。"""
    data = _valid_activity()
    data["nodes"][1]["name"] = ""
    with pytest.raises(ValidationError):
        ActivityModel.model_validate(data)


def test_activity_action_requires_lane():
    """action/decision 节点必须归属某个泳道。"""
    data = _valid_activity()
    data["nodes"][1]["lane"] = ""
    with pytest.raises(ValidationError, match="必须归属"):
        ActivityModel.model_validate(data)


def test_activity_lane_must_be_defined():
    """节点引用未定义的泳道必须拒绝。"""
    data = _valid_activity()
    data["nodes"][1]["lane"] = "不存在的泳道"
    with pytest.raises(ValidationError, match="未定义"):
        ActivityModel.model_validate(data)


def test_activity_duplicate_node_id_rejected():
    """重复节点 ID 必须拒绝。"""
    data = _valid_activity()
    data["nodes"].append({"id": "a1", "name": "重复", "lane": "顾客", "kind": "action"})
    with pytest.raises(ValidationError, match="重复的节点 ID"):
        ActivityModel.model_validate(data)


def test_activity_duplicate_lane_name_rejected():
    """重复泳道名必须拒绝。"""
    data = _valid_activity()
    data["swimlanes"].append({"name": "顾客"})
    with pytest.raises(ValidationError, match="重复的泳道名称"):
        ActivityModel.model_validate(data)


def test_activity_flow_endpoint_must_exist():
    """控制流端点必须存在（to 指向未定义节点拒绝）。"""
    data = _valid_activity()
    data["flows"][0]["to"] = "ghost"
    with pytest.raises(ValidationError, match="不存在"):
        ActivityModel.model_validate(data)


def test_activity_invalid_kind_rejected():
    """非法节点类型（不在枚举内）拒绝。"""
    data = _valid_activity()
    data["nodes"][1]["kind"] = "weird"
    with pytest.raises(ValidationError):
        ActivityModel.model_validate(data)


def test_activity_defaults_empty():
    """缺省列表字段合法。"""
    m = ActivityModel(module="极简模块")
    assert m.nodes == [] and m.swimlanes == [] and m.flows == []


def test_activity_alias_serialization_locked():
    """flow 序列化锁定：by_alias 输出 from/to。"""
    m = ActivityModel.model_validate(_valid_activity())
    dumped = m.model_dump(by_alias=True)
    assert dumped["flows"][0]["from"] == "start"
    assert dumped["flows"][0]["to"] == "a1"


# ---------------- 状态机图 ----------------


def _valid_statemachine() -> dict:
    return {
        "type": "statemachine",
        "object": "订单",
        "states": [
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        "transitions": [
            {"from": "init", "to": "s1"},
            {"from": "s1", "to": "s2", "event": "支付成功"},
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    }


def test_statemachine_model_valid():
    """合法状态机图模型正常构造，类型锁定 statemachine。"""
    m = StateMachineModel.model_validate(_valid_statemachine())
    assert m.type == DiagramType.STATEMACHINE
    assert len(m.states) == 4 and len(m.transitions) == 3


def test_statemachine_two_initials_rejected():
    """初始伪状态超过一个必须拒绝（模型层结构约束）。"""
    data = _valid_statemachine()
    data["states"].insert(1, {"id": "init2", "kind": "initial"})
    with pytest.raises(ValidationError, match="只能有一个"):
        StateMachineModel.model_validate(data)


def test_statemachine_two_finals_rejected():
    """最终伪状态超过一个必须拒绝（模型层结构约束）。"""
    data = _valid_statemachine()
    data["states"].append({"id": "fin2", "kind": "final"})
    with pytest.raises(ValidationError, match="只能有一个"):
        StateMachineModel.model_validate(data)


def test_statemachine_transition_target_undefined_rejected():
    """转换终点指向未定义状态必须拒绝。"""
    data = _valid_statemachine()
    data["transitions"][1]["to"] = "ghost"
    with pytest.raises(ValidationError, match="不存在"):
        StateMachineModel.model_validate(data)


def test_statemachine_history_token_allowed():
    """转换终点为 history 历史伪状态（H）合法，不报未知状态。"""
    data = _valid_statemachine()
    data["transitions"].append({"from": "s2", "to": "history", "event": "中断"})
    m = StateMachineModel.model_validate(data)
    assert m.transitions[-1].target == "history"


def test_statemachine_any_state_allows_undefined_source():
    """any_state=True 时 from 可为任意（不要求为已定义状态）。"""
    data = _valid_statemachine()
    data["transitions"].append({"from": "任意来源", "to": "s1", "event": "唤醒", "any_state": True})
    m = StateMachineModel.model_validate(data)
    assert m.transitions[-1].any_state is True


def test_statemachine_paused_history_must_be_valid():
    """paused 状态的 history 必须为 shallow/deep，否则拒绝。"""
    data = _valid_statemachine()
    data["states"].append({"id": "s3", "name": "暂停", "kind": "paused", "history": "weird"})
    with pytest.raises(ValidationError, match="shallow/deep"):
        StateMachineModel.model_validate(data)


def test_statemachine_kind_enum_values():
    """四种状态类型全部合法（str 枚举）。"""
    for kind in ("initial", "normal", "final", "paused"):
        s = StateMachineModel(states=[{"id": "x", "name": "x", "kind": kind}])
        assert s.states[0].kind.value == kind


def test_statemachine_alias_serialization_locked():
    """transition 序列化锁定：by_alias 输出 from/to/any_state。"""
    m = StateMachineModel.model_validate(_valid_statemachine())
    dumped = m.model_dump(by_alias=True)
    assert dumped["transitions"][0]["from"] == "init"
    assert dumped["transitions"][0]["to"] == "s1"
    assert dumped["transitions"][1]["event"] == "支付成功"


def test_parse_uml_model_dispatch():
    """parse_uml_model 按 type 分发表决为具体模型类。"""
    from app.models.uml import parse_uml_model

    assert isinstance(parse_uml_model(_valid_activity()), ActivityModel)
    assert isinstance(parse_uml_model(_valid_statemachine()), StateMachineModel)
