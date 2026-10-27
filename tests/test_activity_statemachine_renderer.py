"""活动图 / 状态机图 PlantUML 渲染器测试（纯函数，不调真实 PlantUML / 网络 / LLM）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import ActivityModel, StateMachineModel
from app.renderers.plantuml import (
    render_activity_plantuml,
    render_statemachine_plantuml,
    render_uml_plantuml,
)

# ---------------- 活动图 ----------------


def _activity(**overrides) -> ActivityModel:
    data = {
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
            {"id": "f1", "kind": "fork"},
            {"id": "a4", "name": "发货", "lane": "系统", "kind": "action"},
            {"id": "a5", "name": "推送物流", "lane": "系统", "kind": "action"},
            {"id": "j1", "kind": "join"},
            {"id": "end", "kind": "final"},
        ],
        "flows": [
            {"from": "start", "to": "a1"},
            {"from": "a1", "to": "d1"},
            {"from": "d1", "to": "a2", "cond": "充足"},
            {"from": "d1", "to": "a3", "cond": "不足"},
            {"from": "a2", "to": "f1"}, {"from": "a3", "to": "f1"},
            {"from": "f1", "to": "a4"}, {"from": "f1", "to": "a5"},
            {"from": "a4", "to": "j1"}, {"from": "a5", "to": "j1"},
            {"from": "j1", "to": "end"},
        ],
    }
    data.update(overrides)
    return ActivityModel.model_validate(data)


def _render_activity(**overrides) -> str:
    return render_activity_plantuml(_activity(**overrides))


def test_activity_wrapped_by_startuml_enduml():
    out = _render_activity()
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")


def test_activity_start_stop_present():
    """含起始 start 与终止 stop。"""
    out = _render_activity()
    assert "start" in out and "stop" in out


def test_activity_swimlanes_present():
    """泳道以 |名称| 形式出现。"""
    out = _render_activity()
    assert "|顾客|" in out and "|系统|" in out


def test_activity_action_nodes_present():
    """动作节点显示为 :名称; 且中文保留。"""
    out = _render_activity()
    for name in ("提交订单", "扣减库存", "通知缺货", "发货", "推送物流"):
        assert f":{name};" in out


def test_activity_decision_if_else():
    """决策节点渲染为 if/else/endif，分支条件保留。"""
    out = _render_activity()
    assert "if (库存充足?)" in out
    assert "then (充足)" in out
    assert "else (不足)" in out
    assert "endif" in out


def test_activity_fork_join_present():
    """并行分叉/汇合渲染为 fork / fork again / end fork。"""
    out = _render_activity()
    assert "fork" in out
    assert "fork again" in out
    assert "end fork" in out


def test_activity_same_input_same_output():
    """相同输入确定性输出。"""
    assert _render_activity() == _render_activity()


def test_activity_minimal_model():
    """仅初始/终止节点也结构完整。"""
    out = render_activity_plantuml(ActivityModel(module="极简"))
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_activity_non_model_rejected():
    """非法输入在入口被拦截（活动图渲染器无显式类型守卫，非模型报 AttributeError）。"""
    with pytest.raises(AttributeError):
        render_activity_plantuml({"type": "activity"})  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        render_activity_plantuml(None)  # type: ignore[arg-type]


def test_activity_invalid_model_rejected_by_pydantic():
    """结构性非法（泳道未定义）在模型层即被拒，无法到达 renderer。"""
    with pytest.raises(ValidationError):
        _activity(nodes=[{"id": "a1", "name": "x", "lane": "鬼", "kind": "action"}])


# ---------------- 状态机图 ----------------


def _statemachine(**overrides) -> StateMachineModel:
    data = {
        "type": "statemachine",
        "object": "订单",
        "states": [
            {"id": "init", "kind": "initial"},
            {"id": "s1", "name": "待支付", "kind": "normal"},
            {"id": "s2", "name": "已支付", "kind": "normal"},
            {"id": "s3", "name": "暂停", "kind": "paused", "history": "shallow"},
            {"id": "fin", "kind": "final"},
        ],
        "transitions": [
            {"from": "init", "to": "s1"},
            {"from": "s1", "to": "s2", "event": "支付成功"},
            {"from": "s2", "to": "fin", "event": "完成"},
            {"from": "s2", "to": "history", "event": "中断"},
        ],
    }
    data.update(overrides)
    return StateMachineModel.model_validate(data)


def _render_statemachine(**overrides) -> str:
    return render_statemachine_plantuml(_statemachine(**overrides))


def test_statemachine_wrapped_by_startuml_enduml():
    out = _render_statemachine()
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")


def test_statemachine_initial_final_markers():
    """初始 [*] --> 与指向终态的 --> [*] 均出现。"""
    out = _render_statemachine()
    assert "[*] --> st_1" in out
    assert "--> [*]" in out


def test_statemachine_states_named():
    """普通状态以 state "名称" as id 形式渲染，中文保留。"""
    out = _render_statemachine()
    for name in ("待支付", "已支付", "暂停"):
        assert f'state "{name}" as' in out


def test_statemachine_transition_event():
    """转换携带触发事件标注 : 事件。"""
    out = _render_statemachine()
    assert "st_1 --> st_2 : 支付成功" in out


def test_statemachine_transition_to_final_renders_endpoint_token():
    """指向终态的转换必须直接写成 --> [*]，不得引用终态别名。"""
    out = _render_statemachine()
    assert "st_2 --> [*] : 完成" in out


def test_statemachine_final_state_never_becomes_phantom_node():
    """回归：终态不得出现在任何具名位置，否则 PlantUML 会画出名为 st_N 的幽灵状态。"""
    out = _render_statemachine()
    # fin 是第 5 个状态 → 别名为 st_4；它既不该被声明，也不该被引用
    assert "st_4" not in out


def test_statemachine_history_transition():
    """指向 history 的转换渲染为 --> H。"""
    out = _render_statemachine()
    assert "st_2 --> H : 中断" in out


def test_statemachine_same_input_same_output():
    assert _render_statemachine() == _render_statemachine()


def test_statemachine_minimal():
    """仅初/终态结构完整。"""
    out = render_statemachine_plantuml(StateMachineModel(object="对象"))
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_statemachine_non_model_rejected():
    """非法输入在入口被拦截（状态机渲染器无显式类型守卫，非模型报 AttributeError）。"""
    with pytest.raises(AttributeError):
        render_statemachine_plantuml({"type": "statemachine"})  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        render_statemachine_plantuml(None)  # type: ignore[arg-type]


# ---------------- 分发入口 ----------------


def test_render_uml_plantuml_dispatches():
    """render_uml_plantuml 按 isinstance 分发给对应渲染器。"""
    act = _activity()
    sm = _statemachine()
    assert render_uml_plantuml(act) == render_activity_plantuml(act)
    assert render_uml_plantuml(sm) == render_statemachine_plantuml(sm)
    assert render_uml_plantuml(act).startswith("@startuml")
    assert render_uml_plantuml(sm).startswith("@startuml")


# ---------------- 源码纯净性 + 渲染样式注入（inject_skin） ----------------

from app.models.uml import DiagramType  # noqa: E402
from app.renderers.plantuml import inject_skin  # noqa: E402


def test_clean_source_has_no_skinparam():
    """API 返回/导出的 PlantUML 源码保持纯净业务结构（无样式指令）。"""
    for src in (_render_activity(), _render_statemachine()):
        assert "skinparam" not in src
        assert src.startswith("@startuml")


def test_inject_skin_adds_style_without_mutating_source():
    """注入返回副本：原源码不变，注入版含样式且仍为合法 PlantUML 结构。"""
    src = _render_statemachine()
    styled = inject_skin(src, DiagramType.STATEMACHINE)
    assert "skinparam state" in styled
    assert "skinparam" not in src  # 原源码未被修改
    assert styled.startswith("@startuml")
    assert src in styled is False or styled != src


def test_inject_skin_unknown_type_returns_source():
    """未知图型（None 样式）原样返回。"""
    src = "@startuml\nstop\n@enduml"
    assert inject_skin(src, None) == src  # type: ignore[arg-type]
