"""通用结构化输出工具：LLM 调用 → JSON 提取 → Pydantic 校验 → 重试 → 统一异常。

PPT / 教案 / UML 共用这一套，避免各链路复制解析与重试逻辑。

设计约束：
- 不在 import 阶段调用 LLM（工厂延迟到调用时解析）；
- 可注入 Fake LLM 便于测试（llm_factory 参数，见 LLMFactory 协议）；
- 重试覆盖两层失败：API 层（平台偶发 5xx/超时）与结构层（JSON/校验）；
- 统一抛 StructuredOutputError，不向调用方泄露原始异常类型差异；
- 不使用 eval/exec。

⚠️ 安全约定：StructuredOutputError 的字符串包含最后一次底层异常文本
（可能含上游地址/供应商错误详情），**仅用于日志与服务端排查**；
HTTP API 层不得把该异常字符串直接作为客户端响应，应映射为固定错误码。
"""

import json
import logging
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ```json ... ``` 围栏（优先）
_FENCED_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class LLMResponse(Protocol):
    """最小 LLM 响应协议（langchain AIMessage 与测试 Fake 均满足）。"""

    content: str


class LLMClient(Protocol):
    """最小 LLM 客户端协议。"""

    def invoke(self, messages: list) -> LLMResponse: ...


class LLMFactory(Protocol):
    """LLM 工厂协议：可选 timeout 参数，返回客户端实例。"""

    def __call__(self, timeout: float | None = None) -> LLMClient: ...


class StructuredOutputError(RuntimeError):
    """结构化输出最终失败（重试耗尽）：携带模型类名与最后一次错误。

    ⚠️ 异常文本含底层异常细节，仅限服务端日志使用，见模块 docstring 安全约定。
    """

    def __init__(self, model_name: str, last_error: Exception, attempts: int) -> None:
        self.model_name = model_name
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"{model_name} 结构化生成失败（尝试 {attempts} 次）：{last_error}")


def _balanced_json(text: str) -> dict:
    """扫描第一个大括号平衡的 JSON 对象（正确跳过字符串内的大括号/引号）。

    相比贪婪正则 r"\\{.*\\}"，不会把多个 JSON 或前后解释文字一并截入。
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
        # 该起点无法形成平衡对象，尝试下一个 "{"
        start = text.find("{", start + 1)
    raise ValueError("输出中未找到 JSON 对象")


def extract_json(text: str) -> dict:
    """从模型输出提取 JSON：优先 ```json 围栏，其次平衡大括号扫描。"""
    fenced = _FENCED_RE.search(text)
    if fenced:
        return json.loads(fenced.group(1))
    return _balanced_json(text)


def default_llm_factory(timeout: float | None = None):
    """默认 LLM 工厂：延迟导入，避免 import 阶段触发配置加载副作用。"""
    from app.models.llm import get_llm

    return get_llm(timeout=timeout)


def invoke_structured(
    messages: list,
    model_cls: type[T],
    *,
    llm_factory: LLMFactory | None = None,
    retries: int = 1,
    timeout: float | None = None,
    feedback_on_parse_error: bool = True,
) -> T:
    """调用 LLM 并解析为 pydantic 模型；失败重试，最终抛 StructuredOutputError。

    Args:
        messages: (role, content) 消息列表。
        model_cls: 目标 pydantic 模型。
        llm_factory: 可注入的 LLM 工厂（测试传 Fake）；缺省用项目工厂。
        retries: 额外重试次数（总调用 = 1 + retries）。
        timeout: 单请求超时（秒）；None 用工厂默认。
        feedback_on_parse_error: 结构层失败时是否把错误反馈追加进重试消息。

    Returns:
        model_cls 实例。
    """
    factory = llm_factory or default_llm_factory
    llm = factory(timeout=timeout) if _accepts_timeout(factory) else factory()
    last_error: Exception | None = None
    feedback: list = []
    attempts = 1 + max(0, retries)
    for attempt in range(1, attempts + 1):
        try:
            raw = str(llm.invoke(messages + feedback).content)
            return model_cls.model_validate(extract_json(raw))
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if feedback_on_parse_error:
                feedback = [("user", "上次输出解析失败：" + str(exc)[:300] + "。请重新严格只输出符合要求的 JSON。")]
            logger.warning("第 %d/%d 次结构化解析失败（%s）：%s", attempt, attempts, model_cls.__name__, str(exc)[:120])
        except Exception as exc:  # noqa: BLE001 - API 层失败同样重试（平台偶发 5xx/网关超时）
            last_error = exc
            feedback = []
            logger.warning("第 %d/%d 次 API 调用失败（%s）：%s", attempt, attempts, model_cls.__name__, str(exc)[:120])
    raise StructuredOutputError(model_cls.__name__, last_error or ValueError("未知错误"), attempts)


def _accepts_timeout(factory: LLMFactory) -> bool:
    """判断工厂是否接受 timeout 关键字（Fake 工厂可能只有无参签名）。"""
    import inspect

    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return True
    return "timeout" in sig.parameters
