"""教案导出与生成链结构化测试（假数据/mock，不调 LLM）。"""

import pytest
from docx import Document
from pydantic import ValidationError

from app.chains.generation_chain import LessonPlan, extract_json
from app.tools.docx_exporter import lesson_to_docx, lesson_to_markdown

FAKE_LESSON = {
    "course_name": "用例图教学设计",
    "teaching_goals": {
        "knowledge": ["理解用例图三要素"],
        "ability": ["能画出简单用例图"],
        "literacy": ["建立需求工程意识"],
    },
    "key_points": ["参与者与用例识别"],
    "difficult_points": ["include/extend 辨析"],
    "teaching_flow": [
        {"stage": "导入", "minutes": 5, "teacher_activity": "反面案例引入", "student_activity": "讨论"},
        {"stage": "讲解", "minutes": 15, "teacher_activity": "三要素讲解", "student_activity": "听讲记录"},
        {"stage": "案例分析", "minutes": 10, "teacher_activity": "预警平台用例图剖析", "student_activity": "跟画"},
        {"stage": "课堂互动", "minutes": 8, "teacher_activity": "三查追问", "student_activity": "自查互评"},
        {"stage": "小结", "minutes": 7, "teacher_activity": "总结口诀", "student_activity": "复述要点"},
    ],
    "class_exercises": ["为图书借阅画用例图", "指出示例图 3 处错误"],
    "homework": ["为校园二手交易系统画用例图", "阅读教材任务二 2.3 节"],
}


def test_extract_json_strips_fence():
    """应剥离 markdown 围栏取 JSON。"""
    text = '前置说明\n```json\n{"a": 1}\n```\n后置说明'
    assert extract_json(text) == {"a": 1}


def test_extract_json_bare_object():
    """无围栏时取首个大括号块。"""
    assert extract_json('回答如下：{"b": [1, 2]} 完毕') == {"b": [1, 2]}


def test_extract_json_rejects_no_json():
    """无 JSON 时报错。"""
    with pytest.raises(ValueError):
        extract_json("完全没有结构化内容")


def test_lesson_plan_missing_fields():
    """缺字段时 missing_fields 应点名（验收 9 字段校验）。"""
    bad = LessonPlan(course_name="x")
    missing = bad.missing_fields()
    assert "teaching_goals.knowledge" in missing
    assert "teaching_flow(<5)" in missing
    assert "class_exercises(<2)" in missing
    ok = LessonPlan.model_validate(FAKE_LESSON)
    assert ok.missing_fields() == []


def test_lesson_plan_rejects_empty():
    """course_name 必填。"""
    with pytest.raises(ValidationError):
        LessonPlan()


def test_lesson_to_markdown_contains_nine_fields():
    """Markdown 应包含 9 字段与 AI 审核标注。"""
    md = lesson_to_markdown(FAKE_LESSON)
    for header in ("教学目标", "教学重点", "教学难点", "教学流程", "课堂练习", "课后任务", "AI 生成"):
        assert header in md


def test_lesson_to_docx(tmp_path):
    """docx 生成且表格行数正确。"""
    out = lesson_to_docx(FAKE_LESSON, tmp_path / "lesson.docx")
    assert out.exists() and out.stat().st_size > 1024
    doc = Document(str(out))
    tables = doc.tables
    assert len(tables) == 1
    # 表头 + 5 环节
    assert len(tables[0].rows) == 6
