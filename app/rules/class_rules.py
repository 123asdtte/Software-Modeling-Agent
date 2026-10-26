"""类图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 ClassModel，输出 ReviewReport（对齐 usecase_rules 的契约）。
规则分组（对齐教材类图/结构建模校验维度）：
- 关系校验（CL-DUP/CL-REF/CL-REAL）：类名唯一、端点存在、实现必须指向接口；
- 继承校验（CL-CYC）：继承/实现链路不得成环；
- 成员校验（CL-V1/CL-ABS/CL-MULTI）：可见性标注、抽象方法归属、多重性；
- 结构提示（CL-EMPTY/CL-IFACE）：空类、接口含属性。
模型层已拦的结构非法（类名重复/端点缺失/实现非接口）这里做防御性复查。
"""

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import ClassModel, ClassRelationType


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


def _find_inheritance_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """在「子类 -> 父类/接口」有向图中找环（三色 DFS），返回环路径或 None。"""
    white, gray, black = 0, 1, 2
    color = {node: white for node in edges}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = gray
        stack.append(node)
        for nxt in edges.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == gray:
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if color[nxt] == white:
                found = dfs(nxt)
                if found is not None:
                    return found
        stack.pop()
        color[node] = black
        return None

    for node in edges:
        if color[node] == white:
            found = dfs(node)
            if found is not None:
                return found
    return None


def check_class_model(model: ClassModel) -> ReviewReport:
    """对类图模型执行全部规则，产出 ReviewReport（issues 顺序稳定）。"""
    issues: list[ReviewIssue] = []
    class_names = [c.name for c in model.classes]
    name_set = set(class_names)
    by_name = {c.name: c for c in model.classes}

    # ---- CL-DUP 类名唯一（模型层已拦，防御性复查）----
    dup_names = sorted({n for n in class_names if class_names.count(n) > 1})
    for name in dup_names:
        issues.append(
            _issue(
                "CL-DUP",
                "error",
                name,
                f"类名「{name}」重复定义（渲染会产生别名歧义）",
                rule_group="关系校验",
                suggestion="合并重复定义或重命名",
            )
        )

    # ---- 关系遍历：CL-REF / CL-REAL / CL-MULTI + 继承图 ----
    inheritance_edges: dict[str, list[str]] = {name: [] for name in name_set}
    for rel in model.relations:
        if rel.source_id not in name_set or rel.target_id not in name_set:
            issues.append(
                _issue(
                    "CL-REF",
                    "error",
                    f"{rel.source_id} -> {rel.target_id}",
                    "关系端点引用了未定义的类",
                    rule_group="关系校验",
                    suggestion="修改为已定义的类名，或补充对应类",
                )
            )
            continue

        if rel.type == ClassRelationType.REALIZATION:
            target = by_name[rel.target_id]
            if not target.is_interface:
                issues.append(
                    _issue(
                        "CL-REAL",
                        "error",
                        f"{rel.source_id} -> {rel.target_id}",
                        f"实现关系的目标「{rel.target_id}」不是接口",
                        rule_group="关系校验",
                        suggestion="把目标类标记为 is_interface=true，或改用 generalization",
                    )
                )

        if rel.type in (ClassRelationType.GENERALIZATION, ClassRelationType.REALIZATION):
            inheritance_edges[rel.source_id].append(rel.target_id)

        if rel.type in (
            ClassRelationType.COMPOSITION,
            ClassRelationType.AGGREGATION,
        ) and not rel.target_multiplicity:
            issues.append(
                _issue(
                    "CL-MULTI",
                    "warning",
                    f"{rel.source_id} -> {rel.target_id}",
                    "组合/聚合关系未标注目标端多重性",
                    rule_group="成员校验",
                    suggestion="补充 target_multiplicity（如 1、0..*、1..*）",
                )
            )

    # ---- CL-CYC 继承/实现链路成环 ----
    cycle = _find_inheritance_cycle(inheritance_edges)
    if cycle:
        issues.append(
            _issue(
                "CL-CYC",
                "error",
                " -> ".join(cycle),
                "继承/实现关系形成环，模型无法成立",
                rule_group="继承校验",
                suggestion="打破循环：调整继承方向或抽取公共父类/接口",
            )
        )

    # ---- 成员级校验：CL-V1 可见性 / CL-ABS 抽象方法归属 ----
    for item in model.classes:
        for attr in item.attributes:
            if attr.visibility is None:
                issues.append(
                    _issue(
                        "CL-V1",
                        "warning",
                        f"{item.name}.{attr.name}",
                        "属性未标注可见性（+/-/#/~）",
                        rule_group="成员校验",
                        suggestion="按封装原则补充可见性，通常属性为 private（-）",
                    )
                )
        for method in item.methods:
            if method.visibility is None:
                issues.append(
                    _issue(
                        "CL-V1",
                        "warning",
                        f"{item.name}.{method.name}",
                        "方法未标注可见性（+/-/#/~）",
                        rule_group="成员校验",
                        suggestion="补充可见性，对外服务通常为 public（+）",
                    )
                )
            if method.is_abstract and not (item.is_abstract or item.is_interface):
                issues.append(
                    _issue(
                        "CL-ABS",
                        "error",
                        f"{item.name}.{method.name}",
                        "具体类中包含抽象方法，但类本身未声明为抽象类/接口",
                        rule_group="成员校验",
                        suggestion="把类标记为 is_abstract=true，或去掉方法的 is_abstract",
                    )
                )

    # ---- 结构提示：CL-EMPTY 空类 / CL-IFACE 接口含属性 ----
    for item in model.classes:
        if not item.attributes and not item.methods:
            issues.append(
                _issue(
                    "CL-EMPTY",
                    "info",
                    item.name,
                    "类没有任何属性或方法（可能只是占位）",
                    rule_group="结构提示",
                    suggestion="补充职责相关的属性/方法，或确认该类是否应出现在图中",
                )
            )
        if item.is_interface and item.attributes:
            issues.append(
                _issue(
                    "CL-IFACE",
                    "warning",
                    item.name,
                    "接口中包含属性（字段）",
                    rule_group="结构提示",
                    suggestion="接口通常只声明常量；实例属性应放到实现类中",
                )
            )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
