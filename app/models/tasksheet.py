"""实训任务工单领域模型（对齐前端 renderTasksheetResults 消费契约）。

前端字段（不可更名）：
- task_id / course_name / occupational_role / training_mode
- difficulty / duration_minutes / scenario
- deliverables[{name, format, desc}]
- steps[{step_num, step_name, estimated_time, guide, checkpoint}]
"""

from pydantic import BaseModel, Field, field_validator


def _not_blank(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("不能为空白")
    return v


class TaskDeliverable(BaseModel):
    """成果交付物条目。"""

    name: str = Field(max_length=80)
    format: str = Field(max_length=40)
    desc: str = Field(default="", max_length=300)

    @field_validator("name", "format")
    @classmethod
    def _req(cls, v: str) -> str:
        return _not_blank(v)


class TaskStep(BaseModel):
    """阶梯工序条目。"""

    step_num: int = Field(ge=1, le=20)
    step_name: str = Field(max_length=80)
    estimated_time: str = Field(max_length=20)  # 前端按文本展示（如 "15"）
    guide: str = Field(default="", max_length=500)
    checkpoint: str = Field(default="", max_length=300)

    @field_validator("step_name", "estimated_time")
    @classmethod
    def _req(cls, v: str) -> str:
        return _not_blank(v)


class Tasksheet(BaseModel):
    """实训任务工单（含考核评价量规要素）。"""

    task_id: str = Field(max_length=30)
    course_name: str = Field(max_length=100)
    occupational_role: str = Field(default="软件建模师", max_length=50)
    training_mode: str = Field(default="双人结对协作", max_length=50)
    difficulty: str = Field(default="进阶", max_length=20)
    duration_minutes: int = Field(default=45, ge=15, le=240)
    scenario: str = Field(min_length=10, max_length=800)
    deliverables: list[TaskDeliverable] = Field(min_length=2, max_length=6)
    steps: list[TaskStep] = Field(min_length=3, max_length=8)

    @field_validator("task_id", "course_name")
    @classmethod
    def _req(cls, v: str) -> str:
        return _not_blank(v)
