"""UML 领域模型（M4 边界第一步）：目前仅用例图；活动图/状态机图后续扩展。

契约冻结点（评审 P0）：后续 PlantUML 渲染器、规则引擎、HTTP API 都以
本模块的 UseCaseModel / ReviewReport 为数据契约，不再各自定义。
结构对齐 `docs/03-技术方案/04_UML建模Agent详细技术方案.md` 的用例图中间 JSON。

序列化约定（评审 P1 已锁定）：
- Relation 对外 JSON 使用 from/to（`model_dump(by_alias=True)`），
  Python 内部访问 source_id/target_id；渲染器只允许其中一种访问方式，禁止混用。
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 字段长度边界（防恶意超长输入 / 控制渲染与 API 体积；不过度限制正常业务）
_MAX_NAME = 50
_MAX_SYSTEM = 100
_MAX_ID = 20
_MAX_GOAL = 200
_MAX_NOTE = 200
_MAX_ACTORS = 20
_MAX_USECASES = 30
_MAX_RELATIONS = 60


def _reject_blank(value: str) -> str:
    """必填字符串不允许空白（含纯空格）。"""
    if not value or not value.strip():
        raise ValueError("不能为空白")
    return value


class DiagramType(str, Enum):
    """图类型（首期仅用例图，活动图/状态机图按 PRD 后续扩展）。"""

    USECASE = "usecase"


class RelationType(str, Enum):
    """用例图合法关系类型（对齐教材：包含/扩展/关联/泛化）。

    str 枚举：JSON 输入仍可直接用字符串，输出为枚举值字符串。
    """

    INCLUDE = "include"
    EXTEND = "extend"
    ASSOCIATION = "association"
    GENERALIZATION = "generalization"


class Actor(BaseModel):
    """参与者：与系统交互的外部角色（教材：必须画在系统边界外）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)
    role: Literal["primary", "supporting"] = "primary"

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class UseCase(BaseModel):
    """用例：系统对外提供的可辨识价值（画在系统边界内）。"""

    id: str = Field(max_length=_MAX_ID)
    name: str = Field(max_length=_MAX_NAME)
    actors: list[str] = Field(default_factory=list)
    goal: str = Field(default="", max_length=_MAX_GOAL)

    @field_validator("id", "name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class Relation(BaseModel):
    """关系边：对外 JSON 字段名为 from/to（alias），内部访问 source_id/target_id。"""

    model_config = ConfigDict(populate_by_name=True)

    type: RelationType
    source_id: str = Field(alias="from", max_length=_MAX_ID + _MAX_NAME)
    target_id: str = Field(alias="to", max_length=_MAX_ID + _MAX_NAME)
    note: str = Field(default="", max_length=_MAX_NOTE)

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class UseCaseModel(BaseModel):
    """用例图中间模型：LLM 生成 → 质检 → 渲染的共同数据契约。"""

    type: Literal[DiagramType.USECASE] = DiagramType.USECASE
    system: str = Field(max_length=_MAX_SYSTEM)
    actors: list[Actor] = Field(default_factory=list, max_length=_MAX_ACTORS)
    usecases: list[UseCase] = Field(default_factory=list, max_length=_MAX_USECASES)
    relations: list[Relation] = Field(default_factory=list, max_length=_MAX_RELATIONS)

    @field_validator("system")
    @classmethod
    def _system_not_blank(cls, v: str) -> str:
        return _reject_blank(v)

    @model_validator(mode="after")
    def _check_references(self) -> "UseCaseModel":
        """引用与唯一性校验（评审 P1：重复/冲突必须在模型层拦截）。"""
        actor_names = [a.name for a in self.actors]
        usecase_ids = [u.id for u in self.usecases]
        actor_set = set(actor_names)
        usecase_set = set(usecase_ids)

        # 唯一性：重复会产生渲染歧义（同名节点合并/alias 冲突）
        dup_actors = sorted({n for n in actor_names if actor_names.count(n) > 1})
        if dup_actors:
            raise ValueError(f"存在重复的参与者名称：{dup_actors}")
        dup_ids = sorted({i for i in usecase_ids if usecase_ids.count(i) > 1})
        if dup_ids:
            raise ValueError(f"存在重复的用例 ID：{dup_ids}")
        cross = sorted(actor_set & usecase_set)
        if cross:
            raise ValueError(f"参与者名称与用例 ID 冲突：{cross}")

        # 引用一致性：关系两端与用例关联的参与者必须真实存在
        for u in self.usecases:
            for actor in u.actors:
                if actor not in actor_set:
                    raise ValueError(f"用例 {u.id} 引用了不存在的参与者：{actor}")

        for rel in self.relations:
            src, dst = rel.source_id, rel.target_id
            if src not in actor_set | usecase_set:
                raise ValueError(f"关系 {rel.type.value} 的 from 端不存在：{src}")
            if dst not in actor_set | usecase_set:
                raise ValueError(f"关系 {rel.type.value} 的 to 端不存在：{dst}")
            if rel.type in (RelationType.INCLUDE, RelationType.EXTEND) and (
                src not in usecase_set or dst not in usecase_set
            ):
                # 教材语义：包含/扩展只能发生在用例与用例之间
                raise ValueError(f"{rel.type.value} 关系两端必须是用例：{src} -> {dst}")
            if rel.type == RelationType.ASSOCIATION:
                src_actor, dst_actor = src in actor_set, dst in actor_set
                if src_actor == dst_actor:
                    raise ValueError(f"association 关系必须连接参与者与用例：{src} -> {dst}")
        # 注：完全相同的关系重复出现是"学生画重线"错误，由规则引擎报警告，
        # 模型层不拒绝（质检对象是待检图，模型层只拦结构性非法）。
        return self
