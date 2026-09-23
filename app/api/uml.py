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
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.chains.uml_adjust import adjust_usecase_model
from app.chains.uml_chain import generate_usecase_model
from app.config.settings import get_settings
from app.core.structured_output import StructuredOutputError
from app.models.review import ReviewReport
from app.models.uml import UseCaseModel
from app.renderers.diagram_renderer import RenderStatus, render_plantuml_source
from app.renderers.plantuml import render_usecase_plantuml
from app.rules.usecase_rules import check_usecase_model
from app.storage.generated_files import save_bytes_atomic

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
    engine: Literal["plantuml", "drawio"] = "plantuml"


class RenderResponse(BaseModel):
    """图片渲染结果（OpenAPI 完整结构）。

    约定：rendered 时 format/download_url 必须存在；
    source_only 时 download_url 必须为 null（避免指向不存在的文件）。
    """

    status: RenderStatus
    format: Literal["png", "svg"] | None = None
    download_url: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "RenderResponse":
        if self.status == RenderStatus.RENDERED:
            if not self.format or not self.download_url:
                raise ValueError("rendered 状态必须携带 format 与 download_url")
        elif self.download_url is not None:
            raise ValueError("source_only 状态不应携带 download_url")
        return self


class UmlUseCaseResponse(BaseModel):
    """用例图生成响应体（OpenAPI 契约；原有字段名与语义不变）。

    render 为图片渲染结果：环境可用时 rendered + download_url；
    环境缺失/渲染失败时 source_only（PlantUML 源码仍然返回）。
    """

    diagram_type: str
    model: dict
    plantuml: str
    review_report: ReviewReport
    render: RenderResponse
    drawio_download_url: str | None = None
    svg_download_url: str | None = None


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

    # 阶段二点五：可编辑/矢量格式同步导出（draw.io 可继续编辑、SVG 可缩放嵌入；失败不阻塞）
    drawio_url = None
    svg_url = None
    try:
        from app.renderers.drawio_renderer import render_usecase_drawio

        drawio_src = render_usecase_drawio(model)
        drawio_name = save_bytes_atomic("uml", "drawio", drawio_src.encode("utf-8"))
        drawio_url = f"/files/uml/{drawio_name}"
    except Exception:  # noqa: BLE001 - drawio 失败不影响主链路
        logger.exception("draw.io 导出失败（已跳过）")
    try:
        from app.renderers.svg_renderer import render_usecase_svg

        svg_src = render_usecase_svg(model)
        svg_name = save_bytes_atomic("uml", "svg", svg_src.encode("utf-8"))
        svg_url = f"/files/uml/{svg_name}"
    except Exception:  # noqa: BLE001 - svg 失败不影响主链路
        logger.exception("SVG 导出失败（已跳过）")

    # 阶段三：图片渲染（环境缺失/失败自动降级 source_only，不影响 200 响应）
    render_info = RenderResponse(status=RenderStatus.SOURCE_ONLY)
    if req.render and req.engine == "drawio":
        # drawio 引擎：主图走 SVG 渲染器（drawio 版式），不依赖 Java/Jar
        try:
            from app.renderers.svg_renderer import render_usecase_svg

            svg_src = render_usecase_svg(model)
            svg_name = save_bytes_atomic("uml", "svg", svg_src.encode("utf-8"))
            render_info = RenderResponse(
                status=RenderStatus.RENDERED,
                format="svg",
                download_url=f"/files/uml/{svg_name}",
            )
        except Exception:  # noqa: BLE001 - svg 失败降级
            logger.exception("drawio 引擎渲染失败（降级源码）")
            render_info = RenderResponse(
                status=RenderStatus.SOURCE_ONLY, reason="图片渲染异常（已降级返回源码）"
            )
    elif req.render:
        try:
            result = await asyncio.to_thread(render_plantuml_source, plantuml, req.format)
            if result.status == RenderStatus.RENDERED:
                render_info = RenderResponse(
                    status=RenderStatus.RENDERED,
                    format=result.format,
                    download_url=f"/files/uml/{result.filename}",
                )
            else:
                render_info = RenderResponse(status=RenderStatus.SOURCE_ONLY, reason=result.reason)
        except Exception:  # noqa: BLE001 - 图片失败绝不让模型/质检结果整体失败
            logger.exception("图片渲染阶段异常（降级返回源码）")
            render_info = RenderResponse(status=RenderStatus.SOURCE_ONLY, reason="图片渲染异常（已降级返回源码）")

    return UmlUseCaseResponse(
        diagram_type=model.type.value,
        model=model.model_dump(by_alias=True),
        plantuml=plantuml,
        review_report=report,
        render=render_info,
        drawio_download_url=drawio_url,
        svg_download_url=svg_url,
    )


class UmlAdjustRequest(BaseModel):
    """对话式修正请求体（前端 Copilot 面板）。"""

    instruction: str = Field(..., min_length=2, max_length=500)
    current_plantuml: str = Field("", max_length=8000)
    current_model: dict
    format: Literal["png", "svg"] = "png"


@router.post("/chat-adjust")
async def chat_adjust(req: UmlAdjustRequest) -> dict:
    """对话式修正：当前模型 + 指令 → 修正后模型 + 重渲染 + 重质检。"""
    try:
        current = UseCaseModel.model_validate(req.current_model)
    except Exception as exc:  # noqa: BLE001 - 当前模型非法（契约变更/篡改）
        logger.warning("chat-adjust 当前模型校验失败：%s", str(exc)[:120])
        raise HTTPException(status_code=422, detail="当前模型数据无效，请重新生成后再修正") from exc

    try:
        async with _uml_semaphore:
            result = await asyncio.wait_for(
                adjust_usecase_model(current, req.instruction.strip(), req.format),
                timeout=_settings.uml_timeout,
            )
    except asyncio.TimeoutError as exc:
        logger.warning("UML 对话修正超时（>%ss）", _settings.uml_timeout)
        raise HTTPException(status_code=504, detail="修正超时，请稍后重试") from exc
    except StructuredOutputError as exc:
        logger.exception("UML 对话修正结构化失败：%s", exc)
        raise HTTPException(status_code=502, detail="模型未能完成修正，请换个说法重试") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("UML 对话修正异常")
        raise HTTPException(status_code=502, detail="修正失败，请稍后重试") from exc

    return result
