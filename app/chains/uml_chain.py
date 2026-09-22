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
from app.models.uml import UseCaseModel
from app.prompts.uml_prompt import USECASE_SYSTEM_PROMPT, USECASE_USER_TMPL


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
