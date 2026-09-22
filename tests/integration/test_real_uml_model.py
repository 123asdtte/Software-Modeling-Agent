"""可选的真实 LLM 集成测试（默认 skip，显式启用时才消耗 Token）。

启用条件（两者都满足才真正执行）：
    RUN_INTEGRATION_TESTS=1
    DEEPSEEK_API_KEY 已配置（含有效 Base URL / Model）

执行：RUN_INTEGRATION_TESTS=1 pytest -m integration -q
默认 pytest -q 完全离线，不受本文件影响。
"""

import os

import pytest

from app.chains.uml_chain import generate_usecase_model
from app.renderers.plantuml import render_usecase_plantuml
from app.rules.usecase_rules import check_usecase_model

pytestmark = pytest.mark.integration

_REQUIREMENT = "学生可以发布商品，管理员审核商品，买家可以购买商品和浏览商品"


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS") == "1" and bool(os.getenv("DEEPSEEK_API_KEY"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_model_generates_valid_usecase_model():
    """真实模型：返回合法 UseCaseModel → 渲染 → 质检全链路可用。"""
    if not _integration_enabled():
        pytest.skip("未启用集成测试（需 RUN_INTEGRATION_TESTS=1 与 DEEPSEEK_API_KEY）")

    model = await generate_usecase_model(_REQUIREMENT)

    # 结构化输出测试：Pydantic 校验已通过，字段非空
    assert model.system.strip()
    assert len(model.actors) >= 1
    assert len(model.usecases) >= 1
    assert all(uc.name.strip() for uc in model.usecases)

    # 确定性渲染：源码非空且结构完整
    plantuml = render_usecase_plantuml(model)
    assert plantuml.startswith("@startuml") and plantuml.rstrip().endswith("@enduml")
    assert "left to right direction" in plantuml

    # 规则质检：真实模型输出应能通过（error 级）
    report = check_usecase_model(model)
    assert report.error_count == 0, f"真实模型输出存在 error：{report.issues}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_response_never_contains_api_key():
    """真实响应不包含 API Key（密钥不进日志/响应）。"""
    if not _integration_enabled():
        pytest.skip("未启用集成测试")

    from app.config.settings import get_settings

    key = get_settings().deepseek_api_key
    model = await generate_usecase_model("学生借书，管理员处理归还")
    assert key not in model.model_dump_json()
    assert key not in render_usecase_plantuml(model)
