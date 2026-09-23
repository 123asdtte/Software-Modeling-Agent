"""实训工单与全案联产端点测试（Fake LLM，不调真实模型）。"""

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TASKSHEET_JSON = json.dumps(
    {
        "task_id": "WS-2026-SE01",
        "course_name": "用例图建模实训",
        "occupational_role": "软件建模师",
        "training_mode": "双人结对协作",
        "difficulty": "进阶",
        "duration_minutes": 45,
        "scenario": "某电商公司需要为二手交易平台设计用例模型，你作为建模师需要完成任务。",
        "deliverables": [
            {"name": "用例图模型文件", "format": "plantuml", "desc": "完整用例图源码"},
            {"name": "需求分析说明", "format": "docx", "desc": "参与者与用例说明"},
        ],
        "steps": [
            {
                "step_num": 1,
                "step_name": "需求研读",
                "estimated_time": "10",
                "guide": "阅读需求",
                "checkpoint": "识别参与者",
            },
            {
                "step_num": 2,
                "step_name": "建模",
                "estimated_time": "20",
                "guide": "绘制用例图",
                "checkpoint": "边界正确",
            },
            {"step_num": 3, "step_name": "评审", "estimated_time": "15", "guide": "互评", "checkpoint": "规则通过"},
        ],
    },
    ensure_ascii=False,
)


class _FakeLLM:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        idx = min(self.calls - 1, len(self.contents) - 1)
        return type("M", (), {"content": self.contents[idx]})()


def test_tasksheet_endpoint_ok(monkeypatch, tmp_path):
    """Fake LLM 下 /v1/tasksheet 返回 200 + 工单结构 + docx 下载链接。"""
    monkeypatch.chdir(tmp_path)
    from app.chains import tasksheet_chain

    def factory(timeout=None):
        return _FakeLLM([TASKSHEET_JSON])

    monkeypatch.setattr(tasksheet_chain, "generate_tasksheet", None, raising=False)
    # patch 链内部 invoke_structured 的默认工厂：直接 patch 链的 _generate_sync 太深，
    # 这里 patch get_llm 使用的 default factory 更稳：patch tasksheet_chain.invoke_structured
    orig = tasksheet_chain.invoke_structured

    def fake_invoke(messages, model_cls, **kwargs):
        return model_cls.model_validate(json.loads(TASKSHEET_JSON))

    monkeypatch.setattr(tasksheet_chain, "invoke_structured", fake_invoke)
    resp = client.post("/v1/tasksheet", json={"topic": "用例图建模实训", "minutes": 45})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tasksheet"]["task_id"] == "WS-2026-SE01"
    assert body["tasksheet"]["steps"][0]["step_num"] == 1
    assert body["download_url"].endswith(".docx")
    # 下载回环
    dl = client.get(body["download_url"])
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # docx 是 zip
    monkeypatch.setattr(tasksheet_chain, "invoke_structured", orig)


def test_tasksheet_endpoint_422_blank_topic():
    """空课题返回 422。"""
    resp = client.post("/v1/tasksheet", json={"topic": "  "})
    assert resp.status_code == 422


def test_tasksheet_endpoint_502_on_structured_error(monkeypatch, tmp_path):
    """结构化失败返回 502，不泄露内部细节。"""
    monkeypatch.chdir(tmp_path)
    from app.chains import tasksheet_chain
    from app.core.structured_output import StructuredOutputError

    def broken_invoke(messages, model_cls, **kwargs):
        raise StructuredOutputError("Tasksheet", RuntimeError("504 at internal"), 2)

    monkeypatch.setattr(tasksheet_chain, "invoke_structured", broken_invoke)
    resp = client.post("/v1/tasksheet", json={"topic": "测试课题"})
    assert resp.status_code == 502
    assert "internal" not in resp.json()["detail"]


def test_package_endpoint_ok(monkeypatch, tmp_path):
    """全案联产：三件并行生成，响应含 topic/ppt/lesson/tasksheet。"""
    monkeypatch.chdir(tmp_path)
    from app.chains import generation_chain

    fake_deck = {
        "title": "用例图建模入门",
        "outline": {
            "title": "t",
            "subtitle": "s",
            "sections": [{"name": "导入", "page_count": 1, "points": ["p"]}],
        },
        "pages": [{"title": "课程目标", "bullets": ["b"], "note": "n", "minutes": 5}],
    }

    async def fake_deck_async(topic, minutes=90):
        return fake_deck

    def fake_lesson(topic, minutes=45):
        return generation_chain.LessonPlan.model_validate(
            {
                "course_name": "用例图教学设计",
                "teaching_goals": {"knowledge": ["k"], "ability": ["a"], "literacy": ["l"]},
                "key_points": ["p"],
                "difficult_points": ["d"],
                "teaching_flow": [{"stage": "导入", "minutes": 5, "teacher_activity": "t", "student_activity": "s"}],
                "class_exercises": ["e"],
                "homework": ["h"],
            }
        )

    monkeypatch.setattr(generation_chain, "generate_ppt_deck_async", fake_deck_async)
    monkeypatch.setattr(generation_chain, "generate_lesson_plan", fake_lesson)

    from app.chains import tasksheet_chain

    def fake_invoke(messages, model_cls, **kwargs):
        return model_cls.model_validate(json.loads(TASKSHEET_JSON))

    monkeypatch.setattr(tasksheet_chain, "invoke_structured", fake_invoke)

    resp = client.post("/v1/package", json={"topic": "用例图建模入门", "minutes": 45})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"topic", "ppt", "lesson", "tasksheet"}
    assert body["ppt"]["download_url"].endswith(".pptx")
    assert body["lesson"]["download_url"].endswith(".docx")
    assert body["tasksheet"]["tasksheet"]["task_id"] == "WS-2026-SE01"


def test_package_single_part_failure_tolerated(monkeypatch, tmp_path):
    """单件失败容错：tasksheet 失败置 null，其余照常。"""
    monkeypatch.chdir(tmp_path)
    from app.chains import generation_chain, tasksheet_chain

    fake_deck = {
        "title": "t",
        "outline": {"title": "t", "subtitle": "s", "sections": [{"name": "n", "page_count": 1, "points": ["p"]}]},
        "pages": [{"title": "t", "bullets": ["b"], "note": "n", "minutes": 5}],
    }

    async def fake_deck_async(topic, minutes=90):
        return fake_deck

    def fake_lesson(topic, minutes=45):
        return generation_chain.LessonPlan.model_validate(
            {
                "course_name": "c",
                "teaching_goals": {"knowledge": ["k"], "ability": ["a"], "literacy": ["l"]},
                "key_points": ["p"],
                "difficult_points": ["d"],
                "teaching_flow": [{"stage": "导入", "minutes": 5, "teacher_activity": "t", "student_activity": "s"}],
                "class_exercises": ["e"],
                "homework": ["h"],
            }
        )

    monkeypatch.setattr(generation_chain, "generate_ppt_deck_async", fake_deck_async)
    monkeypatch.setattr(generation_chain, "generate_lesson_plan", fake_lesson)

    def broken_invoke(messages, model_cls, **kwargs):
        raise StructuredOutputErrorStatic("Tasksheet", RuntimeError("x"), 2)

    class StructuredOutputErrorStatic(RuntimeError):
        pass

    monkeypatch.setattr(tasksheet_chain, "invoke_structured", broken_invoke)

    resp = client.post("/v1/package", json={"topic": "联产容错测试", "minutes": 45})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ppt"] is not None
    assert body["lesson"] is not None
    assert body["tasksheet"] is None


def test_chat_adjust_endpoint_ok(monkeypatch):
    """对话式修正：Fake LLM 返回修正后模型 → 200 + success/model/plantuml/render。"""
    from app.chains import uml_adjust

    fake_out = uml_adjust.AdjustedOutput.model_validate(
        {
            "model": {
                "type": "usecase",
                "system": "校园二手交易系统",
                "actors": [{"name": "学生"}, {"name": "管理员"}],
                "usecases": [
                    {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
                    {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
                    {"id": "UC-03", "name": "浏览商品", "actors": ["学生"]},
                ],
                "relations": [],
            },
            "reply": "已将审核商品参与者改为审批专员",
            "diff_summary": "参与者重命名",
        }
    )

    def fake_adjust_sync(instruction, current_json, llm_factory=None):
        return fake_out

    monkeypatch.setattr(uml_adjust, "_adjust_sync", fake_adjust_sync)

    current = {
        "type": "usecase",
        "system": "校园二手交易系统",
        "actors": [{"name": "学生"}, {"name": "管理员"}],
        "usecases": [
            {"id": "UC-01", "name": "发布商品", "actors": ["学生"]},
            {"id": "UC-02", "name": "审核商品", "actors": ["管理员"]},
            {"id": "UC-03", "name": "浏览商品", "actors": ["学生"]},
        ],
        "relations": [],
    }
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "把审核商品的参与者改为审批专员", "current_model": current, "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["plantuml"].startswith("@startuml")
    assert "issues" in body and "render" in body and "diff_summary" in body


def test_chat_adjust_invalid_current_model_422():
    """当前模型非法 → 422。"""
    resp = client.post(
        "/v1/uml/chat-adjust",
        json={"instruction": "改一下", "current_model": {"bad": 1}},
    )
    assert resp.status_code == 422
