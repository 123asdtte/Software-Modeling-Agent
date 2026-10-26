"""活动图规则引擎测试（纯函数，不调 LLM）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import ActivityModel
from app.rules.activity_rules import check_activity_model


def _model(nodes, flows, swimlanes=None) -> ActivityModel:
    return ActivityModel.model_validate(
        {
            "type": "activity",
            "module": "订单处理",
            "swimlanes": swimlanes or [{"name": "顾客"}, {"name": "系统"}],
            "nodes": nodes,
            "flows": flows,
        }
    )


def test_valid_activity_passes():
    """正常活动图（动作归属泳道、决策有互斥分支、含起止）无 issue。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "a1", "name": "下单", "lane": "顾客", "kind": "action"},
            {"id": "d1", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "a2", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "a3", "name": "通知缺货", "lane": "系统", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        flows=[
            {"from": "start", "to": "a1"},
            {"from": "a1", "to": "d1"},
            {"from": "d1", "to": "a2", "cond": "充足"},
            {"from": "d1", "to": "a3", "cond": "不足"},
            {"from": "a2", "to": "end"},
            {"from": "a3", "to": "end"},
        ],
    )
    report = check_activity_model(m)
    assert report.passed is True
    assert report.issues == []
    assert report.diagram_type.value == "activity"


def test_ac_s2_internal_component_as_lane_is_error():
    """AC-S2：内部组件（数据库）作为泳道名报 error。"""
    m = _model(
        nodes=[{"id": "start", "kind": "initial"}, {"id": "end", "kind": "final"}],
        flows=[],
        swimlanes=[{"name": "数据库"}, {"name": "系统"}],
    )
    report = check_activity_model(m)
    s2 = [i for i in report.issues if i.rule_id == "AC-S2"]
    assert len(s2) == 1 and s2[0].level == "error"
    assert report.passed is False


def test_ac_g1_ui_operation_word_is_warning():
    """AC-G1：动作名含界面操作词「点击」报 warning。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "a1", "name": "点击提交按钮", "lane": "顾客", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        flows=[{"from": "start", "to": "a1"}, {"from": "a1", "to": "end"}],
    )
    report = check_activity_model(m)
    g1 = [i for i in report.issues if i.rule_id == "AC-G1"]
    assert len(g1) == 1 and g1[0].level == "warning"
    assert report.passed is True  # warning 不影响 passed


def test_ac_f1_isolated_node_is_error():
    """AC-F1：动作节点无任何连入/连出（孤立）报 error。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "a1", "name": "提交订单", "lane": "顾客", "kind": "action"},
            {"id": "a9", "name": "游离动作", "lane": "系统", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        flows=[{"from": "start", "to": "a1"}, {"from": "a1", "to": "end"}],
    )
    report = check_activity_model(m)
    f1 = [i for i in report.issues if i.rule_id == "AC-F1" and i.target == "a9"]
    assert len(f1) == 1 and f1[0].level == "error"
    assert report.passed is False


def test_ac_f2_decision_no_branch_is_error():
    """AC-F2：决策节点没有任何输出分支报 error。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "d1", "name": "是否通过?", "lane": "系统", "kind": "decision"},
            {"id": "end", "kind": "final"},
        ],
        flows=[{"from": "start", "to": "d1"}],
    )
    report = check_activity_model(m)
    f2 = [i for i in report.issues if i.rule_id == "AC-F2"]
    assert len(f2) == 1 and f2[0].level == "error"
    assert report.passed is False


def test_ac_f2_decision_missing_cond_is_error():
    """AC-F2：决策分支缺少监护条件（cond）报 error。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "d1", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "a2", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "a3", "name": "通知缺货", "lane": "系统", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        flows=[
            {"from": "start", "to": "d1"},
            {"from": "d1", "to": "a2"},  # 无 cond
            {"from": "d1", "to": "a3", "cond": "不足"},
            {"from": "a2", "to": "end"},
            {"from": "a3", "to": "end"},
        ],
    )
    report = check_activity_model(m)
    f2 = [i for i in report.issues if i.rule_id == "AC-F2" and i.level == "error"]
    assert len(f2) == 1
    assert report.passed is False


def test_ac_f2_duplicate_branch_target_is_warning():
    """AC-F2：决策多个分支指向同一目标报 warning。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "d1", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "a2", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "end", "kind": "final"},
        ],
        flows=[
            {"from": "start", "to": "d1"},
            {"from": "d1", "to": "a2", "cond": "充足"},
            {"from": "d1", "to": "a2", "cond": "不足"},  # 重复指向 a2
            {"from": "a2", "to": "end"},
        ],
    )
    report = check_activity_model(m)
    f2 = [i for i in report.issues if i.rule_id == "AC-F2" and i.level == "warning"]
    assert len(f2) == 1


def test_ac_f4_fork_join_mismatch_is_error():
    """AC-F4：分叉与汇合数量不匹配报 error（规则仅在 fork 与 join 同时存在时校验配对）。"""
    m = _model(
        nodes=[
            {"id": "start", "kind": "initial"},
            {"id": "f1", "kind": "fork"},
            {"id": "f2", "kind": "fork"},
            {"id": "a1", "name": "发货", "lane": "系统", "kind": "action"},
            {"id": "a2", "name": "推送物流", "lane": "系统", "kind": "action"},
            {"id": "j1", "kind": "join"},
            {"id": "end", "kind": "final"},
        ],
        flows=[
            {"from": "start", "to": "f1"},
            {"from": "f1", "to": "a1"},
            {"from": "f1", "to": "f2"},
            {"from": "f2", "to": "a2"},
            {"from": "a1", "to": "j1"},
            {"from": "a2", "to": "j1"},
            {"from": "j1", "to": "end"},
        ],
    )
    report = check_activity_model(m)
    f4 = [i for i in report.issues if i.rule_id == "AC-F4"]
    assert len(f4) == 1 and f4[0].level == "error"
    assert report.passed is False


def test_ac_s1_defensive_at_model_layer():
    """AC-S1 为防御性规则：动作节点缺泳道/泳道未定义在模型层即被拦截，
    规则引擎对合法近似结构稳定（不重复报错）。"""
    with pytest.raises(ValidationError):
        _model(
            nodes=[{"id": "a1", "name": "x", "kind": "action"}],  # 缺 lane
            flows=[],
        )
    with pytest.raises(ValidationError):
        _model(
            nodes=[{"id": "a1", "name": "x", "lane": "鬼", "kind": "action"}],  # 泳道未定义
            flows=[],
        )


def test_issue_order_stable():
    """同模型多次检查 issues 顺序一致。"""
    m = _model(
        nodes=[{"id": "start", "kind": "initial"}, {"id": "end", "kind": "final"}],
        flows=[],
        swimlanes=[{"name": "数据库"}],
    )
    r1 = check_activity_model(m)
    r2 = check_activity_model(m)
    assert [i.model_dump() for i in r1.issues] == [i.model_dump() for i in r2.issues]
