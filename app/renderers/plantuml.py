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

import re

from app.models.uml import DiagramType, RelationType, UseCaseModel

# PlantUML 显示文本中的控制字符（换行/回车/制表等）一律替换为空格
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
