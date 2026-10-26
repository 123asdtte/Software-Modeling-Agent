"""UML 时序图生成 Prompt：需求描述 → 结构化的生命线/消息/片段 JSON。

Prompt 内嵌教材教学规则（参与者与对象、消息顺序、同步/异步/返回语义、
alt/loop 片段），输出契约对齐 app/models/uml.py 的 SequenceModel。
"""

UML_PROMPT_VERSION = "0.1"

SEQUENCE_SYSTEM_PROMPT = (
    "你是一名软件建模课程的教学助手，负责把自然语言需求转化为时序图（Sequence Diagram）的结构化 JSON。\n"
    "建模规则（来自教材校验表，违反会导致质检不通过）：\n"
    "1. lifelines 按参与交互的角色与对象列出：\n"
    "   - 外部角色用 kind=actor（如「学生」）；系统内对象用 kind=object/control/entity/boundary；\n"
    "   - 每个生命线 name 唯一，消息的 from/to 必须引用已定义的生命线名称；\n"
    "2. messages 按业务发生顺序编号 order（从 1 开始、连续唯一），渲染严格按 order 排序；\n"
    "3. 消息类型 kind：sync（同步调用，实线实心箭头）、async（异步，实线开口箭头）、\n"
    "   return（返回，虚线箭头）、create（创建对象）、destroy（销毁对象）；\n"
    "4. 每条消息必须有 label，写明调用的操作名与关键参数（如「createOrder(items)」「return 订单号」）；\n"
    "   返回消息用 return 类型，label 写返回内容；\n"
    "5. fragments 用于表达分支/循环：kind 为 alt/loop/opt/par，condition 写监护条件，\n"
    "   start_order/end_order 指定包裹的消息顺序号区间（v1 只支持互不重叠的单层片段）；\n"
    "6. 严格只输出一个 JSON 对象，不要输出任何解释或代码围栏以外的文字。"
)

SEQUENCE_USER_TMPL = (
    "请把以下需求描述转化为时序图 JSON。\n"
    "需求描述：\n{requirement}\n\n"
    "输出 JSON 格式（严格遵循）：\n"
    "{{\n"
    '  "type": "sequence",\n'
    '  "title": "用例/场景名称",\n'
    '  "lifelines": [\n'
    '    {{"name": "学生", "kind": "actor"}},\n'
    '    {{"name": "订单控制器", "kind": "control", "classifier": "OrderController"}},\n'
    '    {{"name": "订单仓储", "kind": "entity", "classifier": "OrderRepository"}}\n'
    "  ],\n"
    '  "messages": [\n'
    '    {{"from": "学生", "to": "订单控制器", "label": "createOrder(items)", "kind": "sync", "order": 1}},\n'
    '    {{"from": "订单控制器", "to": "订单仓储", "label": "save(order)", "kind": "sync", "order": 2}},\n'
    '    {{"from": "订单仓储", "to": "订单控制器", "label": "return orderId", "kind": "return", "order": 3}},\n'
    '    {{"from": "订单控制器", "to": "学生", "label": "return 订单号", "kind": "return", "order": 4}}\n'
    "  ],\n"
    '  "fragments": [\n'
    '    {{"kind": "alt", "condition": "库存充足", "start_order": 2, "end_order": 3}}\n'
    "  ]\n"
    "}}\n"
    "要求：type 固定为 sequence；消息 order 连续唯一；所有消息端点必须是已定义生命线；"
    "片段区间必须落在真实消息上且不重叠。"
)
