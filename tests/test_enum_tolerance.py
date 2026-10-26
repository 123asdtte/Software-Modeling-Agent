# -*- coding: utf-8 -*-
"""LLM 枚举容错回归测试。

背景（真实端到端复现）：类图生成时 LLM 输出 `relations[].type = "inheritance"`，
不在 ClassRelationType 枚举内 → ValidationError → 重试仍失败 → `/generate` 返回 502。
修复方式：模型层做同义归一（本文件守护该行为）。

设计原则：
- 归一**只做同义映射**，不做语义猜测；
- 无法识别的值必须仍然报错，不能被静默吞掉（否则错误模型会流进渲染层）；
- 合法值必须原样通过（归一不能改变正常路径）。
"""

import pytest
from pydantic import ValidationError

from app.models.uml import (
    ClassModel,
    ClassRelation,
    ClassRelationType,
    DeployAssociation,
    DeployAssociationKind,
    DeploymentModel,
    DeployNode,
    DeployNodeKind,
    Lifeline,
    LifelineKind,
    MessageKind,
    SequenceFragment,
    SequenceMessage,
    Visibility,
)


# --------------------------------------------------------------- 类图关系类型
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("generalization", ClassRelationType.GENERALIZATION),
        ("inheritance", ClassRelationType.GENERALIZATION),
        ("extends", ClassRelationType.GENERALIZATION),
        ("泛化", ClassRelationType.GENERALIZATION),
        ("继承", ClassRelationType.GENERALIZATION),
        ("realization", ClassRelationType.REALIZATION),
        ("implements", ClassRelationType.REALIZATION),
        ("implementation", ClassRelationType.REALIZATION),
        ("实现", ClassRelationType.REALIZATION),
        ("composition", ClassRelationType.COMPOSITION),
        ("组合", ClassRelationType.COMPOSITION),
        ("aggregation", ClassRelationType.AGGREGATION),
        ("聚合", ClassRelationType.AGGREGATION),
        ("association", ClassRelationType.ASSOCIATION),
        ("关联", ClassRelationType.ASSOCIATION),
        ("dependency", ClassRelationType.DEPENDENCY),
        ("uses", ClassRelationType.DEPENDENCY),
        ("依赖", ClassRelationType.DEPENDENCY),
    ],
)
def test_class_relation_type_aliases(raw, expected):
    """常见英文/中文写法都应归一到六种合法关系。"""
    rel = ClassRelation.model_validate({"type": raw, "from": "A", "to": "B"})
    assert rel.type is expected


def test_class_relation_type_alias_is_case_and_space_insensitive():
    """LLM 常输出 "Generalization" / "  composition " 这类大小写与空格变体。"""
    assert ClassRelation.model_validate({"type": "Generalization", "from": "A", "to": "B"}).type is (
        ClassRelationType.GENERALIZATION
    )
    assert ClassRelation.model_validate({"type": "  composed of ", "from": "A", "to": "B"}).type is (
        ClassRelationType.COMPOSITION
    )


def test_class_relation_type_unknown_still_rejected():
    """归一不能变成"什么都接受"——未知值必须报错，让重试机制介入。"""
    with pytest.raises(ValidationError):
        ClassRelation.model_validate({"type": "wat", "from": "A", "to": "B"})


# ------------------------------------------------------------------- 可见性
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+", Visibility.PUBLIC),
        ("public", Visibility.PUBLIC),
        ("公开", Visibility.PUBLIC),
        ("-", Visibility.PRIVATE),
        ("private", Visibility.PRIVATE),
        ("私有", Visibility.PRIVATE),
        ("#", Visibility.PROTECTED),
        ("protected", Visibility.PROTECTED),
        ("~", Visibility.PACKAGE),
        ("package", Visibility.PACKAGE),
        ("default", Visibility.PACKAGE),
    ],
)
def test_class_member_visibility_aliases(raw, expected):
    """LLM 常写 public/private，而枚举值是 + - # ~，必须双向兼容。"""
    model = ClassModel.model_validate(
        {
            "type": "class",
            "title": "t",
            "classes": [
                {
                    "name": "A",
                    "attributes": [{"name": "x", "type": "String", "visibility": raw}],
                    "methods": [{"name": "m", "return_type": "void", "visibility": raw}],
                }
            ],
            "relations": [],
        }
    )
    item = model.classes[0]
    assert item.attributes[0].visibility is expected
    assert item.methods[0].visibility is expected


def test_visibility_unknown_still_rejected():
    with pytest.raises(ValidationError):
        ClassModel.model_validate(
            {
                "type": "class",
                "title": "t",
                "classes": [{"name": "A", "attributes": [{"name": "x", "visibility": "secret"}]}],
                "relations": [],
            }
        )


# --------------------------------------------------------------- 时序图枚举
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sync", MessageKind.SYNC),
        ("synchronous", MessageKind.SYNC),
        ("同步", MessageKind.SYNC),
        ("async", MessageKind.ASYNC),
        ("asynchronous", MessageKind.ASYNC),
        ("异步", MessageKind.ASYNC),
        ("return", MessageKind.RETURN),
        ("response", MessageKind.RETURN),
        ("返回", MessageKind.RETURN),
        ("create", MessageKind.CREATE),
        ("new", MessageKind.CREATE),
        ("创建", MessageKind.CREATE),
        ("destroy", MessageKind.DESTROY),
        ("delete", MessageKind.DESTROY),
        ("销毁", MessageKind.DESTROY),
    ],
)
def test_message_kind_aliases(raw, expected):
    msg = SequenceMessage.model_validate({"from": "A", "to": "B", "kind": raw, "order": 1})
    assert msg.kind is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("actor", LifelineKind.ACTOR),
        ("participant", LifelineKind.OBJECT),
        ("参与者", LifelineKind.OBJECT),
        ("db", LifelineKind.DATABASE),
        ("数据库", LifelineKind.DATABASE),
        ("边界", LifelineKind.BOUNDARY),
        ("控制", LifelineKind.CONTROL),
        ("实体", LifelineKind.ENTITY),
    ],
)
def test_lifeline_kind_aliases(raw, expected):
    line = Lifeline.model_validate({"name": "X", "kind": raw})
    assert line.kind is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("alt", "alt"),
        ("alternative", "alt"),
        ("条件", "alt"),
        ("loop", "loop"),
        ("循环", "loop"),
        ("opt", "opt"),
        ("optional", "opt"),
        ("par", "par"),
        ("并行", "par"),
    ],
)
def test_fragment_kind_aliases(raw, expected):
    frag = SequenceFragment.model_validate({"kind": raw, "start_order": 1, "end_order": 2})
    assert frag.kind == expected


def test_fragment_kind_unknown_rejected():
    with pytest.raises(ValidationError):
        SequenceFragment.model_validate({"kind": "maybe", "start_order": 1, "end_order": 2})


# --------------------------------------------------------------- 部署图枚举
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("device", DeployNodeKind.DEVICE),
        ("物理机", DeployNodeKind.DEVICE),
        ("设备", DeployNodeKind.DEVICE),
        ("exec_env", DeployNodeKind.EXEC_ENV),
        ("execution_environment", DeployNodeKind.EXEC_ENV),
        ("node", DeployNodeKind.EXEC_ENV),
        ("服务器", DeployNodeKind.EXEC_ENV),
        ("容器", DeployNodeKind.EXEC_ENV),
    ],
)
def test_deploy_node_kind_aliases(raw, expected):
    node = DeployNode.model_validate({"name": "N", "kind": raw})
    assert node.kind is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("communication", DeployAssociationKind.COMMUNICATION),
        ("通信", DeployAssociationKind.COMMUNICATION),
        ("http", DeployAssociationKind.COMMUNICATION),
        ("dependency", DeployAssociationKind.DEPENDENCY),
        ("依赖", DeployAssociationKind.DEPENDENCY),
        ("association", DeployAssociationKind.ASSOCIATION),
        ("连接", DeployAssociationKind.ASSOCIATION),
    ],
)
def test_deploy_association_kind_aliases(raw, expected):
    assoc = DeployAssociation.model_validate({"from": "A", "to": "B", "kind": raw})
    assert assoc.kind is expected


# ------------------------------------------------------------- 整体模型回归
def test_full_class_model_with_llm_style_wording():
    """复现真实失败输入：inheritance + implements + public/private 混写。"""
    model = ClassModel.model_validate(
        {
            "type": "class",
            "title": "校园选课",
            "classes": [
                {
                    "name": "User",
                    "is_abstract": True,
                    "attributes": [{"name": "id", "type": "String", "visibility": "private"}],
                    "methods": [],
                },
                {
                    "name": "Student",
                    "attributes": [],
                    "methods": [{"name": "enroll", "return_type": "boolean", "visibility": "public"}],
                },
                {
                    "name": "Enrollable",
                    "is_interface": True,
                    "attributes": [],
                    "methods": [{"name": "enroll", "return_type": "boolean", "visibility": "+"}],
                },
            ],
            "relations": [
                {"type": "inheritance", "from": "Student", "to": "User"},
                {"type": "implements", "from": "Student", "to": "Enrollable"},
            ],
        }
    )
    types = [r.type for r in model.relations]
    assert types == [ClassRelationType.GENERALIZATION, ClassRelationType.REALIZATION]


def test_full_deployment_model_with_llm_style_wording():
    model = DeploymentModel.model_validate(
        {
            "type": "deployment",
            "title": "部署",
            "nodes": [
                {"name": "db", "kind": "物理机", "stereotype": "database"},
                {"name": "k8s", "kind": "执行环境", "stereotype": "k8s"},
            ],
            "artifacts": [],
            "associations": [{"from": "k8s", "to": "db", "kind": "http"}],
        }
    )
    assert model.nodes[0].kind is DeployNodeKind.DEVICE
    assert model.nodes[1].kind is DeployNodeKind.EXEC_ENV
    assert model.associations[0].kind is DeployAssociationKind.COMMUNICATION
