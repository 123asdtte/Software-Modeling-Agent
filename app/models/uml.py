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
    """图类型。

    第一批（M4）：usecase / activity / statemachine；
    第二批（C 任务）：class / sequence / deployment——对齐配套教材
    模块二（结构建模）、模块三（动态建模）、模块四（架构与部署建模）。
    """

    USECASE = "usecase"
    ACTIVITY = "activity"
    STATEMACHINE = "statemachine"
    CLASS = "class"
    SEQUENCE = "sequence"
    DEPLOYMENT = "deployment"


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


# ============================================================================
# 活动图模型（技术方案文档 §2.2）：泳道 + 动作/决策/分叉/汇合 + 控制流
# ============================================================================

_MAX_MODULE = 100
_MAX_SWIMLANES = 12
_MAX_NODES = 60
_MAX_FLOWS = 80
_MAX_BRANCHES = 12


class ActivityNodeKind(str, Enum):
    """活动图节点类型。"""

    ACTION = "action"
    DECISION = "decision"
    FORK = "fork"
    JOIN = "join"
    INITIAL = "initial"
    FINAL = "final"
    MERGE = "merge"


class Swimlane(BaseModel):
    """泳道（责任分区）：活动图中必须归属动作节点的分区。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ActivityBranch(BaseModel):
    """决策节点的输出分支（条件 + 目标节点 id）。"""

    model_config = ConfigDict(populate_by_name=True)

    cond: str = Field(default="", max_length=_MAX_NOTE)
    to: str = Field(default="", max_length=_MAX_ID + _MAX_NAME)


class ActivityNode(BaseModel):
    """活动图节点：动作/决策/分叉/汇合/起止。

    kind=action/decision 必须有 name 与 lane（归属泳道）；
    fork/join/merge/initial/final 可无 name 与 lane（结构性节点）。
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(max_length=_MAX_ID)
    name: str = Field(default="", max_length=_MAX_NAME)
    lane: str = Field(default="", max_length=_MAX_NAME)
    kind: ActivityNodeKind
    branches: list[ActivityBranch] = Field(default_factory=list, max_length=_MAX_BRANCHES)

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v: str) -> str:
        return _reject_blank(v)

    @model_validator(mode="after")
    def _check_kind_fields(self) -> "ActivityNode":
        if self.kind in (ActivityNodeKind.ACTION, ActivityNodeKind.DECISION) and (
            not self.name or not self.name.strip()
        ):
            raise ValueError(f"动作/决策节点 {self.id} 必须有 name")
        return self


class ActivityFlow(BaseModel):
    """控制流：from/to 为节点 id；决策分支用 cond 标注监护条件。"""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", max_length=_MAX_ID + _MAX_NAME)
    target: str = Field(alias="to", max_length=_MAX_ID + _MAX_NAME)
    cond: str = Field(default="", max_length=_MAX_NOTE)

    @field_validator("source", "target")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ActivityModel(BaseModel):
    """活动图中间模型：LLM 生成 → 质检 → 渲染的共同数据契约。"""

    type: Literal[DiagramType.ACTIVITY] = DiagramType.ACTIVITY
    module: str = Field(default="", max_length=_MAX_MODULE)
    swimlanes: list[Swimlane] = Field(default_factory=list, max_length=_MAX_SWIMLANES)
    nodes: list[ActivityNode] = Field(default_factory=list, max_length=_MAX_NODES)
    flows: list[ActivityFlow] = Field(default_factory=list, max_length=_MAX_FLOWS)

    @model_validator(mode="after")
    def _check_references(self) -> "ActivityModel":
        lane_names = {s.name for s in self.swimlanes}
        node_ids = [n.id for n in self.nodes]
        node_set = set(node_ids)

        # 唯一性
        dup_ids = sorted({i for i in node_ids if node_ids.count(i) > 1})
        if dup_ids:
            raise ValueError(f"存在重复的节点 ID：{dup_ids}")
        dup_lanes = sorted({s.name for s in self.swimlanes if [x.name for x in self.swimlanes].count(s.name) > 1})
        if dup_lanes:
            raise ValueError(f"存在重复的泳道名称：{dup_lanes}")

        # 泳道归属合法（动作/决策节点必须归属已定义泳道；结构性节点允许无泳道）
        for n in self.nodes:
            if n.lane and n.lane not in lane_names:
                raise ValueError(f"节点 {n.id} 的泳道「{n.lane}」未定义")
            if n.kind in (ActivityNodeKind.ACTION, ActivityNodeKind.DECISION) and not n.lane:
                raise ValueError(f"{n.kind.value} 节点 {n.id} 必须归属某个泳道")

        # 控制流端点必须存在
        for f in self.flows:
            if f.source not in node_set:
                raise ValueError(f"控制流 from 端节点不存在：{f.source}")
            if f.target not in node_set:
                raise ValueError(f"控制流 to 端节点不存在：{f.target}")

        # 决策节点的分支目标必须存在（仅当提供了 branches）
        for n in self.nodes:
            if n.kind == ActivityNodeKind.DECISION:
                for b in n.branches:
                    if b.to and b.to not in node_set:
                        raise ValueError(f"决策节点 {n.id} 的分支目标不存在：{b.to}")
        return self


# ============================================================================
# 状态机图模型（技术方案文档 §2.2）：单一反应型对象 + 状态 + 转换 + 历史
# ============================================================================

_MAX_OBJECT = 100
_MAX_STATES = 40
_MAX_TRANSITIONS = 60
_HISTORY_TOKEN = "history"  # 浅/深历史伪状态占位（渲染为 H / H*）


class StateKind(str, Enum):
    """状态机图状态类型（initial/final 为伪状态）。"""

    INITIAL = "initial"
    NORMAL = "normal"
    FINAL = "final"
    PAUSED = "paused"


class StateNode(BaseModel):
    """状态：围绕单一反应型对象；kind 区分初/终/普通/挂起。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(max_length=_MAX_ID)
    name: str = Field(default="", max_length=_MAX_NAME)
    kind: StateKind = StateKind.NORMAL
    history: str = Field(default="", max_length=10)  # shallow / deep（仅 paused 用）

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v: str) -> str:
        return _reject_blank(v)

    @model_validator(mode="after")
    def _check_fields(self) -> "StateNode":
        if self.kind in (StateKind.INITIAL, StateKind.FINAL) and not self.name:
            # 伪状态可无业务名，渲染时用关键字
            pass
        if self.kind == StateKind.PAUSED and self.history and self.history not in ("shallow", "deep"):
            raise ValueError(f"挂起状态 {self.id} 的 history 必须为 shallow/deep")
        return self


class Transition(BaseModel):
    """转换：触发事件 + 监护条件；any_state 表示可自任意状态触发。"""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", max_length=_MAX_ID + _MAX_NAME)
    target: str = Field(alias="to", max_length=_MAX_ID + _MAX_NAME)
    event: str = Field(default="", max_length=_MAX_NOTE)
    guard: str = Field(default="", max_length=_MAX_NOTE)
    any_state: bool = False

    @field_validator("source", "target")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class StateMachineModel(BaseModel):
    """状态机图中间模型：LLM 生成 → 质检 → 渲染的共同数据契约。"""

    type: Literal[DiagramType.STATEMACHINE] = DiagramType.STATEMACHINE
    object: str = Field(default="", max_length=_MAX_OBJECT)
    states: list[StateNode] = Field(default_factory=list, max_length=_MAX_STATES)
    transitions: list[Transition] = Field(default_factory=list, max_length=_MAX_TRANSITIONS)

    @model_validator(mode="after")
    def _check_references(self) -> "StateMachineModel":
        state_ids = [s.id for s in self.states]
        state_set = set(state_ids)
        dup_ids = sorted({i for i in state_ids if state_ids.count(i) > 1})
        if dup_ids:
            raise ValueError(f"存在重复的状态 ID：{dup_ids}")

        initials = [s for s in self.states if s.kind == StateKind.INITIAL]
        finals = [s for s in self.states if s.kind == StateKind.FINAL]
        # 结构性约束（初/终态数量）在规则引擎给 error；模型层只拦明显非法
        if len(initials) > 1:
            raise ValueError("初始伪状态只能有一个")
        if len(finals) > 1:
            raise ValueError("最终伪状态只能有一个")

        for t in self.transitions:
            # 历史伪状态与 any_state 是合法特殊端点
            if t.source != _HISTORY_TOKEN and not t.any_state and t.source not in state_set:
                raise ValueError(f"转换 from 端状态不存在：{t.source}")
            if t.target != _HISTORY_TOKEN and t.target not in state_set:
                raise ValueError(f"转换 to 端状态不存在：{t.target}")
        return self


# ============================================================================
# 类图模型（C 任务）：类/接口 + 属性/方法 + 六种关系
# ============================================================================

_MAX_CLASSES = 40
_MAX_CLASS_RELATIONS = 80
_MAX_MEMBERS = 40
_MAX_PARAMS = 12
_MAX_TYPE = 60
_MAX_LABEL = 120


# ---------------------------------------------------------------------------
# LLM 枚举容错：模型对 UML 术语的写法不稳定（generalization / inheritance / 继承、
# public / + 等都会出现）。这里只做**同义归一**（不做语义猜测），把常见写法映射到
# 枚举合法值；无法识别的原样返回，仍由 pydantic 报明确错误。
# 目的：措辞差异不应该让整张图生成失败（真实端到端已复现：relations.type 报错 → 502）。
# ---------------------------------------------------------------------------
def _normalize_enum(value: object, aliases: dict[str, str]) -> object:
    """按别名表归一字符串枚举值；非字符串原样返回。

    命中别名 → 用别名目标；未命中 → 返回**归一后的 key**（小写、空格/连字符转下划线）。
    后者保证 "Generalization"、" composition " 这类大小写/空白变体也能落到合法枚举值上；
    真正非法的写法（如 "wat"）归一后仍非法，继续由 pydantic 报错。
    """
    if not isinstance(value, str):
        return value
    raw = value.strip()
    # 符号型枚举值（可见性 + - # ~）不做大小写/分隔符归一，否则 "-" 会被转成 "_"
    if len(raw) == 1 and not raw.isalnum():
        return raw
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return aliases.get(key, key)


_VISIBILITY_ALIASES: dict[str, str] = {
    "public": "+",
    "pub": "+",
    "公开": "+",
    "private": "-",
    "priv": "-",
    "私有": "-",
    "protected": "#",
    "prot": "#",
    "受保护": "#",
    "package": "~",
    "default": "~",
    "internal": "~",
    "包": "~",
}

_CLASS_RELATION_ALIASES: dict[str, str] = {
    # generalization 的各种叫法
    "inheritance": "generalization",
    "inherit": "generalization",
    "generalize": "generalization",
    "generalisation": "generalization",
    "extends": "generalization",
    "extension": "generalization",
    "泛化": "generalization",
    "继承": "generalization",
    # realization
    "implementation": "realization",
    "implement": "realization",
    "implements": "realization",
    "realize": "realization",
    "realisation": "realization",
    "实现": "realization",
    # 其余
    "composed_of": "composition",
    "组合": "composition",
    "强聚合": "composition",
    "aggregate": "aggregation",
    "聚合": "aggregation",
    "associate": "association",
    "关联": "association",
    "depend": "dependency",
    "uses": "dependency",
    "use": "dependency",
    "依赖": "dependency",
}

_LIFELINE_KIND_ALIASES: dict[str, str] = {
    "participant": "object",
    "对象": "object",
    "参与者": "object",
    "角色": "actor",
    "用户": "actor",
    "边界": "boundary",
    "控制": "control",
    "实体": "entity",
    "数据库": "database",
    "db": "database",
}

_MESSAGE_KIND_ALIASES: dict[str, str] = {
    "synchronous": "sync",
    "call": "sync",
    "调用": "sync",
    "同步": "sync",
    "asynchronous": "async",
    "异步": "async",
    "reply": "return",
    "response": "return",
    "result": "return",
    "返回": "return",
    "new": "create",
    "creation": "create",
    "创建": "create",
    "delete": "destroy",
    "delete_message": "destroy",
    "destroyed": "destroy",
    "销毁": "destroy",
}

_FRAGMENT_KIND_ALIASES: dict[str, str] = {
    "alternative": "alt",
    "if": "alt",
    "条件": "alt",
    "分支": "alt",
    "while": "loop",
    "repeat": "loop",
    "循环": "loop",
    "optional": "opt",
    "option": "opt",
    "可选": "opt",
    "parallel": "par",
    "并行": "par",
}

_DEPLOY_NODE_KIND_ALIASES: dict[str, str] = {
    "execution_environment": "exec_env",
    "executionenvironment": "exec_env",
    "environment": "exec_env",
    "execenv": "exec_env",
    "node": "exec_env",
    "执行环境": "exec_env",
    "服务器": "exec_env",
    "容器": "exec_env",
    "physical": "device",
    "hardware": "device",
    "设备": "device",
    "物理机": "device",
}

_DEPLOY_ASSOCIATION_ALIASES: dict[str, str] = {
    "comm": "communication",
    "communicates": "communication",
    "http": "communication",
    "tcp": "communication",
    "通信": "communication",
    "depend": "dependency",
    "依赖": "dependency",
    "connect": "association",
    "连接": "association",
    "关联": "association",
}


class Visibility(str, Enum):
    """UML 可见性（渲染为 PlantUML 前缀符号）。"""

    PUBLIC = "+"
    PRIVATE = "-"
    PROTECTED = "#"
    PACKAGE = "~"


class ClassAttribute(BaseModel):
    """类属性：visibility 允许缺省（缺省由规则引擎提示学生补标）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)
    type: str = Field(default="", max_length=_MAX_TYPE)
    visibility: Visibility | None = None
    is_static: bool = False

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility(cls, v):
        return _normalize_enum(v, _VISIBILITY_ALIASES)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class MethodParam(BaseModel):
    """方法参数：名称 + 类型。"""

    name: str = Field(max_length=_MAX_NAME)
    type: str = Field(default="", max_length=_MAX_TYPE)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ClassMethod(BaseModel):
    """类方法：参数、返回类型、可见性、静态/抽象标记。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)
    params: list[MethodParam] = Field(default_factory=list, max_length=_MAX_PARAMS)
    return_type: str = Field(default="void", max_length=_MAX_TYPE)
    visibility: Visibility | None = None
    is_static: bool = False
    is_abstract: bool = False

    @field_validator("visibility", mode="before")
    @classmethod
    def _normalize_visibility(cls, v):
        return _normalize_enum(v, _VISIBILITY_ALIASES)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ClassItem(BaseModel):
    """类/接口：is_interface 优先于 is_abstract（接口本身就是抽象的）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)
    attributes: list[ClassAttribute] = Field(default_factory=list, max_length=_MAX_MEMBERS)
    methods: list[ClassMethod] = Field(default_factory=list, max_length=_MAX_MEMBERS)
    is_abstract: bool = False
    is_interface: bool = False

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ClassRelationType(str, Enum):
    """类图合法关系（对齐 UML 结构关系语义）。"""

    ASSOCIATION = "association"
    AGGREGATION = "aggregation"
    COMPOSITION = "composition"
    GENERALIZATION = "generalization"
    DEPENDENCY = "dependency"
    REALIZATION = "realization"


class ClassRelation(BaseModel):
    """类间关系：from/to 为类名；可标注两端多重性。"""

    model_config = ConfigDict(populate_by_name=True)

    type: ClassRelationType
    source_id: str = Field(alias="from", max_length=_MAX_NAME)
    target_id: str = Field(alias="to", max_length=_MAX_NAME)
    label: str = Field(default="", max_length=_MAX_LABEL)
    source_multiplicity: str = Field(default="", max_length=20)
    target_multiplicity: str = Field(default="", max_length=20)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        return _normalize_enum(v, _CLASS_RELATION_ALIASES)

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class ClassModel(BaseModel):
    """类图中间模型：LLM 生成 → 质检 → 渲染 → 可转 Java 代码。"""

    type: Literal[DiagramType.CLASS] = DiagramType.CLASS
    title: str = Field(default="", max_length=_MAX_SYSTEM)
    classes: list[ClassItem] = Field(default_factory=list, max_length=_MAX_CLASSES)
    relations: list[ClassRelation] = Field(default_factory=list, max_length=_MAX_CLASS_RELATIONS)

    @model_validator(mode="after")
    def _check_references(self) -> "ClassModel":
        names = [c.name for c in self.classes]
        name_set = set(names)

        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"存在重复的类名：{dup}")

        for rel in self.relations:
            if rel.source_id not in name_set:
                raise ValueError(f"关系 {rel.type.value} 的 from 端类不存在：{rel.source_id}")
            if rel.target_id not in name_set:
                raise ValueError(f"关系 {rel.type.value} 的 to 端类不存在：{rel.target_id}")
            # 实现关系只能指向接口（UML 语义；规则引擎再做一次防御性复查）
            if rel.type == ClassRelationType.REALIZATION:
                target = next(c for c in self.classes if c.name == rel.target_id)
                if not target.is_interface:
                    raise ValueError(f"realization 的 to 端必须是接口：{rel.target_id}")
        return self


# ============================================================================
# 时序图模型（C 任务）：生命线 + 有序消息 + 片段(alt/loop/opt/par)
# ============================================================================

_MAX_LIFELINES = 20
_MAX_MESSAGES = 120
_MAX_FRAGMENTS = 20


class LifelineKind(str, Enum):
    """生命线类型（贴图关键字）。"""

    ACTOR = "actor"
    OBJECT = "object"
    BOUNDARY = "boundary"
    CONTROL = "control"
    ENTITY = "entity"
    DATABASE = "database"


class Lifeline(BaseModel):
    """生命线：参与交互的对象/角色。name 为唯一标识（消息端点引用它）。"""

    name: str = Field(max_length=_MAX_NAME)
    kind: LifelineKind = LifelineKind.OBJECT
    classifier: str = Field(default="", max_length=_MAX_NAME)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v):
        return _normalize_enum(v, _LIFELINE_KIND_ALIASES)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class MessageKind(str, Enum):
    """消息类型（决定渲染箭头）。"""

    SYNC = "sync"
    ASYNC = "async"
    RETURN = "return"
    CREATE = "create"
    DESTROY = "destroy"


class SequenceMessage(BaseModel):
    """一条消息：order 为全局顺序号（唯一，渲染按它排序）。"""

    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(alias="from", max_length=_MAX_NAME)
    target_id: str = Field(alias="to", max_length=_MAX_NAME)
    label: str = Field(default="", max_length=_MAX_LABEL)
    kind: MessageKind = MessageKind.SYNC
    order: int = Field(ge=1, le=9999)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v):
        return _normalize_enum(v, _MESSAGE_KIND_ALIASES)

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class SequenceFragment(BaseModel):
    """片段：按 order 区间包裹连续消息（v1 仅支持互不重叠的单层片段）。"""

    kind: Literal["alt", "loop", "opt", "par"] = "alt"
    condition: str = Field(default="", max_length=_MAX_LABEL)
    start_order: int = Field(ge=1, le=9999)
    end_order: int = Field(ge=1, le=9999)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v):
        return _normalize_enum(v, _FRAGMENT_KIND_ALIASES)

    @model_validator(mode="after")
    def _check_range(self) -> "SequenceFragment":
        if self.start_order > self.end_order:
            raise ValueError("片段的 start_order 不能大于 end_order")
        return self


class SequenceModel(BaseModel):
    """时序图中间模型：LLM 生成 → 质检 → 渲染。"""

    type: Literal[DiagramType.SEQUENCE] = DiagramType.SEQUENCE
    title: str = Field(default="", max_length=_MAX_SYSTEM)
    lifelines: list[Lifeline] = Field(default_factory=list, max_length=_MAX_LIFELINES)
    messages: list[SequenceMessage] = Field(default_factory=list, max_length=_MAX_MESSAGES)
    fragments: list[SequenceFragment] = Field(default_factory=list, max_length=_MAX_FRAGMENTS)

    @model_validator(mode="after")
    def _check_references(self) -> "SequenceModel":
        names = [ll.name for ll in self.lifelines]
        name_set = set(names)
        dup_names = sorted({n for n in names if names.count(n) > 1})
        if dup_names:
            raise ValueError(f"存在重复的生命线名称：{dup_names}")

        orders = [m.order for m in self.messages]
        dup_orders = sorted({o for o in orders if orders.count(o) > 1})
        if dup_orders:
            raise ValueError(f"存在重复的消息顺序号：{dup_orders}")
        order_set = set(orders)

        for m in self.messages:
            if m.source_id not in name_set:
                raise ValueError(f"消息 from 端生命线不存在：{m.source_id}")
            if m.target_id not in name_set:
                raise ValueError(f"消息 to 端生命线不存在：{m.target_id}")

        # 片段：边界必须落在真实消息上，且 v1 不允许重叠/嵌套
        ranges: list[tuple[int, int]] = []
        for f in self.fragments:
            if f.start_order not in order_set:
                raise ValueError(f"片段起始顺序号无对应消息：{f.start_order}")
            if f.end_order not in order_set:
                raise ValueError(f"片段结束顺序号无对应消息：{f.end_order}")
            ranges.append((f.start_order, f.end_order))
        ranges.sort()
        for prev, cur in zip(ranges, ranges[1:], strict=False):
            if cur[0] <= prev[1]:
                raise ValueError("暂不支持重叠/嵌套片段（v1 仅单层片段）")
        return self


# ============================================================================
# 部署图模型（C 任务）：节点(设备/执行环境) + 构件 + 部署/通信关系
# ============================================================================

_MAX_DEPLOY_NODES = 30
_MAX_ARTIFACTS = 40
_MAX_DEPLOY_ASSOCIATIONS = 60


class DeployNodeKind(str, Enum):
    """节点类型：物理设备 / 执行环境（容器、K8s 节点等）。"""

    DEVICE = "device"
    EXEC_ENV = "exec_env"


class DeployNode(BaseModel):
    """部署节点：stereotype 用于教学特化（server/k8s/pod/service/deployment/ingress/docker/db）。"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(max_length=_MAX_NAME)
    kind: DeployNodeKind = DeployNodeKind.EXEC_ENV
    stereotype: str = Field(default="", max_length=_MAX_NAME)
    spec: str = Field(default="", max_length=_MAX_LABEL)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v):
        return _normalize_enum(v, _DEPLOY_NODE_KIND_ALIASES)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class DeployArtifact(BaseModel):
    """部署构件：deployed_on 指向所在节点名（可选）。"""

    name: str = Field(max_length=_MAX_NAME)
    deployed_on: str = Field(default="", max_length=_MAX_NAME)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class DeployAssociationKind(str, Enum):
    """部署关系：通信路径 / 依赖 / 普通关联。"""

    COMMUNICATION = "communication"
    DEPENDENCY = "dependency"
    ASSOCIATION = "association"


class DeployAssociation(BaseModel):
    """节点/构件之间的部署关系。"""

    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(alias="from", max_length=_MAX_NAME)
    target_id: str = Field(alias="to", max_length=_MAX_NAME)
    kind: DeployAssociationKind = DeployAssociationKind.COMMUNICATION

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v):
        return _normalize_enum(v, _DEPLOY_ASSOCIATION_ALIASES)

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _reject_blank(v)


class DeploymentModel(BaseModel):
    """部署图中间模型：LLM 生成 → 质检 → 渲染。"""

    type: Literal[DiagramType.DEPLOYMENT] = DiagramType.DEPLOYMENT
    title: str = Field(default="", max_length=_MAX_SYSTEM)
    nodes: list[DeployNode] = Field(default_factory=list, max_length=_MAX_DEPLOY_NODES)
    artifacts: list[DeployArtifact] = Field(default_factory=list, max_length=_MAX_ARTIFACTS)
    associations: list[DeployAssociation] = Field(default_factory=list, max_length=_MAX_DEPLOY_ASSOCIATIONS)

    @model_validator(mode="after")
    def _check_references(self) -> "DeploymentModel":
        node_names = [n.name for n in self.nodes]
        node_set = set(node_names)
        dup_nodes = sorted({n for n in node_names if node_names.count(n) > 1})
        if dup_nodes:
            raise ValueError(f"存在重复的节点名称：{dup_nodes}")

        art_names = [a.name for a in self.artifacts]
        dup_arts = sorted({n for n in art_names if art_names.count(n) > 1})
        if dup_arts:
            raise ValueError(f"存在重复的构件名称：{dup_arts}")
        endpoint_set = node_set | set(art_names)

        for art in self.artifacts:
            if art.deployed_on and art.deployed_on not in node_set:
                raise ValueError(f"构件 {art.name} 部署到不存在的节点：{art.deployed_on}")

        for rel in self.associations:
            if rel.source_id not in endpoint_set:
                raise ValueError(f"部署关系的 from 端不存在：{rel.source_id}")
            if rel.target_id not in endpoint_set:
                raise ValueError(f"部署关系的 to 端不存在：{rel.target_id}")
        return self


# ============================================================================
# 判别分发：按 type 字段把任意模型 dict 解析为具体模型类
# ============================================================================

AnyUmlModel = UseCaseModel | ActivityModel | StateMachineModel | ClassModel | SequenceModel | DeploymentModel


def parse_uml_model(data: dict) -> AnyUmlModel:
    """按 type 字段解析为对应模型实例（用于 chat-adjust / 前端回传的模型校验）。"""
    from pydantic import ValidationError

    dtype = (data or {}).get("type")
    mapping = {
        DiagramType.USECASE.value: UseCaseModel,
        DiagramType.ACTIVITY.value: ActivityModel,
        DiagramType.STATEMACHINE.value: StateMachineModel,
        DiagramType.CLASS.value: ClassModel,
        DiagramType.SEQUENCE.value: SequenceModel,
        DiagramType.DEPLOYMENT.value: DeploymentModel,
    }
    model_cls = mapping.get(dtype)
    if model_cls is None:
        raise ValueError(f"不支持的图类型：{dtype}")
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{dtype} 模型校验失败：{exc}") from exc
