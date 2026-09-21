"""FastAPI 入口（v13 W1）：服务健康检查 + 一句话问答连通性验证。

启动：uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.models.llm import get_llm

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI 教学智能体平台 v13",
)


class ChatRequest(BaseModel):
    """一句话问答请求体。"""

    message: str = Field(..., min_length=1, max_length=1000, description="用户消息")


class ChatResponse(BaseModel):
    """问答响应体。"""

    reply: str
    model: str


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
    except Exception as exc:  # noqa: BLE001 - 统一转为 HTTP 错误返回
        logger.exception("模型调用失败")
        raise HTTPException(status_code=502, detail=f"模型调用失败：{exc}") from exc
    return ChatResponse(reply=reply, model=settings.model_name)
