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


def test_usecase_endpoint_500_on_renderer_bug(monkeypatch):
    """renderer 内部缺陷：返回固定 500 文案，内部异常不泄露。"""

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)

    def _boom(model):
        raise RuntimeError("路径 C:/secret 泄露尝试")

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "render_usecase_plantuml", _boom)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    assert resp.status_code == 500
    assert "secret" not in resp.json()["detail"]  # 内部细节不泄露


def test_usecase_response_contract(monkeypatch):
    """响应符合 UmlUseCaseResponse 契约（response_model 校验后字段稳定）。"""

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    body = resp.json()
    # 字段名与语义保持不变（评审：response_model 不改变已有字段）
    assert set(body.keys()) == {"diagram_type", "model", "plantuml", "review_report", "render"}
    assert body["diagram_type"] == "usecase"
    # OpenAPI 文档中注册了响应模型
    schema = client.get("/openapi.json").json()
    resp_schema = schema["paths"]["/v1/uml/usecase"]["post"]["responses"]["200"]
    assert "UmlUseCaseResponse" in resp_schema["content"]["application/json"]["schema"]["$ref"]


def test_uml_concurrency_limit_enforced(monkeypatch):
    """UML 并发上限（独立于 PPT/教案闸门）仍然生效。"""
    import asyncio as aio

    import httpx

    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "uml_max_concurrency", 1)
    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "_uml_semaphore", aio.Semaphore(1))

    active = 0
    peak = 0

    async def tracked(requirement, llm_factory=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await aio.sleep(0.05)
        active -= 1
        return _fake_model()

    _patch_chain(monkeypatch, tracked)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            responses = await aio.gather(
                *[ac.post("/v1/uml/usecase", json={"requirement": "并发测试"}) for _ in range(3)]
            )
        assert all(r.status_code == 200 for r in responses)

    aio.run(run())
    assert peak == 1  # UML 专属信号量把并发压到 1


# ---------------- 图片渲染集成（render 字段 / 下载接口）----------------


def test_render_field_rendered_with_download(monkeypatch, tmp_path):
    """渲染环境可用：render.status=rendered + download_url，下载回环成功。"""
    monkeypatch.chdir(tmp_path)

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)
    from app.renderers.diagram_renderer import RenderStatus
    from app.storage.generated_files import save_bytes_atomic

    class _Result:
        status = RenderStatus.RENDERED
        format = "png"

        def __init__(self):
            name = save_bytes_atomic("uml", "png", b"\x89PNG fake")
            self.path = str(tmp_path / "outputs" / "uml" / name)

    import app.api.uml as uml_api

    monkeypatch.setattr(uml_api, "render_plantuml_source", lambda src, fmt: _Result())
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    assert resp.status_code == 200
    render_info = resp.json()["render"]
    assert render_info["status"] == "rendered"
    assert render_info["download_url"].endswith(".png")
    dl = client.get(render_info["download_url"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/")


def test_render_field_source_only_when_env_missing(monkeypatch, tmp_path):
    """渲染环境缺失：仍 200，source_only，plantuml 照常返回。"""
    monkeypatch.chdir(tmp_path)
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "plantuml_jar_path", str(tmp_path / "nope.jar"))

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["render"]["status"] == "source_only"
    assert body["render"]["download_url"] is None
    assert body["plantuml"].startswith("@startuml")


def test_render_disabled_returns_source_only(monkeypatch, tmp_path):
    """请求 render=false 时不渲染（即使环境可用）。"""
    monkeypatch.chdir(tmp_path)

    async def fake_gen(requirement, llm_factory=None):
        return _fake_model()

    _patch_chain(monkeypatch, fake_gen)
    resp = client.post("/v1/uml/usecase", json={"requirement": "学生发布商品", "render": False})
    assert resp.status_code == 200
    assert resp.json()["render"]["status"] == "source_only"


def test_uml_download_rejects_bad_names():
    """下载接口：非法文件名/穿越一律 404。"""
    for bad in ["../../.env", "x.png", "..%2F..%2F.env"]:
        assert client.get(f"/files/uml/{bad}").status_code in (404, 400)
