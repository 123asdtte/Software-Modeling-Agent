"""draw.io 渲染器测试（纯函数：XML 结构/确定性/转义/边界）。"""

from xml.etree import ElementTree

import pytest

from app.models.uml import UseCaseModel
from app.renderers.drawio_renderer import render_usecase_drawio


def _model(**overrides) -> UseCaseModel:
    data = {
        "system": "校园二手交易系统",
        "actors": [{"name": "学生"}, {"name": "管理员"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
        ],
        "relations": [{"type": "include", "from": "UC-02", "to": "UC-01"}],
    }
    data.update(overrides)
    return UseCaseModel.model_validate(data)


def test_output_is_valid_xml():
    """输出可被 XML 解析器解析（mxfile 结构完整）。"""
    root = ElementTree.fromstring(render_usecase_drawio(_model()))
    assert root.tag == "mxfile"
    assert root.find("diagram") is not None


def test_deterministic_output():
    """相同输入输出完全一致。"""
    assert render_usecase_drawio(_model()) == render_usecase_drawio(_model())


def test_actors_usecases_boundary_present():
    """actor 形状、usecase 椭圆、系统边界均存在，显示文本保留中文。"""
    out = render_usecase_drawio(_model())
    assert 'value="学生"' in out and "shape=umlActor" in out
    assert 'value="发布商品"' in out and "ellipse" in out
    assert 'value="校园二手交易系统"' in out


def test_all_edge_types_with_labels():
    """include 虚线带构造型标签；association 实线；generalization 空心三角。"""
    data = {
        "system": "系统",
        "actors": [{"name": "学生"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "浏览商品", "actors": ["学生"]},
            {"id": "UC-03", "name": "填写物流单", "actors": ["学生"]},
        ],
        "relations": [
            {"type": "include", "from": "UC-02", "to": "UC-01"},
            {"type": "extend", "from": "UC-03", "to": "UC-01"},
            {"type": "association", "from": "学生", "to": "UC-01"},
            {"type": "generalization", "from": "UC-02", "to": "UC-01"},
        ],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "«include»" in out and "dashed=1" in out
    assert "«extend»" in out
    assert "endArrow=block;endFill=0" in out  # generalization 空心三角
    assert "endArrow=none" in out  # association 无箭头


def test_alias_not_user_input():
    """用户输入不作为元素 id（防注入与重名）。"""
    data = {
        "system": "系统",
        "actors": [{"name": "x&y<z>"}],
        "usecases": [{"id": "UC-01", "name": "用例", "actors": ["x&y<z>"]}],
        "relations": [],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "actor_1" in out
    assert "x&y<z>" not in out  # 已转义为 &amp;
    assert "x&amp;y&lt;z&gt;" in out


def test_same_input_same_xml_with_quotes():
    """含引号名称的确定性 + 转义正确性。"""
    data = {
        "system": '系统"引号"',
        "actors": [{"name": 'a"b'}],
        "usecases": [{"id": "UC-01", "name": "发布商品", "actors": ['a"b']}],
        "relations": [],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "&quot;" in out
    assert out == render_usecase_drawio(UseCaseModel.model_validate(data))


def test_non_model_rejected():
    from app.renderers.drawio_renderer import render_usecase_drawio as r

    with pytest.raises(TypeError):
        r({"system": "不是模型"})  # type: ignore[arg-type]


# ============================================================================
# 活动图 / 状态机图 drawio 渲染（2026-10-09 三图型扩展）
# ============================================================================

from app.models.uml import ActivityModel, StateMachineModel  # noqa: E402
from app.renderers.drawio_renderer import (  # noqa: E402
    render_activity_drawio,
    render_statemachine_drawio,
)


def _activity(**overrides) -> ActivityModel:
    data = {
        "type": "activity",
        "module": "订单处理",
        "swimlanes": [{"name": "顾客"}, {"name": "系统"}],
        "nodes": [
            {"id": "A0", "kind": "initial"},
            {"id": "A-01", "name": "下单", "lane": "顾客", "kind": "action"},
            {"id": "D-01", "name": "库存充足?", "lane": "系统", "kind": "decision"},
            {"id": "A-02", "name": "扣减库存", "lane": "系统", "kind": "action"},
            {"id": "A9", "kind": "final"},
        ],
        "flows": [
            {"from": "A0", "to": "A-01"},
            {"from": "A-01", "to": "D-01"},
            {"from": "D-01", "to": "A-02", "cond": "充足"},
            {"from": "D-01", "to": "A9", "cond": "不足"},
            {"from": "A-02", "to": "A9"},
        ],
    }
    data.update(overrides)
    return ActivityModel.model_validate(data)


def _statemachine(**overrides) -> StateMachineModel:
    data = {
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
            {"from": "s1", "to": "s2", "event": "支付成功", "guard": "余额充足"},
            {"from": "s2", "to": "fin", "event": "完成"},
        ],
    }
    data.update(overrides)
    return StateMachineModel.model_validate(data)


def test_activity_drawio_valid_xml():
    root = ElementTree.fromstring(render_activity_drawio(_activity()))
    assert root.tag == "mxfile"
    assert root.find("diagram") is not None


def test_activity_drawio_lanes_and_nodes():
    out = render_activity_drawio(_activity())
    assert "顾客" in out and "系统" in out  # 泳道背景
    assert "下单" in out and "库存充足?" in out  # 节点显示文本
    assert "rhombus" in out  # 决策节点为菱形


def test_activity_drawio_guard_labels():
    out = render_activity_drawio(_activity())
    assert "充足" in out and "不足" in out  # 监护条件作为边标签


def test_activity_drawio_deterministic():
    assert render_activity_drawio(_activity()) == render_activity_drawio(_activity())


def test_activity_drawio_type_rejected():
    with pytest.raises(TypeError):
        render_activity_drawio({"type": "activity"})  # type: ignore[arg-type]


def test_statemachine_drawio_valid_xml():
    root = ElementTree.fromstring(render_statemachine_drawio(_statemachine()))
    assert root.tag == "mxfile"


def test_statemachine_drawio_states_and_transitions():
    out = render_statemachine_drawio(_statemachine())
    assert "待支付" in out and "已支付" in out
    assert "创建订单" in out and "支付成功" in out
    assert "[余额充足]" in out  # guard 标注在转换边上


def test_statemachine_drawio_deterministic():
    assert render_statemachine_drawio(_statemachine()) == render_statemachine_drawio(_statemachine())


def test_statemachine_drawio_type_rejected():
    with pytest.raises(TypeError):
        render_statemachine_drawio(None)  # type: ignore[arg-type]


# ============================================================================
# 类图 / 时序图 / 部署图 drawio 渲染（2026-10-26 六图型对齐）
# ============================================================================

from app.models.uml import (  # noqa: E402
    ClassModel,
    DeploymentModel,
    SequenceModel,
)
from app.renderers.drawio_renderer import (  # noqa: E402
    render_class_drawio,
    render_deployment_drawio,
    render_sequence_drawio,
)


def _class_model(**overrides) -> ClassModel:
    data = {
        "type": "class",
        "title": "校园选课",
        "classes": [
            {
                "name": "User",
                "is_abstract": True,
                "attributes": [
                    {"name": "id", "type": "Long", "visibility": "#"},
                    {"name": "seq", "type": "int", "visibility": "-", "is_static": True},
                ],
                "methods": [{"name": "getId", "return_type": "Long", "visibility": "+"}],
            },
            {
                "name": "Enrollable",
                "is_interface": True,
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "c", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                        "is_abstract": True,
                    }
                ],
            },
            {
                "name": "Student",
                "attributes": [{"name": "studentNo", "type": "String", "visibility": "-"}],
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "c", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                    }
                ],
            },
            {"name": "Course", "attributes": [{"name": "title", "type": "String"}]},
        ],
        "relations": [
            {"type": "generalization", "from": "Student", "to": "User"},
            {"type": "realization", "from": "Student", "to": "Enrollable"},
            {
                "type": "composition",
                "from": "Course",
                "to": "Student",
                "label": "选课",
                "source_multiplicity": "1",
                "target_multiplicity": "0..*",
            },
        ],
    }
    data.update(overrides)
    return ClassModel.model_validate(data)


def _sequence_model(**overrides) -> SequenceModel:
    data = {
        "type": "sequence",
        "title": "选课交互",
        "lifelines": [
            {"name": "学生", "kind": "actor"},
            {"name": "选课服务", "kind": "control", "classifier": "EnrollService"},
            {"name": "数据库", "kind": "database"},
        ],
        "messages": [
            {"from": "学生", "to": "选课服务", "label": "选课()", "kind": "sync", "order": 1},
            {"from": "选课服务", "to": "数据库", "label": "查余量", "kind": "sync", "order": 2},
            {"from": "数据库", "to": "选课服务", "label": "余量", "kind": "return", "order": 3},
            {"from": "选课服务", "to": "学生", "label": "成功", "kind": "return", "order": 4},
        ],
        "fragments": [{"kind": "alt", "condition": "有余量", "start_order": 2, "end_order": 3}],
    }
    if "messages" in overrides and "fragments" not in overrides:
        data["fragments"] = []
    data.update(overrides)
    return SequenceModel.model_validate(data)


def _deployment_model(**overrides) -> DeploymentModel:
    data = {
        "type": "deployment",
        "title": "微服务部署",
        "nodes": [
            {"name": "ingress-nginx", "stereotype": "ingress", "spec": "1 副本"},
            {"name": "course-service", "stereotype": "deployment", "spec": "2 副本"},
            {"name": "mysql-master", "kind": "device", "stereotype": "database", "spec": "8C16G"},
        ],
        "artifacts": [{"name": "course-service.jar", "deployed_on": "course-service"}],
        "associations": [
            {"from": "ingress-nginx", "to": "course-service", "kind": "communication"},
            {"from": "course-service", "to": "mysql-master", "kind": "dependency"},
        ],
    }
    data.update(overrides)
    return DeploymentModel.model_validate(data)


# ---------------------------- 类图 ----------------------------


def test_class_drawio_valid_xml_and_deterministic():
    out = render_class_drawio(_class_model())
    root = ElementTree.fromstring(out)
    assert root.tag == "mxfile"
    assert out == render_class_drawio(_class_model())


def test_class_drawio_unique_cell_ids():
    root = ElementTree.fromstring(render_class_drawio(_class_model()))
    ids = [c.get("id") for c in root.findall(".//mxCell")]
    assert len(ids) == len(set(ids))


def test_class_drawio_interface_and_abstract_stereotypes():
    out = render_class_drawio(_class_model())
    assert "&#171;interface&#187;" in out
    assert "&#171;abstract&#187;" in out


def test_class_drawio_members_rendered():
    out = render_class_drawio(_class_model())
    # 可见性符号 + 类型
    assert "+ getId(): Long" in out
    assert "- studentNo: String" in out
    # 静态成员加下划线、抽象方法斜体
    assert "&lt;u&gt;- seq: int&lt;/u&gt;" in out
    assert "&lt;i&gt;+ enroll(c: Course): boolean&lt;/i&gt;" in out


def test_class_drawio_relation_arrows():
    out = render_class_drawio(_class_model())
    assert "endArrow=block;endFill=0;html=1;" in out  # 泛化
    assert "endArrow=block;endFill=0;dashed=1;html=1;" in out  # 实现
    assert "startArrow=diamondThin;startFill=1" in out  # 组合实心菱形
    assert "选课" in out


def test_class_drawio_multiplicity_labels():
    out = render_class_drawio(_class_model())
    assert out.count("edgeLabel") == 2
    assert 'value="0..*"' in out and 'value="1"' in out


def test_class_drawio_empty_model_ok():
    """空类图不崩：仍产出合法 mxfile（由 API 层负责 422）。"""
    out = render_class_drawio(_class_model(classes=[], relations=[]))
    assert ElementTree.fromstring(out).tag == "mxfile"
    assert "edgeLabel" not in out


def test_class_drawio_type_rejected():
    with pytest.raises(TypeError):
        render_class_drawio(_class_model().model_dump())  # type: ignore[arg-type]


def test_class_drawio_xml_escaping():
    """类名/成员含 & < > " 时必须转义，且解析后还原为原文。"""
    model = _class_model(
        classes=[
            {
                "name": "A<B>&C",
                "attributes": [{"name": 'x"y', "type": "Map<K,V>"}],
            }
        ],
        relations=[],
    )
    out = render_class_drawio(model)
    root = ElementTree.fromstring(out)  # 不合法即抛错
    values = [c.get("value") or "" for c in root.findall(".//mxCell")]
    assert any("A<B>&C" in v for v in values)
    assert any('x"y: Map<K,V>' in v for v in values)


# ---------------------------- 时序图 ----------------------------


def test_sequence_drawio_valid_xml_and_deterministic():
    out = render_sequence_drawio(_sequence_model())
    assert ElementTree.fromstring(out).tag == "mxfile"
    assert out == render_sequence_drawio(_sequence_model())


def test_sequence_drawio_lifelines_and_stereotypes():
    out = render_sequence_drawio(_sequence_model())
    assert out.count("shape=umlLifeline") == 3
    assert "&#171;actor&#187;" in out
    assert "&#171;control&#187;" in out
    assert "&#171;database&#187;" in out
    assert "选课服务: EnrollService" in out


def test_sequence_drawio_message_order_drives_y():
    """order 决定纵向位置：order 越大 y 越大（渲染按 order 而非列表顺序）。"""
    model = _sequence_model(
        messages=[
            {"from": "学生", "to": "选课服务", "label": "第二步", "kind": "sync", "order": 2},
            {"from": "学生", "to": "选课服务", "label": "第一步", "kind": "sync", "order": 1},
        ]
    )
    out = render_sequence_drawio(model)
    y1 = out.index('id="sd_msg_1"')
    y2 = out.index('id="sd_msg_2"')
    assert y1 < y2  # 先输出 order=1
    assert "第一步" in out


def test_sequence_drawio_message_arrows():
    base = {"lifelines": _sequence_model().lifelines}
    for kind, marker in (
        ("sync", "endArrow=block;endFill=1"),
        ("async", "endArrow=open;endFill=0;html=1;"),
        ("return", "endArrow=open;endFill=0;dashed=1"),
        ("destroy", "endArrow=cross"),
    ):
        model = _sequence_model(
            **base,
            messages=[{"from": "学生", "to": "选课服务", "kind": kind, "order": 1}],
        )
        assert marker in render_sequence_drawio(model), kind


def test_sequence_drawio_self_message_loops_right():
    model = _sequence_model(
        messages=[{"from": "选课服务", "to": "选课服务", "label": "校验", "order": 1}]
    )
    out = render_sequence_drawio(model)
    assert "exitX=1;" in out and "entryX=1;" in out
    assert "edgeStyle=orthogonalEdgeStyle" in out


def test_sequence_drawio_fragment_box():
    out = render_sequence_drawio(_sequence_model())
    assert "&#171;alt&#187;" in out
    assert "有余量" in out
    assert 'id="sd_frag_1"' in out


def test_sequence_drawio_empty_messages_ok():
    """无消息时仍渲染生命线，且不产生消息边。"""
    out = render_sequence_drawio(_sequence_model(messages=[]))
    assert out.count("shape=umlLifeline") == 3
    assert "sd_msg_" not in out


def test_sequence_drawio_type_rejected():
    with pytest.raises(TypeError):
        render_sequence_drawio("not a model")  # type: ignore[arg-type]


# ---------------------------- 部署图 ----------------------------


def test_deployment_drawio_valid_xml_and_deterministic():
    out = render_deployment_drawio(_deployment_model())
    assert ElementTree.fromstring(out).tag == "mxfile"
    assert out == render_deployment_drawio(_deployment_model())


def test_deployment_drawio_node_shapes_and_stereotypes():
    out = render_deployment_drawio(_deployment_model())
    assert out.count("shape=cube") == 3
    assert "&#171;ingress&#187;" in out
    assert "[8C16G]" in out


def test_deployment_drawio_device_uses_grey_fill():
    out = render_deployment_drawio(_deployment_model())
    assert "fillColor=#f5f5f5" in out  # device
    assert "fillColor=#ffffff" in out  # exec_env


def test_deployment_drawio_artifact_nested_in_host():
    """构件必须挂在宿主节点内（拖动节点时跟随）。"""
    root = ElementTree.fromstring(render_deployment_drawio(_deployment_model()))
    cells = {c.get("id"): c for c in root.findall(".//mxCell")}
    art = next(c for cid, c in cells.items() if cid.endswith("_art_1"))
    assert art.get("parent") == "dp_n_2"
    assert art.get("style", "").startswith("shape=document")


def test_deployment_drawio_orphan_artifact_rendered():
    model = _deployment_model(artifacts=[{"name": "loose.war", "deployed_on": ""}])
    out = render_deployment_drawio(model)
    assert 'id="dp_orphan_1"' in out
    assert "loose.war" in out


def test_deployment_drawio_dependency_dashed():
    out = render_deployment_drawio(_deployment_model())
    assert "endArrow=open;dashed=1" in out  # dependency
    assert "endArrow=none" in out  # communication
    assert "dp_edge_1" in out and "dp_edge_2" in out


def test_deployment_drawio_empty_nodes_ok():
    out = render_deployment_drawio(_deployment_model(nodes=[], artifacts=[], associations=[]))
    assert ElementTree.fromstring(out).tag == "mxfile"


def test_deployment_drawio_type_rejected():
    with pytest.raises(TypeError):
        render_deployment_drawio(123)  # type: ignore[arg-type]
