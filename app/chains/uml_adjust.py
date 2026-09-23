"""UML 对话式修正链：当前模型 + 自然语言修正指令 → 修正后的 UseCaseModel。

流程（对齐前端 uml.js 期望响应）：
invoke_structured（当前模型 JSON + 指令 → 修正后模型 JSON）
→ UseCaseModel 校验 → 确定性渲染 → 重质检
→ {success, reply, model, plantuml, issues, diff_summary, render}
"""

import asyncio

from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.core.structured_output import invoke_structured
from app.models.uml import UseCaseModel
from app.renderers.plantuml import render_usecase_plantuml
from app.rules.usecase_rules import check_usecase_model


class AdjustedOutput(BaseModel):
    """LLM 输出契约：修正后模型 + 面向教师的说明。"""

    model: UseCaseModel
    reply: str = Field(min_length=2, max_length=600)
    diff_summary: str = Field(default="", max_length=400)


def _adjust_sync(instruction: str, current_model_json: str, llm_factory=None) -> AdjustedOutput:
    system = (
        "你是 UML 用例图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；\n"
        "2. 参与者只能是外部角色（数据库/界面等内部组件不能作为参与者）；\n"
        "3. 用例名表达业务目标（禁止：点击/输入/按下/选择/填写）；\n"
        "4. 用例 id 保持 UC-01 格式，新增用例接续编号；\n"
        "5. relations 只允许 include/extend/association/generalization；\n"
        "6. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的用例图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    )
    user = f"当前模型 JSON：\n{current_model_json}\n\n修正指令：{instruction}"
    return invoke_structured(
        [("system", system), ("user", user)],
        AdjustedOutput,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().gen_llm_timeout,
    )


async def adjust_usecase_model(
    current_model: UseCaseModel, instruction: str, output_format: str, *, llm_factory=None
) -> dict:
    """对话式修正：返回前端期望的完整响应结构。

    任何失败向上抛出（StructuredOutputError / 其他），由 API 层统一降级。
    """
    from app.renderers.diagram_renderer import render_plantuml_source

    current_json = current_model.model_dump_json(by_alias=True)
    out: AdjustedOutput = await asyncio.to_thread(_adjust_sync, instruction, current_json, llm_factory)
    new_model = out.model.model_copy(update={"type": current_model.type})
    plantuml = render_usecase_plantuml(new_model)
    report = check_usecase_model(new_model)
    render_result = await asyncio.to_thread(render_plantuml_source, plantuml, output_format)

    render_info: dict = {"status": "source_only", "format": None, "download_url": None, "reason": None}
    if render_result.status.value == "rendered":
        from pathlib import Path

        render_info = {
            "status": "rendered",
            "format": render_result.format,
            "download_url": f"/files/uml/{Path(render_result.filename).name}",
            "reason": None,
        }
    else:
        render_info["reason"] = render_result.reason

    return {
        "success": True,
        "reply": out.reply,
        "model": new_model.model_dump(by_alias=True),
        "plantuml": plantuml,
        "issues": [i.model_dump() for i in report.issues],
        "passed": report.passed,
        "diff_summary": out.diff_summary,
        "render": render_info,
    }
