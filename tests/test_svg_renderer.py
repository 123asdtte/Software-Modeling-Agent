"""SVG 渲染器测试（纯函数：XML 结构/确定性/转义/坐标与 drawio 对齐）。"""

from xml.etree import ElementTree

import pytest

from app.models.uml import UseCaseModel
from app.renderers.drawio_renderer import render_usecase_drawio
from app.renderers.svg_renderer import render_usecase_svg


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


def test_output_is_valid_svg():
    root = ElementTree.fromstring(render_usecase_svg(_model()))
    assert root.tag.endswith("svg")


def test_deterministic_output():
    assert render_usecase_svg(_model()) == render_usecase_svg(_model())


def test_shapes_and_labels_present():
    out = render_usecase_svg(_model())
    assert 'value="学生"' not in out  # svg 用 text 元素而非 value 属性
    assert ">学生</text>" in out
    assert ">发布商品</text>" in out
    assert "ellipse" in out
    assert "«include»" in out and "stroke-dasharray" in out
    assert "校园二手交易系统" in out


def test_quote_escaped():
    data = {
        "system": '系统"引号"',
        "actors": [{"name": 'a"b'}],
        "usecases": [{"id": "UC-01", "name": "发布商品", "actors": ['a"b']}],
        "relations": [],
    }
    out = render_usecase_svg(UseCaseModel.model_validate(data))
    assert "&quot;" in out


def test_layout_matches_drawio():
    """SVG 与 drawio 的 usecase 坐标一致（同一套布局常量）。"""
    model = _model()
    svg = render_usecase_svg(model)
    dxio = render_usecase_drawio(model)
    # UC-01 在两者中都出现且坐标 x 相同（drawio x=260 → svg cx=260+85=345）
    assert "345" in svg
    assert 'x="260"' in dxio


def test_non_model_rejected():
    with pytest.raises(TypeError):
        render_usecase_svg({"system": "不是模型"})  # type: ignore[arg-type]
