"""用例图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 app/models/uml.py 的 UseCaseModel（结构非法已在模型层拦截），
输出 app/models/review.py 的 ReviewReport。

规则分组（对齐教材用例图校验维度）：
- 边界校验（UC-B1）：参与者命中内部组件黑名单；
- 粒度校验（UC-G1）：用例名含界面操作词；
- 关系校验（UC-R-*）：重复关系 / 泛化异类 / 引用与类型防御；
- 数量提示（UC-C1）：用例少于 3 个。

判定规则：存在 error → passed=False；warning/info 不影响 passed。
模型层已拦截的问题（引用不存在、非法类型）这里做防御性复查，
保证规则引擎作为独立校验层成立。
"""

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import RelationType, UseCaseModel

# 内部组件黑名单：这些词出现在参与者名称中，说明把系统内部组件画成了参与者
_INTERNAL_COMPONENT_WORDS = (
    "数据库",
    "存储",
    "缓存",
    "消息队列",
    "网络",
    "界面",
    "前端",
    "后端",
    "服务器",
    "表单",
    "按钮",
    "接口",
)

# 界面操作词：出现在用例名中说明粒度落到了操作步骤而非业务目标
_UI_OPERATION_WORDS = ("点击", "输入", "按下", "选择", "填写", "双击", "打开", "关闭")


def _issue(
    rule_id: str,
    level: str,
    target: str,
    message: str,
    *,
    rule_group: str,
    suggestion: str = "",
    table_ref: str = "",
) -> ReviewIssue:
    return ReviewIssue(
        rule_id=rule_id,
        level=level,
        target=target,
        message=message,
        rule_group=rule_group,
        suggestion=suggestion,
        table_ref=table_ref,
    )


def _relation_signature(rel) -> tuple:
    """关系签名：association 无方向语义用无序对，其余保持方向。"""
    if rel.type == RelationType.ASSOCIATION:
        return (rel.type.value, *sorted((rel.source_id, rel.target_id)))
    return (rel.type.value, rel.source_id, rel.target_id)


def check_usecase_model(model: UseCaseModel) -> ReviewReport:
    """对用例图模型执行全部规则，产出 ReviewReport（issues 顺序稳定）。"""
    issues: list[ReviewIssue] = []
    actor_set = {a.name for a in model.actors}
    usecase_set = {u.id for u in model.usecases}

    # ---- UC-B1 边界校验：内部组件不能作为参与者 ----
    for actor in model.actors:
        hit = next((w for w in _INTERNAL_COMPONENT_WORDS if w in actor.name), None)
        if hit:
            issues.append(
                _issue(
                    "UC-B1",
                    "error",
                    actor.name,
                    f"「{hit}」属于系统内部组件，不能作为参与者",
                    rule_group="边界校验",
                    suggestion="内部组件应在系统边界内建模，参与者只保留外部角色",
                    table_ref="表2-6",
                )
            )

    # ---- UC-G1 粒度校验：用例名含界面操作词 ----
    for uc in model.usecases:
        hit = next((w for w in _UI_OPERATION_WORDS if w in uc.name), None)
        if hit:
            issues.append(
                _issue(
                    "UC-G1",
                    "warning",
                    uc.id,
                    f"用例名「{uc.name}」含界面操作词「{hit}」，是操作步骤而非业务目标",
                    rule_group="粒度校验",
                    suggestion="建议改为表达业务目标的名称（如「提交信息」而非「点击提交」）",
                )
            )

    # ---- 关系遍历：重复关系 / 泛化异类 / 引用与类型防御 / 连接索引 ----
    linked_actors: set[str] = set()
    linked_usecases: set[str] = set()
    seen_signatures: dict[tuple, str] = {}

    for rel in model.relations:
        sig = _relation_signature(rel)
        if sig in seen_signatures:
            issues.append(
                _issue(
                    "UC-R-DUP",
                    "warning",
                    f"{rel.source_id} -> {rel.target_id}",
                    f"与之前的 {rel.type.value} 关系重复，渲染会画重线",
                    rule_group="关系校验",
                    suggestion="删除重复的关系连线",
                )
            )
        else:
            seen_signatures[sig] = rel.source_id

        # 防御性复查：模型层已拦截，这里保证规则引擎独立成立
        if rel.source_id not in actor_set | usecase_set:
            issues.append(
                _issue(
                    "UC-R-REF",
                    "error",
                    f"{rel.source_id} -> {rel.target_id}",
                    f"关系 from 端「{rel.source_id}」不存在",
                    rule_group="关系校验",
                    suggestion="修正为已定义的参与者或用例",
                )
            )
            continue
        if rel.target_id not in actor_set | usecase_set:
            issues.append(
                _issue(
                    "UC-R-REF",
                    "error",
                    f"{rel.source_id} -> {rel.target_id}",
                    f"关系 to 端「{rel.target_id}」不存在",
                    rule_group="关系校验",
                    suggestion="修正为已定义的参与者或用例",
                )
            )
            continue

        if rel.type == RelationType.GENERALIZATION and ((rel.source_id in actor_set) != (rel.target_id in actor_set)):
            issues.append(
                _issue(
                    "UC-R-GEN",
                    "error",
                    f"{rel.source_id} -> {rel.target_id}",
                    "泛化关系只能连接同类元素（参与者-参与者 或 用例-用例）",
                    rule_group="关系校验",
                    suggestion="改为同类元素之间的泛化，或改用 association 连接参与者与用例",
                )
            )

        # 连接索引（孤立判定）：任何关系涉及到的元素都算"已连接"
        for endpoint in (rel.source_id, rel.target_id):
            if endpoint in actor_set:
                linked_actors.add(endpoint)
            elif endpoint in usecase_set:
                linked_usecases.add(endpoint)

    # 隐式关联（UseCase.actors）同样算连接
    for uc in model.usecases:
        for actor_name in uc.actors:
            linked_actors.add(actor_name)
            linked_usecases.add(uc.id)

    # ---- UC-R3 孤立元素 ----
    for actor in model.actors:
        if actor.name not in linked_actors:
            issues.append(
                _issue(
                    "UC-R3",
                    "warning",
                    actor.name,
                    "参与者未与任何用例关联（孤立参与者）",
                    rule_group="关系校验",
                    suggestion="为其连接用例，或确认是否应该出现在图中",
                )
            )
    for uc in model.usecases:
        if uc.id not in linked_usecases:
            issues.append(
                _issue(
                    "UC-R3",
                    "warning",
                    uc.id,
                    "用例未与任何参与者或其他用例关联（孤立用例）",
                    rule_group="关系校验",
                    suggestion="连接到参与者，或确认该用例是否属于本系统边界",
                )
            )

    # ---- UC-C1 数量提示 ----
    if len(model.usecases) < 3:
        issues.append(
            _issue(
                "UC-C1",
                "info",
                model.system,
                f"用例数量为 {len(model.usecases)}（少于 3 个），请确认是否覆盖完整需求",
                rule_group="数量提示",
                suggestion="检查需求描述，确认是否有遗漏的用例",
            )
        )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
