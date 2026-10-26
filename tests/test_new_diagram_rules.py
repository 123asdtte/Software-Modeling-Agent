"""类图 / 时序图 / 部署图质检规则测试（纯函数，不调 LLM、不渲染）。"""

from app.models.uml import ClassModel, DeploymentModel, SequenceModel
from app.rules.class_rules import check_class_model
from app.rules.deployment_rules import check_deployment_model
from app.rules.sequence_rules import check_sequence_model


def _ids(report) -> set[str]:
    return {i.rule_id for i in report.issues}


def _level(report, rule_id: str) -> str | None:
    return next((i.level for i in report.issues if i.rule_id == rule_id), None)


# ============================================================================
# 类图规则
# ============================================================================


def _class_model(**overrides) -> ClassModel:
    data = {
        "type": "class",
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
                "attributes": [{"name": "studentId", "type": "String", "visibility": "-"}],
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


def test_class_valid_passes():
    """结构完整的类图质检通过。"""
    report = check_class_model(_class_model())
    assert report.passed is True
    assert report.diagram_type.value == "class"


def test_class_cycle_detected():
    """继承链路成环 → CL-CYC error。"""
    data = {
        "type": "class",
        "classes": [{"name": "A"}, {"name": "B"}],
        "relations": [
            {"type": "generalization", "from": "A", "to": "B"},
            {"type": "generalization", "from": "B", "to": "A"},
        ],
    }
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is False
    assert _level(report, "CL-CYC") == "error"
    assert _ids(report) >= {"CL-CYC", "CL-EMPTY"}


def test_class_missing_visibility_warns():
    """属性/方法未标可见性 → CL-V1 warning（不影响 passed）。"""
    data = {
        "type": "class",
        "classes": [
            {
                "name": "A",
                "attributes": [{"name": "x", "type": "int"}],
                "methods": [{"name": "run", "return_type": "void"}],
            }
        ],
    }
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is True
    assert _level(report, "CL-V1") == "warning"
    assert sum(1 for i in report.issues if i.rule_id == "CL-V1") == 2


def test_class_abstract_method_in_concrete_class_errors():
    """具体类含抽象方法 → CL-ABS error。"""
    data = {
        "type": "class",
        "classes": [
            {
                "name": "Concrete",
                "methods": [{"name": "doIt", "return_type": "void", "is_abstract": True}],
            }
        ],
    }
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is False
    assert _level(report, "CL-ABS") == "error"


def test_class_composition_without_multiplicity_warns():
    """组合/聚合缺多重性 → CL-MULTI warning。"""
    data = {
        "type": "class",
        "classes": [{"name": "Order"}, {"name": "Item"}],
        "relations": [{"type": "composition", "from": "Order", "to": "Item"}],
    }
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is True
    assert _level(report, "CL-MULTI") == "warning"


def test_class_empty_class_info():
    """空类只给 info，不阻断。"""
    data = {"type": "class", "classes": [{"name": "Placeholder"}]}
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is True
    assert _level(report, "CL-EMPTY") == "info"


def test_class_interface_with_attributes_warns():
    """接口含实例属性 → CL-IFACE warning。"""
    data = {
        "type": "class",
        "classes": [
            {
                "name": "Service",
                "is_interface": True,
                "attributes": [{"name": "x", "type": "int", "visibility": "-"}],
            }
        ],
    }
    report = check_class_model(ClassModel.model_validate(data))
    assert report.passed is True
    assert _level(report, "CL-IFACE") == "warning"


# ============================================================================
# 时序图规则
# ============================================================================


def _sequence_model(**overrides) -> SequenceModel:
    data = {
        "type": "sequence",
        "lifelines": [{"name": "学生", "kind": "actor"}, {"name": "控制器", "kind": "control"}],
        "messages": [
            {"from": "学生", "to": "控制器", "label": "enroll()", "kind": "sync", "order": 1},
            {"from": "控制器", "to": "学生", "label": "return ok", "kind": "return", "order": 2},
        ],
    }
    data.update(overrides)
    return SequenceModel.model_validate(data)


def test_sequence_valid_passes():
    """完整时序图质检通过。"""
    report = check_sequence_model(_sequence_model())
    assert report.passed is True
    assert report.diagram_type.value == "sequence"


def test_sequence_no_lifelines_errors():
    """无生命线 → SQ-EMPTY error。"""
    report = check_sequence_model(SequenceModel())
    assert report.passed is False
    assert _level(report, "SQ-EMPTY") == "error"


def test_sequence_no_messages_warns():
    """只有生命线没有消息 → SQ-EMPTY warning。"""
    report = check_sequence_model(SequenceModel(lifelines=[{"name": "学生"}]))
    assert report.passed is True
    assert _level(report, "SQ-EMPTY") == "warning"


def test_sequence_empty_label_warns():
    """消息未标注操作名 → SQ-LABEL warning。"""
    report = check_sequence_model(
        _sequence_model(
            messages=[
                {"from": "学生", "to": "控制器", "label": "", "kind": "sync", "order": 1}
            ]
        )
    )
    assert report.passed is True
    assert _level(report, "SQ-LABEL") == "warning"


# ============================================================================
# 部署图规则
# ============================================================================


def _deployment_model(**overrides) -> DeploymentModel:
    data = {
        "type": "deployment",
        "nodes": [
            {"name": "Nginx", "kind": "exec_env", "stereotype": "gateway"},
            {"name": "K8s", "kind": "exec_env", "stereotype": "k8s"},
            {"name": "order-service", "kind": "exec_env", "stereotype": "deployment"},
            {"name": "MySQL", "kind": "device", "stereotype": "db"},
        ],
        "artifacts": [{"name": "order.jar", "deployed_on": "order-service"}],
        "associations": [{"from": "Nginx", "to": "K8s", "kind": "communication"}],
    }
    data.update(overrides)
    return DeploymentModel.model_validate(data)


def test_deployment_valid_passes():
    """完整部署图质检通过。"""
    report = check_deployment_model(_deployment_model())
    assert report.passed is True
    assert report.diagram_type.value == "deployment"


def test_deployment_empty_errors():
    """空部署图 → DEP-EMPTY error。"""
    report = check_deployment_model(DeploymentModel())
    assert report.passed is False
    assert _level(report, "DEP-EMPTY") == "error"


def test_deployment_artifact_without_host_warns():
    """构件未指定部署节点 → DEP-UNDEP warning。"""
    report = check_deployment_model(
        _deployment_model(artifacts=[{"name": "loose.jar"}])
    )
    assert report.passed is True
    assert _level(report, "DEP-UNDEP") == "warning"


def test_deployment_k8s_service_without_workload_warns():
    """有 Service 无工作负载 → DEP-K8S warning。"""
    report = check_deployment_model(
        _deployment_model(
            nodes=[
                {"name": "svc", "kind": "exec_env", "stereotype": "service"},
                {"name": "db", "kind": "device", "stereotype": "db"},
            ],
            associations=[{"from": "svc", "to": "db", "kind": "dependency"}],
            artifacts=[],
        )
    )
    assert report.passed is True
    assert _level(report, "DEP-K8S") == "warning"


def test_deployment_k8s_ingress_without_service_warns():
    """有 Ingress 无 Service → DEP-K8S warning。"""
    report = check_deployment_model(
        _deployment_model(
            nodes=[
                {"name": "ing", "kind": "exec_env", "stereotype": "ingress"},
                {"name": "pod", "kind": "exec_env", "stereotype": "pod"},
            ],
            associations=[{"from": "ing", "to": "pod", "kind": "communication"}],
            artifacts=[],
        )
    )
    assert report.passed is True
    assert _level(report, "DEP-K8S") == "warning"


def test_deployment_k8s_full_chain_passes_without_k8s_warning():
    """ingress → service → pod 完整链路不触发 K8s 告警。"""
    report = check_deployment_model(
        _deployment_model(
            nodes=[
                {"name": "ing", "kind": "exec_env", "stereotype": "ingress"},
                {"name": "svc", "kind": "exec_env", "stereotype": "service"},
                {"name": "pod", "kind": "exec_env", "stereotype": "pod"},
            ],
            associations=[
                {"from": "ing", "to": "svc", "kind": "communication"},
                {"from": "svc", "to": "pod", "kind": "communication"},
            ],
            artifacts=[],
        )
    )
    assert report.passed is True
    assert "DEP-K8S" not in _ids(report)
