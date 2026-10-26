"""类图 → Java 代码骨架生成器测试（纯函数，不调 LLM）。"""

import pytest

from app.chains.class_to_code import class_model_to_java
from app.models.uml import ClassModel


def _model(**overrides) -> ClassModel:
    data = {
        "type": "class",
        "classes": [
            {
                "name": "Person",
                "is_abstract": True,
                "attributes": [
                    {"name": "name", "type": "String", "visibility": "-"},
                    {"name": "species", "type": "String", "visibility": "~", "is_static": True},
                ],
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
                "attributes": [
                    {"name": "studentId", "type": "String", "visibility": "-"},
                    {"name": "age", "type": "整数", "visibility": "#"},
                ],
                "methods": [
                    {
                        "name": "enroll",
                        "params": [{"name": "course", "type": "Course"}],
                        "return_type": "boolean",
                        "visibility": "+",
                    },
                    {"name": "ping", "return_type": "", "visibility": "+"},
                ],
            },
            {"name": "Course", "attributes": [{"name": "title", "type": "String", "visibility": "-"}]},
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
    data.update(overrides)
    return ClassModel.model_validate(data)


def test_files_keyed_by_class_name():
    files = class_model_to_java(_model())
    assert list(files) == ["Person.java", "Student.java", "Course.java", "Enrollable.java"]


def test_package_declaration():
    files = class_model_to_java(_model(), package="edu.example")
    assert files["Student.java"].startswith("package edu.example;")


def test_empty_package_omits_declaration():
    files = class_model_to_java(_model(), package="")
    assert "package " not in files["Student.java"]


def test_abstract_class_and_abstract_method():
    code = class_model_to_java(_model())["Person.java"]
    assert "public abstract class Person" in code
    assert "public abstract String describe();" in code


def test_class_extends_and_implements():
    code = class_model_to_java(_model())["Student.java"]
    assert "public class Student extends Person implements Enrollable" in code


def test_interface_declaration_and_method():
    code = class_model_to_java(_model())["Enrollable.java"]
    assert "public interface Enrollable" in code
    assert "boolean enroll(Course course);" in code
    # 接口方法只有声明（以分号结尾），不生成方法体
    assert code.count("{") == 1
    assert "UnsupportedOperationException" not in code


def test_visibility_mapping():
    files = class_model_to_java(_model())
    person = files["Person.java"]
    student = files["Student.java"]
    assert "private String name;" in person
    assert "static String species;" in person  # ~ → 包私有（无修饰符）
    assert "protected int age;" in student  # 中文类型「整数」→ int


def test_concrete_method_body_and_todo():
    code = class_model_to_java(_model())["Student.java"]
    assert "public boolean enroll(Course course) {" in code
    assert "// TODO: 实现业务逻辑" in code
    assert 'throw new UnsupportedOperationException("TODO");' in code


def test_void_method_has_no_throw():
    code = class_model_to_java(_model())["Student.java"]
    void_block = code.split("public void ping()")[1]
    assert "TODO" in void_block
    assert "UnsupportedOperationException" not in void_block.split("}")[0]


def test_composition_adds_member_field():
    code = class_model_to_java(_model())["Student.java"]
    assert "private Course course;" in code


def test_aggregation_adds_member_field():
    model = _model(
        relations=[{"type": "aggregation", "from": "Student", "to": "Course"}],
    )
    code = class_model_to_java(model)["Student.java"]
    assert "private Course course;" in code


def test_empty_types_fall_back():
    """空属性类型 → Object；空返回类型 → void。"""
    model = ClassModel.model_validate(
        {
            "type": "class",
            "classes": [
                {
                    "name": "A",
                    "attributes": [{"name": "x", "type": ""}],
                    "methods": [{"name": "run", "return_type": "", "params": [{"name": "p", "type": ""}]}],
                }
            ],
        }
    )
    code = class_model_to_java(model)["A.java"]
    assert "private Object x;" in code
    assert "public void run(Object p)" in code


def test_identifier_sanitization():
    model = ClassModel.model_validate(
        {"type": "class", "classes": [{"name": "My Class", "attributes": [{"name": "1st-field"}]}]}
    )
    files = class_model_to_java(model)
    assert "My_Class.java" in files
    code = files["My_Class.java"]
    assert "public class My_Class" in code
    assert "private Object field_1st_field;" in code  # 数字开头补前缀


def test_deterministic_output():
    assert class_model_to_java(_model()) == class_model_to_java(_model())


def test_non_class_model_rejected():
    with pytest.raises(TypeError):
        class_model_to_java({"type": "class"})  # type: ignore[arg-type]


def test_no_relations_still_compiles_structurally():
    model = ClassModel.model_validate(
        {"type": "class", "classes": [{"name": "Plain", "attributes": [{"name": "id", "type": "long"}]}]}
    )
    code = class_model_to_java(model)["Plain.java"]
    assert "public class Plain {" in code
    assert code.rstrip().endswith("}")
