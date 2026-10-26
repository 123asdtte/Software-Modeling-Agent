"""类图 / 时序图 / 部署图 生成链、意图识别与 API 端点测试（mock LLM，不调真实服务）。"""

import asyncio
import json
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from app.chains.uml_chain import (
    detect_diagram_type,
    generate_class_model,
    generate_deployment_model,
    generate_sequence_model,
    generate_uml_model,
)
from app.main import app
from app.models.uml import ClassModel, DeploymentModel, DiagramType, SequenceModel

client = TestClient(app)


VALID_CLASS_JSON = json.dumps(
    {
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
    },
    ensure_ascii=False,
)

VALID_SEQUENCE_JSON = json.dumps(
    {
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
    },
    ensure_ascii=False,
)

VALID_DEPLOYMENT_JSON = json.dumps(
    {
        "type": "deployment",
        "title": "K8s 部署",
        "nodes": [
            {"name": "Nginx", "kind": "exec_env", "stereotype": "gateway"},
            {"name": "K8s", "kind": "exec_env", "stereotype": "k8s"},
            {"name": "order-service", "kind": "exec_env", "stereotype": "deployment"},
            {"name": "MySQL", "kind": "device", "stereotype": "db"},
        ],
        "artifacts": [{"name": "order.jar", "deployed_on": "order-service"}],
        "associations": [
            {"from": "Nginx", "to": "K8s", "kind": "communication"},
            {"from": "order-service", "to": "MySQL", "kind": "dependency"},
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


# ============================================================================
# 生成链
# ============================================================================


def test_generate_class_model():
    m = _run(generate_class_model("选课系统", llm_factory=_factory(_FakeLLM([VALID_CLASS_JSON]))))
    assert isinstance(m, ClassModel)
    assert m.type == DiagramType.CLASS
    assert m.title == "选课系统"


def test_generate_sequence_model():
    m = _run(generate_sequence_model("选课交互", llm_factory=_factory(_FakeLLM([VALID_SEQUENCE_JSON]))))
    assert isinstance(m, SequenceModel)
    assert m.type == DiagramType.SEQUENCE
    assert len(m.messages) == 4


def test_generate_deployment_model():
    m = _run(
        generate_deployment_model("K8s 部署", llm_factory=_factory(_FakeLLM([VALID_DEPLOYMENT_JSON])))
    )
    assert isinstance(m, DeploymentModel)
    assert m.type == DiagramType.DEPLOYMENT
    assert len(m.nodes) == 4


def test_generate_uml_model_dispatches_new_types():
    c = _run(generate_uml_model(DiagramType.CLASS, "x", llm_factory=_factory(_FakeLLM([VALID_CLASS_JSON]))))
    s = _run(
        generate_uml_model(DiagramType.SEQUENCE, "x", llm_factory=_factory(_FakeLLM([VALID_SEQUENCE_JSON])))
    )
    d = _run(
        generate_uml_model(
            DiagramType.DEPLOYMENT, "x", llm_factory=_factory(_FakeLLM([VALID_DEPLOYMENT_JSON]))
        )
    )
    assert isinstance(c, ClassModel)
    assert isinstance(s, SequenceModel)
    assert isinstance(d, DeploymentModel)


def test_detect_diagram_type_new_types():
    for raw, expected in (
        ("class", DiagramType.CLASS),
        ("sequence", DiagramType.SEQUENCE),
        ("deployment", DiagramType.DEPLOYMENT),
    ):
        payload = json.dumps({"type": raw, "reason": "test"})
        dtype = _run(detect_diagram_type("x", llm_factory=_factory(_FakeLLM([payload]))))
        assert dtype == expected


def test_detect_diagram_type_other_raises():
    payload = json.dumps({"type": "other", "reason": "组件图"})
    with pytest.raises(ValueError, match="unsupported_diagram_type"):
        _run(detect_diagram_type("组件图", llm_factory=_factory(_FakeLLM([payload]))))


# ============================================================================
# API：统一生成端点
# ============================================================================


def _patch_generate(monkeypatch, func) -> None:
    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "generate_uml_model", func)


def test_generate_class_endpoint_ok(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return ClassModel.model_validate(json.loads(VALID_CLASS_JSON))

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "选课系统", "diagram_type": "class", "render": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "class"
    assert body["model"]["title"] == "选课系统"
    assert body["plantuml"].startswith("@startuml")
    assert body["review_report"]["passed"] is True
    # draw.io 导出现已覆盖六图型（与 PlantUML 能力对齐）
    assert body["drawio_download_url"] and body["drawio_download_url"].endswith(".xml")
    # svg 仍仅用例图有自绘渲染器，其余图型保持 null
    assert body["svg_download_url"] is None


def test_generate_sequence_endpoint_ok(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return SequenceModel.model_validate(json.loads(VALID_SEQUENCE_JSON))

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "选课交互", "diagram_type": "sequence", "render": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "sequence"
    assert "alt 课程存在" in body["plantuml"]
    assert body["review_report"]["passed"] is True
    assert body["drawio_download_url"] and body["drawio_download_url"].endswith(".xml")


def test_generate_deployment_endpoint_ok(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return DeploymentModel.model_validate(json.loads(VALID_DEPLOYMENT_JSON))

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "K8s 部署", "diagram_type": "deployment", "render": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "deployment"
    assert 'node "MySQL" as n_4 <<device>>' in body["plantuml"]
    assert body["review_report"]["passed"] is True
    assert body["drawio_download_url"] and body["drawio_download_url"].endswith(".xml")


@pytest.mark.parametrize(
    ("dtype", "model_json"),
    [
        ("class", VALID_CLASS_JSON),
        ("sequence", VALID_SEQUENCE_JSON),
        ("deployment", VALID_DEPLOYMENT_JSON),
    ],
)
def test_drawio_download_is_valid_xml(monkeypatch, dtype, model_json):
    """draw.io 下载链接必须可访问且内容是合法 mxfile（回归：曾经只给 PlantUML 源码）。"""
    model_cls = {"class": ClassModel, "sequence": SequenceModel, "deployment": DeploymentModel}[dtype]

    async def fake(diagram_type, requirement, llm_factory=None):
        return model_cls.model_validate(json.loads(model_json))

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "x", "diagram_type": dtype, "render": False},
    )
    assert resp.status_code == 200
    url = resp.json()["drawio_download_url"]
    assert url

    file_resp = client.get(url)
    assert file_resp.status_code == 200
    root = ElementTree.fromstring(file_resp.text)
    assert root.tag == "mxfile"
    assert root.find(".//diagram") is not None
    assert len(root.findall(".//mxCell")) > 2


def test_generate_auto_detect_class(monkeypatch):
    async def fake_detect(requirement, llm_factory=None):
        return DiagramType.CLASS

    async def fake_gen(diagram_type, requirement, llm_factory=None):
        assert diagram_type == DiagramType.CLASS
        return ClassModel.model_validate(json.loads(VALID_CLASS_JSON))

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "detect_diagram_type", fake_detect)
    monkeypatch.setattr(uml_api, "generate_uml_model", fake_gen)
    resp = client.post(
        "/v1/uml/generate", json={"requirement": "画类图", "diagram_type": "auto", "render": False}
    )
    assert resp.status_code == 200
    assert resp.json()["diagram_type"] == "class"


def test_generate_unsupported_component_422():
    """component 仍未支持 → 422。"""
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "x", "diagram_type": "component", "render": False},
    )
    assert resp.status_code == 422


# ============================================================================
# 空模型兜底：需求与图型不匹配时不允许返回「只有标题」的假成功
# ============================================================================


def test_generate_empty_class_model_422(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return ClassModel.model_validate({"type": "class", "title": "空图", "classes": []})

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "画个部署图", "diagram_type": "class", "render": True},
    )
    assert resp.status_code == 422
    assert "未能从需求中提取到任何模型元素" in resp.json()["detail"]


def test_generate_empty_deployment_model_422(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return DeploymentModel.model_validate({"type": "deployment", "nodes": []})

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "学生选课的类图", "diagram_type": "deployment", "render": True},
    )
    assert resp.status_code == 422


def test_generate_empty_sequence_model_422(monkeypatch):
    async def fake(diagram_type, requirement, llm_factory=None):
        return SequenceModel.model_validate({"type": "sequence", "lifelines": []})

    _patch_generate(monkeypatch, fake)
    resp = client.post(
        "/v1/uml/generate",
        json={"requirement": "画个类图", "diagram_type": "sequence", "render": False},
    )
    assert resp.status_code == 422


# ============================================================================
# API：类图转 Java 代码
# ============================================================================


def test_class_code_endpoint_ok():
    resp = client.post("/v1/uml/class-code", json={"model": json.loads(VALID_CLASS_JSON)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["class_count"] == 4
    assert body["file_count"] == 4
    files = body["files"]
    assert "Student.java" in files
    assert "public class Student extends Person" in files["Student.java"]
    assert "public interface Enrollable" in files["Enrollable.java"]
    assert "package com.example;" in files["Student.java"]


def test_class_code_endpoint_empty_classes_422():
    """空类图没有可转换对象，应明确拒绝而不是返回 0 个文件。"""
    resp = client.post(
        "/v1/uml/class-code",
        json={"model": {"type": "class", "classes": [], "relations": []}},
    )
    assert resp.status_code == 422
    assert "为空" in resp.json()["detail"]


def test_class_code_endpoint_empty_package():
    resp = client.post(
        "/v1/uml/class-code", json={"model": json.loads(VALID_CLASS_JSON), "package": ""}
    )
    assert resp.status_code == 200
    assert "package " not in resp.json()["files"]["Student.java"]


def test_class_code_endpoint_invalid_model_422():
    resp = client.post(
        "/v1/uml/class-code",
        json={"model": {"type": "class", "classes": [{"name": ""}]}},
    )
    assert resp.status_code == 422


def test_class_code_endpoint_wrong_type_422():
    resp = client.post(
        "/v1/uml/class-code",
        json={"model": json.loads(VALID_SEQUENCE_JSON)},
    )
    assert resp.status_code == 422


def test_class_code_endpoint_invalid_package_422():
    resp = client.post(
        "/v1/uml/class-code",
        json={"model": json.loads(VALID_CLASS_JSON), "package": "com.例子"},
    )
    assert resp.status_code == 422


# ============================================================================
# API：对话式修正
# ============================================================================


@pytest.mark.parametrize(
    ("model_json", "dtype", "plantuml"),
    [
        (VALID_CLASS_JSON, "class", "@startuml\nclass_1 <|-- class_2\n@enduml"),
        (VALID_SEQUENCE_JSON, "sequence", "@startuml\nl_1 -> l_2 : x\n@enduml"),
        (VALID_DEPLOYMENT_JSON, "deployment", "@startuml\nn_1 -- n_2\n@enduml"),
    ],
)
def test_chat_adjust_new_types(monkeypatch, model_json, dtype, plantuml):
    async def fake_adjust(current_model, instruction, output_format, llm_factory=None):
        payload = json.loads(model_json)
        return {
            "success": True,
            "reply": "已修正",
            "model": payload,
            "plantuml": plantuml,
            "issues": [],
            "passed": True,
            "diff_summary": "无",
            "render": {"status": "source_only", "format": None, "download_url": None, "reason": None},
        }

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "adjust_uml_model", fake_adjust)
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "微调", "current_model": json.loads(model_json), "format": "png"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"]["type"] == dtype


def test_chat_adjust_unsupported_type_422():
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "x", "current_model": {"type": "component"}, "format": "png"},
    )
    assert resp.status_code == 422


# ============================================================================
# 路由注册取证
# ============================================================================


def test_class_code_route_registered():
    from app.api.uml import router as uml_router

    paths = [r.path for r in uml_router.routes]
    assert "/v1/uml/class-code" in paths
