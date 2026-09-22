"""app.core.structured_output 单元测试（全部注入 Fake LLM，不调真实 API）。"""

import pytest
from pydantic import BaseModel, Field

from app.core.structured_output import (
    StructuredOutputError,
    _balanced_json,
    extract_json,
    invoke_structured,
)


class _Out(BaseModel):
    name: str
    count: int = Field(ge=0)


class _FakeLLM:
    """按预设序列返回 content 的假 LLM（记录调用次数）。"""

    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        idx = min(self.calls - 1, len(self.contents) - 1)
        return type("M", (), {"content": self.contents[idx]})()


def _factory(llm: _FakeLLM):
    return lambda timeout=None: llm


# ---------------- extract_json ----------------


def test_extract_json_plain():
    """纯 JSON 文本直接解析。"""
    assert extract_json('{"name": "a"}') == {"name": "a"}


def test_extract_json_fenced():
    """```json 围栏优先剥离。"""
    text = '说明\n```json\n{"name": "a"}\n```\n结尾'
    assert extract_json(text) == {"name": "a"}


def test_extract_json_with_surrounding_text():
    """前后带杂文时取首个平衡对象。"""
    text = '回答如下：{"name": "a", "note": "包含 } 花括号"} 完毕'
    assert extract_json(text)["name"] == "a"


def test_extract_json_string_with_braces():
    """字符串内部的大括号不破坏平衡扫描（对比贪婪正则会截错）。"""
    text = '{"name": "a", "tpl": "{{x}}"} 尾部 {"other": true}'
    data = extract_json(text)
    assert data == {"name": "a", "tpl": "{{x}}"}


def test_extract_json_no_object():
    """无 JSON 时报 ValueError。"""
    with pytest.raises(ValueError):
        extract_json("完全没有结构化内容")


def test_balanced_json_skips_broken_prefix():
    """首个 { 无法平衡时继续向后扫描。"""
    text = '破碎 {"a": 前缀 {"name": "ok"}'
    assert _balanced_json(text) == {"name": "ok"}


# ---------------- invoke_structured ----------------


def test_invoke_success_first_try():
    """首次即返回合法结构，不重试。"""
    llm = _FakeLLM(['{"name": "a", "count": 1}'])
    out = invoke_structured([("user", "x")], _Out, llm_factory=_factory(llm))
    assert out.name == "a"
    assert llm.calls == 1


def test_invoke_retries_on_parse_error():
    """结构层失败重试一次后成功，且反馈消息追加。"""
    llm = _FakeLLM(["不是 JSON", '{"name": "a", "count": 0}'])
    out = invoke_structured([("user", "x")], _Out, llm_factory=_factory(llm))
    assert out.name == "a"
    assert llm.calls == 2


def test_invoke_retries_on_api_error():
    """API 层异常（平台偶发 5xx）同样触发重试。"""
    llm = _FakeLLM(['{"name": "a", "count": 1}'])

    class _Flaky:
        def invoke(self, messages):
            llm.calls += 1
            if llm.calls == 1:
                raise RuntimeError("504 Gateway Time-out")
            return type("M", (), {"content": llm.contents[0]})()

    out = invoke_structured([("user", "x")], _Out, llm_factory=lambda timeout=None: _Flaky())
    assert out.count == 1


def test_invoke_raises_structured_error_when_exhausted():
    """重试耗尽抛 StructuredOutputError（携带尝试次数）。"""
    llm = _FakeLLM(["坏输出"])
    with pytest.raises(StructuredOutputError) as ei:
        invoke_structured([("user", "x")], _Out, llm_factory=_factory(llm))
    assert ei.value.attempts == 2  # 1 + 1 次重试
    assert isinstance(ei.value.last_error, Exception)


def test_invoke_zero_retries():
    """retries=0 时只调用一次。"""
    llm = _FakeLLM(["坏输出"])
    with pytest.raises(StructuredOutputError):
        invoke_structured([("user", "x")], _Out, llm_factory=_factory(llm), retries=0)
    assert llm.calls == 1


def test_invoke_validation_failure_counts_as_retry():
    """字段校验失败（负数）也走重试路径。"""
    llm = _FakeLLM(['{"name": "a", "count": -1}', '{"name": "a", "count": 3}'])
    out = invoke_structured([("user", "x")], _Out, llm_factory=_factory(llm))
    assert out.count == 3
    assert llm.calls == 2


def test_error_message_carries_last_error_for_logs_only():
    """契约固化：异常文本含底层异常细节（API 层 5xx 时可含上游地址），仅供
    服务端日志定位；HTTP API 层不得把该字符串直接作为客户端响应。"""
    url = "https://internal.upstream.example/v1"

    class _AlwaysFail:
        def invoke(self, messages):
            raise RuntimeError(f"504 Gateway Time-out at {url}")

    with pytest.raises(StructuredOutputError) as ei:
        invoke_structured([("user", "x")], _Out, llm_factory=lambda timeout=None: _AlwaysFail())
    assert url in str(ei.value)  # 日志可定位
    assert ei.value.last_error is not None  # 调用方可取原始异常写日志
