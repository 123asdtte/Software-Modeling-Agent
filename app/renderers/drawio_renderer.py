"""draw.io 确定性渲染器：6 种 UML 图型模型 → mxfile XML（diagrams.net 可直接打开编辑）。

与 plantuml.py 同一设计约束：
- 相同输入 → 完全相同输出（确定性坐标与 id）；
- 用户输入只作为显示文本（XML 转义），不进入 id/结构；
- alias 与 plantuml.py 一致，保证两份产物可互相印证；
- 不调用网络/LLM/文件系统。

2026-10-09 扩展：新增活动图（泳道分区 + 决策/并行）与状态机图（状态/转换/事件）渲染。
2026-10-26 扩展：新增类图（类框分区 + 6 种关系）、时序图（生命线 + 有序消息 + 片段）、
部署图（节点/构件 + 部署与通信关系）渲染，draw.io 导出与 PlantUML 导出能力对齐。
"""

import math
from xml.sax.saxutils import escape

from app.models.uml import (
    ActivityModel,
    ClassModel,
    ClassRelationType,
    DeployAssociationKind,
    DeploymentModel,
    DeployNodeKind,
    LifelineKind,
    MessageKind,
    RelationType,
    SequenceModel,
    StateMachineModel,
    UseCaseModel,
)


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
    # 先按「首个关联参与者」稳定排序：同一参与者的用例聚成一个连续区段，
    # 关联线才能在同一横向带内散开，否则连线会横穿整列用例（实测穿过椭圆内部）。
    actor_order = {a.name: i for i, a in enumerate(model.actors)}
    ordered_cases = sorted(
        enumerate(model.usecases),
        key=lambda pair: (actor_order.get((pair[1].actors or [""])[0], 999), pair[0]),
    )
    uc_cells: list[str] = []
    slot = -1
    cur_actor = object()
    for _, uc in ordered_cases:
        first_actor = (uc.actors or [""])[0]
        if first_actor != cur_actor:
            cur_actor = first_actor
            slot = (slot // 2 + 1) * 2 if slot >= 0 else 0  # 换参与者时另起一行
        else:
            slot += 1
        col = slot % 2
        row = slot // 2
        x = _BOUNDARY_X + _BOUNDARY_PAD + col * (_UC_W + _UC_COL_GAP)
        y = 40 + _BOUNDARY_PAD + row * (_UC_H + _UC_ROW_GAP)
        uc_cells.append(
            f'<mxCell id="{usecase_alias[uc.id]}" value="{esc(uc.name)}" '
            'style="ellipse;perimeter=ellipsePerimeter;whiteSpace=wrap;html=1;fillColor=#ffffff;" '
            f'vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{_UC_W}" height="{_UC_H}" as="geometry"/></mxCell>'
        )

    # 关系边：关联（UseCase.actors 隐式 + 显式 association，按无序对去重）在前，
    # include/extend/泛化在后。与 PlantUML 渲染器保持同一套语义，否则 drawio
    # 导出的用例图会只有参与者与用例漂浮、一根连线都没有。
    assoc_pairs: list[tuple[str, str]] = []
    seen_pairs: set[frozenset[str]] = set()
    for uc in model.usecases:
        for actor_name in uc.actors:
            pair = frozenset((actor_alias[actor_name], usecase_alias[uc.id]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                assoc_pairs.append((actor_alias[actor_name], usecase_alias[uc.id]))

    other_rels: list[tuple[str, str, RelationType]] = []
    for rel in model.relations:
        if rel.type == RelationType.ASSOCIATION:
            src = actor_alias.get(rel.source_id) or usecase_alias[rel.source_id]
            dst = actor_alias.get(rel.target_id) or usecase_alias[rel.target_id]
            pair = frozenset((src, dst))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                assoc_pairs.append((src, dst))
        else:
            other_rels.append(
                (
                    actor_alias.get(rel.source_id) or usecase_alias[rel.source_id],
                    actor_alias.get(rel.target_id) or usecase_alias[rel.target_id],
                    rel.type,
                )
            )

    edge_cells: list[str] = []
    edge_num = 0
    assoc_style = _EDGE_STYLES[RelationType.ASSOCIATION][0]
    for src, dst in assoc_pairs:
        edge_num += 1
        edge_cells.append(
            f'<mxCell id="edge_{edge_num}" style="{assoc_style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )
    for src, dst, rtype in other_rels:
        edge_num += 1
        style, label = _EDGE_STYLES[rtype]
        value_attr = f' value="{esc(label)}"' if label else ""
        edge_cells.append(
            f'<mxCell id="edge_{edge_num}"{value_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    # 层级：边界/参与者 → 连线 → 用例椭圆（椭圆最后画，压住穿过的线尾）
    cells.extend(edge_cells)
    cells.extend(uc_cells)
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


# ============================================================================
# 活动图 drawio 渲染：泳道分区背景 + 动作/决策/分叉汇合 + 监护条件边
# 布局：每个泳道一列（确定性），列内节点按模型顺序垂直排布。
# ============================================================================

_ACT_LANE_W = 220
_ACT_LANE_GAP = 30
_ACT_NODE_W = 172
_ACT_NODE_H = 46
_ACT_ROW_H = 78
_ACT_TOP = 70

_NODE_STYLES = {
    "initial": "ellipse;fillColor=#000000;strokeColor=#000000;html=1;",
    "final": "ellipse;fillColor=#000000;strokeColor=#000000;strokeWidth=4;html=1;",
    "action": "rounded=1;arcSize=40;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "fork": "fillColor=#000000;strokeColor=#000000;html=1;",
    "join": "fillColor=#000000;strokeColor=#000000;html=1;",
    "merge": "rhombus;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;",
}
_NODE_SIZES = {
    "initial": (30, 30),
    "final": (30, 30),
    "action": (_ACT_NODE_W, _ACT_NODE_H),
    "decision": (172, 84),
    "fork": (150, 12),
    "join": (150, 12),
    "merge": (150, 60),
}


def render_activity_drawio(model: ActivityModel) -> str:
    """把活动图模型渲染为 draw.io XML（对齐参考样例）：
    泳道紧贴成池、节点按控制流深度逐行交错（跨泳道呈 Z 字折线）、
    final 双圆环、按泳道着色、正交边出底入顶。
    """
    if not isinstance(model, ActivityModel):
        raise TypeError(f"render_activity_drawio 只接受 ActivityModel，收到 {type(model).__name__}")

    from collections import deque

    esc = _xml_escape
    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    lane_names = [s.name for s in model.swimlanes] or ["流程"]
    lane_col = {name: i for i, name in enumerate(lane_names)}

    # ---- 1) 控制流深度（BFS 层次）：决定节点所在行，跨泳道自然交错 ----
    out_edges: dict[str, list[str]] = {n.id: [] for n in model.nodes}
    in_deg = {n.id: 0 for n in model.nodes}
    for f in model.flows:
        if f.source in in_deg and f.target in in_deg and f.target not in out_edges[f.source]:
            out_edges[f.source].append(f.target)
            in_deg[f.target] += 1
    depth: dict[str, int] = {}
    q = deque([n.id for n in model.nodes if in_deg[n.id] == 0])
    for nid in q:
        depth[nid] = 0
    while q:
        u = q.popleft()
        for v in out_edges[u]:
            in_deg[v] -= 1
            depth[v] = max(depth.get(v, 0), depth[u] + 1)
            if in_deg[v] == 0:
                q.append(v)
    max_depth = max(depth.values()) if depth else 0
    for n in model.nodes:  # 孤立/环上节点兜底：排到最后
        if n.id not in depth:
            max_depth += 1
            depth[n.id] = max_depth

    # ---- 2) 行与泳道分配：无泳道的 initial/final 智能落位 ----
    initial_id = next((n.id for n in model.nodes if n.kind.value == "initial"), None)
    final_id = next((n.id for n in model.nodes if n.kind.value == "final"), None)
    assignments: dict[str, tuple[int, int]] = {}  # node.id -> (lane_idx, row)
    for node in model.nodes:
        li = lane_col.get(node.lane, 0)
        assignments[node.id] = (li, depth[node.id])
    # initial 无泳道 → 首列；final 无泳道 → 最长链尾节点所在泳道
    if initial_id and not next(n for n in model.nodes if n.id == initial_id).lane:
        assignments[initial_id] = (0, 0)
    if final_id and not next(n for n in model.nodes if n.id == final_id).lane:
        tail = max(
            (n.id for n in model.nodes if n.id in depth and n.id != final_id),
            key=lambda nid: depth[nid], default=None,
        )
        li = assignments[tail][0] if tail else 0
        assignments[final_id] = (li, max_depth)

    # ---- 2.5) 并行分支布局：fork 的子节点并列同一行、左右分列 ----
    # 否则两个分支会被排成上下两行，把「并行」画成「串行」——语义错误。
    flows_by_src: dict[str, list] = {}
    flows_by_dst: dict[str, list] = {}
    for f in model.flows:
        flows_by_src.setdefault(f.source, []).append(f)
        flows_by_dst.setdefault(f.target, []).append(f)

    pitch = _ACT_NODE_W + 24
    col_dx: dict[str, float] = {}
    bar_span: dict[str, int] = {}
    max_span = _ACT_NODE_W
    for node in model.nodes:
        if node.kind.value != "fork":
            continue
        kids = flows_by_src.get(node.id, [])
        if len(kids) < 2:
            continue
        base_row = assignments[node.id][1]
        for i, f in enumerate(kids):
            col_dx[f.target] = (i - (len(kids) - 1) / 2) * pitch
            assignments[f.target] = (assignments[f.target][0], base_row + 1)
        span = int((len(kids) - 1) * pitch + _ACT_NODE_W)
        bar_span[node.id] = span
        max_span = max(max_span, span)

    for node in model.nodes:
        if node.kind.value != "join":
            continue
        ins = flows_by_dst.get(node.id, [])
        if len(ins) < 2:
            continue
        dxx = [col_dx.get(f.source, 0) for f in ins]
        span = int(max(dxx) - min(dxx)) + _ACT_NODE_W
        bar_span[node.id] = max(span, bar_span.get(node.id, 0))
        max_span = max(max_span, bar_span[node.id])

    # ---- 2.6) 行号归一：保证每个节点至少比所有前驱低一行（回边不参与）----
    row_of = {nid: assignments[nid][1] for nid in assignments}
    for node in model.nodes:
        preds = [f.source for f in flows_by_dst.get(node.id, []) if f.source != node.id]
        real_preds = [p for p in preds if row_of.get(p, 10**6) < row_of[node.id]]
        if real_preds:
            need = max(row_of[p] for p in real_preds) + 1
            if need > row_of[node.id]:
                row_of[node.id] = need
    for nid, row in row_of.items():
        assignments[nid] = (assignments[nid][0], row)
    max_depth = max(row_of.values()) if row_of else 0

    _LANE_TOP, _ROW_H, _PAD_Y = 40, 100, 60
    _LANE_W = max(240, max_span + 60)  # 泳道至少容纳最宽的并行跨度
    total_rows = max_depth + 1
    lane_h = _PAD_Y + total_rows * _ROW_H + 60

    # ---- 3) 泳道紧贴成池（gap=0，共享边框）----
    lane_ids: list[str] = []
    for i, name in enumerate(lane_names):
        lid = f"lane{i + 1}"
        lane_ids.append(lid)
        x = 40 + i * _LANE_W
        cells.append(
            f'<mxCell id="{lid}" value="{esc(name)}" '
            'style="swimlane;whiteSpace=wrap;html=1;startSize=26;collapsible=0;'
            'fillColor=#f8f9fa;fontStyle=1;fontSize=14;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{_LANE_TOP}" width="{_LANE_W}" height="{lane_h}" as="geometry"/></mxCell>'
        )

    # ---- 4) 节点（parent=泳道；行=控制流深度，列=泳道中心）----
    _LANE_COLORS = [
        ("#dae8fc", "#6c8ebf"),
        ("#d5e8d4", "#82b366"),
        ("#ffe6cc", "#d79b00"),
        ("#e1d5e7", "#9673a6"),
        ("#fff2cc", "#d6b656"),
    ]
    _SIZE = {
        "initial": (34, 34), "final": (34, 34),
        "action": (172, 46), "decision": (172, 84),
        "fork": (150, 12), "join": (150, 12), "merge": (150, 60),
    }
    alias: dict[str, str] = {}
    for idx, node in enumerate(model.nodes):
        li, row = assignments[node.id]
        lid = lane_ids[li]
        alias[node.id] = f"act_{idx}"
        kind = node.kind.value
        w, h = _SIZE[kind]
        if node.id in bar_span:
            w = bar_span[node.id]  # fork/join 横条要覆盖所有并行分支
        cx = (_LANE_W - w) // 2 + int(col_dx.get(node.id, 0))
        cy = _PAD_Y + row * _ROW_H
        value = esc(node.name) if node.name else ""
        nid = alias[node.id]
        if kind == "final":
            cells.append(
                f'<mxCell id="{nid}" value="" '
                'style="ellipse;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;strokeWidth=2;" '
                f'vertex="1" parent="{lid}">'
                f'<mxGeometry x="{cx}" y="{cy}" width="{w}" height="{h}" as="geometry"/></mxCell>'
            )
            cells.append(
                f'<mxCell id="{nid}_inner" value="" '
                'style="ellipse;whiteSpace=wrap;html=1;fillColor=#000000;strokeColor=none;" '
                f'vertex="1" parent="{nid}">'
                '<mxGeometry x="9" y="9" width="16" height="16" as="geometry"/></mxCell>'
            )
            continue
        if kind == "initial":
            style = "ellipse;whiteSpace=wrap;html=1;fillColor=#000000;strokeColor=#000000;"
        elif kind in ("fork", "join"):
            style = "fillColor=#000000;strokeColor=#000000;html=1;"
        elif kind == "decision":
            style = "rhombus;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;"
        elif kind == "merge":
            style = "rhombus;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;"
        else:
            fill, stroke = _LANE_COLORS[li % len(_LANE_COLORS)]
            style = f"rounded=1;whiteSpace=wrap;html=1;arcSize=50;fillColor={fill};strokeColor={stroke};"
        cells.append(
            f'<mxCell id="{nid}" value="{value}" style="{style}" vertex="1" parent="{lid}">'
            f'<mxGeometry x="{cx}" y="{cy}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )

    # ---- 5) 控制流：正交边，统一出底入顶（相邻行自然成 Z 字折线）----
    _FLOW = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;labelBackgroundColor=#ffffff;" \
            "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
    decision_out_seq: dict[str, int] = {}
    fork_out_seq: dict[str, int] = {}
    join_in_seq: dict[str, int] = {}
    nodes_by_id = {n.id: n for n in model.nodes}
    for e_num, flow in enumerate(model.flows, start=1):
        src, dst = alias.get(flow.source), alias.get(flow.target)
        if not src or not dst:
            continue
        style = _FLOW
        src_kind = nodes_by_id[flow.source].kind.value
        dst_kind = nodes_by_id[flow.target].kind.value
        if src_kind == "decision":
            n = decision_out_seq.get(src, 0)
            decision_out_seq[src] = n + 1
            if n > 0:  # 决策第二条分支从右侧出，避免与第一条重叠
                style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;labelBackgroundColor=#ffffff;"
                         "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
        elif src_kind == "fork":
            # 并行分叉：每条分支从横条上按等分点下出，视觉上才是真分叉
            k = len(flows_by_src.get(flow.source, []))
            i = fork_out_seq.get(src, 0)
            fork_out_seq[src] = i + 1
            ex = (i + 1) / (k + 1) if k else 0.5
            style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;labelBackgroundColor=#ffffff;"
                     f"exitX={ex:.4f};exitY=1;exitDx=0;exitDy=0;"
                     "entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
        elif dst_kind == "join":
            # 并行汇合：每条入边按等分点入横条
            k = len(flows_by_dst.get(flow.target, []))
            i = join_in_seq.get(dst, 0)
            join_in_seq[dst] = i + 1
            ex = (i + 1) / (k + 1) if k else 0.5
            style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;labelBackgroundColor=#ffffff;"
                     "exitX=0.5;exitY=1;exitDx=0;exitDy=0;"
                     f"entryX={ex:.4f};entryY=0;entryDx=0;entryDy=0;")
        cond = (flow.cond or "").strip().strip("[]").strip()
        value_attr = f' value="{esc(cond)}"' if cond else ""
        cells.append(
            f'<mxCell id="flow_{e_num}"{value_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    body = "\n        ".join(cells)
    total_w = 40 + len(lane_names) * _LANE_W
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="activity-model" name="UML 活动图">\n'
        '    <mxGraphModel dx="1100" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{total_w}" pageHeight="{_LANE_TOP + lane_h + 60}">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


# 状态机布局常量（对齐活动图新风格：转换链深度逐行排布、双圆环 final）
_SM_STATE_W = 160
_SM_STATE_H = 48
_SM_COL_GAP = 50
_SM_ROW_H = 110
_SM_TOP = 60


def render_statemachine_drawio(model: StateMachineModel) -> str:
    """把状态机图模型渲染为 draw.io XML（对齐参考样例风格）：
    按转换链 BFS 深度逐行排布（主干竖直向下，分支状态横向展开）、
    final 双圆环、normal/paused 配色区分、事件[监护]转换标签。"""
    if not isinstance(model, StateMachineModel):
        raise TypeError(f"render_statemachine_drawio 只接受 StateMachineModel，收到 {type(model).__name__}")

    from collections import deque

    esc = _xml_escape
    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    # ---- 1) BFS 转换链深度：决定状态所在行 ----
    out_edges: dict[str, list[str]] = {s.id: [] for s in model.states}
    in_deg = {s.id: 0 for s in model.states}
    for t in model.transitions:
        if t.source in in_deg and t.target in in_deg and t.target not in out_edges[t.source]:
            out_edges[t.source].append(t.target)
            in_deg[t.target] += 1
    depth: dict[str, int] = {}
    q = deque([s.id for s in model.states if in_deg[s.id] == 0])
    for sid in q:
        depth[sid] = 0
    while q:
        u = q.popleft()
        for v in out_edges[u]:
            in_deg[v] -= 1
            depth[v] = max(depth.get(v, 0), depth[u] + 1)
            if in_deg[v] == 0:
                q.append(v)
    max_depth = max(depth.values()) if depth else 0
    for s in model.states:
        if s.id not in depth:
            max_depth += 1
            depth[s.id] = max_depth

    # ---- 2) 坐标：y=深度；同深度横向展开（居中）----
    _PAGE_W = 860
    center_x = _PAGE_W // 2
    pos: dict[str, tuple[int, int]] = {}  # id -> (x, y)
    by_depth: dict[int, list] = {}
    for st in model.states:
        by_depth.setdefault(depth[st.id], []).append(st)
    for dep, group in sorted(by_depth.items()):
        g = len(group)
        for i, st in enumerate(group):
            x = center_x + (i - (g - 1) / 2) * (_SM_STATE_W + _SM_COL_GAP) - _SM_STATE_W / 2
            pos[st.id] = (int(x), _SM_TOP + dep * _SM_ROW_H)

    # ---- 3) 状态单元（initial 黑圆 / normal 绿 / paused 黄虚线 / final 双圆环）----
    alias: dict[str, str] = {}
    for idx, st in enumerate(model.states):
        alias[st.id] = f"st_{idx}"
        x, y = pos[st.id]
        nid = alias[st.id]
        if st.kind.value == "initial":
            cells.append(
                f'<mxCell id="{nid}" value="" '
                'style="ellipse;whiteSpace=wrap;html=1;fillColor=#000000;strokeColor=#000000;" '
                f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="34" height="34" as="geometry"/></mxCell>'
            )
        elif st.kind.value == "final":
            cells.append(
                f'<mxCell id="{nid}" value="" '
                'style="ellipse;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;strokeWidth=2;" '
                f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="34" height="34" as="geometry"/></mxCell>'
            )
            cells.append(
                f'<mxCell id="{nid}_inner" value="" '
                'style="ellipse;whiteSpace=wrap;html=1;fillColor=#000000;strokeColor=none;" '
                f'vertex="1" parent="{nid}">'
                '<mxGeometry x="9" y="9" width="16" height="16" as="geometry"/></mxCell>'
            )
        else:
            label = esc(st.name) if st.name else esc(st.id)
            style = "rounded=1;whiteSpace=wrap;html=1;arcSize=30;fillColor=#d5e8d4;strokeColor=#82b366;"
            if st.kind.value == "paused":
                style = "rounded=1;whiteSpace=wrap;html=1;arcSize=30;dashed=1;fillColor=#fff2cc;strokeColor=#d6b656;"
            cells.append(
                f'<mxCell id="{nid}" value="{label}" style="{style}" vertex="1" parent="1">'
                f'<mxGeometry x="{x}" y="{y}" width="{_SM_STATE_W}" height="{_SM_STATE_H}" as="geometry"/></mxCell>'
            )

    # ---- 4) 转换边：出底入顶，event[guard] 标签；同源多分支右出 ----
    branch_seq: dict[str, int] = {}
    for t_num, tr in enumerate(model.transitions, start=1):
        src, dst = alias.get(tr.source), alias.get(tr.target)
        if not src or not dst:
            continue
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
                 "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
        n = branch_seq.get(src, 0)
        branch_seq[src] = n + 1
        if n > 0:
            style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
                     "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
        parts = []
        if tr.event:
            parts.append(esc(tr.event))
        if tr.guard:
            parts.append("[" + esc(tr.guard) + "]")
        value_attr = f' value="{" ".join(parts)}"' if parts else ""
        cells.append(
            f'<mxCell id="tr_{t_num}"{value_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    body = "\n        ".join(cells)
    total_rows = max_depth + 1
    page_h = _SM_TOP + total_rows * _SM_ROW_H + 80
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="statemachine-model" name="UML 状态机图">\n'
        '    <mxGraphModel dx="1100" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{_PAGE_W}" pageHeight="{page_h}">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


# ============================================================================
# 类图 drawio 渲染（C 任务）
# 布局：3 列网格（确定性），行高取该行最高类框，避免相互重叠。
# 类框：swimlane 标题 + 属性子行 + 分隔线 + 方法子行（draw.io 原生 UML 类样式）。
# ============================================================================

_CD_CLASS_W = 210
_CD_COL_GAP = 60
_CD_ROW_GAP = 70
_CD_LEFT = 60
_CD_TOP = 60
_CD_HEADER_H = 28
_CD_ROW_H = 19
_CD_SEP_H = 8

# 关系 → 边样式（菱形一律落在 source 端 = 整体/容器端，符合 UML 语义）
_CD_EDGE_STYLES: dict[ClassRelationType, str] = {
    ClassRelationType.ASSOCIATION: "endArrow=none;html=1;",
    ClassRelationType.AGGREGATION: "startArrow=diamondThin;startFill=0;endArrow=none;html=1;",
    ClassRelationType.COMPOSITION: "startArrow=diamondThin;startFill=1;endArrow=none;html=1;",
    ClassRelationType.GENERALIZATION: "endArrow=block;endFill=0;html=1;",
    ClassRelationType.DEPENDENCY: "endArrow=open;dashed=1;html=1;",
    ClassRelationType.REALIZATION: "endArrow=block;endFill=0;dashed=1;html=1;",
}

# 可见性枚举的取值本身即 UML 标记符号（+ - # ~），无需再映射
def _cd_attr_text(attr) -> str:
    """渲染单个属性行。"""
    vis = attr.visibility.value if attr.visibility else ""
    body = f"{attr.name}: {attr.type}" if attr.type else attr.name
    return f"{vis} {body}".strip()


def _cd_method_text(method) -> str:
    """渲染单个方法行（参数列表 + 返回类型）。"""
    vis = method.visibility.value if method.visibility else ""
    params = ", ".join(f"{p.name}: {p.type}" if p.type else p.name for p in method.params)
    ret = method.return_type or "void"
    return f"{vis} {method.name}({params}): {ret}".strip()


def _cd_header_h(item) -> int:
    """标题行高度：带 «interface»/«abstract» 构造型时需要两行空间。"""
    return _CD_HEADER_H + 12 if (item.is_interface or item.is_abstract) else _CD_HEADER_H


def _cd_line_count(text: str) -> int:
    """估算成员行在 210px 宽类框内的换行数（中文按 12px、ASCII 按 6.5px 计）。

    draw.io 的字体是比例字体，精确排版不可行；宁可多留一行高度，也不要文字重叠。
    """
    avail = _CD_CLASS_W - 14  # 左右 spacingLeft/Right 各 6 + 余量
    width = sum(12.0 if ord(ch) > 127 else 6.5 for ch in text)
    return max(1, math.ceil(width / avail))


def _cd_cell_height(item) -> int:
    attr_lines = sum(_cd_line_count(_cd_attr_text(a)) for a in item.attributes) or 1
    meth_lines = sum(_cd_line_count(_cd_method_text(m)) for m in item.methods) or 1
    return (
        _cd_header_h(item)
        + attr_lines * _CD_ROW_H
        + _CD_SEP_H
        + meth_lines * _CD_ROW_H
        + 8
    )


def render_class_drawio(model: ClassModel) -> str:
    """把类图模型渲染为 draw.io XML（类框分区 + 6 种关系边 + 两端多重性）。"""
    if not isinstance(model, ClassModel):
        raise TypeError(f"render_class_drawio 只接受 ClassModel，收到 {type(model).__name__}")

    esc = _xml_escape
    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    # ---- 1) 网格坐标：3 列，行高取该行最高类框 ----
    n = len(model.classes)
    cols = min(3, max(1, n))
    alias = {c.name: f"cls_{i}" for i, c in enumerate(model.classes, start=1)}
    heights = [_cd_cell_height(c) for c in model.classes]
    pos: dict[str, tuple[int, int]] = {}
    y = _CD_TOP
    for row_start in range(0, n, cols):
        row_items = model.classes[row_start : row_start + cols]
        row_h = max(heights[row_start : row_start + cols], default=_CD_HEADER_H)
        for col, item in enumerate(row_items):
            pos[item.name] = (_CD_LEFT + col * (_CD_CLASS_W + _CD_COL_GAP), y)
        y += row_h + _CD_ROW_GAP
    page_h = max(420, y + 40)
    page_w = max(760, _CD_LEFT * 2 + cols * _CD_CLASS_W + (cols - 1) * _CD_COL_GAP)

    # ---- 2) 类/接口框：标题 + 属性区 + 分隔线 + 方法区 ----
    for item in model.classes:
        cid = alias[item.name]
        x, cy = pos[item.name]
        h = _cd_cell_height(item)
        header_h = _cd_header_h(item)
        attr_h = (sum(_cd_line_count(_cd_attr_text(a)) for a in item.attributes) or 1) * _CD_ROW_H + 4
        meth_h = (sum(_cd_line_count(_cd_method_text(m)) for m in item.methods) or 1) * _CD_ROW_H + 4

        title = esc(item.name)
        font_style = 1
        if item.is_interface:
            title = f"&#171;interface&#187;<br>{title}"
        elif item.is_abstract:
            title = f"&#171;abstract&#187;<br>{title}"
            font_style = 2
        # 构造型前缀里的 <br> 需转为实体，才能被 draw.io 按 html 解析
        title = title.replace("<br>", "&lt;br&gt;")

        cells.append(
            f'<mxCell id="{cid}" value="{title}" '
            f'style="swimlane;fontStyle={font_style};align=center;verticalAlign=top;'
            f'startSize={header_h};resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=1;'
            'marginBottom=0;html=1;" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{cy}" width="{_CD_CLASS_W}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

        # 属性区
        attr_lines = []
        for a in item.attributes:
            line = _cd_attr_text(a)
            line = f"&lt;u&gt;{esc(line)}&lt;/u&gt;" if a.is_static else esc(line)
            attr_lines.append(line)
        attr_value = "&lt;br&gt;".join(attr_lines) if attr_lines else ""
        cells.append(
            f'<mxCell id="{cid}_attr" value="{attr_value}" '
            'style="text;strokeColor=none;fillColor=none;align=left;verticalAlign=top;'
            'spacingLeft=6;spacingRight=6;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];'
            'portConstraint=eastwest;whiteSpace=wrap;html=1;" '
            f'vertex="1" parent="{cid}"><mxGeometry y="{header_h}" width="{_CD_CLASS_W}" '
            f'height="{attr_h}" as="geometry"/></mxCell>'
        )

        # 分隔线（属性区 / 方法区之间）
        sep_y = header_h + attr_h
        cells.append(
            f'<mxCell id="{cid}_sep" value="" '
            'style="line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;'
            'spacingTop=-1;spacingLeft=3;spacingRight=3;rotatable=0;labelPosition=right;'
            'points=[];portConstraint=eastwest;strokeColor=inherit;" '
            f'vertex="1" parent="{cid}"><mxGeometry y="{sep_y}" width="{_CD_CLASS_W}" '
            f'height="{_CD_SEP_H}" as="geometry"/></mxCell>'
        )

        # 方法区
        meth_lines = []
        for m in item.methods:
            line = _cd_method_text(m)
            if m.is_abstract:
                line = f"&lt;i&gt;{esc(line)}&lt;/i&gt;"
            elif m.is_static:
                line = f"&lt;u&gt;{esc(line)}&lt;/u&gt;"
            else:
                line = esc(line)
            meth_lines.append(line)
        meth_value = "&lt;br&gt;".join(meth_lines) if meth_lines else ""
        cells.append(
            f'<mxCell id="{cid}_meth" value="{meth_value}" '
            'style="text;strokeColor=none;fillColor=none;align=left;verticalAlign=top;'
            'spacingLeft=6;spacingRight=6;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];'
            'portConstraint=eastwest;whiteSpace=wrap;html=1;" '
            f'vertex="1" parent="{cid}"><mxGeometry y="{sep_y + _CD_SEP_H}" width="{_CD_CLASS_W}" '
            f'height="{meth_h}" as="geometry"/></mxCell>'
        )

    # ---- 3) 关系边：泛化/实现 source=子类 → target=父类/接口（箭头指向 target）----
    for e_num, rel in enumerate(model.relations, start=1):
        src = alias.get(rel.source_id)
        dst = alias.get(rel.target_id)
        if not src or not dst:
            continue
        style = _CD_EDGE_STYLES.get(rel.type, "endArrow=none;html=1;")
        style += "edgeStyle=orthogonalEdgeStyle;rounded=0;"
        label_attr = f' value="{esc(rel.label)}"' if rel.label else ""
        cells.append(
            f'<mxCell id="cd_edge_{e_num}"{label_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )
        # 两端多重性：贴 source / target 侧
        for suffix, mult, xr in (
            ("src", rel.source_multiplicity, "-0.82"),
            ("dst", rel.target_multiplicity, "0.82"),
        ):
            if not mult:
                continue
            cells.append(
                f'<mxCell id="cd_edge_{e_num}_{suffix}" value="{esc(mult)}" '
                'style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];" '
                f'vertex="1" connectable="0" parent="cd_edge_{e_num}">'
                f'<mxGeometry x="{xr}" relative="1" as="geometry"><mxPoint as="offset"/></mxGeometry></mxCell>'
            )

    body = "\n        ".join(cells)
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="class-model" name="UML 类图">\n'
        '    <mxGraphModel dx="1100" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{page_w}" pageHeight="{page_h}">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


# ============================================================================
# 时序图 drawio 渲染（C 任务）
# 布局：生命线横向等距；消息按 order 自上而下等行距；片段框覆盖其 order 区间。
# ============================================================================

_SD_LL_W = 130
_SD_LL_GAP = 60
_SD_LEFT = 60
_SD_TOP = 60
_SD_MSG_TOP = 128
_SD_MSG_ROW = 46
_SD_FRAG_GAP = 10  # 相邻片段框的最小垂直间隙（px），避免边框压线
_SD_BOTTOM = 50

# 消息类型 → 箭头样式
_SD_ARROW_LABEL_BG = "labelBackgroundColor=#ffffff;"

_SD_ARROW = {
    MessageKind.SYNC: "endArrow=block;endFill=1;html=1;",
    MessageKind.ASYNC: "endArrow=open;endFill=0;html=1;",
    MessageKind.RETURN: "endArrow=open;endFill=0;dashed=1;html=1;",
    MessageKind.CREATE: "endArrow=open;endFill=0;dashed=1;html=1;",
    MessageKind.DESTROY: "endArrow=cross;endFill=0;html=1;",
}

# 生命线构造型前缀（object 为默认，不加）
_SD_STEREO = {
    LifelineKind.ACTOR: "actor",
    LifelineKind.BOUNDARY: "boundary",
    LifelineKind.CONTROL: "control",
    LifelineKind.ENTITY: "entity",
    LifelineKind.DATABASE: "database",
}


def render_sequence_drawio(model: SequenceModel) -> str:
    """把时序图模型渲染为 draw.io XML（生命线 + 有序消息 + 单层片段）。"""
    if not isinstance(model, SequenceModel):
        raise TypeError(f"render_sequence_drawio 只接受 SequenceModel，收到 {type(model).__name__}")

    esc = _xml_escape
    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    n_ll = max(1, len(model.lifelines))
    n_msg = len(model.messages)
    ll_h = _SD_MSG_TOP + n_msg * _SD_MSG_ROW + _SD_BOTTOM
    page_w = max(760, _SD_LEFT * 2 + n_ll * _SD_LL_W + (n_ll - 1) * _SD_LL_GAP)
    page_h = _SD_TOP + ll_h + 80

    alias = {ll.name: f"ll_{i}" for i, ll in enumerate(model.lifelines, start=1)}
    xs: dict[str, int] = {
        ll.name: _SD_LEFT + i * (_SD_LL_W + _SD_LL_GAP) for i, ll in enumerate(model.lifelines)
    }

    # ---- 1) 生命线（umlLifeline 容器，高度覆盖全部消息）----
    for ll in model.lifelines:
        x = xs[ll.name]
        name = esc(ll.name)
        if ll.classifier:
            name = f"{name}: {esc(ll.classifier)}"
        stereo = _SD_STEREO.get(ll.kind)
        if stereo:
            name = f"&#171;{stereo}&#187;&lt;br&gt;{name}"
        cells.append(
            f'<mxCell id="{alias[ll.name]}" value="{name}" '
            'style="shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;'
            'container=1;collapsible=0;recursiveResize=0;outlineConnect=0;size=50;" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{_SD_TOP}" width="{_SD_LL_W}" '
            f'height="{ll_h}" as="geometry"/></mxCell>'
        )

    # ---- 2) 消息 y 坐标（按 order 排序后逐行）----
    ordered = sorted(model.messages, key=lambda m: m.order)
    msg_y: dict[int, int] = {
        m.order: _SD_MSG_TOP + idx * _SD_MSG_ROW for idx, m in enumerate(ordered)
    }

    # ---- 3) 片段框（画在消息下层；覆盖其 order 区间的全部端点生命线）----
    # 相邻片段必须留缝：框顶取 start-30、框底取 end+24，若消息行距(_SD_MSG_ROW=46)
    # 小于 54，两框会纵向压在一起。按 start_order 顺序布局并记录上一框底边兜底。
    prev_bottom = 0
    for f_num, frag in enumerate(sorted(model.fragments, key=lambda f: f.start_order), start=1):
        covered = [m for m in ordered if frag.start_order <= m.order <= frag.end_order]
        if not covered:
            continue
        ends = {m.source_id for m in covered} | {m.target_id for m in covered}
        end_xs = [xs[e] for e in ends if e in xs]
        if not end_xs:
            continue
        fx = max(0, min(end_xs) - 18)
        fw = max(end_xs) + _SD_LL_W + 18 - fx
        fy = msg_y[frag.start_order] - 30
        if fy < prev_bottom + _SD_FRAG_GAP:
            fy = prev_bottom + _SD_FRAG_GAP
        fh = max(60, msg_y[frag.end_order] + 24 - fy)
        prev_bottom = fy + fh
        label = f"&#171;{esc(frag.kind)}&#187;"
        if frag.condition:
            label += f"&lt;br&gt;[{esc(frag.condition)}]"
        cells.append(
            f'<mxCell id="sd_frag_{f_num}" value="{label}" '
            'style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;verticalAlign=top;align=left;'
            'spacingLeft=8;spacingTop=4;fontSize=12;" '
            f'vertex="1" parent="1"><mxGeometry x="{fx}" y="{fy}" width="{fw}" '
            f'height="{fh}" as="geometry"/></mxCell>'
        )

    # ---- 4) 消息边：中心线出、中心线入；自消息走右侧回环 ----
    for m_num, msg in enumerate(ordered, start=1):
        src = alias.get(msg.source_id)
        dst = alias.get(msg.target_id)
        if not src or not dst:
            continue
        y = msg_y[msg.order]
        ratio = (y - _SD_TOP) / ll_h
        arrow = _SD_ARROW_LABEL_BG + _SD_ARROW.get(msg.kind, _SD_ARROW[MessageKind.SYNC])
        geo_attr = '<mxGeometry relative="1" as="geometry"/>'
        if msg.source_id == msg.target_id:
            # 自消息：drawio 的 reasoner 对 source==target 的正交自环会退化成一条横贯
            # 全图的直线（实测），因此显式给两个右侧折点，画成标准右回环。
            entry_ratio = min(0.99, ratio + 0.06)
            style = arrow + "rounded=0;"
            rx = xs[msg.source_id] + _SD_LL_W + 40
            y1 = _SD_TOP + ratio * ll_h
            y2 = _SD_TOP + entry_ratio * ll_h
            geo_attr = (
                '<mxGeometry relative="1" as="geometry"><Array as="points">'
                f'<mxPoint x="{rx}" y="{y1:.0f}"/><mxPoint x="{rx}" y="{y2:.0f}"/>'
                "</Array></mxGeometry>"
            )
            style += (
                f"exitX=1;exitY={ratio:.4f};exitDx=0;exitDy=0;"
                f"entryX=1;entryY={entry_ratio:.4f};entryDx=0;entryDy=0;"
            )
        else:
            style = (
                arrow
                + f"exitX=0.5;exitY={ratio:.4f};exitDx=0;exitDy=0;"
                + f"entryX=0.5;entryY={ratio:.4f};entryDx=0;entryDy=0;"
            )
        label_attr = f' value="{esc(msg.label)}"' if msg.label else ""
        cells.append(
            f'<mxCell id="sd_msg_{m_num}"{label_attr} style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}">{geo_attr}</mxCell>'
        )

    body = "\n        ".join(cells)
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="sequence-model" name="UML 时序图">\n'
        '    <mxGraphModel dx="1100" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{page_w}" pageHeight="{page_h}">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


# ============================================================================
# 部署图 drawio 渲染（C 任务）
# 布局：3 列网格；构件作为节点容器的子元素（拖动节点时构件跟随）。
# 节点用 UML node 立方体（device 与 exec_env 用底色区分），构件用 document 形状。
# ============================================================================

_DP_NODE_W = 200
_DP_NODE_BASE_H = 72
_DP_ART_TOP = 62  # 构件起始 y：需在节点顶对齐的标题（≈3 行 54px）之下
_DP_ART_H = 36
_DP_ART_GAP = 6
_DP_COL_GAP = 70
_DP_ROW_GAP = 70
_DP_LEFT = 60
_DP_TOP = 60

# 部署关系 → 边样式（通信路径为实线，依赖为虚线箭头）
_DP_EDGE_STYLES: dict[DeployAssociationKind, str] = {
    DeployAssociationKind.COMMUNICATION: "endArrow=none;html=1;",
    DeployAssociationKind.DEPENDENCY: "endArrow=open;dashed=1;html=1;",
    DeployAssociationKind.ASSOCIATION: "endArrow=none;html=1;",
}


def _dp_node_style(kind: DeployNodeKind) -> str:
    """device 用浅灰底，exec_env 用白底，其余保持同一立方体骨架。

    标签必须顶对齐：立方体默认垂直居中，而构件（jar）从节点顶部偏移放置，
    居中的标题会被构件压住（实测「教务服务deployment」被 jar 完全遮掉）。
    """
    fill = "#f5f5f5" if kind == DeployNodeKind.DEVICE else "#ffffff"
    return (
        "shape=cube;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;"
        f"darkOpacity=0.05;darkOpacity2=0.1;fillColor={fill};"
        "verticalAlign=top;align=center;spacingTop=6;fontSize=12;"
    )


def render_deployment_drawio(model: DeploymentModel) -> str:
    """把部署图模型渲染为 draw.io XML（节点 + 构件 + 部署/通信关系）。"""
    if not isinstance(model, DeploymentModel):
        raise TypeError(f"render_deployment_drawio 只接受 DeploymentModel，收到 {type(model).__name__}")

    esc = _xml_escape
    cells: list[str] = []
    cells.append('<mxCell id="0"/>')
    cells.append('<mxCell id="1" parent="0"/>')

    # 构件按所属节点分组（deployed_on 为空则平铺在网格外，单独成块）
    arts_by_node: dict[str, list] = {n.name: [] for n in model.nodes}
    orphans: list = []
    for art in model.artifacts:
        if art.deployed_on and art.deployed_on in arts_by_node:
            arts_by_node[art.deployed_on].append(art)
        elif not art.deployed_on:
            orphans.append(art)

    def node_height(name: str) -> int:
        arts = arts_by_node.get(name, [])
        return _DP_NODE_BASE_H + (len(arts) * (_DP_ART_H + _DP_ART_GAP) + 8 if arts else 0)

    # ---- 1) 网格坐标：3 列，行高取该行最高节点 ----
    n = len(model.nodes)
    cols = min(3, max(1, n))
    alias: dict[str, str] = {}
    pos: dict[str, tuple[int, int]] = {}
    y = _DP_TOP
    for row_start in range(0, n, cols):
        row_nodes = model.nodes[row_start : row_start + cols]
        row_h = max((node_height(nd.name) for nd in row_nodes), default=_DP_NODE_BASE_H)
        for col, nd in enumerate(row_nodes):
            pos[nd.name] = (_DP_LEFT + col * (_DP_NODE_W + _DP_COL_GAP), y)
        y += row_h + _DP_ROW_GAP
    page_h = max(420, y + 40)
    page_w = max(760, _DP_LEFT * 2 + cols * _DP_NODE_W + (cols - 1) * _DP_COL_GAP)

    # ---- 2) 节点（立方体 + 构造型 + 规格说明）----
    for idx, nd in enumerate(model.nodes, start=1):
        nid = f"dp_n_{idx}"
        alias[nd.name] = nid
        x, ny = pos[nd.name]
        h = node_height(nd.name)
        parts = []
        if nd.stereotype:
            parts.append(f"&#171;{esc(nd.stereotype)}&#187;")
        parts.append(esc(nd.name))
        if nd.spec:
            parts.append(f"[{esc(nd.spec)}]")
        value = "&lt;br&gt;".join(parts)
        cells.append(
            f'<mxCell id="{nid}" value="{value}" style="{_dp_node_style(nd.kind)}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{ny}" width="{_DP_NODE_W}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

        # 构件：作为节点子元素，拖动节点时跟随
        for a_idx, art in enumerate(arts_by_node.get(nd.name, []), start=1):
            aid = f"{nid}_art_{a_idx}"
            alias[art.name] = aid
            ay = _DP_ART_TOP + (a_idx - 1) * (_DP_ART_H + _DP_ART_GAP)
            cells.append(
                f'<mxCell id="{aid}" value="{esc(art.name)}" '
                'style="shape=document;whiteSpace=wrap;html=1;boundedLbl=1;'
                f'fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="{nid}">'
                f'<mxGeometry x="15" y="{ay}" width="{_DP_NODE_W - 30}" height="{_DP_ART_H}" as="geometry"/>'
                "</mxCell>"
            )

    # ---- 3) 未标注宿主的构件：放在节点区下方，单独一行 ----
    if orphans:
        oy = y
        for i, art in enumerate(orphans):
            aid = f"dp_orphan_{i + 1}"
            alias[art.name] = aid
            ox = _DP_LEFT + i * (_DP_NODE_W + _DP_COL_GAP)
            cells.append(
                f'<mxCell id="{aid}" value="{esc(art.name)}" '
                'style="shape=document;whiteSpace=wrap;html=1;boundedLbl=1;dashed=1;'
                'fillColor=#ffffff;strokeColor=#999999;" vertex="1" parent="1">'
                f'<mxGeometry x="{ox}" y="{oy}" width="{_DP_NODE_W - 30}" height="{_DP_ART_H}" as="geometry"/>'
                "</mxCell>"
            )
        page_h = max(page_h, oy + _DP_ART_H + 60)

    # ---- 4) 关系边 ----
    for e_num, rel in enumerate(model.associations, start=1):
        src = alias.get(rel.source_id)
        dst = alias.get(rel.target_id)
        if not src or not dst:
            continue
        style = _DP_EDGE_STYLES.get(rel.kind, _DP_EDGE_STYLES[DeployAssociationKind.COMMUNICATION])
        style += "edgeStyle=orthogonalEdgeStyle;rounded=0;"
        cells.append(
            f'<mxCell id="dp_edge_{e_num}" style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )

    body = "\n        ".join(cells)
    return (
        '<mxfile host="edu-agent" version="24.7.7">\n'
        '  <diagram id="deployment-model" name="UML 部署图">\n'
        '    <mxGraphModel dx="1100" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{page_w}" pageHeight="{page_h}">\n'
        "      <root>\n"
        f"        {body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )
