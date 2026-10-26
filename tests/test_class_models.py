"""类图领域模型测试（纯模型校验，不调 LLM、不渲染）。"""

import pytest
from pydantic import ValidationError

from app.models.uml import (
    ClassModel,
    ClassRelationType,
    DiagramType,
    Visibility,
    parse_uml_model,
)


def valid_class_data() -> dict:
    return {
        "type": "class",
        "title": "选课系统",
        "classes": [
            {
                "name": "Person",
                "is_abstract": True,
                "attributes": [{"name": "name", "type": "String", "visibility": "-"}],
                "methods": [
                    {
                        "name": "describe",
                        "return_type": "String",
                        "visibility": "+",
                        "is_abstract": True,
                    }
                ],
            },
            {
                "name": "Student",
                "attributes": [{"name": "studentId", "type": "String", "visibility": "-"}],
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "course", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                    }
                ],
            },
            {
                "name": "Course",
                "attributes": [{"name": "title", "type": "String", "visibility": "#"}],
            },
            {
                "name": "Enrollable",
                "is_interface": True,
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "course", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                        "is_abstract": True,
                    }
                ],
            },
        ],
        "relations": [
            {"type": "generalization", "from": "Student", "to": "Person"},
            {"type": "realization", "from": "Student", "to": "Enrollable"},
            {
                "type": "composition",
                "from": "Student",
                "to": "Course",
                "target_multiplicity": "1..*",
            },
        ],
    }


# ---------------- 基本结构 ----------------


def test_class_model_valid():
    """合法类图模型正常构造，类型锁定 class。"""
    m = ClassModel.model_validate(valid_class_data())
    assert m.type == DiagramType.CLASS
    assert len(m.classes) == 4 and len(m.relations) == 3
    assert m.classes[0].is_abstract is True
    assert m.classes[3].is_interface is True


def test_class_model_defaults_empty():
    """缺省列表字段合法。"""
    m = ClassModel()
    assert m.classes == [] and m.relations == []
    assert m.title == ""


def test_class_item_blank_name_rejected():
    """类名不允许空白。"""
    data = valid_class_data()
    data["classes"][0]["name"] = "   "
    with pytest.raises(ValidationError):
        ClassModel.model_validate(data)


def test_attribute_blank_name_rejected():
    """属性名不允许空白。"""
    data = valid_class_data()
    data["classes"][1]["attributes"][0]["name"] = ""
    with pytest.raises(ValidationError):
        ClassModel.model_validate(data)


# ---------------- 唯一性与引用 ----------------


def test_duplicate_class_name_rejected():
    """重复类名必须拒绝（渲染别名冲突）。"""
    data = valid_class_data()
    data["classes"].append({"name": "Student"})
    with pytest.raises(ValidationError, match="重复的类名"):
        ClassModel.model_validate(data)


def test_relation_source_must_exist():
    """关系 from 端必须是已定义类。"""
    data = valid_class_data()
    data["relations"][0]["from"] = "Ghost"
    with pytest.raises(ValidationError, match="from 端类不存在"):
        ClassModel.model_validate(data)


def test_relation_target_must_exist():
    """关系 to 端必须是已定义类。"""
    data = valid_class_data()
    data["relations"][1]["to"] = "Ghost"
    with pytest.raises(ValidationError, match="to 端类不存在"):
        ClassModel.model_validate(data)


def test_realization_target_must_be_interface():
    """实现关系目标必须是接口（UML 语义）。"""
    data = valid_class_data()
    data["relations"] = [{"type": "realization", "from": "Student", "to": "Person"}]
    with pytest.raises(ValidationError, match="必须是接口"):
        ClassModel.model_validate(data)


def test_realization_to_interface_ok():
    """实现关系指向接口合法。"""
    data = valid_class_data()
    data["relations"] = [{"type": "realization", "from": "Student", "to": "Enrollable"}]
    m = ClassModel.model_validate(data)
    assert m.relations[0].type == ClassRelationType.REALIZATION


# ---------------- 枚举与序列化 ----------------


def test_visibility_enum_values():
    """可见性符号与 UML 一致。"""
    assert Visibility.PUBLIC.value == "+"
    assert Visibility.PRIVATE.value == "-"
    assert Visibility.PROTECTED.value == "#"
    assert Visibility.PACKAGE.value == "~"


def test_all_relation_types_accepted():
    """六种关系类型全部合法。"""
    base = {
        "type": "class",
        "classes": [
            {"name": "A"},
            {"name": "B", "is_interface": True},
        ],
    }
    for rtype in (
        "association",
        "aggregation",
        "composition",
        "generalization",
        "dependency",
        "realization",
    ):
        target = "B" if rtype == "realization" else "A"
        data = {**base, "relations": [{"type": rtype, "from": "A", "to": target}]}
        m = ClassModel.model_validate(data)
        assert m.relations[0].type.value == rtype


def test_relation_alias_serialization_locked():
    """by_alias 输出 from/to（与用例图约定一致）。"""
    m = ClassModel.model_validate(valid_class_data())
    dumped = m.model_dump(by_alias=True)
    assert dumped["relations"][0]["from"] == "Student"
    assert dumped["relations"][0]["to"] == "Person"
    assert dumped["relations"][2]["target_multiplicity"] == "1..*"


def test_visibility_optional_for_rule_engine():
    """可见性允许缺省（由规则引擎提示学生补标，而非模型层拒绝）。"""
    data = valid_class_data()
    data["classes"][2]["attributes"][0].pop("visibility")
    m = ClassModel.model_validate(data)
    assert m.classes[2].attributes[0].visibility is None


# ---------------- 分发表决 ----------------


def test_parse_uml_model_dispatch_class():
    """parse_uml_model 按 type 分派为 ClassModel。"""
    m = parse_uml_model(valid_class_data())
    assert isinstance(m, ClassModel)


def test_parse_uml_model_unknown_type_raises():
    """未知 type 抛 ValueError。"""
    with pytest.raises(ValueError, match="不支持的图类型"):
        parse_uml_model({"type": "component"})
