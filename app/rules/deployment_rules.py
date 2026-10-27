"""部署图质检规则引擎（纯 Python，不调用 LLM，不耗 token）。

输入 DeploymentModel，输出 ReviewReport（对齐 usecase_rules 的契约）。
规则分组（对齐教材部署图/架构建模校验维度）：
- 结构校验（DEP-DUP/DEP-REF/DEP-EMPTY）：节点唯一、端点存在、图非空；
- 部署校验（DEP-UNDEP）：构件必须部署到节点；
- K8s 链路（DEP-K8S）：ingress → service → workload 的可达性提示。
模型层已拦的结构非法（节点重复/端点缺失/构件宿主不存在）这里做防御性复查。
"""

import re

from app.models.review import ReviewIssue, ReviewReport
from app.models.uml import DeploymentModel


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


def _stereotypes(model: DeploymentModel) -> set[str]:
    return {n.stereotype.strip().lower() for n in model.nodes if n.stereotype.strip()}


def check_deployment_model(model: DeploymentModel) -> ReviewReport:
    """对部署图模型执行全部规则，产出 ReviewReport（issues 顺序稳定）。"""
    issues: list[ReviewIssue] = []
    node_names = [n.name for n in model.nodes]
    node_set = set(node_names)
    art_names = [a.name for a in model.artifacts]
    endpoint_set = node_set | set(art_names)

    # ---- DEP-EMPTY 部署图为空 ----
    if not model.nodes:
        issues.append(
            _issue(
                "DEP-EMPTY",
                "error",
                model.title or "deployment",
                "部署图没有任何节点，无法表达运行环境",
                rule_group="结构校验",
                suggestion="至少声明一个设备/执行环境节点，并把构件部署上去",
            )
        )

    # ---- DEP-DUP 节点唯一（模型层已拦，防御性复查）----
    dup_nodes = sorted({n for n in node_names if node_names.count(n) > 1})
    for name in dup_nodes:
        issues.append(
            _issue(
                "DEP-DUP",
                "error",
                name,
                f"节点名「{name}」重复定义",
                rule_group="结构校验",
                suggestion="合并重复节点或重命名",
            )
        )

    # ---- DEP-REF 关系端点必须存在（模型层已拦，防御性复查）----
    for rel in model.associations:
        if rel.source_id not in endpoint_set or rel.target_id not in endpoint_set:
            issues.append(
                _issue(
                    "DEP-REF",
                    "error",
                    f"{rel.source_id} -> {rel.target_id}",
                    "部署关系端点引用了未定义的节点/构件",
                    rule_group="结构校验",
                    suggestion="修改为已定义的节点或构件名",
                )
            )

    # ---- DEP-UNDEP 构件必须部署到节点 ----
    for art in model.artifacts:
        if not art.deployed_on:
            issues.append(
                _issue(
                    "DEP-UNDEP",
                    "warning",
                    art.name,
                    "构件未指定部署节点（deployed_on 为空）",
                    rule_group="部署校验",
                    suggestion="填写 deployed_on 为所在节点名，或从图中移除该构件",
                )
            )
        elif art.deployed_on not in node_set:
            issues.append(
                _issue(
                    "DEP-UNDEP",
                    "error",
                    art.name,
                    f"构件部署到不存在的节点：{art.deployed_on}",
                    rule_group="部署校验",
                    suggestion="补充该节点，或改为已存在节点",
                )
            )

    # ---- DEP-K8S K8s 链路可达性（教学特化）----
    stereotypes = _stereotypes(model)
    has_workload = bool(stereotypes & {"pod", "deployment", "statefulset", "daemonset"})
    if "service" in stereotypes and not has_workload:
        issues.append(
            _issue(
                "DEP-K8S",
                "warning",
                "service",
                "存在 Service 但缺少工作负载（Pod/Deployment），流量无处转发",
                rule_group="K8s 链路",
                suggestion="补充 Pod/Deployment 节点，并用通信关系连接 Service",
            )
        )
    if "ingress" in stereotypes and "service" not in stereotypes:
        issues.append(
            _issue(
                "DEP-K8S",
                "warning",
                "ingress",
                "存在 Ingress 但缺少 Service，外部流量无法到达工作负载",
                rule_group="K8s 链路",
                suggestion="补充 Service 节点，形成 Ingress → Service → Pod 链路",
            )
        )

    # ---- DEP-NAME 名称与构造型/技术词重复（如「教务服务service」「ingress ingress」）----
    for n in model.nodes:
        stereo = n.stereotype.strip()
        if not stereo:
            continue
        # 名称尾部出现与构造型相同的英文单词（大小写不敏感）即为中英混拼冗余
        tail = re.search(r"[A-Za-z]+$", n.name)
        if tail and tail.group(0).lower() == stereo.lower() and n.name != stereo:
            issues.append(
                _issue(
                    "DEP-NAME",
                    "warning",
                    n.name,
                    f"节点名「{n.name}」把构造型「{stereo}」重复拼进了名称，中英混拼不专业",
                    rule_group="命名规范",
                    suggestion=f"名称只写业务语义（如「教务服务」），技术类型交给 stereotype=\"{stereo}\" 表达",
                )
            )

    passed = not any(i.level == "error" for i in issues)
    return ReviewReport(diagram_type=model.type, passed=passed, issues=issues)
