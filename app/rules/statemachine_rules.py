"""状态机图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 StateMachineModel，输出 ReviewReport（对齐 usecase_rules 的契约）。
规则分组（对齐教材状态机图表 7-4/7-5/7-6）：
- 状态与生命周期（SM-L2/L3/L4）：初/终态齐全、状态非动作、历史状态；
- 转换逻辑（SM-T1/T4）：转换必须标注触发事件、终点不得悬空。
模型层已拦的结构非法（状态未定义/初终态数量）这里做防御性复查。
"""

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import StateKind, StateMachineModel

_HISTORY_TOKEN = "history"


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


def check_statemachine_model(model: StateMachineModel) -> ReviewReport:
    """对状态机图模型执行全部规则，产出 ReviewReport。"""
    issues: list[ReviewIssue] = []
    state_ids = {s.id for s in model.states}

    initials = [s for s in model.states if s.kind == StateKind.INITIAL]
    finals = [s for s in model.states if s.kind == StateKind.FINAL]

    # ---- SM-L2/L4 初/终态齐全 ----
    if len(initials) == 0:
        issues.append(
            _issue(
                "SM-L4",
                "error",
                model.object or "object",
                "缺少初始伪状态（●），状态机无法确定起点",
                rule_group="状态与生命周期",
                suggestion="增加一个 kind=initial 的初始伪状态",
                table_ref="表7-4",
            )
        )
    elif len(initials) > 1:
        issues.append(
            _issue(
                "SM-L4",
                "error",
                model.object or "object",
                "初始伪状态超过一个",
                rule_group="状态与生命周期",
                suggestion="状态机只能有一个初始伪状态",
                table_ref="表7-4",
            )
        )
    if len(finals) == 0:
        issues.append(
            _issue(
                "SM-L4",
                "error",
                model.object or "object",
                "缺少最终伪状态（◉），状态机生命周期未闭合",
                rule_group="状态与生命周期",
                suggestion="增加一个 kind=final 的最终伪状态",
                table_ref="表7-4",
            )
        )

    # ---- SM-L3 状态粒度：状态不能是动作节点 ----
    for s in model.states:
        if s.kind in (StateKind.INITIAL, StateKind.FINAL):
            continue
        if s.name and ("正在" in s.name or "执行" in s.name or "处理中" in s.name):
            issues.append(
                _issue(
                    "SM-L3",
                    "warning",
                    s.id,
                    f"状态「{s.name}」像是动作节点而非稳定状态",
                    rule_group="状态与生命周期",
                    suggestion="改为稳定状态，或将动作放到转换的 effect 中",
                    table_ref="表7-5",
                )
            )

    # ---- SM-L5 状态未命名（normal/paused 缺中文名，图面显示为 id）----
    for s in model.states:
        if s.kind in (StateKind.NORMAL, StateKind.PAUSED) and (not s.name or not s.name.strip()):
            issues.append(
                _issue(
                    "SM-L5",
                    "warning",
                    s.id,
                    f"状态 {s.id} 缺少中文名称（显示为 id，建议补充稳定状态名）",
                    rule_group="状态与生命周期",
                    suggestion="为该状态补充简洁中文状态名（如「已支付」）",
                    table_ref="表7-5",
                )
            )

    # ---- SM-T1 转换必须标注触发事件 ----
    for t in model.transitions:
        if not t.event or not t.event.strip():
            issues.append(
                _issue(
                    "SM-T1",
                    "error",
                    f"{t.source} -> {t.target}",
                    "转换未标注触发事件（无源触发）",
                    rule_group="转换逻辑",
                    suggestion="为转换标注触发事件（调用/变化/时间/信号之一），如 审核通过",
                    table_ref="表7-6",
                )
            )

    # ---- SM-T4 转换终点不得悬空 ----
    for t in model.transitions:
        if t.target != _HISTORY_TOKEN and t.target not in state_ids:
            issues.append(
                _issue(
                    "SM-T4",
                    "error",
                    f"{t.source} -> {t.target}",
                    f"转换终点指向未定义状态：{t.target}",
                    rule_group="转换逻辑",
                    suggestion="将终点改为已定义的状态 id，或 history 历史伪状态",
                    table_ref="表7-6",
                )
            )
        if t.source != _HISTORY_TOKEN and not t.any_state and t.source not in state_ids:
            issues.append(
                _issue(
                    "SM-T4",
                    "error",
                    f"{t.source} -> {t.target}",
                    f"转换起点指向未定义状态：{t.source}",
                    rule_group="转换逻辑",
                    suggestion="将起点改为已定义的状态 id",
                    table_ref="表7-6",
                )
            )

    # ---- SM-C3 中断/恢复应有历史状态 ----
    has_paused = any(s.kind == StateKind.PAUSED for s in model.states)
    has_history_trans = any(t.target == _HISTORY_TOKEN or t.source == _HISTORY_TOKEN for t in model.transitions)
    if has_history_trans and not has_paused:
        issues.append(
            _issue(
                "SM-C3",
                "warning",
                model.object or "object",
                "存在恢复/中断转换但缺少 paused 状态（历史状态 H 无载体）",
                rule_group="复合/历史状态",
                suggestion="增加一个 kind=paused、history=shallow/deep 的挂起状态承接中断",
                table_ref="表7-5",
            )
        )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
