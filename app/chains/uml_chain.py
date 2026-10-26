"""UML 用例图结构化生成链：自然语言需求 → UseCaseModel（结构化 JSON）。

评审 P0 约束：LLM 只产出结构化 JSON，最终 PlantUML 由
app.renderers.plantuml.render_usecase_plantuml() 确定性生成。

复用 app.core.structured_output：JSON 提取 / Pydantic 校验 / 重试 /
统一异常全部走 core 工具，支持 llm_factory 注入 Fake LLM。

并发模型（评审 P1 修正）：本模块**不再自建限流**——generate_usecase_model
是单次 LLM 调用，HTTP 请求级并发由 app/api/uml.py 的 _uml_semaphore 统一控制，
且不跨业务模块导入 generation_chain 的私有 semaphore（与 PPT/教案完全隔离）。
"""

import asyncio

from app.config.settings import get_settings
from app.core.structured_output import invoke_structured
from app.models.uml import (
    ActivityModel,
    ClassModel,
    DeploymentModel,
    DiagramType,
    SequenceModel,
    StateMachineModel,
    UseCaseModel,
)
from app.prompts.uml_activity_prompt import ACTIVITY_SYSTEM_PROMPT, ACTIVITY_USER_TMPL
from app.prompts.uml_class_prompt import CLASS_SYSTEM_PROMPT, CLASS_USER_TMPL
from app.prompts.uml_deployment_prompt import DEPLOYMENT_SYSTEM_PROMPT, DEPLOYMENT_USER_TMPL
from app.prompts.uml_intent_prompt import INTENT_SYSTEM_PROMPT, INTENT_USER_TMPL
from app.prompts.uml_prompt import USECASE_SYSTEM_PROMPT, USECASE_USER_TMPL
from app.prompts.uml_sequence_prompt import SEQUENCE_SYSTEM_PROMPT, SEQUENCE_USER_TMPL
from app.prompts.uml_statemachine_prompt import (
    STATEMACHINE_SYSTEM_PROMPT,
    STATEMACHINE_USER_TMPL,
)


def _generate_sync(requirement: str, llm_factory=None) -> UseCaseModel:
    """同步实现：组装消息 → 结构化调用（UML 专属 LLM 超时）。"""
    user = USECASE_USER_TMPL.format(requirement=requirement)
    messages = [("system", USECASE_SYSTEM_PROMPT), ("user", user)]
    return invoke_structured(
        messages,
        UseCaseModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_usecase_model(requirement: str, *, llm_factory=None) -> UseCaseModel:
    """异步生成用例图模型（供 API 调用；测试可注入 llm_factory）。

    Args:
        requirement: 自然语言需求描述（调用方已做非空/长度校验）。
        llm_factory: 可注入 LLM 工厂；缺省用项目工厂（get_llm）。

    Returns:
        UseCaseModel：结构非法（引用/唯一性）会在 pydantic 校验阶段被拒，
        触发重试；重试耗尽抛 StructuredOutputError。
    """
    # to_thread：invoke_structured 为同步阻塞调用，线程化避免卡死事件循环
    return await asyncio.to_thread(_generate_sync, requirement, llm_factory)


def _generate_activity_sync(requirement: str, llm_factory=None) -> ActivityModel:
    user = ACTIVITY_USER_TMPL.format(requirement=requirement)
    return invoke_structured(
        [("system", ACTIVITY_SYSTEM_PROMPT), ("user", user)],
        ActivityModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_activity_model(requirement: str, *, llm_factory=None) -> ActivityModel:
    """异步生成活动图模型。"""
    return await asyncio.to_thread(_generate_activity_sync, requirement, llm_factory)


def _generate_statemachine_sync(requirement: str, llm_factory=None) -> StateMachineModel:
    user = STATEMACHINE_USER_TMPL.format(requirement=requirement)
    return invoke_structured(
        [("system", STATEMACHINE_SYSTEM_PROMPT), ("user", user)],
        StateMachineModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_statemachine_model(requirement: str, *, llm_factory=None) -> StateMachineModel:
    """异步生成状态机图模型。"""
    return await asyncio.to_thread(_generate_statemachine_sync, requirement, llm_factory)


def _generate_class_sync(requirement: str, llm_factory=None) -> ClassModel:
    user = CLASS_USER_TMPL.format(requirement=requirement)
    return invoke_structured(
        [("system", CLASS_SYSTEM_PROMPT), ("user", user)],
        ClassModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_class_model(requirement: str, *, llm_factory=None) -> ClassModel:
    """异步生成类图模型。"""
    return await asyncio.to_thread(_generate_class_sync, requirement, llm_factory)


def _generate_sequence_sync(requirement: str, llm_factory=None) -> SequenceModel:
    user = SEQUENCE_USER_TMPL.format(requirement=requirement)
    return invoke_structured(
        [("system", SEQUENCE_SYSTEM_PROMPT), ("user", user)],
        SequenceModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_sequence_model(requirement: str, *, llm_factory=None) -> SequenceModel:
    """异步生成时序图模型。"""
    return await asyncio.to_thread(_generate_sequence_sync, requirement, llm_factory)


def _generate_deployment_sync(requirement: str, llm_factory=None) -> DeploymentModel:
    user = DEPLOYMENT_USER_TMPL.format(requirement=requirement)
    return invoke_structured(
        [("system", DEPLOYMENT_SYSTEM_PROMPT), ("user", user)],
        DeploymentModel,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )


async def generate_deployment_model(requirement: str, *, llm_factory=None) -> DeploymentModel:
    """异步生成部署图模型。"""
    return await asyncio.to_thread(_generate_deployment_sync, requirement, llm_factory)


async def generate_uml_model(diagram_type: DiagramType, requirement: str, *, llm_factory=None):
    """按图类型分发到对应生成链，返回具体模型实例。"""
    if diagram_type == DiagramType.USECASE:
        return await generate_usecase_model(requirement, llm_factory=llm_factory)
    if diagram_type == DiagramType.ACTIVITY:
        return await generate_activity_model(requirement, llm_factory=llm_factory)
    if diagram_type == DiagramType.STATEMACHINE:
        return await generate_statemachine_model(requirement, llm_factory=llm_factory)
    if diagram_type == DiagramType.CLASS:
        return await generate_class_model(requirement, llm_factory=llm_factory)
    if diagram_type == DiagramType.SEQUENCE:
        return await generate_sequence_model(requirement, llm_factory=llm_factory)
    if diagram_type == DiagramType.DEPLOYMENT:
        return await generate_deployment_model(requirement, llm_factory=llm_factory)
    raise ValueError(f"不支持的图类型：{diagram_type}")


async def detect_diagram_type(requirement: str, *, llm_factory=None) -> DiagramType:
    """LLM 意图识别：用户未指定图型时判断六种图型之一。

    识别为 other（组件图/对象图等未支持）时抛 ValueError，由上层提示后续版本。
    """
    from pydantic import BaseModel, Field

    from app.core.structured_output import invoke_structured

    class IntentResult(BaseModel):
        type: str = Field(description="usecase/activity/statemachine/class/sequence/deployment/other")
        reason: str = ""

    user = INTENT_USER_TMPL.format(requirement=requirement)
    result = await asyncio.to_thread(
        invoke_structured,
        [("system", INTENT_SYSTEM_PROMPT), ("user", user)],
        IntentResult,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().uml_llm_timeout,
    )
    mapping = {
        DiagramType.USECASE.value: DiagramType.USECASE,
        DiagramType.ACTIVITY.value: DiagramType.ACTIVITY,
        DiagramType.STATEMACHINE.value: DiagramType.STATEMACHINE,
        DiagramType.CLASS.value: DiagramType.CLASS,
        DiagramType.SEQUENCE.value: DiagramType.SEQUENCE,
        DiagramType.DEPLOYMENT.value: DiagramType.DEPLOYMENT,
    }
    if result.type not in mapping:
        raise ValueError(f"unsupported_diagram_type:{result.type}")
    return mapping[result.type]
