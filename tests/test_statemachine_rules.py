"""状态机图规则引擎测试（纯函数，不调 LLM）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import StateMachineModel
from app.rules.statemachine_rules import check_statemachine_model


def _model(states, transitions, object_="订单") -> StateMachineModel:
    return StateMachineModel.model_validate(
        {"type": "statemachine", "object": object_, "states": states, "transitions": transitions}
    )


def test_valid_statemachine_passes():
    """正常状态机（初/终态齐全、转换均有触发事件、终点合法）无 issue。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[
            {"from": "init", "to": "s1", "event": "创建订单"},
            {"from": "s1", "to": "s2", "event": "支付成功"},
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    )
    report = check_statemachine_model(m)
    assert report.passed is True
    assert report.issues == []
    assert report.diagram_type.value == "statemachine"


def test_sm_l4_missing_initial_is_error():
    """SM-L4：缺少初始伪状态报 error。"""
    m = _model(
        states=[
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[{"from": "s1", "to": "fin", "event": "完成"}],
    )
    report = check_statemachine_model(m)
    l4 = [i for i in report.issues if i.rule_id == "SM-L4" and "初始" in i.message]
    assert len(l4) == 1 and l4[0].level == "error"
    assert report.passed is False


def test_sm_l4_missing_final_is_error():
    """SM-L4：缺少最终伪状态报 error。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
        ],
        transitions=[{"from": "init", "to": "s1", "event": "创建"}],
    )
    report = check_statemachine_model(m)
    l4 = [i for i in report.issues if i.rule_id == "SM-L4" and "最终" in i.message]
    assert len(l4) == 1 and l4[0].level == "error"
    assert report.passed is False


def test_sm_l4_multiple_initials_defensive_at_model_layer():
    """SM-L4（>1 初始）为防御性：模型层直接拒绝，规则引擎对合法结构稳定。"""
    with pytest.raises(ValidationError):
        _model(
            states=[
                {"id": "init", "kind": "initial"},
                {"id": "init2", "kind": "initial"},
                {"id": "fin", "kind": "final"},
            ],
            transitions=[],
        )


def test_sm_l3_state_looks_like_action_is_warning():
    """SM-L3：状态名含「正在/执行/处理中」像动作节点报 warning。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "正在支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[{"from": "init", "to": "s1", "event": "下单"}, {"from": "s1", "to": "fin", "event": "完成"}],
    )
    report = check_statemachine_model(m)
    l3 = [i for i in report.issues if i.rule_id == "SM-L3"]
    assert len(l3) == 1 and l3[0].level == "warning"
    assert report.passed is True


def test_sm_t1_transition_missing_event_is_error():
    """SM-T1：转换未标注触发事件报 error。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[
            {"from": "init", "to": "s1", "event": "创建订单"},
            {"from": "s1", "to": "s2"},  # 无 event
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    )
    report = check_statemachine_model(m)
    t1 = [i for i in report.issues if i.rule_id == "SM-T1"]
    assert len(t1) == 1 and t1[0].level == "error"
    assert report.passed is False


def test_sm_t4_dangling_endpoint_defensive_at_model_layer():
    """SM-T4 为防御性：转换终点指向未定义状态在模型层即被拦截。"""
    with pytest.raises(ValidationError):
        _model(
            states=[
                {"id": "init", "kind": "initial"},
                {"id": "s1", "name": "待支付", "kind": "normal"},
                {"id": "fin", "kind": "final"},
            ],
            transitions=[{"from": "init", "to": "s1"}, {"from": "s1", "to": "ghost", "event": "x"}],
        )


def test_sm_c3_history_without_paused_is_warning():
    """SM-C3：存在指向 history 的转换但缺少 paused 状态报 warning。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[
            {"from": "init", "to": "s1", "event": "创建订单"},
            {"from": "s1", "to": "s2", "event": "支付成功"},
            {"from": "s2", "to": "history", "event": "中断"},
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    )
    report = check_statemachine_model(m)
    c3 = [i for i in report.issues if i.rule_id == "SM-C3"]
    assert len(c3) == 1 and c3[0].level == "warning"
    assert report.passed is True


def test_sm_c3_history_with_paused_passes():
    """含 paused 状态承接 history 转换：不报 SM-C3。"""
    m = _model(
        states=[
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s3", "name": "暂停", "kind": "paused", "history": "shallow"},
            {"id": "fin", "kind": "final"},
        ],
        transitions=[
            {"from": "init", "to": "s1", "event": "下单"},
            {"from": "s1", "to": "history", "event": "中断"},
            {"from": "s1", "to": "fin", "event": "完成"},
        ],
    )
    report = check_statemachine_model(m)
    assert [i for i in report.issues if i.rule_id == "SM-C3"] == []


def test_issue_order_stable():
    """同模型多次检查 issues 顺序一致。"""
    m = _model(
        states=[{"id": "s1", "name": "待支付", "kind": "normal"}],  # 缺初/终态
        transitions=[],
    )
    r1 = check_statemachine_model(m)
    r2 = check_statemachine_model(m)
    assert [i.model_dump() for i in r1.issues] == [i.model_dump() for i in r2.issues]
