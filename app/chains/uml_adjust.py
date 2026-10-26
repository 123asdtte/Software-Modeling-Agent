"""UML 对话式修正链（三图型统一）：当前模型 + 自然语言修正指令 → 修正后的模型。

流程（对齐前端 uml.js 期望响应）：
invoke_structured（当前模型 JSON + 指令 → 修正后模型 JSON）
→ 按 type 校验（UseCase/Activity/StateMachine）→ 确定性渲染 → 重质检
→ {success, reply, model, plantuml, issues, passed, diff_summary, render}

2026-10-09 扩展：原仅用例图（定向迭代），现按模型 type 分派支持活动图/状态机图，
规则约束与各自规则引擎（AC-*/SM-*/UC-*）对齐。
"""

import asyncio

from pydantic import BaseModel, Field

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
from app.renderers.plantuml import inject_skin, render_uml_plantuml
from app.rules.activity_rules import check_activity_model
from app.rules.class_rules import check_class_model
from app.rules.deployment_rules import check_deployment_model
from app.rules.sequence_rules import check_sequence_model
from app.rules.statemachine_rules import check_statemachine_model
from app.rules.usecase_rules import check_usecase_model

AnyUmlModel = UseCaseModel | ActivityModel | StateMachineModel | ClassModel | SequenceModel | DeploymentModel


class AdjustedOutput(BaseModel):
    """LLM 输出契约：修正后模型 + 面向教师的说明。

    model 为联合类型：三个模型均含 Literal type 字段，pydantic smart union
    按 type 精确匹配，不会交叉误配（字段集互不重叠）。
    """

    model: UseCaseModel | ActivityModel | StateMachineModel | ClassModel | SequenceModel | DeploymentModel
    reply: str = Field(min_length=2, max_length=600)
    diff_summary: str = Field(default="", max_length=400)


# 各图型修正规则（与对应规则引擎约束一致，避免修正后再触发质检错误）
_ADJUST_RULES: dict[DiagramType, str] = {
    DiagramType.USECASE: (
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
    ),
    DiagramType.ACTIVITY: (
        "你是 UML 活动图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；model.type 固定为 activity；\n"
        "2. 泳道只能是外部责任主体（数据库/缓存/队列等内部组件不能作为泳道）；\n"
        "3. 动作名表达业务目标（禁止：点击/输入/按下/选择/填写/提交）；\n"
        "4. action/decision 节点必须有 name 与 lane（lane 必须在 swimlanes 中已定义）；\n"
        "5. 决策节点（kind=decision）的每条输出 flow 必须带互斥监护条件 cond；\n"
        "6. 分叉（fork）与汇合（join）必须成对出现；\n"
        "7. flows 的 from/to 必须引用已存在的节点 id；每个节点都要有控制流连接（不留孤立节点）；\n"
        "8. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的活动图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    ),
    DiagramType.STATEMACHINE: (
        "你是 UML 状态机图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；model.type 固定为 statemachine；\n"
        "2. 初始伪状态（kind=initial）与最终伪状态（kind=final）各只能有一个；\n"
        "3. 状态名表达稳定状态（禁止：正在xx/xx执行/处理中）；\n"
        "4. 每条 transition 必须标注触发事件 event；\n"
        "5. transitions 的 from/to 必须引用已定义的 states id（to 允许 history 历史伪状态）；\n"
        "6. 存在指向 history 的转换时，应有 kind=paused 且 history=shallow/deep 的挂起状态承接；\n"
        "7. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的状态机图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    ),
    DiagramType.CLASS: (
        "你是 UML 类图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；model.type 固定为 class；\n"
        "2. classes 中的类名唯一；relations 的 from/to 必须引用已定义的类名；\n"
        "3. 属性/方法都要标注 visibility（+/-/#/~）；\n"
        "4. 抽象方法只能出现在 is_abstract 或 is_interface 的类中；\n"
        "5. realization 的 to 端必须是 is_interface=true 的类；\n"
        "6. composition/aggregation 需标注 target_multiplicity；继承/实现链路不得成环；\n"
        "7. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的类图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    ),
    DiagramType.SEQUENCE: (
        "你是 UML 时序图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；model.type 固定为 sequence；\n"
        "2. messages 的 from/to 必须引用已定义的 lifelines 名称；order 唯一且按业务顺序编号；\n"
        "3. 每条消息必须标注 label（操作名与参数），返回消息用 kind=return；\n"
        "4. fragments 的 start_order/end_order 必须落在真实消息上，且互不重叠（v1 单层）；\n"
        "5. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的时序图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    ),
    DiagramType.DEPLOYMENT: (
        "你是 UML 部署图建模助手。用户会给出「当前模型 JSON」和一条「修正指令」。\n"
        "规则：\n"
        "1. 只做指令要求的修改，其余部分保持原样；model.type 固定为 deployment；\n"
        "2. nodes/artifacts 名称唯一；associations 端点必须是已定义节点或构件；\n"
        "3. artifacts 的 deployed_on 必须是已定义节点名；\n"
        "4. stereotype 使用教学常用值（server/docker/k8s/pod/service/deployment/ingress/db/gateway）；\n"
        "5. K8s 场景保持 ingress → service → pod/deployment 可达链路；\n"
        "6. 严格只输出一个 JSON 对象，格式：\n"
        '{"model": <完整修正后的部署图 JSON，结构同当前模型>,\n'
        ' "reply": "对教师的修改说明", "diff_summary": "变更点摘要"}'
    ),
}

_CHECKERS = {
    DiagramType.USECASE: check_usecase_model,
    DiagramType.ACTIVITY: check_activity_model,
    DiagramType.STATEMACHINE: check_statemachine_model,
    DiagramType.CLASS: check_class_model,
    DiagramType.SEQUENCE: check_sequence_model,
    DiagramType.DEPLOYMENT: check_deployment_model,
}


def _adjust_sync(instruction: str, current_model_json: str, dtype: DiagramType, llm_factory=None) -> AdjustedOutput:
    system = _ADJUST_RULES[dtype]
    user = f"当前模型 JSON：\n{current_model_json}\n\n修正指令：{instruction}"
    return invoke_structured(
        [("system", system), ("user", user)],
        AdjustedOutput,
        llm_factory=llm_factory,
        retries=1,
        timeout=get_settings().gen_llm_timeout,
    )


async def adjust_uml_model(
    current_model: AnyUmlModel, instruction: str, output_format: str, *, llm_factory=None
) -> dict:
    """对话式修正（三图型统一入口）：返回前端期望的完整响应结构。

    任何失败向上抛出（StructuredOutputError / ValueError / 其他），由 API 层统一降级。
    """
    from app.renderers.diagram_renderer import render_plantuml_source

    dtype = current_model.type
    current_json = current_model.model_dump_json(by_alias=True)
    out: AdjustedOutput = await asyncio.to_thread(_adjust_sync, instruction, current_json, dtype, llm_factory)

    new_model = out.model
    if new_model.type != dtype:
        # 防御：LLM 改动了 type（联合类型会校验成另一模型），拒绝本次修正
        raise ValueError(f"修正后模型类型不一致：期望 {dtype.value}，得到 {new_model.type.value}")

    plantuml = render_uml_plantuml(new_model)
    report = _CHECKERS[dtype](new_model)
    render_result = await asyncio.to_thread(
        render_plantuml_source, inject_skin(plantuml, current_model.type), output_format
    )

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


async def adjust_usecase_model(
    current_model: UseCaseModel, instruction: str, output_format: str, *, llm_factory=None
) -> dict:
    """向后兼容别名：等价于 adjust_uml_model（用例图）。"""
    return await adjust_uml_model(current_model, instruction, output_format, llm_factory=llm_factory)
