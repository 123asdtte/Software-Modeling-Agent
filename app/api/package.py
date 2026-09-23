"""教学全案联产 API：POST /v1/package——一次生成「PPT + 教案 + 工单」三件套。

响应契约对齐前端 renderPackageResults（嵌套结构，字段名不可更名）：
{topic, ppt: <v1/ppt 响应>, lesson: <v1/lesson 响应>, tasksheet: <v1/tasksheet 响应>}

导出逻辑与 main.py 的单件端点保持一致（deck_to_pptx / lesson_to_docx + uuid 命名）。
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.chains.tasksheet_chain import export_tasksheet_docx, generate_tasksheet
from app.config.settings import get_settings
from app.models.tasksheet import Tasksheet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["package"])

_settings = get_settings()
_package_semaphore = asyncio.Semaphore(2)


class PackageRequest(BaseModel):
    """全案联产请求体（前端额外字段 target_student/template/venue 接受但不参与生成）。"""

    topic: str = Field(..., min_length=2, max_length=100)
    minutes: int = Field(90, ge=15, le=240)
    difficulty: str = Field("进阶", min_length=1, max_length=20)
    mode: str = Field("双人结对协作", min_length=1, max_length=50)
    target_student: str = Field("", max_length=100)
    template: str = Field("", max_length=40)
    venue: str = Field("", max_length=40)


def _out_path(kind: str, ext: str) -> Path:
    path = Path(_settings.outputs_dir) / kind / f"{uuid.uuid4().hex}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


async def _tasksheet_part(req: PackageRequest) -> dict:
    """工单部分：生成 → docx 导出 → 下载链接。"""
    ts: Tasksheet = await generate_tasksheet(req.topic, req.minutes, req.difficulty, req.mode)
    docx_path = _out_path("lesson", "docx")
    docx_path.write_bytes(export_tasksheet_docx(ts))
    return {"tasksheet": ts.model_dump(), "download_url": f"/files/lesson/{docx_path.name}"}


@router.post("/package")
async def generate_package_endpoint(req: PackageRequest) -> dict:
    """课题 → 三件套联产（PPT / 教案 / 工单并行生成，单件失败降级 null）。"""
    # 复用 main.py 单件端点的导出链（延迟导入避免循环依赖）
    from app.chains.generation_chain import generate_lesson_plan, generate_ppt_deck_async
    from app.tools.docx_exporter import lesson_to_docx, lesson_to_markdown
    from app.tools.ppt_generator import deck_to_pptx

    async def _run_ppt():
        async with _package_semaphore:
            return await generate_ppt_deck_async(req.topic, req.minutes)

    async def _run_lesson():
        async with _package_semaphore:
            return await asyncio.to_thread(generate_lesson_plan, req.topic, req.minutes)

    async def _tasksheet_part_safe():
        try:
            return await _tasksheet_part(req)
        except Exception:  # noqa: BLE001 - 单件失败降级 null
            logger.exception("全案联产工单件失败")
            return None

    async def _ppt_part_safe():
        try:
            deck = await _run_ppt()
            out = _out_path("ppt", "pptx")
            deck_to_pptx(deck, out)
            return {
                "title": deck["outline"].get("title", req.topic),
                "total_pages": len(deck["pages"]),
                "outline": deck["outline"],
                "pages": deck["pages"],
                "download_url": f"/files/ppt/{out.name}",
            }
        except Exception:  # noqa: BLE001
            logger.exception("全案联产 PPT 件失败")
            return None

    async def _lesson_part_safe():
        try:
            lesson = await _run_lesson()
            data = lesson.model_dump()
            docx_path = _out_path("lesson", "docx")
            lesson_to_docx(data, docx_path)
            return {
                "lesson": data,
                "markdown": lesson_to_markdown(data),
                "missing_fields": lesson.missing_fields(),
                "download_url": f"/files/lesson/{docx_path.name}",
            }
        except Exception:  # noqa: BLE001
            logger.exception("全案联产教案件失败")
            return None

    try:
        ppt, lesson, tasksheet = await asyncio.wait_for(
            asyncio.gather(_ppt_part_safe(), _lesson_part_safe(), _tasksheet_part_safe()),
            timeout=_settings.gen_timeout + 60,  # 并行总墙钟 = 单件超时 + 排队冗余
        )
    except asyncio.TimeoutError as exc:
        logger.warning("全案联产超时（>%ss）", _settings.gen_timeout + 60)
        raise HTTPException(status_code=504, detail="全案生成超时，请稍后重试") from exc

    if not any([ppt, lesson, tasksheet]):
        # 三件全灭通常是模型平台整体不可用
        raise HTTPException(status_code=502, detail="生成失败（模型服务暂时不可用），请稍后重试")

    return {"topic": req.topic, "ppt": ppt, "lesson": lesson, "tasksheet": tasksheet}
