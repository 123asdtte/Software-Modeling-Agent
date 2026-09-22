"""教案导出工具：结构化 LessonPlan → Markdown / Word（docx）。

PRD LS-6：结构化 Markdown 可导出 Word；验收要求"一键导出 docx 供提交存档"。
页眉统一标注"AI 生成，请教师审核后使用"（PRD 边界要求）。
"""

import logging
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt

logger = logging.getLogger(__name__)

AI_NOTICE = "AI 生成，请教师审核后使用"


def lesson_to_markdown(lesson: dict[str, Any]) -> str:
    """教案 dict → Markdown 文本（LS-6 结构化输出）。"""
    goals = lesson.get("teaching_goals", {})
    lines = [
        f"# {lesson.get('course_name', '教学设计')}",
        f"> {AI_NOTICE}",
        "",
        "## 一、教学目标",
        "**知识目标**",
        *[f"- {g}" for g in goals.get("knowledge", [])],
        "**能力目标**",
        *[f"- {g}" for g in goals.get("ability", [])],
        "**素养目标**",
        *[f"- {g}" for g in goals.get("literacy", [])],
        "",
        "## 二、教学重点",
        *[f"- {p}" for p in lesson.get("key_points", [])],
        "",
        "## 三、教学难点",
        *[f"- {p}" for p in lesson.get("difficult_points", [])],
        "",
        "## 四、教学流程",
        "| 环节 | 时间 | 教师活动 | 学生活动 |",
        "|---|---|---|---|",
        *[
            f"| {s.get('stage', '')} | {s.get('minutes', '')}分钟 "
            f"| {s.get('teacher_activity', '')} | {s.get('student_activity', '')} |"
            for s in lesson.get("teaching_flow", [])
        ],
        "",
        "## 五、课堂练习",
        *[f"{i}. {e}" for i, e in enumerate(lesson.get("class_exercises", []), start=1)],
        "",
        "## 六、课后任务",
        *[f"{i}. {h}" for i, h in enumerate(lesson.get("homework", []), start=1)],
        "",
    ]
    return "\n".join(lines)


def lesson_to_docx(lesson: dict[str, Any], out_path: str | Path) -> Path:
    """教案 dict → .docx（中文正文，宋体/雅黑，供提交存档）。"""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(11)

    doc.add_heading(lesson.get("course_name", "教学设计"), level=0)
    doc.add_paragraph(AI_NOTICE)

    goals = lesson.get("teaching_goals", {})
    doc.add_heading("一、教学目标", level=1)
    for label, key in (("知识目标", "knowledge"), ("能力目标", "ability"), ("素养目标", "literacy")):
        doc.add_paragraph(label, style="List Number")
        for g in goals.get(key, []):
            doc.add_paragraph(g, style="List Bullet 2")

    doc.add_heading("二、教学重点", level=1)
    for p in lesson.get("key_points", []):
        doc.add_paragraph(p, style="List Bullet")
    doc.add_heading("三、教学难点", level=1)
    for p in lesson.get("difficult_points", []):
        doc.add_paragraph(p, style="List Bullet")

    doc.add_heading("四、教学流程", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for i, header in enumerate(("环节", "时间", "教师活动", "学生活动")):
        table.rows[0].cells[i].text = header
    for s in lesson.get("teaching_flow", []):
        cells = table.add_row().cells
        cells[0].text = str(s.get("stage", ""))
        cells[1].text = f"{s.get('minutes', '')}分钟"
        cells[2].text = str(s.get("teacher_activity", ""))
        cells[3].text = str(s.get("student_activity", ""))

    doc.add_heading("五、课堂练习", level=1)
    for e in lesson.get("class_exercises", []):
        doc.add_paragraph(e, style="List Number")
    doc.add_heading("六、课后任务", level=1)
    for h in lesson.get("homework", []):
        doc.add_paragraph(h, style="List Number")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    logger.info("教案 docx 已生成：%s", out)
    return out
