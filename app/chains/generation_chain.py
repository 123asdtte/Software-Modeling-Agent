"""教学资源生成链：PPT（大纲→分节并行生成页）与教案（9 字段结构化）。

固定 Prompt Chain 而非 Agent（C3 判断：大纲→分页→文件是确定性流水线，
不需要自主循环）。结构化输出策略：Prompt 要求"只输出 JSON" →
剥离围栏 → pydantic 校验 → 失败带错误反馈重试一次。

生成节奏（对齐 PRD 验收：90 分钟课题 ≤60s）：
- 大纲 1 次 LLM 调用；分页内容按 section 分批并发生成（Semaphore 限并发），
  避免单次生成 20+ 页大 JSON 导致的超时与截断。
"""

import asyncio
import logging
from functools import lru_cache
from typing import ClassVar

from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.core.structured_output import (
    extract_json,  # noqa: F401 - re-export 保持既有导入路径兼容
    invoke_structured,
)
from app.prompts.teacher_prompt import (
    LESSON_SYSTEM_PROMPT,
    LESSON_USER_TMPL,
    PPT_OUTLINE_USER_TMPL,
    PPT_SECTION_USER_TMPL,
    PPT_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------- 输出模型 ----------------


class OutlineSection(BaseModel):
    """大纲的一个部分（7 要素之一）。"""

    name: str
    page_count: int = Field(ge=1, le=10)
    points: list[str] = Field(default_factory=list)


class PptOutline(BaseModel):
    """PPT 大纲：7 要素结构。"""

    title: str
    subtitle: str = ""
    sections: list[OutlineSection]

    @property
    def total_pages(self) -> int:
        return sum(s.page_count for s in self.sections)


class SlidePage(BaseModel):
    """一页 PPT：标题 + 要点 + 讲课备注。"""

    title: str
    bullets: list[str] = Field(default_factory=list)
    note: str = ""
    minutes: int = 3


class SectionPages(BaseModel):
    """一个 section 的分页内容。"""

    pages: list[SlidePage]


class FlowStage(BaseModel):
    """教学流程的一个环节（师生活动拆分，PRD LS-4）。"""

    stage: str
    minutes: int = 5
    teacher_activity: str = ""
    student_activity: str = ""


class LessonPlan(BaseModel):
    """教案：9 个必填字段（PRD 输出契约）。"""

    course_name: str
    teaching_goals: dict[str, list[str]] = Field(default_factory=dict)
    key_points: list[str] = Field(default_factory=list)
    difficult_points: list[str] = Field(default_factory=list)
    teaching_flow: list[FlowStage] = Field(default_factory=list)
    class_exercises: list[str] = Field(default_factory=list)
    homework: list[str] = Field(default_factory=list)

    # 类常量必须标 ClassVar，否则 pydantic 会把它当模型字段
    REQUIRED_GOAL_KEYS: ClassVar[tuple[str, ...]] = ("knowledge", "ability", "literacy")

    def missing_fields(self) -> list[str]:
        """验收用：缺失的必填字段列表（空列表 = 9 字段齐全）。"""
        missing = []
        if not self.course_name:
            missing.append("course_name")
        for key in self.REQUIRED_GOAL_KEYS:
            if not self.teaching_goals.get(key):
                missing.append(f"teaching_goals.{key}")
        if not self.key_points:
            missing.append("key_points")
        if not self.difficult_points:
            missing.append("difficult_points")
        if len(self.teaching_flow) < 5:
            missing.append("teaching_flow(<5)")
        if len(self.class_exercises) < 2:
            missing.append("class_exercises(<2)")
        if len(self.homework) < 2:
            missing.append("homework(<2)")
        return missing


# ---------------- JSON 提取与校验 ----------------


def _invoke_json(messages, model_cls, retries: int = 1):
    """调用 LLM 并解析为 pydantic 模型（薄包装，逻辑统一在 core.structured_output）。

    使用长超时（gen_llm_timeout）：大 JSON + 推理模型的输出时间远超 QA 场景。
    失败抛 StructuredOutputError（是 RuntimeError 子类，既有异常语义兼容）。
    """
    return invoke_structured(
        messages,
        model_cls,
        retries=retries,
        timeout=get_settings().gen_llm_timeout,
    )


# ---------------- PPT 生成 ----------------


@lru_cache(maxsize=1)
def _gen_semaphore() -> asyncio.Semaphore:
    """分节生成的并发闸门（进程级，避免打满 API 限流）。"""
    return asyncio.Semaphore(3)


def generate_ppt_outline(topic: str, minutes: int = 90) -> PptOutline:
    """第一步：生成 7 要素大纲（同步单次调用）。"""
    user = PPT_OUTLINE_USER_TMPL.format(topic=topic, minutes=minutes, pages=max(6, minutes // 5))
    messages = [("system", PPT_SYSTEM_PROMPT), ("user", user)]
    return _invoke_json(messages, PptOutline)


async def _generate_section_pages(topic: str, section: OutlineSection) -> list[SlidePage]:
    """单个 section 的分页生成（并发闸门内）。"""
    user = PPT_SECTION_USER_TMPL.format(
        section=section.name,
        page_count=section.page_count,
        topic=topic,
        points="；".join(section.points) or "（按大纲自行展开）",
    )
    messages = [("system", PPT_SYSTEM_PROMPT), ("user", user)]
    async with _gen_semaphore():
        parsed: SectionPages = await asyncio.to_thread(_invoke_json, messages, SectionPages)
    return parsed.pages[: section.page_count]


async def generate_ppt_deck_async(topic: str, minutes: int = 90) -> dict:
    """完整 PPT 内容（async）：大纲 → 分节并发生成 → 组装。

    Returns:
        dict: {"outline": 大纲 dict, "pages": [页 dict]}；页按节顺序拼接。
    """
    outline = await asyncio.to_thread(generate_ppt_outline, topic, minutes)
    results = await asyncio.gather(*(_generate_section_pages(topic, s) for s in outline.sections))
    pages = [page.model_dump() for section_pages in results for page in section_pages]
    return {"outline": outline.model_dump(), "pages": pages}


def generate_lesson_plan(topic: str, minutes: int = 45) -> LessonPlan:
    """教案生成：9 字段结构化（同步单次调用）。"""
    user = LESSON_USER_TMPL.format(topic=topic, minutes=minutes)
    messages = [("system", LESSON_SYSTEM_PROMPT), ("user", user)]
    return _invoke_json(messages, LessonPlan)
