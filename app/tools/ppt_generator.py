"""PPT 文件生成工具：结构化 PptDeck → 可编辑 .pptx（python-pptx）。

版式策略（演示优先，教师可二次编辑）：
- 封面用标题版式；内容页用「标题+内容」版式，bullets 一行一条；
- 讲课备注写入 notes_slide（PRD PPT-4：讲解要点 + 时间分配）；
- 中文编码由 python-pptx 内部 UTF-8 保证，统一设置微软雅黑。
"""

import logging
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Pt

logger = logging.getLogger(__name__)

FONT_NAME = "微软雅黑"
TITLE_SIZE = Pt(28)
BODY_SIZE = Pt(16)


def _set_font(text_frame, size: Pt) -> None:
    """统一设置段落字体（含东亚字体名，避免中文回退宋体）。"""
    for para in text_frame.paragraphs:
        for run in para.runs:
            run.font.name = FONT_NAME
            run.font.size = size
            # python-pptx 不直接暴露 ea 字体，需设置 rPr 的 eastAsia
            r_pr = run._r.get_or_add_rPr()
            ea = r_pr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ea")
            if ea is None:
                ea = r_pr.makeelement(
                    "{http://schemas.openxmlformats.org/drawingml/2006/main}ea",
                    {"typeface": FONT_NAME},
                )
                r_pr.append(ea)
            else:
                ea.set("typeface", FONT_NAME)


def deck_to_pptx(deck: dict[str, Any], out_path: str | Path) -> Path:
    """把 deck（outline + pages）渲染为 .pptx 文件。

    Args:
        deck: {"outline": {"title","subtitle",...}, "pages": [{"title","bullets","note"}]}
        out_path: 输出 .pptx 路径。

    Returns:
        Path: 生成的文件路径。
    """
    outline = deck.get("outline", {})
    pages = deck.get("pages", [])
    if not pages:
        raise ValueError("deck 中没有页面内容，拒绝生成空 PPT")

    prs = Presentation()

    # 封面
    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = outline.get("title", "课程课件")
    if outline.get("subtitle") and len(cover.placeholders) > 1:
        cover.placeholders[1].text = outline["subtitle"]
    _set_font(cover.shapes.title.text_frame, TITLE_SIZE)

    # 内容页
    for page in pages:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = page.get("title", "")
        _set_font(slide.shapes.title.text_frame, TITLE_SIZE)
        body = slide.placeholders[1].text_frame
        body.clear()
        bullets = page.get("bullets", [])
        for i, line in enumerate(bullets):
            para = body.paragraphs[0] if i == 0 else body.add_paragraph()
            para.text = f"• {line}"
        _set_font(body, BODY_SIZE)
        # 讲课备注（PRD PPT-4）
        note = page.get("note", "")
        if note:
            slide.notes_slide.notes_text_frame.text = note

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    logger.info("PPT 已生成：%s（%d 页）", out, len(pages) + 1)
    return out
