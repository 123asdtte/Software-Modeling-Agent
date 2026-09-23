"""SVG 确定性渲染器：UseCaseModel → 矢量图（与 drawio XML 共用同一套布局常量）。

设计约束（同 drawio_renderer）：
- 相同输入 → 完全相同输出；
- 用户输入只作为显示文本（XML 转义）；
- 布局坐标与 drawio_renderer 一致，两份产物视觉对应；
- 不调用网络/LLM/文件系统。
"""

from xml.sax.saxutils import escape

from app.models.uml import RelationType, UseCaseModel
from app.renderers.drawio_renderer import (
    _ACTOR_GAP,
    _ACTOR_H,
    _ACTOR_W,
    _ACTOR_X,
    _BOUNDARY_PAD,
    _BOUNDARY_X,
    _UC_COL_GAP,
    _UC_H,
    _UC_ROW_GAP,
    _UC_W,
)


def _xml_escape(text: str) -> str:
    """XML 转义：& < > 与引号。"""
    return escape(text, {'"': "&quot;"})


def render_usecase_svg(model: UseCaseModel) -> str:
    """把用例图模型渲染为 SVG 字符串（可缩放矢量图）。"""
    if not isinstance(model, UseCaseModel):
        raise TypeError(f"render_usecase_svg 只接受 UseCaseModel，收到 {type(model).__name__}")

    esc = _xml_escape

    # 布局坐标（与 drawio_renderer 一致）
    actor_centers: dict[str, tuple[float, float]] = {}
    for i, actor in enumerate(model.actors):
        y = 80 + i * (_ACTOR_H + _ACTOR_GAP)
        actor_centers[actor.name] = (_ACTOR_X + _ACTOR_W / 2, y + _ACTOR_H / 2)

    uc_centers: dict[str, tuple[float, float]] = {}
    for i, uc in enumerate(model.usecases):
        col, row = i % 2, i // 2
        x = _BOUNDARY_X + _BOUNDARY_PAD + col * (_UC_W + _UC_COL_GAP)
        y = 40 + _BOUNDARY_PAD + row * (_UC_H + _UC_ROW_GAP)
        uc_centers[uc.id] = (x + _UC_W / 2, y + _UC_H / 2)

    uc_rows = (len(model.usecases) + 1) // 2
    boundary_h = max(240, uc_rows * (_UC_H + _UC_ROW_GAP) + _BOUNDARY_PAD * 2)
    max_y = 80 + max(len(model.actors) - 1, 0) * (_ACTOR_H + _ACTOR_GAP) + _ACTOR_H + 40
    width = max(1100, _BOUNDARY_X + 520 + 40)
    height = max(850, boundary_h + 80, max_y + 40)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, Microsoft YaHei, sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')

    # 关系边先画（在形状下层），连接两端中心
    for rel in model.relations:
        src = actor_centers.get(rel.source_id) or uc_centers.get(rel.source_id)
        dst = actor_centers.get(rel.target_id) or uc_centers.get(rel.target_id)
        if not src or not dst:
            continue
        style_map = {
            RelationType.ASSOCIATION: 'stroke="#374151" stroke-width="1.5"',
            RelationType.INCLUDE: 'stroke="#6b7280" stroke-width="1.5" stroke-dasharray="6,4"',
            RelationType.EXTEND: 'stroke="#6b7280" stroke-width="1.5" stroke-dasharray="6,4"',
            RelationType.GENERALIZATION: 'stroke="#374151" stroke-width="1.5"',
        }
        parts.append(
            f'<line x1="{src[0]:.0f}" y1="{src[1]:.0f}" x2="{dst[0]:.0f}" y2="{dst[1]:.0f}" {style_map[rel.type]} />'
        )
        if rel.type in (RelationType.INCLUDE, RelationType.EXTEND):
            mx = (src[0] + dst[0]) / 2
            my = (src[1] + dst[1]) / 2
            label = "«include»" if rel.type == RelationType.INCLUDE else "«extend»"
            parts.append(
                f'<text x="{mx:.0f}" y="{my - 6:.0f}" font-size="12" fill="#6b7280" '
                f'text-anchor="middle">{esc(label)}</text>'
            )

    # 系统边界
    parts.append(
        f'<rect x="{_BOUNDARY_X}" y="40" width="520" height="{boundary_h}" fill="#f8fafc" '
        'stroke="#334155" stroke-width="1.5" />'
    )
    parts.append(
        f'<text x="{_BOUNDARY_X + 260}" y="66" font-size="15" font-weight="bold" '
        f'fill="#111827" text-anchor="middle">{esc(model.system)}</text>'
    )

    # Actor：简笔人形（头 + 身体 + 臂 + 腿）+ 底部名称
    for actor in model.actors:
        cx, cy = actor_centers[actor.name]
        top = cy - _ACTOR_H / 2
        head_r = 9
        parts.append(
            f'<circle cx="{cx:.0f}" cy="{top + head_r:.0f}" r="{head_r}" '
            'fill="#fff" stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx:.0f}" y1="{top + head_r * 2:.0f}" '
            f'x2="{cx:.0f}" y2="{top + 52:.0f}" stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx - 14:.0f}" y1="{top + 28:.0f}" '
            f'x2="{cx + 14:.0f}" y2="{top + 28:.0f}" stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx:.0f}" y1="{top + 52:.0f}" x2="{cx - 12:.0f}" '
            f'y2="{top + 72:.0f}" stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx:.0f}" y1="{top + 52:.0f}" x2="{cx + 12:.0f}" '
            f'y2="{top + 72:.0f}" stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{cx:.0f}" y="{top + _ACTOR_H + 16:.0f}" font-size="13" '
            f'fill="#111827" text-anchor="middle">{esc(actor.name)}</text>'
        )

    # UseCase：椭圆 + 居中名称
    for uc in model.usecases:
        cx, cy = uc_centers[uc.id]
        parts.append(
            f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{_UC_W / 2}" ry="{_UC_H / 2}" '
            'fill="#eff6ff" stroke="#1a56db" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{cx:.0f}" y="{cy + 5:.0f}" font-size="13" fill="#111827" '
            f'text-anchor="middle">{esc(uc.name)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)
