"""UML 图型意图识别 Prompt：用户需求 → 应选图型（路由用）。

用户未显式指定图型时，由 LLM 判断六种图型之一；
识别为 other（组件图等未支持类型）时，上层提示「该图型列入后续版本」。
"""

UML_PROMPT_VERSION = "0.2"

INTENT_SYSTEM_PROMPT = (
    "你是 UML 建模助手的图型路由模块。根据用户的需求描述，判断应生成哪种 UML 图。\n"
    "候选图型：\n"
    "- usecase：关注系统外部参与者与对外提供的业务功能（谁用系统、能做什么）；\n"
    "- activity：关注业务流程的步骤、顺序、分支判断、并行（一件事怎么做、先后的控制流）；\n"
    "- statemachine：关注某个对象在生命周期内的稳定状态与触发状态转换的事件（订单/预警/设备如何变迁）；\n"
    "- class：关注系统内部静态结构——有哪些类/接口、属性与方法、类之间的继承/组合/聚合/依赖关系；\n"
    "- sequence：关注一次交互的时间顺序——哪些对象参与、按先后发送什么消息、同步/异步/返回；\n"
    "- deployment：关注系统如何部署到硬件/运行环境——服务器、容器、K8s 资源、构件与通信路径；\n"
    "- other：组件图、对象图、包图等当前未支持的图型。\n"
    "只输出一个 JSON 对象，不要任何解释或代码围栏以外的文字。"
)

INTENT_USER_TMPL = (
    "请判断以下需求描述最适宜生成哪种 UML 图。\n"
    "需求描述：\n{requirement}\n\n"
    "输出 JSON 格式：\n"
    "{{\n"
    '  "type": "usecase | activity | statemachine | class | sequence | deployment | other",\n'
    '  "reason": "一句话判断理由"\n'
    "}}"
)
