# UML 图型扩展实施方案（C 任务）

> **状态：✅ 已全部实现并通过测试（2026-10-26）**
> 落地结果：类图 / 时序图 / 部署图 三图型 + 类图→Java 骨架代码全部可用；完整测试 **528 passed, 3 skipped**，覆盖率 **88%**；真实 LLM 端到端验证见第 12 节。
> 导出能力：**draw.io 已覆盖全部 6 种图型**（`drawio_renderer.py` 三新增渲染器 + `/generate` 分发登记），SVG 仍仅用例图有自绘渲染器——这是设计取舍，不是缺失。

> 目标：补齐课程模块二/三/四 在平台上**无法跑通**的图型能力，让《软件建模智能体平台》能真正支撑配套教材的三个 AI 建模素养专题。
> 范围：新增 **类图(class) / 时序图(sequence) / 部署图(deployment)** 三种图型，外加 **类图→Java 代码框架** 生成能力。
> 约束：严格复用现有 UML 链路的"8 层模式"，不另起炉灶；LLM 只产结构化 JSON，PlantUML 由确定性渲染器生成（与现有用例图/活动图/状态机图一致）。

---

## 1. 背景：课程要求 vs 平台现状

| 课程模块 | 要求学生生成的图型/活动 | 平台现状 |
|---|---|---|
| 模块二·需求与结构(A) | 类图"人 vs 智能体"对决、类图错误诊断 | ❌ 类图未实现 |
| 模块三·行为/动态(B) | 活动图(✅)、状态可达性(✅)、**时序图接口约定精细化** | ❌ 时序图未实现 |
| 模块四·架构/实现(C) | **部署图(K8s)**、**类图→Java 代码框架**、约束施加 | ❌ 部署图/代码生成未实现 |

结论：**模块二活动一、模块三活动三、模块四全部** 当前缺对应能力，是课程在平台落地的硬阻塞。C 任务即地基。

---

## 2. 既有 UML 架构模式（必须复用，不要重写）

每个图型落地都遵循同一套 8 个挂点（以"用例图"为参考样板）：

| # | 层 | 文件 | 现有样板（用例图） |
|---|---|---|---|
| 1 | 数据契约 | `app/models/uml.py` | `UseCaseModel` + `DiagramType.USECASE` + 引用/唯一性校验 |
| 2 | 提示词 | `app/prompts/uml_X_prompt.py` | `USECASE_SYSTEM_PROMPT` + `USECASE_USER_TMPL` |
| 3 | 规则引擎 | `app/rules/X_rules.py` | `check_usecase_model(model) -> ReviewReport` |
| 4 | 渲染器 | `app/renderers/plantuml.py` | `render_usecase_plantuml` + `_STYLE_BY_TYPE` + `render_uml_plantuml` 分发 |
| 5 | 生成链 | `app/chains/uml_chain.py` | `generate_usecase_model` + `generate_uml_model` 分发 + `detect_diagram_type` |
| 6 | 修正链 | `app/chains/uml_adjust.py` | `_ADJUST_RULES` + `_CHECKERS` 两处字典登记 |
| 7 | HTTP 接口 | `app/api/uml.py` | `UmlGenerateRequest` Literal、`check_uml_model`、`parse_uml_model`、`/render` Literal、`chat-adjust` 的 `model_cls` 映射 |
| 8 | 测试 | `tests/` | `test_uml_*.py`（模型/渲染/规则/链/接口/修正 6 类） |

**关键复用事实（已读源码确认）：**
- `render_uml_plantuml(model)` 按 `isinstance` 分发；`inject_skin` 按 `DiagramType` 注入教学配色；新图型只需在 `plantuml.py` 加 `render_X_plantuml` 并登记两处，PNG 渲染自动可用。
- `detect_diagram_type` 当前把类图/时序图识别为 `other` 并抛 `ValueError`（接口已提示"后续版本"）——本次把它纳入 `IntentResult.type` 与 `mapping`，并更新 `/generate` 的 422 文案。
- `app/api/uml.py` 的 drawio/svg 导出对未登记图型**自动跳过**（不报错）。本次已把 drawio 分发登记补齐到 6 图型；svg 仍只登记用例图（无自绘渲染器时不伪造）。
- `llm_factory` 注入机制已就绪（`generate_X_model(..., llm_factory=)`），测试可用 FakeLLM，无需真实 key。

---

## 3. 统一改动清单（共享文件，每图型都要改）

以下文件需为 **class / sequence / deployment** 三图型各登记一次：

1. `app/models/uml.py`
   - `DiagramType` 枚举新增 `CLASS="class"` / `SEQUENCE="sequence"` / `DEPLOYMENT="deployment"`
   - 新增 `ClassModel` / `SequenceModel` / `DeploymentModel`（含各自字段与 `model_validator` 引用/唯一性校验）
   - `parse_uml_model` 的 `mapping` 加三项
2. `app/chains/uml_chain.py`
   - 新增 `generate_class_model` / `generate_sequence_model` / `generate_deployment_model`
   - `generate_uml_model` 分发加三分支
   - `detect_diagram_type` 的 `IntentResult.type` 描述与 `mapping` 加三图型
3. `app/rules/`
   - 新增 `class_rules.py` / `sequence_rules.py` / `deployment_rules.py`，各导出 `check_X_model`
4. `app/renderers/plantuml.py`
   - 新增 `render_class_plantuml` / `render_sequence_plantuml` / `render_deployment_plantuml`
   - `_STYLE_BY_TYPE` 加三图型配色
   - `render_uml_plantuml` 分发加三分支
5. `app/chains/uml_adjust.py`
   - `_ADJUST_RULES` 加三图型修正规则（对齐各自规则引擎约束）
   - `_CHECKERS` 加三项
6. `app/api/uml.py`
   - `UmlGenerateRequest.diagram_type` Literal 加 `class`/`sequence`/`deployment`
   - `UmlRenderRequest.diagram_type` Literal 加三项
   - `check_uml_model` 分发加三分支
   - `chat-adjust` 的 `model_cls` 字典加三项
   - 更新 auto 模式 422 文案（移除"类图/时序图"提示，或改为"更多图型研发中"）
7. `app/prompts/`
   - 新增 `uml_class_prompt.py` / `uml_sequence_prompt.py` / `uml_deployment_prompt.py`
8. `tests/`
   - 每图型 6 类测试（模型校验 / 渲染确定性 / 规则 / 链+FakeLLM / 接口 / 修正）
   - `test_uml_chain.py` 的意图识别测试加三图型用例

---

## 4. 三类图数据契约设计（重点，类图最复杂）

### 4.1 类图 `ClassModel`（工作量 L，最高优先级先做）

```python
class Visibility(str, Enum):   # UML 可见性
    PUBLIC = "+"; PRIVATE = "-"; PROTECTED = "#"; PACKAGE = "~"

class UmlAttribute(BaseModel):       # 属性 + 方法参数可复用
    name: str
    type: str = ""
    visibility: Visibility = PUBLIC
    is_static: bool = False

class UmlMethod(BaseModel):
    name: str
    params: list[UmlAttribute] = []   # 复用 UmlAttribute 表示 名称:类型
    return_type: str = "void"
    visibility: Visibility = PUBLIC
    is_static: bool = False
    is_abstract: bool = False

class ClassItem(BaseModel):
    name: str                          # 类/接口名
    attributes: list[UmlAttribute] = []
    methods: list[UmlMethod] = []
    is_abstract: bool = False
    is_interface: bool = False

class ClassRelationType(str, Enum):
    ASSOCIATION = "association"; AGGREGATION = "aggregation"
    COMPOSITION = "composition"; GENERALIZATION = "generalization"
    DEPENDENCY = "dependency"; REALIZATION = "realization"

class ClassRelation(BaseModel):
    type: ClassRelationType
    source_id: str = Field(alias="from")     # 复用 from/to alias 约定
    target_id: str = Field(alias="to")
    label: str = ""
    source_multiplicity: str = ""            # 例 "1" / "0..*"
    target_multiplicity: str = ""

class ClassModel(BaseModel):
    type: Literal["class"] = "class"
    title: str = ""
    classes: list[ClassItem] = Field(max_length=40)
    relations: list[ClassRelation] = Field(max_length=80)
    # model_validator: 类名唯一、relation 端点存在、realization 的 target 必为 interface
```

**渲染要点（PlantUML class 语法）：** 类名含空格/特殊字符 → 用 `class_N` alias；属性/方法按 `可见性 名称: 类型` 格式化；关系箭头：泛化 `<|--`、组合 `*--`、聚合 `o--`、依赖 `<..`、实现 `<|..`；多重性标在端点。

### 4.2 时序图 `SequenceModel`（工作量 M，渲染最 tricky）

```python
class LifelineKind(str, Enum):
    ACTOR = "actor"; OBJECT = "object"; BOUNDARY = "boundary"; CONTROL = "control"

class Lifeline(BaseModel):
    name: str
    kind: LifelineKind = OBJECT
    classifier: str = ""          # 如 "OrderController"

class MessageKind(str, Enum):
    SYNC = "sync"; ASYNC = "async"; RETURN = "return"; CREATE = "create"; DESTROY = "destroy"

class Message(BaseModel):
    source_id: str = Field(alias="from")
    target_id: str = Field(alias="to")
    label: str = ""
    kind: MessageKind = SYNC
    order: int                     # 全局顺序号，渲染按 order 排序

class Fragment(BaseModel):         # alt / loop / opt 包裹一段连续 message
    kind: Literal["alt", "loop", "opt", "par"] = "alt"
    condition: str = ""
    start_order: int
    end_order: int

class SequenceModel(BaseModel):
    type: Literal["sequence"] = "sequence"
    title: str = ""
    lifelines: list[Lifeline] = Field(max_length=20)
    messages: list[Message] = Field(max_length=120)
    fragments: list[Fragment] = Field(default_factory=list)
    # model_validator: lifeline 名唯一、message 端点存在、order 连续无重复
```

**渲染要点：** 按 `order` 排序输出 `l_from -> l_to : label`；`async` 用 `-->>`，`return` 用 `-->`，`create` 用 `++`；Fragment 按 `start_order..end_order` 把消息包进 `alt cond ... end` / `loop ... end`。**v1 先支持单层 alt/loop，嵌套 fragment 留 v2**（复杂度高，且课程只要求"接口约定精细化"，单层足够）。

### 4.3 部署图 `DeploymentModel`（工作量 M，含 K8s 教学特化）

```python
class NodeKind(str, Enum):
    DEVICE = "device"; EXEC_ENV = "exec_env"   # 设备 / 执行环境(节点/容器)

class DeployNode(BaseModel):
    name: str
    kind: NodeKind = EXEC_ENV
    stereotype: str = ""            # 教学特化：可填 k8s/pod/service/deployment/ingress/docker/server/db
    spec: str = ""                  # 自由文本规格（CPU/内存/副本数）

class Artifact(BaseModel):
    name: str                       # 如 "order-service.jar"
    deployed_on: str = ""           # 部署到的节点名

class DeployAssociation(BaseModel):
    source_id: str = Field(alias="from")
    target_id: str = Field(alias="to")
    kind: Literal["communication", "dependency", "association"] = "communication"

class DeploymentModel(BaseModel):
    type: Literal["deployment"] = "deployment"
    title: str = ""
    nodes: list[DeployNode] = Field(max_length=30)
    artifacts: list[Artifact] = Field(default_factory=list)
    associations: list[DeployAssociation] = Field(default_factory=list)
    # model_validator: 节点名唯一、association/artifact 端点存在
```

**渲染要点：** `node "X" as n_1 <<stereotype>>`；构件 `artifact "Y" as a_1`；关联 `n_1 -- n_2`。**K8s 校验（DEP-K8S）** 为教学新增规则：当 stereotype 含 `service`/`deployment` 时，提示应配套 `pod` 与 `ingress` 形成可达链路（对齐模块四"部署故障场景验证"）。

---

## 5. 类图→Java 代码框架（额外能力，确定性生成，无 LLM）

- 新增 `app/chains/class_to_code.py`：`class_model_to_java(model: ClassModel) -> dict[str, str]`（文件名 → 源码）。
- 纯模板拼接：包声明（可配置默认包 `com.example`）、`class`/`interface`/`abstract` 头、字段、方法桩（抽象方法无体、其余空 `{}`）、关系映射为字段引用（组合/聚合 → 成员字段，依赖 → 注释）。
- 新增接口 `POST /v1/uml/class-code`，请求 `{ model: dict }`，响应 `{ files: { "Student.java": "...", ... } }`。
- 不走 LLM、不耗 token，与生成链路解耦，可独立测试。

---

## 6. 渲染与质检策略

| 图型 | PNG(PlantUML/Java) | drawio | 质检规则组 |
|---|---|---|---|
| 类图 | ✅ Phase 1 | ✅ 已实现（`render_class_drawio`：类框分区 + 菱形/三角箭头 + 两端多重性） | CL-DUP / CL-REF / CL-CYC(循环继承) / CL-REAL(实现必须接口) / CL-V1(可见性缺失) |
| 时序图 | ✅ Phase 1 | ✅ 已实现（`render_sequence_drawio`：umlLifeline + 顺序化消息边 + alt/loop/opt/par 框） | SQ-REF(端点) / SQ-ORD(顺序) / SQ-ASYNC(异步无返回) / SQ-FRAG(fragment 闭合) |
| 部署图 | ✅ Phase 1 | ✅ 已实现（`render_deployment_drawio`：cube 节点 + document 构件 + 通信/依赖边） | DEP-REF / DEP-DUP / DEP-K8S(K8s 链路) / DEP-UNDEP(构件未部署) |
| 类图→Java | 文本输出 | — | 生成正确性由单元测试覆盖（非 ReviewReport） |

质检规则一律对齐课程验证表（模块 A/B/C 的 A-1~A-5 / B-1~B-6 / C-1~C-3），`table_ref` 字段回填表号以便学生溯源。

---

## 7. 意图识别与接口改动聚合

- `app/prompts/uml_intent_prompt.py`：`INTENT_USER_TMPL` 把 `type` 取值扩为 `usecase/activity/statemachine/class/sequence/deployment/other`；`detect_diagram_type` 的 `mapping` 同步加三项。
- `UmlGenerateRequest` / `UmlRenderRequest` 的 `diagram_type` Literal 加 `class`/`sequence`/`deployment`。
- `chat-adjust` 的 `model_cls` 字典加三图型；`/render` 支持三图型源码重绘（安全加固 `!include` 拒绝已就位）。
- auto 模式 422 文案从"类图/时序图等未支持"改为"暂未支持的图型"。

---

## 8. 测试计划（每图型 6 类，沿用 FakeLLM）

- **模型层**：唯一性/引用/类型校验（合法用例通过、非法用例抛 `ValueError`）。
- **渲染层**：固定输入 → 固定 PlantUML 字符串（确定性断言）。
- **规则层**：构造含典型缺陷的模型 → 断言对应 rule_id/level 命中。
- **链层**：注入 `llm_factory=FakeLLM` → 断言返回具体模型实例；`detect_diagram_type` 三图型识别用例。
- **接口层**：`TestClient` 直接调 `routes`（绕过 portal 启动，沿用现有 `api_deps` fixture）→ 断言 200 + 响应结构。
- **修正层**：`adjust_uml_model` 三图型 + 防御（type 被改拒绝）。
- 跑法：沿用 `run_all_tests.py`（`-q` + unbuffered + in-process），避免 Windows 多进程通信卡顿。

---

## 9. 阶段拆解（建议顺序）

| 阶段 | 内容 | 产出 | 相对工作量 |
|---|---|---|---|
| **Phase 1** | 类图：模型+提示词+规则+渲染+链+意图+接口+修正+测试 | 类图端到端贯通（含 `/generate`/`/render`/`chat-adjust`） | L（最大，先做地基） |
| **Phase 2** | 时序图：同上 8 层 + 单层 alt/loop 渲染 | 时序图端到端（v1 单层 fragment） | M |
| **Phase 3** | 部署图 + K8s 教学校验规则 | 部署图端到端 | M |
| **Phase 4** | 类图→Java 代码框架 + `/v1/uml/class-code` | 代码生成能力 | S |
| **Phase 5** | ① ✅ 三图型 drawio 导出（svg 仅用例图，设计取舍）② ✅ 前端 `static/uml.html` 三图型选项卡/输入引导/KPI/要素清单/Java 面板 ③ ✅ README 能力状态表刷新 ④ ✅ 全量测试回归（528 passed） | 课程三模块可在平台完整跑通 | M |

> 说明：Phase 1 先做类图，因为它同时服务模块二(类图对决)与模块四(类图→代码)，复用价值最高；且其数据契约最复杂，先啃下来后续两图型是降维。

---

## 10. 风险与待确认（C1，未臆测，需你拍板）

1. **类图循环继承检测（CL-CYC）**：需在规则引擎建有向图做 DFS，工作量可控但要写单测覆盖；是否纳入 Phase 1 还是先 warning 后 error？→ 建议 Phase 1 直接 error。
2. **时序图嵌套 fragment（alt 内再 alt/loop）**：v1 只做单层，嵌套留 v2。是否接受 v1 限制？→ 默认接受（课程只要求接口约定）。
3. **部署图 K8s 特化深度**：stereotype 是否预置 `pod/service/deployment/ingress` 标准集？→ 建议预置，对齐模块四。
4. **`max_tokens=16384`**：类图/时序图 JSON 可能偏大（数十节点），当前上限应够但需 Phase 1 实测一次超复杂图；若报错下调到 8192。
5. **前端 `uml.html` 改造（Phase 5）**：现有前端只引导用例图/活动图/状态机图，三图型需新增交互引导（如类图字段编辑、时序图消息列表）。需前端工作量，是否纳入本次还是另开前端任务？
6. **与 P1 的关系**：本方案（C）是 **P1（43 互动点练习-批改闭环）的前置依赖**——P1 的"AI 先出题→学生建模→AI 批改"必须建立在图型能力之上。建议 C 完成后再做 P1。

---

## 11. 验收标准（Definition of Done）

- `POST /v1/uml/generate {diagram_type: "class"|"sequence"|"deployment"}` 返回合法模型 + PlantUML + 质检报告，PNG 可下载。
- `POST /v1/uml/render` 支持三图型源码重绘（不含 `!include`）。
- `POST /v1/uml/chat-adjust` 三图型均可对话修正并重新质检。
- `POST /v1/uml/class-code` 返回 `files` 字典，Java 源码可编译级正确（字段/方法签名正确）。
- 三图型全量测试通过；README 能力状态表刷新；模块二/三/四 可在平台完整演示。

---

## 12. 实施结果（2026-10-26 实测记录）

### 12.1 代码落点

| 层 | 新增/改动 |
|---|---|
| 数据契约 | `app/models/uml.py`：`DiagramType` +3；`ClassModel` / `SequenceModel` / `DeploymentModel` 及全部子模型；`AnyUmlModel` 联合类型 |
| 提示词 | `app/prompts/uml_class_prompt.py` / `uml_sequence_prompt.py` / `uml_deployment_prompt.py`；`uml_intent_prompt.py` 扩到 7 类意图 |
| 规则引擎 | `app/rules/class_rules.py`（CL-DUP/REF/REAL/CYC/MULTI/V1/ABS/EMPTY/IFACE）、`sequence_rules.py`（SQ-EMPTY/REF/LABEL/ORD/FRAG）、`deployment_rules.py`（DEP-EMPTY/DUP/REF/UNDEP/K8S） |
| 渲染器 | `app/renderers/plantuml.py`：`render_class_plantuml` / `render_sequence_plantuml` / `render_deployment_plantuml` + 三套 skinparam + 分发 |
| 生成/修正链 | `app/chains/uml_chain.py`（3 个 `_generate_*_sync` + 分发 + 意图映射）、`app/chains/uml_adjust.py`（`_ADJUST_RULES` / `_CHECKERS` 双字典） |
| 正向工程 | `app/chains/class_to_code.py`（确定性 Java 骨架，含标识符净化、可见性映射、extends/implements 推导） |
| HTTP | `app/api/uml.py`：`/generate` Literal 扩到 7、`check_uml_model` 6 路分发、`/render` 6 图型、`chat-adjust` 6 映射、新增 `POST /v1/uml/class-code` |
| 前端 | `static/uml.html`（3 个图型选项 + 3 个示例 + KPI 第三卡 subtext 补 id + Java 面板）；`static/js/uml.js`（KPI/画布标题/要素清单 3 套渲染、Copilot 指令按图型切换、Java 面板调用、undo 图型修正、可见性符号修正） |
| 测试 | `test_class_models.py` / `test_sequence_deployment_models.py` / `test_new_diagram_rules.py` / `test_new_diagram_renderer.py` / `test_new_diagram_chain_api.py` / `test_class_to_code.py` |

### 12.2 测试与验证

- 全量单测：**528 passed, 3 skipped**（含新增 3 图型模型/规则/渲染/链/接口/正向工程用例；原有用例零回归）。
- 真实 LLM（spark-x2.6，8101 实例）三图型端到端：
  - 类图：7 类 / 7 关系 / 0 违规 / PNG 82KB；Java 7 个文件（`Student extends User implements Enrollable` 推导正确）。
  - 时序图：3 生命线 / 7 消息 / 2 片段 / 0 违规 / PNG 19KB。
  - 部署图：9 节点 / 4 构件 / 13 关系 / 0 违规 / PNG 29KB。
  - `chat-adjust` 三图型均 200；非法包名 / 空类图 / 非 class 模型均 422。
- **端到端发现并修复的 2 个真实缺陷**：
  1. 部署图原用 PlantUML 不存在的 `device` 关键字，导致 PNG 渲染静默降级为 `source_only`。现统一 `node "x" as n <<device>>`，并补 `test_deployment_never_emits_device_keyword` 回归防线。
  2. 需求与所选图型不匹配时 LLM 会返回空模型，平台仍渲染出「只有标题」的 180×54 图片且质检 0 违规（假成功）。现 `/generate` 增加空模型兜底 → 422「未能从需求中提取到任何模型元素…」，并补 3 条单测。
- 浏览器级端到端（Edge + Playwright，`/uml.html`）：图型下拉 6 项齐全、类图生成后 KPI 4 张卡文案正确、PNG 真实加载、要素清单双表、Java 面板生成 6 个文件并可展开/下载、切到部署图后 Java 面板自动隐藏、部署图 566×787 正常出图、Copilot 快捷指令按图型切换、控制台无 JS 报错。

### 12.3 draw.io 导出补齐（2026-10-26 追加，原 Phase 2 已完成）

> 触发原因：用户反馈「选了 draw.io 引擎，拿到的还是 PlantUML 代码」。定位为 `app/api/uml.py` 的 `_drawio_dispatch` 只登记了 3 个旧图型，新图型 `drawio_url` 恒为 `None`，前端只能回落 PlantUML 源码。

- 新增 `render_class_drawio` / `render_sequence_drawio` / `render_deployment_drawio`（`app/renderers/drawio_renderer.py`），沿用「确定性坐标 + 唯一 id + XML 转义」同一约束。
- `_drawio_dispatch` 由 3 项扩到 6 项；`/generate` 返回的 `drawio_download_url` 对六图型均非空。
- 修复前端时序缺陷：XML 是异步 `fetch` 拿到的，首次渲染时源码为空导致下载按钮被隐藏且不再恢复。抽出 `refreshDrawioDownloadBtn(xmlSrc, nameHint)`，在 fetch 回填后重新同步。
- 测试：`test_drawio_renderer.py` 新增 30 条（结构/箭头/片段/转义/空模型/确定性）；`test_new_diagram_chain_api.py` 新增参数化 3 条（下载链接可访问且为合法 mxfile）。合计 **528 passed, 3 skipped**。
- 浏览器级：类图 11/11、时序图 + 部署图 12/12，均断言「源码面板为 `<mxfile>`、viewer 渲染出 SVG、下载按钮为 .xml」。

### 12.4 演示前全链路复测发现的缺陷：LLM 枚举措辞不容错（2026-10-26 追加）

> 触发原因：用 `demo_regression.py` 按老师会看到的顺序跑六图型 + 问答 + PPT/教案，
> **类图返回 502**（其余 8 项全部通过）。

**根因**（服务端日志确认，不是偶发）：

```
第 1/2 次结构化解析失败（ClassModel）：1 validation error for ClassModel
relations.5.type
  Input should be 'association', 'aggregation', 'composition', 'gener...
第 2/2 次结构化解析失败（ClassModel）：输出中未找到 JSON 对象
```

LLM 把泛化写成 `inheritance`、把实现写成 `implements`，不在 `ClassRelationType`
枚举内 → Pydantic 校验失败 → 重试拼接的反馈消息反而让第二次连 JSON 都没给出 → 502。
同类风险也存在于可见性（模型写 `public`，枚举值是 `+`）、消息类型、节点类型等。

**修复**（`app/models/uml.py`，模型层同义归一，不依赖模型听话）：

- 新增 `_normalize_enum(value, aliases)` + 6 张别名表：类关系、可见性、生命线类型、
  消息类型、片段类型、部署节点/关系类型。
- 七个字段加 `field_validator(..., mode="before")`，在枚举校验前完成归一。
- **两个边界**（都由测试锁死）：
  1. 符号型枚举（`+ - # ~`）不能走空格/连字符替换，否则 `-` 会变成 `_` —— 单字符非字母数字直接原样返回；
  2. 归一后仍需拒绝未知值（如 `wat`），否则错误模型会流进渲染层。只做同义映射，不做语义猜测。
- 测试：新增 `tests/test_enum_tolerance.py`（82 条，参数化覆盖中英文/大小写/空格变体 + 否定用例 +
  「真实失败输入的完整模型复现」）。

**复测结果**（同一请求，修复后）：

- 类图成功：5 类 / 4 关系 / 质检 0 违规 / PNG 22.6KB / drawio 8.1KB，耗时 107.5s；
- Java 骨架 5 文件：`public class Student extends User implements Enrollable`、
  `public abstract class User`、`public interface Enrollable` 推导全部正确。

**附带修复**：前端 UML 按钮原写死「生成中…（约 30 秒）」，但类图实测 90–110 秒，演示时像卡死。
现改为按图型给预期值并每秒刷新「已用 / 约需」；`resources.html` 的 PPT 提示同步改为「约 1~2 分钟」。

### 12.5 仍未覆盖

- SVG 导出仍仅用例图（其余图型无自绘 SVG 渲染器，`svg_download_url` 保持 null，不伪造）。
- 时序图嵌套/重叠片段（模型层显式拒绝，v1 只支持单层）。
- 部署图节点嵌套（K8s 集群 → Pod 的层级目前平铺表达）。

