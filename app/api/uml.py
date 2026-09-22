"""UML API 路由（M4）：POST /v1/uml/usecase——需求描述 → 模型 → PlantUML 源码 + 质检报告。

链路：generate_usecase_model（LLM 只产结构化 JSON）
   → render_usecase_plantuml（确定性渲染）
   → check_usecase_model（纯代码质检）
错误约定：StructuredOutputError 与其他内部异常统一映射为固定文案 502，
异常细节只写日志，不向客户端透传（见 app.core.structured_output 安全约定）。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.chains.uml_chain import generate_usecase_model
from app.config.settings import get_settings
from app.core.structured_output import StructuredOutputError
from app.models.review import ReviewReport
from app.models.uml import UseCaseModel
from app.renderers.plantuml import render_usecase_plantuml
from app.rules.usecase_rules import check_usecase_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/uml", tags=["uml"])

_settings = get_settings()
_uml_semaphore = asyncio.Semaphore(_settings.uml_max_concurrency)

# 固定对外错误文案（不携带任何内部异常细节）
_ERR_UPSTREAM = "用例图生成失败，请稍后重试或调整需求描述"


class UmlUseCaseRequest(BaseModel):
    """用例图生成请求体：需求描述必填、去空白后非空、≤3000 字符。"""

    requirement: str = Field(min_length=1, max_length=3000)


@router.post("/usecase")
async def generate_usecase(req: UmlUseCaseRequest) -> dict:
    """自然语言需求 → 用例图 JSON 模型 + PlantUML 源码 + 质检报告。"""
    requirement = req.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=422, detail="需求描述不能为空白")

    try:
        async with _uml_semaphore:
            model = await asyncio.wait_for(generate_usecase_model(requirement), timeout=_settings.uml_timeout)
    except asyncio.TimeoutError as exc:
        logger.warning("用例图生成超时（>%ss）", _settings.uml_timeout)
        raise HTTPException(status_code=504, detail="生成超时，请稍后重试") from exc
    except StructuredOutputError as exc:
        # 细节（含上游错误）只进日志
        logger.exception("用例图结构化生成失败：%s", exc)
        raise HTTPException(status_code=502, detail=_ERR_UPSTREAM) from exc
    except Exception as exc:  # noqa: BLE001 - 统一固定文案，防内部泄露
        logger.exception("用例图生成异常")
        raise HTTPException(status_code=502, detail=_ERR_UPSTREAM) from exc

    # 渲染与质检：确定性代码，除非模型契约被破坏否则不应失败
    plantuml = render_usecase_plantuml(model)
    report: ReviewReport = check_usecase_model(model)

    # 防御：EnsureCaseModel 类型契约（render/check 均要求 UseCaseModel）
    assert isinstance(model, UseCaseModel)

    return {
        "diagram_type": model.type.value,
        "model": model.model_dump(by_alias=True),
        "plantuml": plantuml,
        "review_report": report.model_dump(),
    }
