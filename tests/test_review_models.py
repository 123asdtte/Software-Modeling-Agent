"""审查报告模型测试（纯模型校验）。"""

import pytest
from pydantic import ValidationError

from app.models.review import ReviewIssue, ReviewReport


def test_review_issue_valid():
    issue = ReviewIssue(
        rule_id="UC-03",
        level="error",
        target="数据库",
        message="数据库是系统内部组件，不能作为参与者",
        rule_group="边界校验",
        suggestion="从参与者中移除数据库",
        table_ref="表2-6",
    )
    assert issue.level == "error"


def test_review_issue_level_whitelist():
    """level 白名单外的值拒绝（契约：技术方案统一用 level，不引入 severity）。"""
    with pytest.raises(ValidationError):
        ReviewIssue(rule_id="X", level="fatal", target="t", message="m")
    # 旧字段名 severity 不被接受（防止双命名漂移）
    with pytest.raises(ValidationError):
        ReviewIssue(rule_id="X", severity="error", target="t", message="m")


def test_review_issue_blank_rejected():
    with pytest.raises(ValidationError):
        ReviewIssue(rule_id="  ", level="error", target="t", message="m")
    with pytest.raises(ValidationError):
        ReviewIssue(rule_id="X", level="error", target="t", message="")


def test_review_report_counts():
    """error/warning 计数 property 基于 level 统计。"""
    report = ReviewReport(
        diagram_type="usecase",
        passed=False,
        issues=[
            ReviewIssue(rule_id="A", level="error", target="t1", message="m"),
            ReviewIssue(rule_id="B", level="warning", target="t2", message="m"),
        ],
    )
    assert report.error_count == 1
    assert report.warning_count == 1


def test_review_report_empty_issues_pass():
    """无问题即通过（issues default_factory）。"""
    report = ReviewReport(diagram_type="usecase", passed=True)
    assert report.issues == []
