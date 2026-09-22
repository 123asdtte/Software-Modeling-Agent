"""POST /v1/uml/usecase 端点测试（mock 生成链，不调真实 LLM）。"""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.uml import UseCaseModel

client = TestClient(app)


def _fake_model(**overrides) -> UseCaseModel:
    """可通过规则质检的正常模型（含一条 include 关系，验证 from/to 序列化）。"""
    data = {
        "system": "校园二手交易系统",
        "actors": [{"name": "学生"}, {"name": "管理员"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
            {"id": "UC-03", "name": "浏览商品", "actors": ["学生"]},
        ],
        "relations": [{"type": "include", "from": "UC-02", "to": "UC-01"}],
    }
    data.update(overrides)
    return UseCaseModel.model_validate(data)


def _patch_chain(monkeypatch, func) -> None:
    """patch 必须打在 app.api.uml 命名空间（该模块为顶部 import 绑定），
    打在源模块 uml_chain 上不会生效。"""
    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "generate_usecase_model", func)


def test_usecase_endpoint_ok(monkeypatch):
    """正常链路：200 + diagram_type/model/plantuml/review_report 完整。"""

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品，管理员审核商品"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagram_type"] == "usecase"
    assert body["model"]["system"] == "校园二手交易系统"
    assert body["plantuml"].startswith("@startuml")
    assert body["plantuml"].rstrip().endswith("@enduml")
    assert body["review_report"]["passed"] is True
    # model 序列化使用对外别名 from/to
    assert "from" in json.dumps(body["model"])


def test_usecase_endpoint_422_blank():
    """空白需求（纯空格）返回 422。"""
    resp = client.post("/v1/uml/usecase", json={"requirement": "   "})
    assert resp.status_code == 422


def test_usecase_endpoint_422_too_long():
    """超过 3000 字符返回 422。"""
    resp = client.post("/v1/uml/usecase", json={"requirement": "长" * 3001})
    assert resp.status_code == 422


def test_usecase_endpoint_502_on_structured_error(monkeypatch):
    """结构化生成失败（重试耗尽）返回 502，且不泄露内部异常细节。"""
    from app.core.structured_output import StructuredOutputError

    async def boom(requirement, llm_factory=None):
        raise StructuredOutputError("UseCaseModel", RuntimeError("504 Gateway at https://internal.upstream.example"), 2)

    _patch_chain(monkeypatch, boom)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    assert resp.status_code == 502
    assert "upstream" not in resp.json()["detail"]  # 内部细节不泄露


def test_usecase_endpoint_error_when_review_has_error(monkeypatch):
    """质检存在 error：仍返回 200，但 review_report.passed=False。"""

    async def fake_gen(requirement, llm_factory=None):
        # “数据库”作为参与者 → UC-B1 error
        return _fake_model(
            actors=[{"name": "数据库"}, {"name": "管理员"}],
            usecases=[
                {"id": "UC-01", "name": "备份数据", "actors": ["数据库"]},
                {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
                {"id": "UC-03", "name": "导出报表", "actors": ["数据库"]},
            ],
            relations=[],
        )

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "管理员审核商品"})
    assert resp.status_code == 200
    assert resp.json()["review_report"]["passed"] is False
    assert any(i["level"] == "error" for i in resp.json()["review_report"]["issues"])


def test_usecase_endpoint_warning_only_passes(monkeypatch):
    """质检只有 warning（孤立参与者）：200 且 passed=True。"""

    async def fake_gen(requirement, llm_factory=None):
        # 访客无任何关联 → UC-R3 warning；用例 3 个满足 UC-C1
        return _fake_model(actors=[{"name": "学生"}, {"name": "管理员"}, {"name": "访客"}])

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_report"]["passed"] is True
    assert any(i["rule_id"] == "UC-R3" for i in body["review_report"]["issues"])


def test_old_endpoints_still_work():
    """旧端点回归：/health 与路由注册不受 UML 改动影响。"""
    assert client.get("/health").status_code == 200
