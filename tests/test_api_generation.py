"""/v1/ppt、/v1/lesson 端点测试（mock 生成链，不调 LLM）。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FAKE_DECK = {
    "outline": {"title": "用例图建模入门", "subtitle": "s", "sections": []},
    "pages": [
        {"title": "课程目标", "bullets": ["a", "b"], "note": "n", "minutes": 5},
        {"title": "知识讲解", "bullets": ["c"], "note": "n2", "minutes": 4},
    ],
}


def test_ppt_endpoint_ok(monkeypatch, tmp_path):
    """mock 链路后应返回大纲 + 页 + 下载地址，且文件真实生成。"""
    monkeypatch.chdir(tmp_path)  # outputs 落盘到临时目录

    async def fake_deck(topic, minutes=90):
        return FAKE_DECK

    from app.chains import generation_chain

    monkeypatch.setattr(generation_chain, "generate_ppt_deck_async", fake_deck)
    # main.py 内是函数内延迟 import，monkeypatch 生成链模块属性即可生效

    resp = client.post("/v1/ppt", json={"topic": "用例图建模", "minutes": 45})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_pages"] == 2
    assert body["download_url"].startswith("/files/ppt/")
    assert body["download_url"].endswith(".pptx")
    # 下载回环
    dl = client.get(body["download_url"])
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # pptx 是 zip


def test_ppt_endpoint_rejects_short_topic():
    """课题过短应 422。"""
    resp = client.post("/v1/ppt", json={"topic": "图", "minutes": 45})
    assert resp.status_code == 422


def test_ppt_endpoint_502_on_error(monkeypatch):
    """生成异常统一 502。"""
    from app.chains import generation_chain

    async def boom(topic, minutes=90):
        raise RuntimeError("结构化生成失败")

    monkeypatch.setattr(generation_chain, "generate_ppt_deck_async", boom)
    resp = client.post("/v1/ppt", json={"topic": "用例图建模", "minutes": 45})
    assert resp.status_code == 502


def test_lesson_endpoint_ok(monkeypatch, tmp_path):
    """教案端点返回 9 字段 JSON + markdown + docx 下载。"""
    monkeypatch.chdir(tmp_path)

    from app.chains import generation_chain

    fake_lesson = generation_chain.LessonPlan.model_validate({
        "course_name": "用例图教学设计",
        "teaching_goals": {"knowledge": ["k"], "ability": ["a"], "literacy": ["l"]},
        "key_points": ["p"],
        "difficult_points": ["d"],
        "teaching_flow": [
            {"stage": "导入", "minutes": 5, "teacher_activity": "t", "student_activity": "s"},
            {"stage": "讲解", "minutes": 15, "teacher_activity": "t", "student_activity": "s"},
            {"stage": "案例", "minutes": 10, "teacher_activity": "t", "student_activity": "s"},
            {"stage": "互动", "minutes": 8, "teacher_activity": "t", "student_activity": "s"},
            {"stage": "小结", "minutes": 7, "teacher_activity": "t", "student_activity": "s"},
        ],
        "class_exercises": ["e1", "e2"],
        "homework": ["h1", "h2"],
    })

    def fake_lesson_gen(topic, minutes=45):
        return fake_lesson

    monkeypatch.setattr(generation_chain, "generate_lesson_plan", fake_lesson_gen)
    resp = client.post("/v1/lesson", json={"topic": "用例图教学设计", "minutes": 45})
    assert resp.status_code == 200
    body = resp.json()
    assert body["missing_fields"] == []
    assert "教学目标" in body["markdown"]
    assert body["download_url"].endswith(".docx")
    dl = client.get(body["download_url"])
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"


def test_download_rejects_path_traversal():
    """非法文件名（穿越/任意文件）应 404。"""
    assert client.get("/files/ppt/..%2F..%2F.env").status_code in (404, 400)
    assert client.get("/files/ppt/not-a-uuid.pptx").status_code == 404
