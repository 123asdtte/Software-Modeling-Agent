"""M5 前端静态页挂载测试（纯静态断言，不调 LLM）。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_page_served():
    """GET / 返回 Demo 首页（入口）。"""
    r = client.get("/")
    assert r.status_code == 200
    assert "AI 教学智能体平台" in r.text


def test_all_pages_served():
    """四个页面均可通过 /static 访问。"""
    for page in ("index.html", "uml.html", "qa.html", "resources.html"):
        assert client.get(f"/static/{page}").status_code == 200


def test_static_assets_served():
    """CSS/JS 资源可访问。"""
    for asset in ("/static/css/tokens.css", "/static/css/main.css", "/static/js/api.js", "/static/js/uml.js"):
        assert client.get(asset).status_code == 200


def test_static_traversal_blocked():
    """静态挂载不允许穿越到项目外文件。"""
    assert client.get("/static/../.env").status_code in (404, 400, 403)


def test_frontend_uses_relative_api_paths():
    """前端 JS 不得硬编码绝对地址（同源部署约束，设计文档 §2.3）。"""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "static"
    for js in (root / "js").glob("*.js"):
        src = js.read_text(encoding="utf-8")
        assert not re.search(r"http://|https://", src), f"{js.name} 含硬编码地址"
