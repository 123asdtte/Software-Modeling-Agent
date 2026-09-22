"""PlantUML 用例图渲染器测试（纯函数，不调真实 PlantUML / 网络 / LLM）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import UseCaseModel
from app.renderers.plantuml import render_usecase_plantuml


def _model(**overrides) -> UseCaseModel:
    """标准两 Actor 两用例模型（含隐式关联与 include）。"""
    data = {
        "type": "usecase",
        "system": "校园二手交易系统",
        "actors": [
            {"name": "学生", "role": "primary"},
            {"name": "管理员", "role": "supporting"},
        ],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
        ],
        "relations": [{"type": "include", "from": "UC-02", "to": "UC-01"}],
    }
    data.update(overrides)
    return UseCaseModel.model_validate(data)


def _render(**overrides) -> str:
    return render_usecase_plantuml(_model(**overrides))


# ---------------- 结构要求 ----------------


def test_output_wrapped_by_startuml_enduml():
    """输出以 @startuml 开始、@enduml 结束。"""
    out = _render()
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")


def test_output_has_direction_and_boundary():
    """包含 left to right direction 与系统边界 rectangle。"""
    out = _render()
    assert "left to right direction" in out
    assert 'rectangle "校园二手交易系统" {' in out


def test_all_actors_and_usecases_present():
    """所有 Actor 与 Use Case 都出现在输出中（显示文本保留中文）。"""
    out = _render()
    for text in ("学生", "管理员", "发布商品", "审核商品"):
        assert text in out


def test_aliases_are_deterministic_and_safe():
    """alias 按输入顺序生成 actor_1/usecase_1，用户输入不进 alias。"""
    out = _render()
    assert 'actor "学生" as actor_1' in out
    assert 'actor "管理员" as actor_2' in out
    assert "usecase_1" in out and "usecase_2" in out
    # 用户名称不能当 alias（同名别名注入防线）
    assert "as 学生" not in out
    assert "as 发布商品" not in out


# ---------------- 关系输出 ----------------


def test_implicit_association_from_usecase_actors():
    """UseCase.actors 自动生成 actor --> usecase 关联。"""
    out = _render()
    assert "actor_1 --> usecase_1" in out
    assert "actor_2 --> usecase_2" in out


def test_multiple_actors_one_usecase():
    """一个用例被多个 Actor 关联。"""
    data = {
        "system": "系统",
        "actors": [{"name": "甲"}, {"name": "乙"}],
        "usecases": [{"id": "UC-01", "name": "共享用例", "actors": ["甲", "乙"]}],
        "relations": [],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert "actor_1 --> usecase_1" in out
    assert "actor_2 --> usecase_1" in out


def test_one_actor_multiple_usecases():
    """一个 Actor 关联多个用例。"""
    data = {
        "system": "系统",
        "actors": [{"name": "学生"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "浏览商品", "actors": ["学生"]},
        ],
        "relations": [],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert "actor_1 --> usecase_1" in out
    assert "actor_1 --> usecase_2" in out


def test_explicit_association_rendered():
    """显式 association 关系输出为 -->，保持模型方向。"""
    data = {
        "system": "系统",
        "actors": [{"name": "学生"}],
        "usecases": [{"id": "UC-01", "name": "发布商品"}],
        "relations": [{"type": "association", "from": "学生", "to": "UC-01"}],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert "actor_1 --> usecase_1" in out


def test_include_extend_generalization_syntax():
    """include/extend/generalization 语法与方向保持模型 source→target。"""
    data = {
        "system": "系统",
        "actors": [],
        "usecases": [
            {"id": "UC-01", "name": "基础用例"},
            {"id": "UC-02", "name": "包含方"},
            {"id": "UC-03", "name": "扩展方"},
            {"id": "UC-04", "name": "子用例"},
        ],
        "relations": [
            {"type": "include", "from": "UC-02", "to": "UC-01"},
            {"type": "extend", "from": "UC-03", "to": "UC-01"},
            {"type": "generalization", "from": "UC-04", "to": "UC-01"},
        ],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert "usecase_2 .> usecase_1 : <<include>>" in out
    assert "usecase_3 .> usecase_1 : <<extend>>" in out
    assert "usecase_4 --|> usecase_1" in out


def test_empty_relations_and_no_usecases():
    """空 relations / 无用例时结构完整、不报错。"""
    out = render_usecase_plantuml(UseCaseModel(system="只有标题"))
    assert out.startswith("@startuml") and out.rstrip().endswith("@enduml")
    assert "-->" not in out and "<<include>>" not in out


def test_association_dedup_between_explicit_and_implicit():
    """隐式关联与完全相同的显式 association 去重（无序对，association 无方向语义）；
    渲染只画一条线，重复连线属质检对象的问题，由规则引擎报警告。"""
    data = {
        "system": "系统",
        "actors": [{"name": "学生"}],
        "usecases": [{"id": "UC-01", "name": "发布商品", "actors": ["学生"]}],
        "relations": [{"type": "association", "from": "学生", "to": "UC-01"}],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert out.count("actor_1 --> usecase_1") == 1


# ---------------- 转义与安全 ----------------


def test_chinese_system_name():
    """中文系统名称保留在显示文本。"""
    out = render_usecase_plantuml(UseCaseModel(system="智慧校园图书管理系统"))
    assert 'rectangle "智慧校园图书管理系统" {' in out


def test_double_quote_escaped():
    """显示文本中的双引号被转义，不破坏 PlantUML 引号结构。"""
    data = {"system": "系统", "actors": [{"name": '他说"你好"'}], "usecases": [], "relations": []}
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert 'actor "他说\\"你好\\"" as actor_1' in out


def test_backslash_escaped():
    """反斜杠先于引号转义，避免产生转义序列歧义。"""
    data = {"system": "系统", "actors": [{"name": "路径\\用户"}], "usecases": [], "relations": []}
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    assert 'actor "路径\\\\用户" as actor_1' in out


def test_newline_and_control_chars_replaced():
    """换行/回车/制表/控制字符替换为空格：用户内容无法逃逸出引号形成新指令行。

    注：被压平后的文本即使包含 "@enduml" 字样，仍在引号内属于显示文本，
    PlantUML 不会解析引号内的指令——安全判据是"没有产生独立指令行"。
    """
    data = {
        "system": "系统",
        "actors": [{"name": '坏人\n@enduml\nactor "注入" as evil'}],
        "usecases": [],
        "relations": [],
    }
    out = render_usecase_plantuml(UseCaseModel.model_validate(data))
    # 结构行仅由渲染器生成：@ 行只有 startuml/enduml 两个
    at_lines = [line for line in out.splitlines() if line.startswith("@")]
    assert at_lines == ["@startuml", "@enduml"]
    # 注入内容被压成单行显示文本，内嵌双引号已转义，引号未被打断
    assert 'actor "坏人 @enduml actor \\"注入\\" as evil" as actor_1' in out


# ---------------- 确定性与入口校验 ----------------


def test_same_input_same_output():
    """相同输入必须产生完全相同的输出。"""
    assert _render() == _render()
    assert _render() == _render()


def test_alias_roundtrip_does_not_affect_renderer():
    """by_alias 序列化再回填构造的模型，渲染结果与原模型完全一致。"""
    model = _model()
    dumped = model.model_dump(by_alias=True)
    rebuilt = UseCaseModel.model_validate(dumped)
    assert render_usecase_plantuml(rebuilt) == render_usecase_plantuml(model)


def test_non_model_rejected():
    """非法输入（dict/None）在入口被 TypeError 拦截，不进入渲染。"""
    with pytest.raises(TypeError):
        render_usecase_plantuml({"system": "不是模型"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        render_usecase_plantuml(None)  # type: ignore[arg-type]


def test_invalid_model_rejected_by_pydantic_before_renderer():
    """结构性非法（关系引用不存在）在模型层即被拒绝，无法到达 renderer。"""
    with pytest.raises(ValidationError):
        UseCaseModel.model_validate(
            {
                "system": "系统",
                "actors": [],
                "usecases": [],
                "relations": [{"type": "include", "from": "UC-99", "to": "UC-98"}],
            }
        )
