"""UML 领域模型（M4 边界第一步）：目前仅用例图；活动图/状态机图后续扩展。

契约冻结点（评审 P0）：后续 PlantUML 渲染器、规则引擎、HTTP API 都以
本模块的 UseCaseModel / ReviewReport 为数据契约，不再各自定义。
结构对齐 `docs/03-技术方案/04_UML建模Agent详细技术方案.md` 的用例图中间 JSON。
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NON_SPACE = ("name", "id", "system", "source_id", "target_id")


def _reject_blank(value: str) -> str:
    """必填字符串不允许空白（含纯空格）。"""
    if not value or not value.strip():
        raise ValueError("不能为空白")
    return value


class DiagramType(str, Enum):
    """图类型（首期仅用例图，活动图/状态机图按 PRD 后续扩展）。"""

    USECASE = "usecase"


class Actor(BaseModel):
    """参与者：与系统交互的外部角色（教材：必须画在系统边界外）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    role: Literal["primary", "supporting"] = "primary"

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class UseCase(BaseModel):
    """用例：系统对外提供的可辨识价值（画在系统边界内）。"""

    id: str
    name: str
    actors: list[str] = Field(default_factory=list)
    goal: str = ""

    @field_validator("id", "name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class RelationType:
    """用例图合法关系类型（对齐教材：包含/扩展/关联/泛化）。"""

    INCLUDE = "include"
    EXTEND = "extend"
    ASSOCIATION = "association"
    GENERALIZATION = "generalization"

    ALL = (INCLUDE, EXTEND, ASSOCIATION, GENERALIZATION)


class Relation(BaseModel):
    """关系边：JSON 字段名沿用技术方案文档的 from/to（alias 兼容 Python 保留字）。"""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["include", "extend", "association", "generalization"]
    source_id: str = Field(alias="from")
    target_id: str = Field(alias="to")
    note: str = ""

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class UseCaseModel(BaseModel):
    """用例图中间模型：LLM 生成 → 质检 → 渲染的共同数据契约。"""

    type: Literal[DiagramType.USECASE] = DiagramType.USECASE
    system: str
    actors: list[Actor] = Field(default_factory=list)
    usecases: list[UseCase] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)

    @field_validator("system")
    @classmethod
    def _system_not_blank(cls, v: str) -> str:
        return _reject_blank(v)

    @model_validator(mode="after")
    def _check_references(self) -> "UseCaseModel":
        """引用一致性：关系两端与用例关联的参与者必须真实存在（评审 P0 契约）。"""
        actor_names = {a.name for a in self.actors}
        usecase_ids = {u.id for u in self.usecases}

        for u in self.usecases:
            for actor in u.actors:
                if actor not in actor_names:
                    raise ValueError(f"用例 {u.id} 引用了不存在的参与者：{actor}")

        for rel in self.relations:
            src, dst = rel.source_id, rel.target_id
            if src not in actor_names | usecase_ids:
                raise ValueError(f"关系 {rel.type} 的 from 端不存在：{src}")
            if dst not in actor_names | usecase_ids:
                raise ValueError(f"关系 {rel.type} 的 to 端不存在：{dst}")
            if rel.type in (RelationType.INCLUDE, RelationType.EXTEND) and (
                src not in usecase_ids or dst not in usecase_ids
            ):
                # 教材语义：包含/扩展只能发生在用例与用例之间
                raise ValueError(f"{rel.type} 关系两端必须是用例：{src} -> {dst}")
            if rel.type == RelationType.ASSOCIATION:
                # 教材语义：关联连接参与者与用例
                src_actor, dst_actor = src in actor_names, dst in actor_names
                if src_actor == dst_actor:
                    raise ValueError(f"association 关系必须连接参与者与用例：{src} -> {dst}")
        return self
