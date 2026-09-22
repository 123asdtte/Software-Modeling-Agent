"""FastAPI 入口（v13）：健康检查 + 一句话问答 + 教材智能问答（RAG）+ 教学资源生成（PPT/教案）。

启动：python -m app 或 uvicorn app.main:app --reload
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.uml import router as uml_router
from app.chains.rag_chain import build_qa_answer
from app.config.settings import get_settings
from app.models.llm import get_llm
from app.storage.generated_files import resolve_download_path  # 下载白名单解析（防穿越）

logger = logging.getLogger(__name__)

settings = get_settings()

# /v1/qa 并发闸门：hybrid 检索每问要串多次 LLM 调用，无限制并发会打满配额
_qa_semaphore = asyncio.Semaphore(settings.qa_max_concurrency)
# /v1/ppt、/v1/lesson 并发闸门：结构化生成更重，2 路足够演示
_gen_semaphore = asyncio.Semaphore(settings.gen_max_concurrency)


def _outputs_path(kind: str, filename: str) -> Path:
    path = resolve_download_path(kind, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI 教学智能体平台 v13",
)

# M4 起：新功能路由独立成包（评审 P0），main.py 只负责注册
app.include_router(uml_router)


class ChatRequest(BaseModel):
    """一句话问答请求体。"""

    message: str = Field(..., min_length=1, max_length=1000, description="用户消息")


class ChatResponse(BaseModel):
    """问答响应体。"""

    reply: str
    model: str


class QARequest(BaseModel):
    """教材智能问答请求体。"""

    question: str = Field(..., min_length=1, max_length=1000, description="学生问题")


class QAResponse(BaseModel):
    """教材智能问答响应体。"""

    reply: str
    sources: list[str]


@app.get("/health")
def health() -> dict:
    """健康检查：确认服务与模型配置就绪。"""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "model": settings.model_name,
        "provider": settings.model_provider,
        "api_key_configured": bool(settings.deepseek_api_key),
    }


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """一句话问答：用于 W1 验证模型连通（后续由 QA Agent 承接正式问答）。"""
    try:
        llm = get_llm()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        reply = llm.invoke(req.message).content
    except Exception as exc:
        # 统一转为 HTTP 错误返回，避免内部异常暴露给前端
        logger.exception("模型调用失败")
        raise HTTPException(status_code=502, detail=f"模型调用失败：{exc}") from exc
    return ChatResponse(reply=reply, model=settings.model_name)


@app.post("/v1/qa", response_model=QAResponse)
async def qa(req: QARequest) -> QAResponse:
    """教材智能问答（W2）：RAG 检索 + 四段式回答 + 来源标注。

    演示安全兜底：Semaphore 限并发 + wait_for 整体墙钟（LightRAG 内部
    单次 LLM 超时高达 240s，无整体超时会让请求长时间挂死）。
    """
    try:
        async with _qa_semaphore:
            result = await asyncio.wait_for(build_qa_answer(req.question), timeout=settings.qa_timeout)
    except asyncio.TimeoutError as exc:
        logger.warning("教材问答超时（>%ss）：%s", settings.qa_timeout, req.question[:50])
        raise HTTPException(status_code=504, detail=f"问答超时（>{settings.qa_timeout:.0f}s），请稍后重试") from exc
    except FileNotFoundError as exc:
        logger.warning("知识库索引未构建：%s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("教材问答失败")
        raise HTTPException(status_code=502, detail=f"教材问答失败：{exc}") from exc
    return QAResponse(reply=result["reply"], sources=result["sources"])


# ---------------- 教学资源生成（M3：PPT / 教案）----------------


class PptRequest(BaseModel):
    """PPT 生成请求体（PRD：课题 + 课时）。"""

    topic: str = Field(..., min_length=2, max_length=100, description="课程主题")
    minutes: int = Field(90, ge=15, le=240, description="课时（分钟）")


class LessonRequest(BaseModel):
    """教案生成请求体（PRD：课题 + 课时）。"""

    topic: str = Field(..., min_length=2, max_length=100, description="课程主题")
    minutes: int = Field(45, ge=15, le=240, description="课时（分钟）")


@app.post("/v1/ppt")
async def generate_ppt(req: PptRequest) -> dict:
    """PPT 生成（M3）：大纲 → 分节并发生成 → .pptx 落盘。

    返回大纲与全部页面 JSON（供前端二次编辑重生成，PRD PPT-6）+ 下载地址。
    """
    from app.chains.generation_chain import generate_ppt_deck_async
    from app.tools.ppt_generator import deck_to_pptx

    try:
        async with _gen_semaphore:
            deck = await asyncio.wait_for(
                generate_ppt_deck_async(req.topic, req.minutes),
                timeout=settings.gen_timeout,
            )
    except asyncio.TimeoutError as exc:
        logger.warning("PPT 生成超时（>%ss）：%s", settings.gen_timeout, req.topic)
        raise HTTPException(status_code=504, detail=f"生成超时（>{settings.gen_timeout:.0f}s），请稍后重试") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PPT 生成失败")
        raise HTTPException(status_code=502, detail=f"PPT 生成失败：{exc}") from exc

    file_id = uuid.uuid4().hex
    out = Path(settings.outputs_dir) / "ppt" / f"{file_id}.pptx"
    deck_to_pptx(deck, out)
    return {
        "title": deck["outline"].get("title", req.topic),
        "total_pages": len(deck["pages"]),
        "outline": deck["outline"],
        "pages": deck["pages"],
        "download_url": f"/files/ppt/{file_id}.pptx",
    }


@app.post("/v1/lesson")
async def generate_lesson(req: LessonRequest) -> dict:
    """教案生成（M3）：9 字段结构化 → Markdown + docx 落盘。"""
    from app.chains.generation_chain import generate_lesson_plan
    from app.tools.docx_exporter import lesson_to_docx, lesson_to_markdown

    try:
        async with _gen_semaphore:
            lesson = await asyncio.wait_for(
                asyncio.to_thread(generate_lesson_plan, req.topic, req.minutes),
                timeout=settings.gen_timeout,
            )
    except asyncio.TimeoutError as exc:
        logger.warning("教案生成超时（>%ss）：%s", settings.gen_timeout, req.topic)
        raise HTTPException(status_code=504, detail=f"生成超时（>{settings.gen_timeout:.0f}s），请稍后重试") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("教案生成失败")
        raise HTTPException(status_code=502, detail=f"教案生成失败：{exc}") from exc

    data = lesson.model_dump()
    file_id = uuid.uuid4().hex
    docx_path = Path(settings.outputs_dir) / "lesson" / f"{file_id}.docx"
    lesson_to_docx(data, docx_path)
    return {
        "lesson": data,
        "markdown": lesson_to_markdown(data),
        "missing_fields": lesson.missing_fields(),
        "download_url": f"/files/lesson/{file_id}.docx",
    }


@app.get("/files/ppt/{filename}")
def download_ppt(filename: str) -> FileResponse:
    """下载生成的 PPT 文件（uuid 白名单校验）。"""
    return FileResponse(_outputs_path("ppt", filename), filename=filename)


@app.get("/files/lesson/{filename}")
def download_lesson(filename: str) -> FileResponse:
    """下载生成的教案文件（uuid 白名单校验）。"""
    return FileResponse(_outputs_path("lesson", filename), filename=filename)


@app.get("/files/uml/{filename}")
def download_uml(filename: str) -> FileResponse:
    """下载生成的 UML 图片（png/svg，uuid 白名单校验）。"""
    media = "image/png" if filename.endswith(".png") else "image/svg+xml"
    return FileResponse(_outputs_path("uml", filename), filename=filename, media_type=media)
