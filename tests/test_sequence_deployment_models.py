"""时序图 / 部署图领域模型测试（纯模型校验，不调 LLM、不渲染）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import (
    DeploymentModel,
    DiagramType,
    MessageKind,
    SequenceModel,
    parse_uml_model,
)

# ============================================================================
# 时序图
# ============================================================================


def valid_sequence_data() -> dict:
    return {
        "type": "sequence",
        "title": "选课",
        "lifelines": [
            {"name": "学生", "kind": "actor"},
            {"name": "选课控制器", "kind": "control", "classifier": "EnrollController"},
            {"name": "课程仓储", "kind": "entity", "classifier": "CourseRepository"},
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


def test_sequence_model_valid():
    """合法时序图模型正常构造。"""
    m = SequenceModel.model_validate(valid_sequence_data())
    assert m.type == DiagramType.SEQUENCE
    assert len(m.lifelines) == 3 and len(m.messages) == 4 and len(m.fragments) == 1


def test_sequence_defaults_empty():
    """缺省列表合法。"""
    m = SequenceModel()
    assert m.lifelines == [] and m.messages == [] and m.fragments == []


def test_sequence_duplicate_lifeline_rejected():
    """重复生命线名称必须拒绝。"""
    data = valid_sequence_data()
    data["lifelines"].append({"name": "学生", "kind": "actor"})
    with pytest.raises(ValidationError, match="重复的生命线名称"):
        SequenceModel.model_validate(data)


def test_sequence_message_source_must_exist():
    """消息 from 端必须是已定义生命线。"""
    data = valid_sequence_data()
    data["messages"][0]["from"] = "幽灵"
    with pytest.raises(ValidationError, match="from 端生命线不存在"):
        SequenceModel.model_validate(data)


def test_sequence_message_target_must_exist():
    """消息 to 端必须是已定义生命线。"""
    data = valid_sequence_data()
    data["messages"][0]["to"] = "幽灵"
    with pytest.raises(ValidationError, match="to 端生命线不存在"):
        SequenceModel.model_validate(data)


def test_sequence_duplicate_order_rejected():
    """重复消息顺序号必须拒绝（渲染顺序不确定）。"""
    data = valid_sequence_data()
    data["messages"][1]["order"] = 1
    with pytest.raises(ValidationError, match="重复的消息顺序号"):
        SequenceModel.model_validate(data)


def test_sequence_order_must_be_positive():
    """顺序号必须 >= 1。"""
    data = valid_sequence_data()
    data["messages"][0]["order"] = 0
    with pytest.raises(ValidationError):
        SequenceModel.model_validate(data)


def test_sequence_all_message_kinds_accepted():
    """五种消息类型全部合法。"""
    for kind in ("sync", "async", "return", "create", "destroy"):
        data = valid_sequence_data()
        data["messages"][0]["kind"] = kind
        m = SequenceModel.model_validate(data)
        assert m.messages[0].kind.value == kind
        assert MessageKind(kind)  # 枚举可反查


def test_sequence_fragment_range_order():
    """片段 start > end 必须拒绝。"""
    data = valid_sequence_data()
    data["fragments"] = [{"kind": "alt", "condition": "x", "start_order": 3, "end_order": 2}]
    with pytest.raises(ValidationError, match="不能大于"):
        SequenceModel.model_validate(data)


def test_sequence_fragment_bounds_must_hit_messages():
    """片段边界必须对应真实消息。"""
    data = valid_sequence_data()
    data["fragments"] = [{"kind": "alt", "condition": "x", "start_order": 2, "end_order": 99}]
    with pytest.raises(ValidationError, match="无对应消息"):
        SequenceModel.model_validate(data)


def test_sequence_overlapping_fragments_rejected():
    """v1 不支持重叠/嵌套片段。"""
    data = valid_sequence_data()
    data["fragments"] = [
        {"kind": "alt", "condition": "a", "start_order": 1, "end_order": 3},
        {"kind": "loop", "condition": "b", "start_order": 2, "end_order": 4},
    ]
    with pytest.raises(ValidationError, match="重叠/嵌套"):
        SequenceModel.model_validate(data)


def test_sequence_adjacent_fragments_allowed():
    """首尾相接（不重叠）的片段合法。"""
    data = valid_sequence_data()
    data["fragments"] = [
        {"kind": "alt", "condition": "a", "start_order": 1, "end_order": 2},
        {"kind": "opt", "condition": "b", "start_order": 3, "end_order": 4},
    ]
    m = SequenceModel.model_validate(data)
    assert len(m.fragments) == 2


def test_sequence_fragment_kind_whitelist():
    """片段类型仅 alt/loop/opt/par。

    注：`while` 等常见同义写法由模型层归一为 loop（见 test_enum_tolerance.py），
    因此这里用真正无法识别的值验证白名单仍然生效。
    """
    data = valid_sequence_data()
    data["fragments"] = [{"kind": "maybe", "condition": "x", "start_order": 1, "end_order": 2}]
    with pytest.raises(ValidationError):
        SequenceModel.model_validate(data)


def test_sequence_alias_serialization_locked():
    """by_alias 输出 from/to。"""
    m = SequenceModel.model_validate(valid_sequence_data())
    dumped = m.model_dump(by_alias=True)
    assert dumped["messages"][0]["from"] == "学生"
    assert dumped["messages"][0]["to"] == "选课控制器"


# ============================================================================
# 部署图
# ============================================================================


def valid_deployment_data() -> dict:
    return {
        "type": "deployment",
        "title": "K8s 部署",
        "nodes": [
            {"name": "Nginx", "kind": "exec_env", "stereotype": "gateway", "spec": "2C4G"},
            {"name": "K8s", "kind": "exec_env", "stereotype": "k8s"},
            {"name": "order-service", "kind": "exec_env", "stereotype": "deployment", "spec": "replicas=3"},
            {"name": "MySQL", "kind": "device", "stereotype": "db"},
        ],
        "artifacts": [{"name": "order.jar", "deployed_on": "order-service"}],
        "associations": [
            {"from": "Nginx", "to": "K8s", "kind": "communication"},
            {"from": "order-service", "to": "MySQL", "kind": "dependency"},
        ],
    }


def test_deployment_model_valid():
    """合法部署图模型正常构造。"""
    m = DeploymentModel.model_validate(valid_deployment_data())
    assert m.type == DiagramType.DEPLOYMENT
    assert len(m.nodes) == 4 and len(m.artifacts) == 1 and len(m.associations) == 2


def test_deployment_defaults_empty():
    """缺省列表合法。"""
    m = DeploymentModel()
    assert m.nodes == [] and m.artifacts == [] and m.associations == []


def test_deployment_duplicate_node_rejected():
    """重复节点名必须拒绝。"""
    data = valid_deployment_data()
    data["nodes"].append({"name": "K8s", "kind": "exec_env"})
    with pytest.raises(ValidationError, match="重复的节点名称"):
        DeploymentModel.model_validate(data)


def test_deployment_duplicate_artifact_rejected():
    """重复构件名必须拒绝。"""
    data = valid_deployment_data()
    data["artifacts"].append({"name": "order.jar"})
    with pytest.raises(ValidationError, match="重复的构件名称"):
        DeploymentModel.model_validate(data)


def test_deployment_artifact_host_must_exist():
    """构件 deployed_on 必须是已定义节点。"""
    data = valid_deployment_data()
    data["artifacts"][0]["deployed_on"] = "幽灵节点"
    with pytest.raises(ValidationError, match="不存在的节点"):
        DeploymentModel.model_validate(data)


def test_deployment_association_endpoint_must_exist():
    """部署关系端点必须是节点或构件。"""
    data = valid_deployment_data()
    data["associations"][0]["from"] = "幽灵"
    with pytest.raises(ValidationError, match="from 端不存在"):
        DeploymentModel.model_validate(data)


def test_deployment_association_can_point_to_artifact():
    """部署关系端点允许构件（节点 ↔ 构件）。"""
    data = valid_deployment_data()
    data["associations"].append({"from": "K8s", "to": "order.jar", "kind": "association"})
    m = DeploymentModel.model_validate(data)
    assert m.associations[-1].target_id == "order.jar"


def test_deployment_node_kind_enum():
    """节点类型仅 device / exec_env。"""
    for kind in ("device", "exec_env"):
        m = DeploymentModel.model_validate(
            {"type": "deployment", "nodes": [{"name": "N", "kind": kind}]}
        )
        assert m.nodes[0].kind.value == kind
    with pytest.raises(ValidationError):
        DeploymentModel.model_validate(
            {"type": "deployment", "nodes": [{"name": "N", "kind": "vm"}]}
        )


def test_deployment_association_kind_enum():
    """部署关系类型仅 communication / dependency / association。"""
    for kind in ("communication", "dependency", "association"):
        data = valid_deployment_data()
        data["associations"] = [{"from": "Nginx", "to": "K8s", "kind": kind}]
        m = DeploymentModel.model_validate(data)
        assert m.associations[0].kind.value == kind


def test_deployment_alias_serialization_locked():
    """by_alias 输出 from/to。"""
    m = DeploymentModel.model_validate(valid_deployment_data())
    dumped = m.model_dump(by_alias=True)
    assert dumped["associations"][0]["from"] == "Nginx"
    assert dumped["associations"][0]["to"] == "K8s"


# ============================================================================
# 分发表决
# ============================================================================


def test_parse_uml_model_dispatch_sequence_deployment():
    """parse_uml_model 按 type 分派为对应模型类。"""
    assert isinstance(parse_uml_model(valid_sequence_data()), SequenceModel)
    assert isinstance(parse_uml_model(valid_deployment_data()), DeploymentModel)
