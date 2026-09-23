"""draw.io 确定性渲染器：UseCaseModel → mxfile XML（diagrams.net 可直接打开编辑）。

与 plantuml.py 同一设计约束：
- 相同输入 → 完全相同输出（确定性坐标与 id）；
- 用户输入只作为显示文本（XML 转义），不进入 id/结构；
- alias 与 plantuml.py 一致（actor_N / usecase_N），保证两份产物可互相印证；
- 不调用网络/LLM/文件系统。
"""

from xml.sax.saxutils import escape

from app.models.uml import RelationType, UseCaseModel


def _xml_escape(text: str) -> str:
    """XML 转义：& < > 与引号（引号在属性值中必须转义，否则破坏 XML 结构）。"""
    return escape(text, {'"': "&quot;"})


# 布局常量（确定性网格）
_ACTOR_X = 60
_ACTOR_W = 40
_ACTOR_H = 80
_ACTOR_GAP = 40
_UC_W = 170
_UC_H = 56
_UC_COL_GAP = 30
_UC_ROW_GAP = 30
_BOUNDARY_PAD = 40
_BOUNDARY_X = 220

# 关系 → 边样式与构造型标签（direction 保持 source → target）
_EDGE_STYLES: dict[RelationType, tuple[str, str]] = {
    RelationType.ASSOCIATION: ("endArrow=none;html=1;", ""),
    RelationType.INCLUDE: ("endArrow=open;dashed=1;html=1;", "«include»"),
    RelationType.EXTEND: ("endArrow=open;dashed=1;html=1;", "«extend»"),
    RelationType.GENERALIZATION: ("endArrow=block;endFill=0;html=1;", ""),
}


def render_usecase_drawio(model: UseCaseModel) -> str:
    """把用例图模型渲染为 draw.io (mxfile) XML 字符串。"""
    if not isinstance(model, UseCaseModel):
        raise TypeError(f"render_usecase_drawio 只接受 UseCaseModel，收到 {type(model).__name__}")

    esc = _xml_escape
    actor_alias = {a.name: f"actor_{i}" for i, a in enumerate(model.actors, start=1)}
    usecase_alias = {u.id: f"usecase_{i}" for i, u in enumerate(model.usecases, start=1)}

    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    # 系统边界（尺寸随用例数量自适应，2 列网格）
    uc_rows = (len(model.usecases) + 1) // 2
    boundary_h = max(240, uc_rows * (_UC_H + _UC_ROW_GAP) + _BOUNDARY_PAD * 2)
    cells.append(
        f'<mxCell id="boundary" value="{esc(model.system)}" '
        'style="rounded=0;whiteSpace=wrap;html=1;verticalAlign=top;align=center;fontSize=14;fontStyle=1;" '
        f'vertex="1" parent="1"><mxGeometry x="{_BOUNDARY_X}" y="40" width="520" '
        f'height="{boundary_h}" as="geometry"/></mxCell>'
    )

    # Actor：左列垂直均布
    for actor in model.actors:
        i = model.actors.index(actor) + 1
        y = 80 + (i - 1) * (_ACTOR_H + _ACTOR_GAP)
        cells.append(
            f'<mxCell id="{actor_alias[actor.name]}" value="{esc(actor.name)}" '
            'style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;" '
            f'vertex="1" parent="1"><mxGeometry x="{_ACTOR_X}" y="{y}" width="{_ACTOR_W}" '
            f'height="{_ACTOR_H}" as="geometry"/></mxCell>'
        )

    # UseCase：边界内 2 列网格（确定性坐标）
    for i, uc in enumerate(model.usecases):
        col = i % 2
        row = i // 2
        x = _BOUNDARY_X + _BOUNDARY_PAD + col * (_UC_W + _UC_COL_GAP)
        y = 40 + _BOUNDARY_PAD + row * (_UC_H + _UC_ROW_GAP)
        cells.append(
            f'<mxCell id="{usecase_alias[uc.id]}" value="{esc(uc.name)}" '
            'style="ellipse;whiteSpace=wrap;html=1;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{_UC_W}" height="{_UC_H}" as="geometry"/></mxCell>'
        )

    # 关系边：方向保持 source → target，样式由类型决定
    for edge_num, rel in enumerate(model.relations, start=1):
        src = actor_alias.get(rel.source_id) or usecase_alias[rel.source_id]
        dst = actor_alias.get(rel.target_id) or usecase_alias[rel.target_id]
        style, label = _EDGE_STYLES[rel.type]
        value_attr = f' value="{esc(label)}"' if label else ""
        cells.append(
            f'<mxCell id="edge_{edge_num}"{value_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    body = "\n        ".join(cells)
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="usecase-model" name="UML 用例图">\n'
        '    <mxGraphModel dx="1000" dy="700" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1100" pageHeight="850">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )
