"""UML 用例图领域模型测试（纯模型校验，不调 LLM、不渲染）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import Actor, DiagramType, Relation, UseCase, UseCaseModel


def _valid_model() -> dict:
    return {
        "type": "usecase",
        "system": "校园二手交易系统",
        "actors": [
            {"name": "学生", "role": "primary"},
            {"name": "管理员", "role": "supporting"},
        ],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"], "goal": "发布二手商品"},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
        ],
        "relations": [
            {"type": "include", "from": "UC-02", "to": "UC-01"},
        ],
    }


def test_usecase_model_valid():
    """合法模型正常构造，类型锁定 usecase。"""
    m = UseCaseModel.model_validate(_valid_model())
    assert m.type == DiagramType.USECASE
    assert len(m.actors) == 2 and len(m.usecases) == 2


def test_relation_alias_from_to():
    """JSON 的 from/to 字段通过 alias 映射到 source_id/target_id。"""
    rel = Relation.model_validate({"type": "include", "from": "UC-01", "to": "UC-02"})
    assert rel.source_id == "UC-01" and rel.target_id == "UC-02"
    # populate_by_name：也接受字段名
    rel2 = Relation(type="extend", source_id="UC-01", target_id="UC-02")
    assert rel2.source_id == "UC-01"


def test_blank_name_rejected():
    """必填字符串不允许空白。"""
    with pytest.raises(ValidationError):
        Actor(name="   ")
    with pytest.raises(ValidationError):
        UseCase(id="UC-01", name="")
    with pytest.raises(ValidationError):
        UseCaseModel.model_validate({**_valid_model(), "system": "  "})


def test_relation_reference_must_exist():
    """关系两端引用不存在的元素时拒绝。"""
    data = _valid_model()
    data["relations"] = [{"type": "include", "from": "UC-99", "to": "UC-01"}]
    with pytest.raises(ValidationError, match="不存在"):
        UseCaseModel.model_validate(data)


def test_usecase_actor_reference_must_exist():
    """用例引用不存在的参与者时拒绝。"""
    data = _valid_model()
    data["usecases"][0]["actors"] = ["不存在的人"]
    with pytest.raises(ValidationError, match="不存在"):
        UseCaseModel.model_validate(data)


def test_include_must_be_usecase_to_usecase():
    """include/extend 两端必须是用例（教材语义）。"""
    data = _valid_model()
    data["relations"] = [{"type": "include", "from": "学生", "to": "UC-01"}]
    with pytest.raises(ValidationError, match="必须是用例"):
        UseCaseModel.model_validate(data)


def test_association_must_link_actor_and_usecase():
    """association 必须连接参与者与用例。"""
    data = _valid_model()
    data["relations"] = [{"type": "association", "from": "UC-01", "to": "UC-02"}]
    with pytest.raises(ValidationError, match="参与者与用例"):
        UseCaseModel.model_validate(data)
    # 合法关联：参与者 -> 用例
    data["relations"] = [{"type": "association", "from": "学生", "to": "UC-01"}]
    UseCaseModel.model_validate(data)


def test_relation_type_whitelist():
    """关系类型不在白名单内拒绝。"""
    with pytest.raises(ValidationError):
        Relation.model_validate({"type": "depends", "from": "UC-01", "to": "UC-02"})


def test_defaults_are_empty_lists():
    """列表字段 default_factory，缺省合法。"""
    m = UseCaseModel(system="极简系统")
    assert m.actors == [] and m.usecases == [] and m.relations == []
