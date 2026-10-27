"""PlantUML 确定性渲染器：UseCaseModel → PlantUML 源码。

设计约束（评审冻结）：
- 纯确定性：相同输入 → 完全相同输出；不调用 LLM / 网络 / 文件系统；
- 用户输入只作为**显示文本**（经转义），alias 由渲染器按输入顺序生成
  （actor_1 / usecase_1 ...），绝不把用户名称当 PlantUML 标识符；
- 关系方向保持模型语义（source_id → target_id），不反转 include/extend；
- 关联去重：UseCase.actors 的隐式关联与显式 association 按无序对去重
  （association 无方向语义，重复连线是质检对象的问题，渲染不画两条线）；
- 只使用模型内部字段 source_id/target_id，不读 from/to 字典。
"""

import contextlib
import re

from app.models.uml import (
    ActivityModel,
    ActivityNodeKind,
    ClassModel,
    ClassRelationType,
    DeployAssociationKind,
    DeploymentModel,
    DeployNodeKind,
    DiagramType,
    LifelineKind,
    MessageKind,
    RelationType,
    SequenceModel,
    StateKind,
    StateMachineModel,
    UseCaseModel,
)

# 统一教学配色（对齐前端 drawio 导出风格）：**只在渲染 PNG 时注入**（inject_skin），
# API 返回/导出的 PlantUML 源码保持纯净业务结构，可直接粘贴到 PlantUML 编辑器。
_STYLE_BY_TYPE: dict[DiagramType, list[str]] = {
    DiagramType.USECASE: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam actor {",
        "  BackgroundColor #f8f9fa",
        "  BorderColor #666666",
        "}",
        "skinparam usecase {",
        "  BackgroundColor #d5e8d4",
        "  BorderColor #82b366",
        "}",
        "skinparam rectangle {",
        "  BorderColor #333333",
        "  FontStyle bold",
        "}",
    ],
    DiagramType.ACTIVITY: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam activity {",
        "  BackgroundColor #dae8fc",
        "  BorderColor #6c8ebf",
        "  DiamondBackgroundColor #ffe6cc",
        "  DiamondBorderColor #d79b00",
        "}",
        "skinparam swimlane {",
        "  BorderColor #666666",
        "  TitleFontSize 14",
        "}",
    ],
    DiagramType.STATEMACHINE: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam state {",
        "  BackgroundColor #d5e8d4",
        "  BorderColor #82b366",
        "  FontColor #1a1a1a",
        "}",
    ],
    DiagramType.CLASS: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam class {",
        "  BackgroundColor #dae8fc",
        "  BorderColor #6c8ebf",
        "  HeaderBackgroundColor #b1d0f0",
        "}",
        "skinparam interface {",
        "  BackgroundColor #fff2cc",
        "  BorderColor #d6b656",
        "}",
    ],
    DiagramType.SEQUENCE: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam sequence {",
        "  ParticipantBackgroundColor #dae8fc",
        "  ParticipantBorderColor #6c8ebf",
        "  LifeLineBorderColor #999999",
        "  LifeLineBackgroundColor #f8f9fa",
        "  GroupBorderColor #b85450",
        "  GroupBackgroundColor #f8cecc",
        "}",
    ],
    DiagramType.DEPLOYMENT: [
        "skinparam backgroundColor #FFFFFF",
        "skinparam shadowing false",
        'skinparam defaultFontName "Microsoft YaHei"',
        "skinparam defaultFontSize 13",
        "skinparam ArrowColor #444444",
        "skinparam node {",
        "  BackgroundColor #d5e8d4",
        "  BorderColor #82b366",
        "}",
        "skinparam device {",
        "  BackgroundColor #e1d5e7",
        "  BorderColor #9673a6",
        "}",
        "skinparam artifact {",
        "  BackgroundColor #ffe6cc",
        "  BorderColor #d79b00",
        "}",
    ],
}


def inject_skin(source: str, dtype: DiagramType) -> str:
    """渲染用注入：在 @startuml 后插入图型对应样式，返回**副本**，不改原始源码。"""
    style = _STYLE_BY_TYPE.get(dtype)
    if not style or not source.startswith("@startuml"):
        return source
    rest = source[len("@startuml"):]
    return "@startuml\n" + "\n".join(style) + rest


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _escape_display(text: str) -> str:
    """转义显示文本：反斜杠 → 引号 → 控制字符，保证只作为文本出现。"""
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    return _CONTROL_RE.sub(" ", text)


def _check_model(model: UseCaseModel) -> None:
    """renderer 只接受已校验的 UseCaseModel（非法输入在入口拦截）。"""
    if not isinstance(model, UseCaseModel):
        raise TypeError(f"render_usecase_plantuml 只接受 UseCaseModel，收到 {type(model).__name__}")
    if model.type != DiagramType.USECASE:
        raise ValueError(f"仅支持用例图渲染，收到 {model.type}")


def render_usecase_plantuml(model: UseCaseModel) -> str:
    """把用例图模型渲染为 PlantUML 源码（确定性输出）。

    输出顺序：文件头 → Actor 定义 → 系统边界内 Use Case → 关联行 →
    其他关系（include/extend/generalization，按输入顺序）→ 文件尾。
    """
    _check_model(model)

    # 确定性 alias：按输入顺序编号，与用户输入无关
    actor_alias = {actor.name: f"actor_{i}" for i, actor in enumerate(model.actors, start=1)}
    usecase_alias = {uc.id: f"usecase_{i}" for i, uc in enumerate(model.usecases, start=1)}

    lines: list[str] = ["@startuml", "left to right direction", ""]

    # Actor 定义（按 model.actors 顺序）
    for actor in model.actors:
        lines.append(f'actor "{_escape_display(actor.name)}" as {actor_alias[actor.name]}')

    # 系统边界始终输出（边界是用例图核心语义），内部为空也画
    lines.append("")
    lines.append(f'rectangle "{_escape_display(model.system)}" {{')
    for uc in model.usecases:
        lines.append(f'  usecase "{_escape_display(uc.name)}" as {usecase_alias[uc.id]}')
    lines.append("}")

    # 关联行：UseCase.actors 隐式关联 + 显式 association（无序对去重）
    association_pairs: list[tuple[str, str]] = []
    seen_pairs: set[frozenset[str]] = set()
    for uc in model.usecases:
        for actor_name in uc.actors:
            pair = frozenset((actor_alias[actor_name], usecase_alias[uc.id]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                association_pairs.append((actor_alias[actor_name], usecase_alias[uc.id]))

    other_lines: list[str] = []
    for rel in model.relations:
        src = actor_alias.get(rel.source_id) or usecase_alias[rel.source_id]
        dst = actor_alias.get(rel.target_id) or usecase_alias[rel.target_id]
        if rel.type == RelationType.ASSOCIATION:
            pair = frozenset((src, dst))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                association_pairs.append((src, dst))
        elif rel.type == RelationType.INCLUDE:
            other_lines.append(f"{src} .> {dst} : <<include>>")
        elif rel.type == RelationType.EXTEND:
            other_lines.append(f"{src} .> {dst} : <<extend>>")
        else:  # GENERALIZATION
            other_lines.append(f"{src} --|> {dst}")

    if association_pairs:
        lines.append("")
        for src, dst in association_pairs:
            lines.append(f"{src} --> {dst}")

    if other_lines:
        lines.append("")
        lines.extend(other_lines)

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 活动图渲染：泳道 + 起止 + 动作 + 决策(if/else) + 并行(fork/join)
# 设计约束（与用例图渲染器一致）：纯确定性、显示文本经转义、别名由渲染器生成。
# 图→源码是编译问题；本实现覆盖教学常见模式（顺序/决策/并行），并对复杂拓扑
# 安全降级（try/except 兜底为合法 PlantUML，不会抛异常）。
# ============================================================================

_HISTORY_TOKEN = "history"


def _cond_label(cond: str, fallback: str) -> str:
    """决策分支标签：取监护条件去方括号，空则用目标名。"""
    c = (cond or "").strip().strip("[]").strip()
    return c or fallback


def render_activity_plantuml(model: ActivityModel) -> str:
    """把活动图模型渲染为 PlantUML 源码（确定性输出，始终合法）。"""
    nodes = {n.id: n for n in model.nodes}
    out_edges: dict[str, list] = {n.id: [] for n in model.nodes}
    for f in model.flows:
        out_edges.setdefault(f.source, []).append(f)
    in_cnt = {n.id: 0 for n in model.nodes}
    for f in model.flows:
        in_cnt[f.target] = in_cnt.get(f.target, 0) + 1

    initial = next((n for n in model.nodes if n.kind == ActivityNodeKind.INITIAL), None)
    no_incoming = next((i for i in in_cnt if in_cnt[i] == 0), None)
    first_node = model.nodes[0].id if model.nodes else None
    start = initial.id if initial else (no_incoming or first_node)
    if start is None:
        return "@startuml\n@enduml"

    lines: list[str] = ["@startuml"]
    # PlantUML 新版活动图语法：第一个泳道声明必须出现在 start 之前，
    # 否则泳道行报「Some diagram description contains errors」（实测 1.2026.8）。
    # 因此把起始泳道前置声明；活动之间的泳道切换仍由 lane_switch 按流程输出（合法）。
    lane_names = []
    for n in model.nodes:
        if n.lane and n.lane not in lane_names:
            lane_names.append(n.lane)
    # 泳道浅灰背景（与 drawio 导出一致）。注意：PlantUML 对「切回泳道后改变
    # 节点行内颜色」存在解析怪癖（实测 1.2026.8 换色即报错），因此节点行内
    # 不做着色，统一由 skinparam activity 提供颜色；泳道仅首次声明带背景色。
    _LANE_BG = "#f8f9fa"
    declared_lanes: set[str] = set()

    first_lane = next((n.lane for n in model.nodes if n.lane), "")
    if first_lane:
        lines.append(f"|{_LANE_BG}|{_escape_display(first_lane)}|")
        declared_lanes.add(first_lane)
    cur_lane: list[str | None] = [first_lane or None]
    visited: set[str] = set()

    def lane_switch(lane: str) -> None:
        if lane and lane != cur_lane[0]:
            if lane in declared_lanes:
                lines.append(f"|{_escape_display(lane)}|")
            else:
                lines.append(f"|{_LANE_BG}|{_escape_display(lane)}|")
                declared_lanes.add(lane)
            cur_lane[0] = lane

    def advance(nid: str) -> None:
        edges = out_edges.get(nid, [])
        if edges:
            emit_node(edges[0].target)

    def emit_inline(tid: str) -> None:
        """并行分支内只画首节点（不递归下钻），保证 fork 块结构完整。"""
        n = nodes.get(tid)
        if n is None:
            return
        if n.kind == ActivityNodeKind.ACTION:
            lane_switch(n.lane)
            lines.append(f":{_escape_display(n.name)};")
        elif n.kind == ActivityNodeKind.DECISION:
            lane_switch(n.lane)
            lines.append(f":{_escape_display(n.name)}?;")
        elif n.kind == ActivityNodeKind.FINAL:
            lines.append("stop")

    def emit_node(nid: str, depth: int = 0) -> None:
        if nid in visited:
            return
        visited.add(nid)
        n = nodes.get(nid)
        if n is None:
            return
        if n.kind == ActivityNodeKind.INITIAL:
            lines.append("start")
            advance(nid)
            return
        if n.kind == ActivityNodeKind.FINAL:
            lines.append("stop")
            return
        if n.kind == ActivityNodeKind.ACTION:
            lane_switch(n.lane)
            lines.append(f":{_escape_display(n.name)};")
            advance(nid)
            return
        if n.kind == ActivityNodeKind.DECISION:
            lane_switch(n.lane)
            edges = out_edges.get(nid, [])
            if len(edges) >= 2:
                lines.append(f"if ({_escape_display(n.name)}) then ({_cond_label(edges[0].cond, edges[0].target)})")
                emit_node(edges[0].target, depth + 1)
                for e in edges[1:-1]:
                    lines.append(f"elseif ({_cond_label(e.cond, e.target)})")
                    emit_node(e.target, depth + 1)
                lines.append(f"else ({_cond_label(edges[-1].cond, edges[-1].target)})")
                emit_node(edges[-1].target, depth + 1)
                lines.append("endif")
            elif edges:
                advance(nid)
            return
        if n.kind == ActivityNodeKind.FORK:
            edges = out_edges.get(nid, [])
            if edges:
                lines.append("fork")
                first = True
                for e in edges:
                    if not first:
                        lines.append("fork again")
                    first = False
                    emit_inline(e.target)
                lines.append("end fork")
                # 从汇合节点继续（并行已在 fork 处闭合）
                join = next(
                    (nn for nn in model.nodes if nn.kind == ActivityNodeKind.JOIN and nn.id not in visited),
                    None,
                )
                if join is not None:
                    emit_node(join.id)
            return
        # JOIN / MERGE：继续其单条出边
        edges = out_edges.get(nid, [])
        if edges:
            advance(nid)

    with contextlib.suppress(Exception):  # 任何拓扑异常都兜底为已累积的合法片段
        emit_node(start)
    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 状态机图渲染：初/终伪状态 + 状态定义 + 转换(事件[监护]) + 历史(H)
# ============================================================================

def render_statemachine_plantuml(model: StateMachineModel) -> str:
    """把状态机图模型渲染为 PlantUML 源码（确定性输出）。

    状态引用一律使用安全别名 st_N：LLM 生成的 id 可能含连字符等
    PlantUML 标识符非法字符（实测 S-01 导致 Error line 2）。
    输出顺序：状态定义在前 → 初始转换 → 普通转换。

    终态（kind=final）**绝不声明为具名状态**，也不允许成为转换的具名目标：
    指向终态的转换必须直接写成 `--> [*]`。否则 PlantUML 会把未声明的
    别名 st_N 当成一个真实状态画出来（实测出现名字为 "st_7" 的幽灵节点）。
    """
    lines: list[str] = ["@startuml"]
    alias = {s.id: f"st_{i}" for i, s in enumerate(model.states)}
    final_ids = {s.id for s in model.states if s.kind == StateKind.FINAL}

    def dst_label(tid: str) -> str:
        if tid == _HISTORY_TOKEN:
            return "H"
        # 终态渲染成终结点 [*]，不引用任何别名
        if tid in final_ids:
            return "[*]"
        return alias.get(tid, tid)

    # 1) 普通/挂起状态定义（带显示名，先于任何转换引用）
    for s in model.states:
        if s.kind in (StateKind.NORMAL, StateKind.PAUSED):
            label = _escape_display(s.name) if s.name else "未命名状态"
            lines.append(f'state "{label}" as {alias[s.id]}')

    # 2) 初始伪状态 → 首转换
    initials = [s for s in model.states if s.kind == StateKind.INITIAL]
    initial_ids = {s.id for s in initials}
    for s in initials:
        first = next((t for t in model.transitions if t.source == s.id), None)
        if first:
            lines.append(f"[*] --> {dst_label(first.target)}")

    # 3) 其他转换（跳过 initial 的自动首转换；从终态出发的转换非法，跳过）
    for t in model.transitions:
        if t.source in initial_ids or t.source in final_ids:
            continue
        src = "H" if t.source == _HISTORY_TOKEN else alias.get(t.source, t.source)
        dst = dst_label(t.target)
        arrow = f"{src} --> {dst}"
        parts: list[str] = []
        if t.event:
            parts.append(_escape_display(t.event))
        if t.guard:
            parts.append(f"[{_escape_display(t.guard)}]")
        if parts:
            arrow += " : " + " ".join(parts)
        lines.append(arrow)

    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 类图渲染：类/接口 + 属性/方法（可见性/静态/抽象）+ 六种关系 + 多重性
# ============================================================================

_CLASS_ARROW: dict[ClassRelationType, str] = {
    # 泛化/实现：父类/接口在左端（目标 <|-- 子类）
    ClassRelationType.GENERALIZATION: "<|--",
    ClassRelationType.REALIZATION: "<|..",
    # 组合/聚合/关联：整体/源在左端（整体 *-- 部分）
    ClassRelationType.COMPOSITION: "*--",
    ClassRelationType.AGGREGATION: "o--",
    ClassRelationType.ASSOCIATION: "--",
    # 依赖：源在左端（源 ..> 目标）
    ClassRelationType.DEPENDENCY: "..>",
}


def _class_member_lines(item) -> list[str]:
    """渲染类体成员：属性在前、方法在后（确定性顺序，保持模型输入顺序）。"""
    lines: list[str] = []
    for attr in item.attributes:
        vis = attr.visibility.value if attr.visibility else ""
        mods = "{static} " if attr.is_static else ""
        type_part = f": {attr.type}" if attr.type else ""
        lines.append(f"  {mods}{vis}{attr.name}{type_part}")
    for method in item.methods:
        vis = method.visibility.value if method.visibility else ""
        mods = " ".join(
            token
            for token in (
                "{static}" if method.is_static else "",
                "{abstract}" if method.is_abstract else "",
            )
            if token
        )
        mods = f"{mods} " if mods else ""
        params = ", ".join(
            f"{p.name}: {p.type}" if p.type else p.name for p in method.params
        )
        ret = f": {method.return_type}" if method.return_type else ""
        lines.append(f"  {mods}{vis}{method.name}({params}){ret}")
    return lines


def render_class_plantuml(model: ClassModel) -> str:
    """把类图模型渲染为 PlantUML 源码（确定性输出）。

    关键字选择：is_interface → interface；is_abstract → abstract class；否则 class。
    关系箭头与多重性按 UML 语义输出（source 侧多重性在左、target 侧在右）。
    """
    if not isinstance(model, ClassModel):
        raise TypeError(f"render_class_plantuml 只接受 ClassModel，收到 {type(model).__name__}")

    alias = {c.name: f"class_{i}" for i, c in enumerate(model.classes, start=1)}
    lines: list[str] = ["@startuml"]
    if model.title:
        lines.append(f"title {_escape_display(model.title)}")

    for item in model.classes:
        if item.is_interface:
            keyword = "interface"
        elif item.is_abstract:
            keyword = "abstract class"
        else:
            keyword = "class"
        lines.append(f'{keyword} "{_escape_display(item.name)}" as {alias[item.name]} {{')
        lines.extend(_class_member_lines(item))
        lines.append("}")

    if model.relations:
        lines.append("")
    for rel in model.relations:
        src = alias.get(rel.source_id)
        dst = alias.get(rel.target_id)
        if src is None or dst is None:
            # 模型层已拦引用缺失；渲染器兜底跳过，保证始终输出合法源码
            continue
        arrow = _CLASS_ARROW[rel.type]
        # 泛化/实现：模型方向是「子 → 父」，PlantUML 需要「父 <|-- 子」；
        # 其余关系（组合/聚合/关联/依赖）模型方向即绘图方向。
        if rel.type in (ClassRelationType.GENERALIZATION, ClassRelationType.REALIZATION):
            left, right = dst, src
            left_mult, right_mult = rel.target_multiplicity, rel.source_multiplicity
        else:
            left, right = src, dst
            left_mult, right_mult = rel.source_multiplicity, rel.target_multiplicity
        parts: list[str] = [left]
        if left_mult:
            parts.append(f'"{_escape_display(left_mult)}"')
        parts.append(arrow)
        if right_mult:
            parts.append(f'"{_escape_display(right_mult)}"')
        parts.append(right)
        line = " ".join(parts)
        if rel.label:
            line += f" : {_escape_display(rel.label)}"
        lines.append(line)

    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 时序图渲染：生命线 + 有序消息 + 单层片段（alt/loop/opt/par）
# ============================================================================

_LIFELINE_KEYWORD: dict[LifelineKind, str] = {
    LifelineKind.ACTOR: "actor",
    LifelineKind.OBJECT: "participant",
    LifelineKind.BOUNDARY: "boundary",
    LifelineKind.CONTROL: "control",
    LifelineKind.ENTITY: "entity",
    LifelineKind.DATABASE: "database",
}

_MESSAGE_ARROW: dict[MessageKind, str] = {
    MessageKind.SYNC: "->",
    MessageKind.ASYNC: "->>",
    MessageKind.RETURN: "-->",
    MessageKind.CREATE: "->",
    MessageKind.DESTROY: "->x",
}


def render_sequence_plantuml(model: SequenceModel) -> str:
    """把时序图模型渲染为 PlantUML 源码（确定性输出）。

    消息严格按 order 升序输出；片段在 start_order 处开块、end_order 处闭块，
    v1 仅支持互不重叠的单层片段（模型层已校验）。
    """
    if not isinstance(model, SequenceModel):
        raise TypeError(f"render_sequence_plantuml 只接受 SequenceModel，收到 {type(model).__name__}")

    alias = {ll.name: f"l_{i}" for i, ll in enumerate(model.lifelines, start=1)}
    lines: list[str] = ["@startuml"]
    if model.title:
        lines.append(f"title {_escape_display(model.title)}")

    for ll in model.lifelines:
        keyword = _LIFELINE_KEYWORD[ll.kind]
        lines.append(f'{keyword} "{_escape_display(ll.name)}" as {alias[ll.name]}')

    starts = {f.start_order: f for f in model.fragments}
    ends = {f.end_order: f for f in model.fragments}
    if model.messages:
        lines.append("")
    for msg in sorted(model.messages, key=lambda m: m.order):
        frag = starts.get(msg.order)
        if frag is not None:
            cond = f" {_escape_display(frag.condition)}" if frag.condition else ""
            lines.append(f"{frag.kind}{cond}")
        src = alias.get(msg.source_id, msg.source_id)
        dst = alias.get(msg.target_id, msg.target_id)
        arrow = _MESSAGE_ARROW[msg.kind]
        label = f" : {_escape_display(msg.label)}" if msg.label else ""
        lines.append(f"{src} {arrow} {dst}{label}")
        if msg.order in ends:
            lines.append("end")

    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 部署图渲染：节点(设备/执行环境) + 构件 + 通信/依赖关系
# ============================================================================

_DEPLOY_ARROW: dict[DeployAssociationKind, str] = {
    DeployAssociationKind.COMMUNICATION: "<-->",
    DeployAssociationKind.DEPENDENCY: "..>",
    DeployAssociationKind.ASSOCIATION: "--",
}


def render_deployment_plantuml(model: DeploymentModel) -> str:
    """把部署图模型渲染为 PlantUML 源码（确定性输出）。

    节点统一用 `node` 关键字：exec_env 直接输出 node，device 追加 `<<device>>` 构造型
    （PlantUML 没有独立 `device` 关键字）。构件先声明，再用节点--构件连线表达「部署在」语义。
    """
    if not isinstance(model, DeploymentModel):
        raise TypeError(f"render_deployment_plantuml 只接受 DeploymentModel，收到 {type(model).__name__}")

    node_alias = {n.name: f"n_{i}" for i, n in enumerate(model.nodes, start=1)}
    art_alias = {a.name: f"a_{i}" for i, a in enumerate(model.artifacts, start=1)}

    lines: list[str] = ["@startuml"]
    if model.title:
        lines.append(f"title {_escape_display(model.title)}")

    for node in model.nodes:
        # 注意：PlantUML 部署图没有独立 `device` 关键字（写 `device "x"` 会语法报错），
        # 物理设备统一用 `node` + `<<device>>` 构造型表达（内置图标）。
        stereos: list[str] = []
        if node.kind == DeployNodeKind.DEVICE:
            stereos.append("device")
        if node.stereotype and node.stereotype != "device":
            stereos.append(_escape_display(node.stereotype))
        stereo_txt = "".join(f" <<{s}>>" for s in stereos)
        lines.append(f'node "{_escape_display(node.name)}" as {node_alias[node.name]}{stereo_txt}')

    for art in model.artifacts:
        lines.append(f'artifact "{_escape_display(art.name)}" as {art_alias[art.name]}')

    if model.associations or any(a.deployed_on for a in model.artifacts):
        lines.append("")

    # 构件部署：节点 -- 构件（「部署在」语义）
    for art in model.artifacts:
        if art.deployed_on and art.deployed_on in node_alias:
            lines.append(f"{node_alias[art.deployed_on]} -- {art_alias[art.name]}")

    for rel in model.associations:
        src = node_alias.get(rel.source_id) or art_alias.get(rel.source_id)
        dst = node_alias.get(rel.target_id) or art_alias.get(rel.target_id)
        if src is None or dst is None:
            continue
        lines.append(f"{src} {_DEPLOY_ARROW[rel.kind]} {dst}")

    lines.append("@enduml")
    return "\n".join(lines)


# ============================================================================
# 统一分发：按模型 type 选择渲染器（供 API 调用）
# ============================================================================

def render_uml_plantuml(model) -> str:
    """按图类型分发到对应 PlantUML 渲染器。"""
    if isinstance(model, UseCaseModel):
        return render_usecase_plantuml(model)
    if isinstance(model, ActivityModel):
        return render_activity_plantuml(model)
    if isinstance(model, StateMachineModel):
        return render_statemachine_plantuml(model)
    if isinstance(model, ClassModel):
        return render_class_plantuml(model)
    if isinstance(model, SequenceModel):
        return render_sequence_plantuml(model)
    if isinstance(model, DeploymentModel):
        return render_deployment_plantuml(model)
    raise TypeError(f"不支持的模型类型：{type(model).__name__}")
