"""实训任务工单 API：POST /v1/tasksheet。

响应契约对齐前端 renderTasksheetResults：
{tasksheet: {...}, download_url: "/files/lesson/<uuid>.docx"}

并发模型：信号量获取计入 wait_for 超时预算（与 main.py 重构后模式一致，
幽灵请求占槽时新请求也能超时兜底，而非无限挂起）。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.chains.tasksheet_chain import export_tasksheet_docx, generate_tasksheet
from app.config.settings import get_settings
from app.core.structured_output import StructuredOutputError
from app.storage.generated_files import save_bytes_atomic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["tasksheet"])

_settings = get_settings()
_tasksheet_semaphore = asyncio.Semaphore(2)


class TasksheetRequest(BaseModel):
    """实训工单生成请求体。"""

    topic: str = Field(..., min_length=1, max_length=100)

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("课题不能为空白")
        return v

    minutes: int = Field(45, ge=15, le=240)
    difficulty: str = Field("进阶", min_length=1, max_length=20)
    mode: str = Field("双人结对协作", min_length=1, max_length=50)


@router.post("/tasksheet")
async def generate_tasksheet_endpoint(req: TasksheetRequest) -> dict:
    """课题 → 实训任务工单（结构化 + docx 下载）。"""

    async def _run():
        async with _tasksheet_semaphore:
            return await generate_tasksheet(req.topic, req.minutes, req.difficulty, req.mode)

    try:
        ts = await asyncio.wait_for(_run(), timeout=_settings.gen_timeout)
    except asyncio.TimeoutError as exc:
        logger.warning("实训工单生成超时（>%ss）：%s", _settings.gen_timeout, req.topic[:50])
        raise HTTPException(status_code=504, detail="工单生成超时，请稍后重试") from exc
    except StructuredOutputError as exc:
        logger.exception("实训工单结构化生成失败：%s", exc)
        raise HTTPException(status_code=502, detail="工单生成失败，请稍后重试或调整课题") from exc
    except Exception as exc:  # noqa: BLE001 - 固定文案防内部泄露
        logger.exception("实训工单生成异常")
        raise HTTPException(status_code=502, detail="工单生成失败，请稍后重试或调整课题") from exc

    try:
        docx_bytes = await asyncio.to_thread(export_tasksheet_docx, ts)
        filename = save_bytes_atomic("lesson", "docx", docx_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("工单 docx 导出失败")
        raise HTTPException(status_code=500, detail="工单导出异常，请联系维护者查看服务日志") from exc

    return {
        "tasksheet": ts.model_dump(),
        "download_url": f"/files/lesson/{filename}",
    }
