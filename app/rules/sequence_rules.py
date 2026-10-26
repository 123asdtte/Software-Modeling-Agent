"""时序图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 SequenceModel，输出 ReviewReport（对齐 usecase_rules 的契约）。
规则分组（对齐教材时序图/动态建模校验维度）：
- 消息校验（SQ-REF/SQ-ORD/SQ-LABEL）：端点存在、顺序号唯一、消息标注操作名；
- 片段校验（SQ-FRAG）：片段区间必须落在真实消息上且合法；
- 结构提示（SQ-EMPTY）：空时序图/无消息。
模型层已拦的结构非法（端点缺失/顺序号重复/片段重叠）这里做防御性复查。
"""

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import SequenceModel


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


def check_sequence_model(model: SequenceModel) -> ReviewReport:
    """对时序图模型执行全部规则，产出 ReviewReport（issues 顺序稳定）。"""
    issues: list[ReviewIssue] = []
    lifeline_names = [ll.name for ll in model.lifelines]
    name_set = set(lifeline_names)

    # ---- SQ-EMPTY 空时序图 ----
    if not model.lifelines:
        issues.append(
            _issue(
                "SQ-EMPTY",
                "error",
                model.title or "sequence",
                "时序图没有任何生命线，无法表达交互",
                rule_group="结构提示",
                suggestion="至少声明一个参与者/对象生命线",
            )
        )
    if not model.messages:
        issues.append(
            _issue(
                "SQ-EMPTY",
                "warning",
                model.title or "sequence",
                "时序图没有任何消息（只有生命线）",
                rule_group="结构提示",
                suggestion="补充按顺序发生的消息（含返回消息）",
            )
        )

    # ---- SQ-REF 消息端点必须存在（模型层已拦，防御性复查）----
    orders = [m.order for m in model.messages]
    order_set = set(orders)

    for msg in model.messages:
        if msg.source_id not in name_set or msg.target_id not in name_set:
            issues.append(
                _issue(
                    "SQ-REF",
                    "error",
                    f"{msg.source_id} -> {msg.target_id}",
                    "消息端点引用了未定义的生命线",
                    rule_group="消息校验",
                    suggestion="修改为已定义的生命线名称，或补充生命线声明",
                )
            )
        # ---- SQ-LABEL 消息必须标注操作/接口名 ----
        if not msg.label or not msg.label.strip():
            issues.append(
                _issue(
                    "SQ-LABEL",
                    "warning",
                    f"order={msg.order}",
                    "消息未标注操作名/接口名",
                    rule_group="消息校验",
                    suggestion="按「操作名(参数)」标注，如 createOrder(items)",
                )
            )

    # ---- SQ-ORD 顺序号唯一（模型层已拦，防御性复查）----
    dup_orders = sorted({o for o in orders if orders.count(o) > 1})
    for order in dup_orders:
        issues.append(
            _issue(
                "SQ-ORD",
                "error",
                f"order={order}",
                "多条消息使用了相同的顺序号，渲染顺序不确定",
                rule_group="消息校验",
                suggestion="为每条消息分配唯一且连续的 order",
            )
        )

    # ---- SQ-FRAG 片段区间合法性（防御性复查）----
    for frag in model.fragments:
        if frag.start_order > frag.end_order:
            issues.append(
                _issue(
                    "SQ-FRAG",
                    "error",
                    f"{frag.kind}[{frag.start_order}-{frag.end_order}]",
                    "片段起始顺序号大于结束顺序号",
                    rule_group="片段校验",
                    suggestion="修正 start_order/end_order，使区间为正序",
                )
            )
            continue
        if frag.start_order not in order_set or frag.end_order not in order_set:
            issues.append(
                _issue(
                    "SQ-FRAG",
                    "error",
                    f"{frag.kind}[{frag.start_order}-{frag.end_order}]",
                    "片段边界没有对应的消息",
                    rule_group="片段校验",
                    suggestion="让片段边界对齐真实消息的 order",
                )
            )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
