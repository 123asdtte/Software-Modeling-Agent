"""UML 用例图生成链测试（全部注入 Fake LLM，不调真实 API）。"""

import asyncio
import json

import pytest

from app.chains.uml_chain import generate_usecase_model
from app.core.structured_output import StructuredOutputError
from app.models.uml import UseCaseModel

VALID_JSON = json.dumps(
    {
        "type": "usecase",
        "system": "校园二手交易系统",
        "actors": [{"name": "学生", "role": "primary"}],
        "usecases": [{"id": "UC-01", "name": "发布商品", "actors": ["学生"], "goal": "发布二手商品"}],
        "relations": [],
    },
    ensure_ascii=False,
)

FENCED = "```json\n" + VALID_JSON + "\n```"
WITH_TEXT = "好的，以下是建模结果：\n" + VALID_JSON + "\n如需调整请告诉我。"


class _FakeLLM:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        idx = min(self.calls - 1, len(self.contents) - 1)
        return type("M", (), {"content": self.contents[idx]})()


def _factory(llm: _FakeLLM):
    return lambda timeout=None: llm


def _run(requirement: str, llm: _FakeLLM) -> UseCaseModel:
    return asyncio.run(generate_usecase_model(requirement, llm_factory=_factory(llm)))


def test_valid_json():
    """纯 JSON 正常解析。"""
    model = _run("学生发布商品", _FakeLLM([VALID_JSON]))
    assert model.system == "校园二手交易系统"
    assert model.usecases[0].name == "发布商品"


def test_fenced_json():
    """markdown 围栏 JSON 正常解析。"""
    model = _run("学生发布商品", _FakeLLM([FENCED]))
    assert model.actors[0].name == "学生"


def test_json_with_surrounding_text():
    """前后带解释文本仍可提取。"""
    model = _run("学生发布商品", _FakeLLM([WITH_TEXT]))
    assert model.system == "校园二手交易系统"


def test_invalid_json_retry_then_success():
    """第一次非法 JSON，重试后成功。"""
    llm = _FakeLLM(["抱歉我不会输出 JSON", VALID_JSON])
    model = _run("学生发布商品", llm)
    assert llm.calls == 2
    assert model.system == "校园二手交易系统"


def test_missing_field_fails_then_retry_success():
    """字段丢失（缺 system）触发校验失败，重试成功。"""
    broken = json.dumps({"type": "usecase", "actors": []}, ensure_ascii=False)
    llm = _FakeLLM([broken, VALID_JSON])
    model = _run("学生发布商品", llm)
    assert model.system == "校园二手交易系统"


def test_wrong_field_type_fails_then_retry_success():
    """字段类型错误（actors 是字符串）触发重试成功。"""
    broken = json.dumps({**json.loads(VALID_JSON), "actors": "学生"}, ensure_ascii=False)
    llm = _FakeLLM([broken, VALID_JSON])
    model = _run("学生发布商品", llm)
    assert isinstance(model.actors, list)


def test_both_attempts_fail_raises():
    """两次都失败抛 StructuredOutputError（尝试 2 次）。"""
    llm = _FakeLLM(["坏输出"])
    with pytest.raises(StructuredOutputError) as ei:
        _run("学生发布商品", llm)
    assert ei.value.attempts == 2


def test_domain_invalid_json_triggers_retry():
    """JSON 合法但领域非法（关系引用不存在）也触发重试（UseCaseModel 校验兜底）。"""
    broken = json.dumps(
        {
            "type": "usecase",
            "system": "系统",
            "actors": [],
            "usecases": [],
            "relations": [{"type": "include", "from": "UC-99", "to": "UC-98"}],
        },
        ensure_ascii=False,
    )
    llm = _FakeLLM([broken, VALID_JSON])
    model = _run("学生发布商品", llm)
    assert model.system == "校园二手交易系统"


def test_prompt_contains_modeling_rules():
    """发给模型的 system 消息必须包含教学规则（防模型输出内部组件参与者）。"""
    captured: dict = {}

    class _Capture:
        def invoke(self, messages):
            captured["messages"] = messages
            return type("M", (), {"content": VALID_JSON})()

    model = asyncio.run(generate_usecase_model("学生发布商品", llm_factory=lambda timeout=None: _Capture()))
    assert model.system == "校园二手交易系统"
    system_text = captured["messages"][0][1]
    assert "内部组件" in system_text
    assert "只输出一个 JSON" in system_text
