"""PPT 文件生成工具：结构化 PptDeck → 可编辑 .pptx（python-pptx）。

版式策略 v3（设计系统升级，参考 ppt-deck-production / kals-mint-editorial 适配）：

视觉语言「Academic Blueprint」——教育蓝 + 青绿 + 暖金的高级编辑部风：
- 16:9 宽屏；全部用空白版式自绘（不用默认模板占位符）。
- 配色：深蓝主色 / 青绿强调 / 暖金高亮 / 浅蓝灰底；正文深灰，页脚浅灰。
- 版式族（按内容智能选择）：封面、章节分隔页、双栏论点、卡片组、大数字、
  时间轴、要点正文、金句陈述。
- 装饰：半透明圆形光斑、编号徽章、短强调线、页脚页码，提升精致度。
- 授课备注写入 notes_slide。

设计 token 与组件族命名对齐 ppt-deck-production 的 Shared Rules，
便于后续接入物料工厂（ImageGen 插图）与字体三级方案。
"""

import logging
import re
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

logger = logging.getLogger(__name__)

# ---- 字体（三级方案：默认系统通用字体，跨机可读）----
FONT = "微软雅黑"  # 封面/标题/正文统一；如需更 distinctive 可换优设标题黑/阿里巴巴普惠体

# ---- 设计 token（Academic Blueprint）----
C_NAVY = RGBColor(0x12, 0x3A, 0x5E)      # 深蓝：主色 / 封面 / 章节页底色
C_NAVY_DK = RGBColor(0x0C, 0x27, 0x42)   # 更深的蓝：装饰圆
C_TEAL = RGBColor(0x1F, 0xA8, 0xA0)      # 青绿：强调 / 徽章 / 标记
C_TEAL_LT = RGBColor(0xD6, 0xF0, 0xEC)   # 浅青：白色底上的装饰圆
C_GOLD = RGBColor(0xF2, 0xA9, 0x3B)      # 暖金：高亮 / 大数字 / 强调线
C_GOLD_LT = RGBColor(0xFB, 0xE9, 0xC8)   # 浅金：装饰
C_TEXT = RGBColor(0x1F, 0x29, 0x33)      # 正文深灰
C_MUTED = RGBColor(0x6B, 0x77, 0x87)     # 辅助浅灰
C_LINE = RGBColor(0xDC, 0xE6, 0xF0)      # 细线 / 卡片描边
C_CARD = RGBColor(0xFF, 0xFF, 0xFF)       # 卡片底
C_PAGE_BG = RGBColor(0xF2, 0xF7, 0xFB)    # 内容页浅蓝底
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# 16:9 画布
SLIDE_W = Emu(12192000)
SLIDE_H = Emu(6858000)
IN = 914400  # EMU per inch

# 字号（pt）
SZ_COVER = Pt(40)
SZ_SECTION = Pt(34)
SZ_TITLE = Pt(25)
SZ_CLAIM = Pt(23)
SZ_BODY = Pt(16)
SZ_CARD_T = Pt(18)
SZ_CARD_B = Pt(14)
SZ_BIGNUM = Pt(66)
SZ_TAG = Pt(12)
SZ_FOOT = Pt(10)

FOOTER_TEXT = "AI 教学智能体平台 · 软件建模课程"
COURSE_TAG = "软件建模课程"


# ----------------------------------------------------------------------------
# 基础绘制助手
# ----------------------------------------------------------------------------
def _ea(run, font: str = FONT) -> None:
    """给 run 设置东亚字体名，避免中文回退宋体。"""
    run.font.name = font
    r_pr = run._r.get_or_add_rPr()
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    ea = r_pr.find(f"{ns}ea")
    if ea is None:
        ea = r_pr.makeelement(f"{ns}ea", {"typeface": font})
        r_pr.append(ea)
    else:
        ea.set("typeface", font)


def style(run, size: Pt, *, bold: bool = False, color: RGBColor = C_TEXT, font: str = FONT) -> None:
    run.font.name = font
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = color
    _ea(run, font)


def add_rect(slide, x, y, w, h, color, *, line=None, line_w=Pt(1), shadow=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = line_w
    shp.shadow.inherit = shadow
    return shp


def add_round(slide, x, y, w, h, color, *, line=None, line_w=Pt(1.25), radius=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = line_w
    shp.shadow.inherit = False
    return shp


def add_circle(slide, x, y, d, color):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_text(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(2)
    tf.margin_top = tf.margin_bottom = Pt(2)
    return tf


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


# ----------------------------------------------------------------------------
# 版式分类（智能选择版式族）
# ----------------------------------------------------------------------------
def classify_layout(page: dict[str, Any]) -> str:
    """根据页面内容推断版式族；支持 page['layout'] 显式覆盖。"""
    if page.get("layout"):
        return page["layout"]
    bullets = page.get("bullets", [])
    if not bullets:
        return "statement"
    text = " ".join(bullets)
    is_metric = any(re.search(r"\d+\s*%|倍|提升|增长|覆盖|节省|降低|效率", b) for b in bullets) and len(bullets) <= 2
    if is_metric:
        return "big_number"
    if re.search(r"[①②③⑷⑸]|第一|第二|第三|步骤|阶段|首先|其次|接着|最后|流程|环节", text) or len(bullets) >= 7:
        return "timeline"
    if 3 <= len(bullets) <= 6:
        return "card_grid"
    if len(bullets) <= 2:
        return "two_column"
    return "bullet_body"


# ----------------------------------------------------------------------------
# 共用：页脚 + 页码 + 内容页底纹
# ----------------------------------------------------------------------------
def _page_chrome(slide, idx: int, total: int) -> None:
    ft = add_text(slide, int(0.55 * IN), SLIDE_H - int(0.42 * IN), int(6 * IN), int(0.3 * IN))
    r = ft.paragraphs[0].add_run()
    r.text = FOOTER_TEXT
    style(r, SZ_FOOT, color=C_MUTED)
    num = add_text(slide, SLIDE_W - int(1.6 * IN), SLIDE_H - int(0.42 * IN), int(1.05 * IN), int(0.3 * IN))
    num.paragraphs[0].alignment = PP_ALIGN.RIGHT
    r2 = num.paragraphs[0].add_run()
    r2.text = f"{idx} / {total}"
    style(r2, SZ_FOOT, color=C_MUTED)


def _section_tag(slide, section: str) -> None:
    if not section:
        return
    w = int(0.18 * IN) * len(section) + int(0.5 * IN)
    tag = add_round(slide, SLIDE_W - w - int(0.55 * IN), int(0.55 * IN), w, int(0.42 * IN),
                    C_TEAL_LT, line=C_TEAL, line_w=Pt(1))
    tf = tag.text_frame
    tf.word_wrap = False
    tf.margin_top = tf.margin_bottom = Pt(1)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = section
    style(r, SZ_TAG, bold=True, color=C_NAVY)


def _content_bg(slide) -> None:
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, C_PAGE_BG)


def _content_header(slide, title: str, section: str) -> None:
    """内容页标题：左上深蓝粗体 + 青绿短强调线 + 右上章节标签 + 右侧装饰圆。"""
    # 标题
    tf = add_text(slide, int(0.6 * IN), int(0.5 * IN), int(10.5 * IN), int(0.9 * IN))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = tf.paragraphs[0].add_run()
    r.text = title
    style(r, SZ_TITLE, bold=True, color=C_NAVY)
    # 青绿短强调线
    add_rect(slide, int(0.62 * IN), int(1.42 * IN), int(1.0 * IN), int(0.07 * IN), C_GOLD)
    # 右上章节标签
    _section_tag(slide, section)
    # 右上角浅青装饰圆
    add_circle(slide, SLIDE_W - int(1.05 * IN), int(0.95 * IN), int(0.55 * IN), C_TEAL_LT)


# ----------------------------------------------------------------------------
# 各版式实现
# ----------------------------------------------------------------------------
def _cover_slide(prs, outline: dict[str, Any]) -> None:
    slide = _blank(prs)
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, C_WHITE)
    # 左侧深蓝竖条
    add_rect(slide, 0, 0, int(0.32 * IN), SLIDE_H, C_NAVY)
    # 装饰圆（右上青绿、右下深蓝）
    add_circle(slide, SLIDE_W - int(2.6 * IN), int(-0.9 * IN), int(3.4 * IN), C_TEAL_LT)
    add_circle(slide, SLIDE_W - int(1.7 * IN), int(3.4 * IN), int(2.2 * IN), C_PAGE_BG)
    # 顶部 logo 徽章（青绿圆 + 白字）
    badge = add_circle(slide, int(1.1 * IN), int(1.15 * IN), int(0.7 * IN), C_TEAL)
    btf = badge.text_frame
    btf.vertical_anchor = MSO_ANCHOR.MIDDLE
    bp = btf.paragraphs[0]
    bp.alignment = PP_ALIGN.CENTER
    br = bp.add_run()
    br.text = "UML"
    style(br, Pt(15), bold=True, color=C_WHITE)
    # 标题上方金色短强调线
    add_rect(slide, int(1.12 * IN), int(2.35 * IN), int(1.7 * IN), int(0.1 * IN), C_GOLD)
    # 主标题
    title = outline.get("title", "课程课件")
    tf = add_text(slide, int(1.08 * IN), int(2.6 * IN), int(10.6 * IN), int(1.7 * IN))
    r = tf.paragraphs[0].add_run()
    r.text = title
    style(r, SZ_COVER, bold=True, color=C_NAVY)
    # 副标题
    subtitle = outline.get("subtitle", "")
    if subtitle:
        st = add_text(slide, int(1.12 * IN), int(4.35 * IN), int(10.2 * IN), int(0.9 * IN))
        r2 = st.paragraphs[0].add_run()
        r2.text = subtitle
        style(r2, Pt(19), color=C_MUTED)
    # 底部深蓝带 + 课程标签
    add_rect(slide, 0, SLIDE_H - int(0.85 * IN), SLIDE_W, int(0.85 * IN), C_NAVY)
    add_rect(slide, 0, SLIDE_H - int(0.85 * IN), int(3.2 * IN), int(0.85 * IN), C_TEAL)
    tfb = add_text(slide, int(0.6 * IN), SLIDE_H - int(0.85 * IN), int(9 * IN), int(0.85 * IN))
    tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
    rb = tfb.paragraphs[0].add_run()
    rb.text = COURSE_TAG
    style(rb, Pt(15), bold=True, color=C_WHITE)
    r3 = add_text(slide, int(3.5 * IN), SLIDE_H - int(0.85 * IN), int(8 * IN), int(0.85 * IN))
    r3.vertical_anchor = MSO_ANCHOR.MIDDLE
    rr = r3.paragraphs[0].add_run()
    rr.text = FOOTER_TEXT
    style(rr, Pt(12), color=C_TEAL_LT)


def _section_divider(prs, section: str, number: int) -> None:
    slide = _blank(prs)
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, C_NAVY)
    # 装饰圆
    add_circle(slide, SLIDE_W - int(3.0 * IN), int(-1.0 * IN), int(3.6 * IN), C_NAVY_DK)
    add_circle(slide, int(-0.6 * IN), SLIDE_H - int(2.0 * IN), int(2.6 * IN), C_TEAL)
    add_rect(slide, 0, 0, int(0.3 * IN), SLIDE_H, C_GOLD)
    # 大章节号
    tf_n = add_text(slide, int(0.9 * IN), int(1.7 * IN), int(4 * IN), int(2.4 * IN))
    tf_n.vertical_anchor = MSO_ANCHOR.MIDDLE
    rn = tf_n.paragraphs[0].add_run()
    rn.text = f"{number:02d}"
    style(rn, Pt(96), bold=True, color=C_GOLD)
    # 章节名
    tf_t = add_text(slide, int(1.0 * IN), int(4.0 * IN), int(10.6 * IN), int(1.5 * IN))
    rt = tf_t.paragraphs[0].add_run()
    rt.text = section
    style(rt, SZ_SECTION, bold=True, color=C_WHITE)
    # 金色短强调线
    add_rect(slide, int(1.04 * IN), int(3.75 * IN), int(1.2 * IN), int(0.09 * IN), C_GOLD)


def _split_head(bullet: str):
    bullet = str(bullet).strip()
    if "：" in bullet[:18]:
        head, rest = bullet.split("：", 1)
        return head, rest
    if ":" in bullet[:18]:
        head, rest = bullet.split(":", 1)
        return head, rest
    return "", bullet


def _bullet_rows(tf, bullets, size=SZ_BODY, *, color=C_TEXT, marker=C_TEAL):
    for i, line in enumerate(bullets):
        line = str(line).strip()
        if not line:
            continue
        p = tf.paragraphs[0] if (i == 0 and not tf.paragraphs[0].runs) else tf.add_paragraph()
        p.line_spacing = 1.25
        p.space_after = Pt(11)
        m = p.add_run()
        m.text = "▪ "
        style(m, size, bold=True, color=marker)
        head, rest = _split_head(line)
        if head:
            rh = p.add_run()
            rh.text = head + "："
            style(rh, size, bold=True, color=C_NAVY)
        rb = p.add_run()
        rb.text = rest
        style(rb, size, color=color)


def _layout_statement(slide, page):
    # 金句 / 标题陈述：居中大字号
    bullets = page.get("bullets", [])
    lead = bullets[0] if bullets else page.get("title", "")
    tf = add_text(slide, int(1.2 * IN), int(2.4 * IN), int(10.4 * IN), int(2.6 * IN))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = lead
    style(r, Pt(30), bold=True, color=C_NAVY)
    add_rect(slide, int(5.9 * IN), int(2.1 * IN), int(1.4 * IN), int(0.1 * IN), C_GOLD)


def _layout_two_column(slide, page):
    bullets = page.get("bullets", [])
    # 左：大论点（取第一条，head 加粗）
    head, rest = _split_head(bullets[0]) if bullets else ("", "")
    left = add_text(slide, int(0.7 * IN), int(2.0 * IN), int(6.0 * IN), int(4.0 * IN))
    left.vertical_anchor = MSO_ANCHOR.MIDDLE
    if head:
        pl = left.paragraphs[0]
        rl = pl.add_run(); rl.text = head
        style(rl, SZ_CLAIM, bold=True, color=C_NAVY)
        if rest:
            pl2 = left.add_paragraph(); rl2 = pl2.add_run(); rl2.text = rest
            style(rl2, SZ_CLAIM, color=C_TEXT)
    else:
        pl = left.paragraphs[0]
        rl = pl.add_run(); rl.text = rest
        style(rl, SZ_CLAIM, bold=True, color=C_NAVY)
    # 右：其余要点
    right = add_text(slide, int(7.1 * IN), int(2.1 * IN), int(4.6 * IN), int(3.9 * IN))
    _bullet_rows(right, bullets[1:], size=SZ_BODY)


def _layout_card_grid(slide, page):
    bullets = page.get("bullets", [])
    n = len(bullets)
    cols = 2 if n <= 4 else 3
    rows = (n + cols - 1) // cols
    gap = int(0.3 * IN)
    area_x = int(0.65 * IN)
    area_y = int(1.75 * IN)
    area_w = int(11.6 * IN)
    area_h = int(4.6 * IN)
    cw = (area_w - gap * (cols - 1)) // cols
    ch = (area_h - gap * (rows - 1)) // rows
    for i, line in enumerate(bullets):
        r = i // cols
        c = i % cols
        x = area_x + c * (cw + gap)
        y = area_y + r * (ch + gap)
        card = add_round(slide, x, y, cw, ch, C_WHITE, line=C_LINE, line_w=Pt(1.25))
        # 浅色大号水印数字（填充留白、增强设计感，置于文本之下）
        wm = add_text(slide, x + cw - int(1.5 * IN), y + ch - int(1.7 * IN),
                      int(1.5 * IN), int(1.7 * IN))
        wm.vertical_anchor = MSO_ANCHOR.BOTTOM
        wp = wm.paragraphs[0]
        wp.alignment = PP_ALIGN.RIGHT
        wrun = wp.add_run(); wrun.text = str(i + 1)
        style(wrun, Pt(72), bold=True, color=C_TEAL_LT)
        # 顶部青绿条
        add_rect(slide, x, y, cw, int(0.12 * IN), C_TEAL)
        # 编号徽章
        badge = add_circle(slide, x + int(0.28 * IN), y + int(0.32 * IN), int(0.5 * IN), C_TEAL)
        btf = badge.text_frame; btf.vertical_anchor = MSO_ANCHOR.MIDDLE
        bp = btf.paragraphs[0]; bp.alignment = PP_ALIGN.CENTER
        br = bp.add_run(); br.text = str(i + 1)
        style(br, Pt(15), bold=True, color=C_WHITE)
        # 标题 + 正文
        head, rest = _split_head(line)
        tf = add_text(slide, x + int(0.95 * IN), y + int(0.28 * IN), cw - int(1.15 * IN), int(0.7 * IN))
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        ct = tf.paragraphs[0]
        cr = ct.add_run(); cr.text = (head or rest)[:24]
        style(cr, SZ_CARD_T, bold=True, color=C_NAVY)
        if head and rest:
            bt = add_text(slide, x + int(0.3 * IN), y + int(1.0 * IN), cw - int(0.55 * IN), ch - int(1.25 * IN))
            pr = bt.paragraphs[0]
            pr.line_spacing = 1.35
            rr = pr.add_run(); rr.text = rest
            style(rr, SZ_CARD_B, color=C_MUTED)


def _layout_timeline(slide, page):
    bullets = page.get("bullets", [])
    n = len(bullets)
    x_line = int(1.5 * IN)
    top = int(2.1 * IN)
    bottom = int(6.1 * IN)
    step = (bottom - top) / max(1, n - 1) if n > 1 else 0
    # 竖线
    add_rect(slide, x_line - int(0.03 * IN), top, int(0.06 * IN), bottom - top, C_LINE)
    for i, line in enumerate(bullets):
        y = top + int(step * i) if n > 1 else int((top + bottom) / 2)
        # 节点圆
        node = add_circle(slide, x_line - int(0.28 * IN), y - int(0.28 * IN), int(0.56 * IN), C_TEAL)
        ntf = node.text_frame; ntf.vertical_anchor = MSO_ANCHOR.MIDDLE
        np_ = ntf.paragraphs[0]; np_.alignment = PP_ALIGN.CENTER
        nr = np_.add_run(); nr.text = str(i + 1)
        style(nr, Pt(14), bold=True, color=C_WHITE)
        # 文本
        head, rest = _split_head(line)
        tf = add_text(slide, x_line + int(0.55 * IN), y - int(0.5 * IN), int(9.2 * IN), int(0.95 * IN))
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pr = tf.paragraphs[0]
        if head:
            rh = pr.add_run(); rh.text = head + "："
            style(rh, SZ_CARD_T, bold=True, color=C_NAVY)
            rb = pr.add_run(); rb.text = rest
            style(rb, SZ_CARD_T, color=C_TEXT)
        else:
            rr = pr.add_run(); rr.text = rest
            style(rr, SZ_CARD_T, color=C_NAVY)


def _parse_metric(bullet: str):
    # 同时捕获数字后紧邻的单位（%、倍、万、个…），避免标签残留 " 倍" 之类悬空单位
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(%|倍|万|千|个|项|条|名|人|门|节|次|所|家|页|天|分|秒|小时)?",
        bullet,
    )
    if not m:
        return None, bullet
    num = m.group(1) + (m.group(2) or "")
    label = (bullet[: m.start()] + bullet[m.end():]).strip()
    label = re.sub(r"[\s　]+", " ", label).strip(" ：:，,。、；;")
    return num, label


def _layout_big_number(slide, page):
    bullets = page.get("bullets", [])
    pairs = [_parse_metric(b) for b in bullets][:2]
    pairs = [(num, label) for num, label in pairs if num]
    if not pairs:
        _layout_two_column(slide, page)
        return
    n = len(pairs)
    cx = int(1.0 * IN)
    cw = (int(11.2 * IN) - (n - 1) * int(0.6 * IN)) // n if n > 1 else int(11.2 * IN)
    for i, (num, label) in enumerate(pairs):
        x = cx + i * (cw + int(0.6 * IN))
        # 大数字
        tf = add_text(slide, x, int(2.5 * IN), cw, int(2.0 * IN))
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = num
        style(r, SZ_BIGNUM, bold=True, color=C_GOLD)
        # 标签
        lt = add_text(slide, x, int(4.7 * IN), cw, int(1.2 * IN))
        lt.vertical_anchor = MSO_ANCHOR.MIDDLE
        p2 = lt.paragraphs[0]; p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run(); r2.text = label or "关键指标"
        style(r2, Pt(16), color=C_MUTED)
        # 装饰
        add_circle(slide, x + cw // 2 - int(0.9 * IN), int(1.5 * IN), int(1.8 * IN), C_TEAL_LT)


def _layout_bullet_body(slide, page):
    bullets = page.get("bullets", [])
    # 多于 4 条分两栏
    if len(bullets) > 4:
        half = (len(bullets) + 1) // 2
        left = add_text(slide, int(0.8 * IN), int(1.9 * IN), int(5.6 * IN), int(4.3 * IN))
        right = add_text(slide, int(6.6 * IN), int(1.9 * IN), int(5.6 * IN), int(4.3 * IN))
        _bullet_rows(left, bullets[:half])
        _bullet_rows(right, bullets[half:])
    else:
        body = add_text(slide, int(0.85 * IN), int(1.9 * IN), int(11.4 * IN), int(4.3 * IN))
        _bullet_rows(body, bullets, size=SZ_BODY + Pt(1))


def _content_slide(prs, page: dict[str, Any], idx: int, total: int, section: str) -> None:
    slide = _blank(prs)
    _content_bg(slide)
    _content_header(slide, page.get("title", ""), section)
    layout = classify_layout(page)
    dispatch = {
        "statement": _layout_statement,
        "two_column": _layout_two_column,
        "card_grid": _layout_card_grid,
        "timeline": _layout_timeline,
        "big_number": _layout_big_number,
        "bullet_body": _layout_bullet_body,
    }
    dispatch.get(layout, _layout_bullet_body)(slide, page)
    _page_chrome(slide, idx, total)


def deck_to_pptx(deck: dict[str, Any], out_path: str | Path) -> Path:
    """把 deck（outline + pages）渲染为 .pptx 文件。

    Args:
        deck: {"outline": {"title","subtitle",...}, "pages": [{"title","bullets","note","minutes","section"}]}
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

    prev_section = None
    content_idx = 0
    total_content = len(pages)
    section_number = 0
    for page in pages:
        sec = str(page.get("section", "") or "")
        if sec and sec != prev_section:
            section_number += 1
            _section_divider(prs, sec, section_number)
            prev_section = sec
        _content_slide(prs, page, content_idx + 1, total_content, sec)
        note = page.get("note", "")
        if note:
            prs.slides[-1].notes_slide.notes_text_frame.text = note
        content_idx += 1

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    logger.info("PPT 已生成：%s（%d 页，含封面/章节页）", out, len(prs.slides._sldIdLst))
    return out
