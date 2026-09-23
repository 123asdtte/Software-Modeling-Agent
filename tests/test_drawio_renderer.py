"""draw.io 渲染器测试（纯函数：XML 结构/确定性/转义/边界）。"""

from xml.etree import ElementTree

import pytest

from app.models.uml import UseCaseModel
from app.renderers.drawio_renderer import render_usecase_drawio


def _model(**overrides) -> UseCaseModel:
    data = {
        "system": "校园二手交易系统",
        "actors": [{"name": "学生"}, {"name": "管理员"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
        ],
        "relations": [{"type": "include", "from": "UC-02", "to": "UC-01"}],
    }
    data.update(overrides)
    return UseCaseModel.model_validate(data)


def test_output_is_valid_xml():
    """输出可被 XML 解析器解析（mxfile 结构完整）。"""
    root = ElementTree.fromstring(render_usecase_drawio(_model()))
    assert root.tag == "mxfile"
    assert root.find("diagram") is not None


def test_deterministic_output():
    """相同输入输出完全一致。"""
    assert render_usecase_drawio(_model()) == render_usecase_drawio(_model())


def test_actors_usecases_boundary_present():
    """actor 形状、usecase 椭圆、系统边界均存在，显示文本保留中文。"""
    out = render_usecase_drawio(_model())
    assert 'value="学生"' in out and "shape=umlActor" in out
    assert 'value="发布商品"' in out and "ellipse" in out
    assert 'value="校园二手交易系统"' in out


def test_all_edge_types_with_labels():
    """include 虚线带构造型标签；association 实线；generalization 空心三角。"""
    data = {
        "system": "系统",
        "actors": [{"name": "学生"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "浏览商品", "actors": ["学生"]},
            {"id": "UC-03", "name": "填写物流单", "actors": ["学生"]},
        ],
        "relations": [
            {"type": "include", "from": "UC-02", "to": "UC-01"},
            {"type": "extend", "from": "UC-03", "to": "UC-01"},
            {"type": "association", "from": "学生", "to": "UC-01"},
            {"type": "generalization", "from": "UC-02", "to": "UC-01"},
        ],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "«include»" in out and "dashed=1" in out
    assert "«extend»" in out
    assert "endArrow=block;endFill=0" in out  # generalization 空心三角
    assert "endArrow=none" in out  # association 无箭头


def test_alias_not_user_input():
    """用户输入不作为元素 id（防注入与重名）。"""
    data = {
        "system": "系统",
        "actors": [{"name": "x&y<z>"}],
        "usecases": [{"id": "UC-01", "name": "用例", "actors": ["x&y<z>"]}],
        "relations": [],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "actor_1" in out
    assert "x&y<z>" not in out  # 已转义为 &amp;
    assert "x&amp;y&lt;z&gt;" in out


def test_same_input_same_xml_with_quotes():
    """含引号名称的确定性 + 转义正确性。"""
    data = {
        "system": '系统"引号"',
        "actors": [{"name": 'a"b'}],
        "usecases": [{"id": "UC-01", "name": "发布商品", "actors": ['a"b']}],
        "relations": [],
    }
    out = render_usecase_drawio(UseCaseModel.model_validate(data))
    assert "&quot;" in out
    assert out == render_usecase_drawio(UseCaseModel.model_validate(data))


def test_non_model_rejected():
    from app.renderers.drawio_renderer import render_usecase_drawio as r

    with pytest.raises(TypeError):
        r({"system": "不是模型"})  # type: ignore[arg-type]
