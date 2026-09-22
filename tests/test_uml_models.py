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


# ---------------- 唯一性与冲突（评审 P1）----------------


def test_duplicate_actor_name_rejected():
    """重复参与者名称必须拒绝，错误信息指出冲突对象。"""
    data = _valid_model()
    data["actors"].append({"name": "学生", "role": "supporting"})
    with pytest.raises(ValidationError, match="重复的参与者名称"):
        UseCaseModel.model_validate(data)


def test_duplicate_usecase_id_rejected():
    """重复用例 ID 必须拒绝。"""
    data = _valid_model()
    data["usecases"].append({"id": "UC-01", "name": "另一个用例"})
    with pytest.raises(ValidationError, match="重复的用例 ID"):
        UseCaseModel.model_validate(data)


def test_actor_name_usecase_id_conflict_rejected():
    """参与者名称与用例 ID 冲突必须拒绝。"""
    data = _valid_model()
    data["actors"].append({"name": "UC-01"})
    with pytest.raises(ValidationError, match="冲突"):
        UseCaseModel.model_validate(data)


def test_duplicate_relation_allowed_by_design():
    """完全相同的关系重复出现是"学生画重线"错误——由规则引擎报警告，
    模型层只拦结构性非法，不拒绝（设计决定，渲染按输入顺序输出）。"""
    data = _valid_model()
    data["relations"].append({"type": "include", "from": "UC-02", "to": "UC-01"})
    m = UseCaseModel.model_validate(data)
    assert len(m.relations) == 2


# ---------------- 字段边界（评审 P1）----------------


def test_field_length_limits():
    """超长字段必须拒绝（防失控输入撑爆渲染与 API）。"""
    data = _valid_model()
    data["system"] = "长" * 101
    with pytest.raises(ValidationError):
        UseCaseModel.model_validate(data)
    ok = UseCaseModel.model_validate({**_valid_model(), "system": "长" * 100})
    assert len(ok.system) == 100
    with pytest.raises(ValidationError):
        Actor(name="长" * 51)
    with pytest.raises(ValidationError):
        UseCase(id="长" * 21, name="x")
    with pytest.raises(ValidationError):
        Relation.model_validate({"type": "include", "from": "UC-01", "to": "UC-02", "note": "长" * 201})


def test_collection_size_limits():
    """列表数量上限必须生效。"""
    data = _valid_model()
    data["actors"] = [{"name": f"角色{i}"} for i in range(21)]
    with pytest.raises(ValidationError):
        UseCaseModel.model_validate(data)
    data = _valid_model()
    data["usecases"] = [{"id": f"UC-{i:02d}", "name": f"用例{i}"} for i in range(31)]
    with pytest.raises(ValidationError):
        UseCaseModel.model_validate(data)


# ---------------- 关系类型枚举（评审 P1）----------------


def test_relation_type_all_values():
    """四种关系类型全部合法（str 枚举：JSON 字符串直接可用）。"""
    for rtype in ("include", "extend", "association", "generalization"):
        rel = Relation.model_validate({"type": rtype, "from": "UC-01", "to": "UC-02"})
        assert rel.type.value == rtype


def test_relation_type_enum_output():
    """枚举输出为稳定字符串值。"""
    data = _valid_model()
    m = UseCaseModel.model_validate(data)
    dumped = m.model_dump()
    assert dumped["relations"][0]["type"] == "include"


# ---------------- alias 序列化行为锁定（评审 P1）----------------


def test_relation_alias_serialization_locked():
    """序列化行为锁定：model_dump() 默认输出 source_id/target_id；
    对外 JSON 契约（技术方案文档）要求 from/to，必须用 by_alias=True。
    渲染器与 API 只允许明确选择一种访问方式，禁止混用。"""
    rel = Relation.model_validate({"type": "include", "from": "UC-01", "to": "UC-02"})
    by_field = rel.model_dump()
    assert by_field == {
        "type": "include",
        "source_id": "UC-01",
        "target_id": "UC-02",
        "note": "",
    }
    by_alias = rel.model_dump(by_alias=True)
    assert by_alias == {"type": "include", "from": "UC-01", "to": "UC-02", "note": ""}
    # 整图级序列化同样锁定
    m = UseCaseModel.model_validate(_valid_model())
    top = m.model_dump(by_alias=True)
    assert top["relations"][0]["from"] == "UC-02"
