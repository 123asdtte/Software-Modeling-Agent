"""document_reader 解析器测试（纯函数，无外部依赖）。"""

from pathlib import Path

from app.tools.document_reader import parse_markdown, parse_markdown_dir

SAMPLE = """# 用例图概述

用例图是需求分析的重要工具。

## 参与者

参与者画在系统边界外。

任务二 使用用例图进行需求分析建模

本章介绍用例图建模方法。

正文内容。
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_splits_by_heading(tmp_path):
    """按标题层级切块，heading 记录最近一次标题。"""
    f = _write(tmp_path, "a.md", SAMPLE)
    doc = parse_markdown(f)
    headings = [c.heading for c in doc.chunks]
    assert "用例图概述" in headings
    assert "参与者" in headings
    # 标题行应作为新块的开头
    first_texts = [c.text.splitlines()[0] for c in doc.chunks]
    assert any(t.startswith("#") for t in first_texts)


def test_parse_task_line_is_boundary(tmp_path):
    """教材"任务X"行（无 # 前缀）也应作为新块边界。"""
    f = _write(tmp_path, "a.md", SAMPLE)
    doc = parse_markdown(f)
    task_chunks = [c for c in doc.chunks if c.heading.startswith("任务")]
    assert len(task_chunks) == 1
    assert task_chunks[0].text.startswith("任务二")


def test_parse_source_name(tmp_path):
    """自定义来源名优先生效；缺省用文件名。"""
    f = _write(tmp_path, "a.md", SAMPLE)
    custom = parse_markdown(f, source_name="教材·智能问答")
    assert all(c.source == "教材·智能问答" for c in custom.chunks)
    default = parse_markdown(f)
    assert all(c.source == "a" for c in default.chunks)


def test_parse_no_empty_chunks(tmp_path):
    """连续标题/空行不应产生空块。"""
    f = _write(tmp_path, "a.md", "# 标题1\n\n\n# 标题2\n\n\n")
    doc = parse_markdown(f)
    assert all(c.text.strip() for c in doc.chunks)


def test_parse_markdown_dir_merges(tmp_path):
    """目录解析合并多文件块，来源带前缀。"""
    _write(tmp_path, "b.md", "# B标题\n\nB 内容。\n")
    _write(tmp_path, "a.md", "# A标题\n\nA 内容。\n")
    chunks = parse_markdown_dir(tmp_path, source_prefix="教材·")
    sources = {c.source for c in chunks}
    assert sources == {"教材·a", "教材·b"}
    # 排序后 a 的块在前
    assert chunks[0].heading == "A标题"
