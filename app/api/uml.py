"""UML API 路由（M4）：POST /v1/uml/usecase——需求描述 → 模型 → PlantUML 源码 + 质检报告。

链路：generate_usecase_model（LLM 只产结构化 JSON）
   → render_usecase_plantuml（确定性渲染）
   → check_usecase_model（纯代码质检）
错误约定：
- LLM 侧失败（结构化/上游）→ 502 固定文案；
- 超时 → 504；
- renderer/rules 未预期异常（属服务端内部缺陷而非上游失败）→ 500 固定文案；
- 异常细节只写日志，不向客户端透传（见 app.core.structured_output 安全约定）。
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.chains.uml_chain import generate_usecase_model
from app.config.settings import get_settings
from app.core.structured_output import StructuredOutputError
from app.models.review import ReviewReport
from app.renderers.diagram_renderer import RenderStatus, render_plantuml_source
from app.renderers.plantuml import render_usecase_plantuml
from app.rules.usecase_rules import check_usecase_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/uml", tags=["uml"])

_settings = get_settings()
_uml_semaphore = asyncio.Semaphore(_settings.uml_max_concurrency)

# 固定对外错误文案（不携带任何内部异常细节）
_ERR_UPSTREAM = "用例图生成失败，请稍后重试或调整需求描述"
_ERR_INTERNAL = "用例图处理异常，请联系维护者查看服务日志"


class UmlUseCaseRequest(BaseModel):
    """用例图生成请求体：需求描述必填、去空白后非空、≤3000 字符。

    render/format 为可选字段（默认开启 PNG），旧请求体完全兼容。
    """

    requirement: str = Field(min_length=1, max_length=3000)
    render: bool = True
    format: Literal["png", "svg"] = "png"


class UmlUseCaseResponse(BaseModel):
    """用例图生成响应体（OpenAPI 契约；原有字段名与语义不变）。

    render 为图片渲染结果：环境可用时 rendered + download_url；
    环境缺失/渲染失败时 source_only（PlantUML 源码仍然返回）。
    """

    diagram_type: str
    model: dict
    plantuml: str
    review_report: ReviewReport
    render: dict


@router.post("/usecase", response_model=UmlUseCaseResponse)
async def generate_usecase(req: UmlUseCaseRequest) -> UmlUseCaseResponse:
    """自然语言需求 → 用例图 JSON 模型 + PlantUML 源码 + 质检报告。"""
    requirement = req.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=422, detail="需求描述不能为空白")

    # 阶段一：LLM 结构化生成（上游失败 → 502，超时 → 504）
    try:
        async with _uml_semaphore:
            model = await asyncio.wait_for(generate_usecase_model(requirement), timeout=_settings.uml_timeout)
    except asyncio.TimeoutError as exc:
        logger.warning("用例图生成超时（>%ss）", _settings.uml_timeout)
        raise HTTPException(status_code=504, detail="生成超时，请稍后重试") from exc
    except StructuredOutputError as exc:
        logger.exception("用例图结构化生成失败：%s", exc)
        raise HTTPException(status_code=502, detail=_ERR_UPSTREAM) from exc
    except Exception as exc:  # noqa: BLE001 - 统一固定文案，防内部泄露
        logger.exception("用例图生成异常")
        raise HTTPException(status_code=502, detail=_ERR_UPSTREAM) from exc

    # 阶段二：渲染 + 质检（确定性代码；异常属服务端缺陷 → 500 而非 502）
    try:
        plantuml = render_usecase_plantuml(model)
        report: ReviewReport = check_usecase_model(model)
    except Exception as exc:  # noqa: BLE001 - renderer/rules 缺陷不向客户端泄露
        logger.exception("用例图渲染/质检阶段异常")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL) from exc

    # 阶段三：图片渲染（环境缺失/失败自动降级 source_only，不影响 200 响应）
    render_info: dict = {"status": "source_only", "format": None, "download_url": None, "reason": None}
    if req.render:
        try:
            result = await asyncio.to_thread(render_plantuml_source, plantuml, req.format)
            if result.status == RenderStatus.RENDERED:
                render_info = {
                    "status": "rendered",
                    "format": result.format,
                    "download_url": f"/files/uml/{Path(result.path).name}",
                    "reason": None,
                }
            else:
                render_info["reason"] = result.reason
        except Exception:  # noqa: BLE001 - 图片失败绝不让模型/质检结果整体失败
            logger.exception("图片渲染阶段异常（降级返回源码）")
            render_info["reason"] = "图片渲染异常（已降级返回源码）"

    return UmlUseCaseResponse(
        diagram_type=model.type.value,
        model=model.model_dump(by_alias=True),
        plantuml=plantuml,
        review_report=report,
        render=render_info,
    )
