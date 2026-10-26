"""活动图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 ActivityModel，输出 ReviewReport（对齐 usecase_rules 的契约）。
规则分组（对齐教材活动图表 6-2/6-3/6-4）：
- 泳道分区（AC-S1/S2）：动作必须归属泳道；系统内部组件不可作泳道；
- 控制流（AC-F1/F2/F4）：孤立节点、决策分支条件、分叉/汇合配对；
- 动作粒度（AC-G1）：动作名含界面操作词。
模型层已拦的结构非法（泳道未定义/端点不存在）这里做防御性复查。
"""

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import ActivityModel, ActivityNodeKind

# 系统内部组件黑名单：作为泳道名出现说明把内部组件画成了责任分区
_INTERNAL_COMPONENT_WORDS = (
    "数据库",
    "存储",
    "缓存",
    "消息队列",
    "队列",
    "网络",
    "服务器",
    "中间件",
    "接口",
)

# 界面操作词：出现在动作名说明落到了操作步骤而非业务目标
_UI_OPERATION_WORDS = ("点击", "输入", "按下", "选择", "填写", "双击", "打开", "关闭", "提交")


def _issue(rule_id, level, target, message, *, rule_group, suggestion="", table_ref=""):
    return ReviewIssue(
        rule_id=rule_id,
        level=level,
        target=target,
        message=message,
        rule_group=rule_group,
        suggestion=suggestion,
        table_ref=table_ref,
    )


def check_activity_model(model: ActivityModel) -> ReviewReport:
    """对活动图模型执行全部规则，产出 ReviewReport。"""
    issues: list[ReviewIssue] = []
    lane_names = {s.name for s in model.swimlanes}
    node_ids = {n.id for n in model.nodes}

    # ---- AC-S2 泳道分区：内部组件被列为泳道 ----
    for lane in model.swimlanes:
        hit = next((w for w in _INTERNAL_COMPONENT_WORDS if w in lane.name), None)
        if hit:
            issues.append(
                _issue(
                    "AC-S2",
                    "error",
                    lane.name,
                    f"「{hit}」属于系统内部组件，不能作为泳道（责任分区）",
                    rule_group="泳道分区",
                    suggestion="泳道只保留外部角色/岗位，内部组件应在泳道内的动作中体现",
                    table_ref="表6-2",
                )
            )

    # ---- 节点级遍历：AC-S1 归属 / AC-G1 粒度 ----
    linked: set[str] = set()
    for n in model.nodes:
        # AC-S1（防御性：模型层已拦，这里保证规则引擎独立成立）
        if n.kind in (ActivityNodeKind.ACTION, ActivityNodeKind.DECISION) and not n.lane:
            issues.append(
                _issue(
                    "AC-S1",
                    "error",
                    n.id,
                    f"{n.kind.value} 节点未归属任何泳道",
                    rule_group="泳道分区",
                    suggestion="为其指定所属责任分区（泳道名）",
                )
            )
        elif n.kind in (ActivityNodeKind.ACTION, ActivityNodeKind.DECISION) and n.lane and n.lane not in lane_names:
            issues.append(
                _issue(
                    "AC-S1",
                    "error",
                    n.id,
                    f"节点 {n.id} 的泳道「{n.lane}」未定义",
                    rule_group="泳道分区",
                    suggestion="先在 swimlanes 中定义该泳道",
                )
            )
        # AC-G1 动作粒度
        if n.kind == ActivityNodeKind.ACTION:
            hit = next((w for w in _UI_OPERATION_WORDS if w in n.name), None)
            if hit:
                issues.append(
                    _issue(
                        "AC-G1",
                        "warning",
                        n.id,
                        f"动作「{n.name}」含界面操作词「{hit}」，是操作步骤而非业务目标",
                        rule_group="动作粒度",
                        suggestion="建议改为表达业务目标的名称（如「提交信息」而非「点击提交」）",
                    )
                )

    # ---- AC-F1/F2/F4：控制流连通与结构 ----
    in_deg: dict[str, int] = {nid: 0 for nid in node_ids}
    out_deg: dict[str, int] = {nid: 0 for nid in node_ids}
    for f in model.flows:
        out_deg[f.source] = out_deg.get(f.source, 0) + 1
        in_deg[f.target] = in_deg.get(f.target, 0) + 1
        linked.add(f.source)
        linked.add(f.target)

    # 孤立节点（无任何连入/连出）
    for n in model.nodes:
        if n.kind in (ActivityNodeKind.INITIAL, ActivityNodeKind.FINAL):
            continue
        if in_deg.get(n.id, 0) == 0 and out_deg.get(n.id, 0) == 0:
            issues.append(
                _issue(
                    "AC-F1",
                    "error",
                    n.id,
                    f"节点「{n.name or n.id}」未与任何控制流连接（孤立节点）",
                    rule_group="控制流",
                    suggestion="为其连接前驱/后继节点，或确认是否应出现在图中",
                    table_ref="表6-3",
                )
            )

    # AC-F2 决策分支：条件互斥且全覆盖
    for n in model.nodes:
        if n.kind != ActivityNodeKind.DECISION:
            continue
        out_edges = [f for f in model.flows if f.source == n.id]
        if not out_edges:
            issues.append(
                _issue(
                    "AC-F2",
                    "error",
                    n.id,
                    "决策节点没有任何输出分支",
                    rule_group="控制流",
                    suggestion="为决策节点连接至少两个互斥输出分支",
                    table_ref="表6-3",
                )
            )
            continue
        missing_cond = [f for f in out_edges if not f.cond or not f.cond.strip()]
        if missing_cond:
            issues.append(
                _issue(
                    "AC-F2",
                    "error",
                    n.id,
                    "决策节点的输出分支缺少互斥监护条件（cond）",
                    rule_group="控制流",
                    suggestion="为每个分支标注互斥监护条件，如 [需修改] / [无需修改]",
                    table_ref="表6-3",
                )
            )
        # 分支目标需覆盖（无重复指向同一目标导致逻辑缺失）
        targets = [f.target for f in out_edges]
        dup = sorted({t for t in targets if targets.count(t) > 1})
        if dup:
            issues.append(
                _issue(
                    "AC-F2",
                    "warning",
                    n.id,
                    f"决策节点的多个分支指向同一目标：{dup}",
                    rule_group="控制流",
                    suggestion="检查是否漏写某个分支的目标节点",
                )
            )

    # AC-F4 并行：分叉与汇合数量配对
    forks = [n for n in model.nodes if n.kind == ActivityNodeKind.FORK]
    joins = [n for n in model.nodes if n.kind == ActivityNodeKind.JOIN]
    if forks and joins and len(forks) != len(joins):
        issues.append(
            _issue(
                "AC-F4",
                "error",
                "fork/join",
                f"分叉节点数({len(forks)})与汇合节点数({len(joins)})不匹配",
                rule_group="控制流",
                suggestion="每个分叉(fork)都应有对应的汇合(join)，数量保持一致",
                table_ref="表6-4",
            )
        )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
