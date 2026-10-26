"""类图 / 时序图 / 部署图 PlantUML 渲染器测试（纯函数，不调真实 PlantUML）。"""

import pytest

from app.models.uml import ClassModel, DeploymentModel, DiagramType, SequenceModel
from app.renderers.plantuml import (
    inject_skin,
    render_class_plantuml,
    render_deployment_plantuml,
    render_sequence_plantuml,
    render_uml_plantuml,
)

# ============================================================================
# 类图
# ============================================================================


def _class_model(**overrides) -> ClassModel:
    data = {
        "type": "class",
        "title": "选课系统",
        "classes": [
            {
                "name": "Person",
                "is_abstract": True,
                "attributes": [{"name": "name", "type": "String", "visibility": "-"}],
                "methods": [
                    {
                        "name": "describe",
                        "return_type": "String",
                        "visibility": "+",
                        "is_abstract": True,
                    }
                ],
            },
            {
                "name": "Student",
                "attributes": [
                    {"name": "studentId", "type": "String", "visibility": "-"},
                    {"name": "count", "type": "int", "visibility": "#", "is_static": True},
                ],
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "course", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                    }
                ],
            },
            {"name": "Course", "attributes": [{"name": "title", "type": "String", "visibility": "#"}]},
            {
                "name": "Enrollable",
                "is_interface": True,
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "course", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                        "is_abstract": True,
                    }
                ],
            },
        ],
        "relations": [
            {"type": "generalization", "from": "Student", "to": "Person"},
            {"type": "realization", "from": "Student", "to": "Enrollable"},
            {
                "type": "composition",
                "from": "Student",
                "to": "Course",
                "target_multiplicity": "1..*",
            },
        ],
    }
    data.update(overrides)
    return ClassModel.model_validate(data)


def test_class_wrapped_by_startuml_enduml():
    out = render_class_plantuml(_class_model())
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")


def test_class_title_rendered():
    assert "title 选课系统" in render_class_plantuml(_class_model())


def test_class_keywords_and_names():
    """抽象类/接口/普通类关键字正确，中文类名保留。"""
    out = render_class_plantuml(_class_model())
    assert 'abstract class "Person" as class_1' in out
    assert 'class "Student" as class_2' in out
    assert 'interface "Enrollable" as class_4' in out


def test_class_members_visibility_and_type():
    """属性带可见性前缀，方法带参数与返回类型。"""
    out = render_class_plantuml(_class_model())
    assert "-name: String" in out
    assert "+enroll(course: Course): boolean" in out
    assert "#title: String" in out


def test_class_static_and_abstract_modifiers():
    """静态属性输出 {static}，抽象方法输出 {abstract}。"""
    out = render_class_plantuml(_class_model())
    assert "{static} #count: int" in out
    assert "{abstract} +describe(): String" in out


def test_class_generalization_direction():
    """泛化方向：父类 <|-- 子类（Person <|-- Student）。"""
    out = render_class_plantuml(_class_model())
    assert "class_1 <|-- class_2" in out
    assert "class_2 <|-- class_1" not in out


def test_class_realization_direction():
    """实现方向：接口 <|.. 实现类（Enrollable <|.. Student）。"""
    out = render_class_plantuml(_class_model())
    assert "class_4 <|.. class_2" in out


def test_class_composition_multiplicity():
    """组合关系输出整体 *-- 部分 与目标多重性。"""
    out = render_class_plantuml(_class_model())
    assert 'class_2 *-- "1..*" class_3' in out


def test_class_dependency_direction():
    """依赖方向：源 ..> 目标。"""
    model = _class_model(
        relations=[{"type": "dependency", "from": "Student", "to": "Course"}]
    )
    out = render_class_plantuml(model)
    assert "class_2 ..> class_3" in out


def test_class_aggregation_arrow():
    model = _class_model(
        relations=[{"type": "aggregation", "from": "Student", "to": "Course"}]
    )
    assert "class_2 o-- class_3" in render_class_plantuml(model)


def test_class_association_arrow():
    model = _class_model(
        relations=[{"type": "association", "from": "Student", "to": "Course"}]
    )
    assert "class_2 -- class_3" in render_class_plantuml(model)


def test_class_same_input_same_output():
    assert render_class_plantuml(_class_model()) == render_class_plantuml(_class_model())


def test_class_minimal_model():
    out = render_class_plantuml(ClassModel())
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_class_non_model_rejected():
    with pytest.raises(TypeError):
        render_class_plantuml({"type": "class"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        render_class_plantuml(None)  # type: ignore[arg-type]


def test_class_inject_skin_style():
    src = render_class_plantuml(_class_model())
    styled = inject_skin(src, DiagramType.CLASS)
    assert "skinparam class" in styled
    assert "skinparam interface" in styled
    assert "skinparam" not in src  # 原始源码保持纯净


# ============================================================================
# 时序图
# ============================================================================


def _sequence_model(**overrides) -> SequenceModel:
    data = {
        "type": "sequence",
        "title": "选课",
        "lifelines": [
            {"name": "学生", "kind": "actor"},
            {"name": "选课控制器", "kind": "control"},
            {"name": "课程仓储", "kind": "entity"},
        ],
        "messages": [
            {"from": "学生", "to": "选课控制器", "label": "enroll(courseId)", "kind": "sync", "order": 1},
            {"from": "选课控制器", "to": "课程仓储", "label": "find(courseId)", "kind": "sync", "order": 2},
            {"from": "课程仓储", "to": "选课控制器", "label": "return course", "kind": "return", "order": 3},
            {"from": "选课控制器", "to": "学生", "label": "return 结果", "kind": "return", "order": 4},
        ],
        "fragments": [
            {"kind": "alt", "condition": "课程存在", "start_order": 2, "end_order": 3}
        ],
    }
    data.update(overrides)
    # 覆盖 messages 时默认片段区间会失效，需一并清空（除非显式指定 fragments）
    if "messages" in overrides and "fragments" not in overrides:
        data["fragments"] = []
    return SequenceModel.model_validate(data)


def test_sequence_wrapped():
    out = render_sequence_plantuml(_sequence_model())
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_sequence_lifeline_keywords():
    out = render_sequence_plantuml(_sequence_model())
    assert 'actor "学生" as l_1' in out
    assert 'control "选课控制器" as l_2' in out
    assert 'entity "课程仓储" as l_3' in out


def test_sequence_sync_and_return_arrows():
    out = render_sequence_plantuml(_sequence_model())
    assert "l_1 -> l_2 : enroll(courseId)" in out
    assert "l_3 --> l_2 : return course" in out
    assert "l_2 --> l_1 : return 结果" in out


def test_sequence_async_arrow():
    model = _sequence_model(
        messages=[{"from": "学生", "to": "选课控制器", "label": "notify()", "kind": "async", "order": 1}]
    )
    assert "l_1 ->> l_2 : notify()" in render_sequence_plantuml(model)


def test_sequence_create_and_destroy_arrows():
    model = _sequence_model(
        messages=[
            {"from": "选课控制器", "to": "课程仓储", "label": "new()", "kind": "create", "order": 1},
            {"from": "选课控制器", "to": "课程仓储", "label": "close()", "kind": "destroy", "order": 2},
        ]
    )
    out = render_sequence_plantuml(model)
    assert "l_2 -> l_3 : new()" in out
    assert "l_2 ->x l_3 : close()" in out


def test_sequence_messages_sorted_by_order():
    """输入顺序打乱时按 order 升序输出。"""
    model = _sequence_model(
        messages=[
            {"from": "选课控制器", "to": "学生", "label": "second()", "kind": "return", "order": 2},
            {"from": "学生", "to": "选课控制器", "label": "first()", "kind": "sync", "order": 1},
        ]
    )
    out = render_sequence_plantuml(model)
    assert out.index("first()") < out.index("second()")


def test_sequence_fragment_block():
    """片段在 start_order 开块、end_order 闭块。"""
    out = render_sequence_plantuml(_sequence_model())
    lines = out.splitlines()
    start = lines.index("alt 课程存在")
    end = lines.index("end")
    assert start < end
    assert any("find(courseId)" in line for line in lines[start:end])
    assert any("return course" in line for line in lines[start:end])


def test_sequence_all_fragment_kinds():
    for kind in ("alt", "loop", "opt", "par"):
        model = _sequence_model(
            fragments=[{"kind": kind, "condition": "c", "start_order": 2, "end_order": 3}]
        )
        out = render_sequence_plantuml(model)
        assert f"{kind} c" in out


def test_sequence_same_input_same_output():
    assert render_sequence_plantuml(_sequence_model()) == render_sequence_plantuml(_sequence_model())


def test_sequence_minimal_model():
    out = render_sequence_plantuml(SequenceModel())
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_sequence_non_model_rejected():
    with pytest.raises(TypeError):
        render_sequence_plantuml({"type": "sequence"})  # type: ignore[arg-type]


def test_sequence_inject_skin_style():
    src = render_sequence_plantuml(_sequence_model())
    styled = inject_skin(src, DiagramType.SEQUENCE)
    assert "skinparam sequence" in styled
    assert "skinparam" not in src


# ============================================================================
# 部署图
# ============================================================================


def _deployment_model(**overrides) -> DeploymentModel:
    data = {
        "type": "deployment",
        "title": "K8s 部署",
        "nodes": [
            {"name": "Nginx", "kind": "exec_env", "stereotype": "gateway"},
            {"name": "K8s", "kind": "exec_env", "stereotype": "k8s"},
            {"name": "MySQL", "kind": "device", "stereotype": "db"},
        ],
        "artifacts": [{"name": "order.jar", "deployed_on": "MySQL"}],
        "associations": [
            {"from": "Nginx", "to": "K8s", "kind": "communication"},
            {"from": "K8s", "to": "MySQL", "kind": "dependency"},
        ],
    }
    data.update(overrides)
    return DeploymentModel.model_validate(data)


def test_deployment_wrapped():
    out = render_deployment_plantuml(_deployment_model())
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_deployment_node_keywords_and_stereotypes():
    out = render_deployment_plantuml(_deployment_model())
    assert 'node "Nginx" as n_1 <<gateway>>' in out
    assert 'node "K8s" as n_2 <<k8s>>' in out
    # 物理设备用 node + <<device>>（PlantUML 无独立 device 关键字，写了会语法报错）
    assert 'node "MySQL" as n_3 <<device>> <<db>>' in out


def test_deployment_never_emits_device_keyword():
    """回归防线：`device "x" as n` 在 PlantUML 中非法，必须走 node + <<device>>。"""
    out = render_deployment_plantuml(_deployment_model())
    for line in out.splitlines():
        assert not line.strip().startswith("device "), line


def test_deployment_device_without_stereotype():
    model = DeploymentModel.model_validate(
        {"type": "deployment", "nodes": [{"name": "Server", "kind": "device"}]}
    )
    out = render_deployment_plantuml(model)
    assert 'node "Server" as n_1 <<device>>' in out


def test_deployment_artifact_and_host_link():
    out = render_deployment_plantuml(_deployment_model())
    assert 'artifact "order.jar" as a_1' in out
    assert "n_3 -- a_1" in out


def test_deployment_communication_arrow():
    assert "n_1 <--> n_2" in render_deployment_plantuml(_deployment_model())


def test_deployment_dependency_arrow():
    assert "n_2 ..> n_3" in render_deployment_plantuml(_deployment_model())


def test_deployment_association_arrow():
    model = _deployment_model(associations=[{"from": "Nginx", "to": "K8s", "kind": "association"}])
    assert "n_1 -- n_2" in render_deployment_plantuml(model)


def test_deployment_same_input_same_output():
    assert render_deployment_plantuml(_deployment_model()) == render_deployment_plantuml(
        _deployment_model()
    )


def test_deployment_minimal_model():
    out = render_deployment_plantuml(DeploymentModel())
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")


def test_deployment_non_model_rejected():
    with pytest.raises(TypeError):
        render_deployment_plantuml({"type": "deployment"})  # type: ignore[arg-type]


def test_deployment_inject_skin_style():
    src = render_deployment_plantuml(_deployment_model())
    styled = inject_skin(src, DiagramType.DEPLOYMENT)
    assert "skinparam node" in styled and "skinparam device" in styled
    assert "skinparam" not in src


# ============================================================================
# 统一分发
# ============================================================================


def test_render_uml_plantuml_dispatches_new_types():
    c = _class_model()
    s = _sequence_model()
    d = _deployment_model()
    assert render_uml_plantuml(c) == render_class_plantuml(c)
    assert render_uml_plantuml(s) == render_sequence_plantuml(s)
    assert render_uml_plantuml(d) == render_deployment_plantuml(d)
    for model in (c, s, d):
        assert render_uml_plantuml(model).startswith("@startuml")
