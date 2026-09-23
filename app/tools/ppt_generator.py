"""PPT 文件生成工具：结构化 PptDeck → 可编辑 .pptx（python-pptx）。

版式策略 v2（视觉重设计）：
- 16:9 宽屏；弃用默认模板占位符，全部用空白版式自绘（默认模板是白底 4:3、
  内容只占上半屏，且内容占位符自带项目符号会与手动 "• " 前缀叠加成双符号）；
- 统一视觉：深蓝标题带 + 橙色强调色，微软雅黑，每页页脚页码；
- 每页右上角显示该节时长徽章（deck.pages[].minutes，PRD 的时间分配可视化）；
- bullet 拆分渲染：冒号前缀加粗，避免整行均质灰字；
- 讲课备注写入 notes_slide（PRD PPT-4：讲解要点 + 时间分配）。
"""

import logging
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

logger = logging.getLogger(__name__)

FONT_NAME = "微软雅黑"

# 视觉规范：深蓝主色 + 橙色强调，正文深灰，辅助浅灰
C_PRIMARY = RGBColor(0x1F, 0x4E, 0x79)  # 深蓝：标题带 / 封面主色
C_ACCENT = RGBColor(0xE8, 0x7D, 0x2C)  # 橙色：bullet 符号 / 徽章 / 下划线
C_TEXT = RGBColor(0x33, 0x33, 0x33)  # 正文深灰
C_MUTED = RGBColor(0x8A, 0x8A, 0x8A)  # 页脚浅灰
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# 16:9 画布
SLIDE_W = Emu(12192000)  # 13.333 in
SLIDE_H = Emu(6858000)  # 7.5 in

IN = 914400  # EMU per inch

TITLE_SIZE = Pt(26)  # 内容页标题（标题带内）
COVER_TITLE_SIZE = Pt(42)
BODY_SIZE = Pt(18)
FOOT_SIZE = Pt(10)

FOOTER_TEXT = "AI 教学智能体平台 · 软件建模课程"


def _style_run(run, size: Pt, *, bold: bool = False, color: RGBColor = C_TEXT) -> None:
    """统一设置单个 run 的字体（含东亚字体名，避免中文回退宋体）。"""
    run.font.name = FONT_NAME
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = color
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


def _add_rect(slide, x: int, y: int, w: int, h: int, color: RGBColor) -> None:
    """加一个无边框纯色矩形。"""
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False


def _add_textbox(slide, x: int, y: int, w: int, h: int):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    return tf


def _fill_bullets(tf, bullets: list[str]) -> None:
    """bullet 渲染：橙色符号 + 冒号前缀加粗（文本框无自动符号，不会出现双 bullet）。"""
    for i, line in enumerate(bullets):
        line = str(line).strip()
        if not line:
            continue
        para = tf.paragraphs[0] if i == 0 and not tf.paragraphs[0].runs else tf.add_paragraph()
        para.line_spacing = 1.3
        para.space_after = Pt(12)

        dot = para.add_run()
        dot.text = "▪ "
        _style_run(dot, BODY_SIZE, bold=True, color=C_ACCENT)

        # 「前缀：其余」拆分：前缀（≤14 字）加粗，提高可扫读性
        head, rest = (line.split("：", 1) if "：" in line[:16] else ("", line))
        if head:
            r_head = para.add_run()
            r_head.text = head + "："
            _style_run(r_head, BODY_SIZE, bold=True, color=C_TEXT)
        r_body = para.add_run()
        r_body.text = rest
        _style_run(r_body, BODY_SIZE, color=C_TEXT)


def _content_slide(prs, page: dict[str, Any], idx: int, total: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    # 顶部标题带
    band_h = int(1.05 * IN)
    _add_rect(slide, 0, 0, SLIDE_W, band_h, C_PRIMARY)
    _add_rect(slide, 0, band_h, SLIDE_W, int(0.05 * IN), C_ACCENT)

    # 标题（带内垂直居中）
    tf_title = _add_textbox(slide, int(0.55 * IN), 0, int(9.6 * IN), band_h)
    tf_title.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf_title.paragraphs[0]
    r = p.add_run()
    r.text = page.get("title", "")
    _style_run(r, TITLE_SIZE, bold=True, color=C_WHITE)

    # 时长徽章（右上角，deck.pages[].minutes）
    minutes = page.get("minutes")
    if minutes:
        chip_w, chip_h = int(1.5 * IN), int(0.5 * IN)
        chip = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            SLIDE_W - chip_w - int(0.55 * IN),
            (band_h - chip_h) // 2,
            chip_w,
            chip_h,
        )
        chip.fill.solid()
        chip.fill.fore_color.rgb = C_ACCENT
        chip.line.fill.background()
        chip.shadow.inherit = False
        ctf = chip.text_frame
        ctf.word_wrap = False
        ctf.margin_top = ctf.margin_bottom = 0
        cp = ctf.paragraphs[0]
        cp.alignment = PP_ALIGN.CENTER
        cr = cp.add_run()
        cr.text = f"约 {minutes} 分钟"
        _style_run(cr, Pt(13), bold=True, color=C_WHITE)

    # 正文区（占满版心，不再挤在左上角）
    body = _add_textbox(
        slide,
        int(0.85 * IN),
        int(1.5 * IN),
        int(11.6 * IN),
        int(5.1 * IN),
    )
    _fill_bullets(body, page.get("bullets", []))

    # 页脚：课程名 + 页码
    tf_foot = _add_textbox(slide, int(0.55 * IN), SLIDE_H - int(0.42 * IN), int(6 * IN), int(0.3 * IN))
    fr = tf_foot.paragraphs[0].add_run()
    fr.text = FOOTER_TEXT
    _style_run(fr, FOOT_SIZE, color=C_MUTED)

    tf_num = _add_textbox(slide, SLIDE_W - int(1.5 * IN), SLIDE_H - int(0.42 * IN), int(1.0 * IN), int(0.3 * IN))
    tf_num.paragraphs[0].alignment = PP_ALIGN.RIGHT
    nr = tf_num.paragraphs[0].add_run()
    nr.text = f"{idx + 1} / {total}"
    _style_run(nr, FOOT_SIZE, color=C_MUTED)


def _cover_slide(prs, outline: dict[str, Any]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    # 左侧主色竖条 + 底部横条
    _add_rect(slide, 0, 0, int(0.28 * IN), SLIDE_H, C_PRIMARY)
    _add_rect(slide, 0, SLIDE_H - int(0.16 * IN), SLIDE_W, int(0.16 * IN), C_PRIMARY)
    _add_rect(slide, 0, SLIDE_H - int(0.16 * IN), int(4.2 * IN), int(0.16 * IN), C_ACCENT)

    # 标题上方橙色短线
    _add_rect(slide, int(1.15 * IN), int(2.25 * IN), int(1.6 * IN), int(0.09 * IN), C_ACCENT)

    # 主标题 / 副标题
    title = outline.get("title", "课程课件")
    tf_t = _add_textbox(slide, int(1.1 * IN), int(2.5 * IN), int(10.8 * IN), int(1.5 * IN))
    r = tf_t.paragraphs[0].add_run()
    r.text = title
    _style_run(r, COVER_TITLE_SIZE, bold=True, color=C_PRIMARY)

    subtitle = outline.get("subtitle", "")
    if subtitle:
        tf_s = _add_textbox(slide, int(1.15 * IN), int(4.15 * IN), int(10.5 * IN), int(0.9 * IN))
        sr = tf_s.paragraphs[0].add_run()
        sr.text = subtitle
        _style_run(sr, Pt(20), color=C_MUTED)

    # 页脚课程信息
    tf_f = _add_textbox(slide, int(1.15 * IN), SLIDE_H - int(0.75 * IN), int(9 * IN), int(0.35 * IN))
    fr = tf_f.paragraphs[0].add_run()
    fr.text = FOOTER_TEXT
    _style_run(fr, Pt(12), color=C_MUTED)


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
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    _cover_slide(prs, outline)
    total = len(pages) + 1
    for idx, page in enumerate(pages):
        _content_slide(prs, page, idx, total)
        note = page.get("note", "")
        if note:
            prs.slides[-1].notes_slide.notes_text_frame.text = note

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    logger.info("PPT 已生成：%s（%d 页）", out, total)
    return out
