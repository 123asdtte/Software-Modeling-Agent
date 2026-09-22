"""审查报告模型：UML 质检（规则引擎 + LLM 复核）的统一输出契约。

规则引擎产出的每条问题与 LLM 复核意见都映射为 ReviewIssue，
渲染与前端只依赖 ReviewReport，不关心问题来自哪一层。

字段命名以 `docs/03-技术方案/04_UML建模Agent详细技术方案.md` 为准：
审查问题级别字段统一为 `level`（不用 severity，避免双命名漂移）。
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.uml import DiagramType

# 审查问题级别（技术方案 §2.3：error 拦截、warning 提示、info 说明）
IssueLevel = Literal["error", "warning", "info"]


class ReviewIssue(BaseModel):
    """一条审查问题：规则 ID + 级别 + 定位 + 说明 + 修改建议。"""

    rule_id: str
    level: IssueLevel
    target: str
    message: str
    rule_group: str = ""
    suggestion: str = ""
    table_ref: str = ""  # 教材校验表号（如 表2-6），可溯源

    @field_validator("rule_id", "target", "message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("不能为空白")
        return v


class ReviewReport(BaseModel):
    """审查报告：passed 由调用方根据问题级别判定后写入。"""

    diagram_type: DiagramType
    passed: bool
    issues: list[ReviewIssue] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")
