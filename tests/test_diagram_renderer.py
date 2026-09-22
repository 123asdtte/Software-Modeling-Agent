"""PlantUML 本地渲染服务测试（全部 mock subprocess，不调真实 Java）。

真实渲染链路已在本机验证（Java 21 + plantuml 1.2026.8 → PNG 魔数正确），
单元测试用 monkeypatch 模拟，保证离线稳定。
"""

import subprocess
from pathlib import Path

from app.renderers.diagram_renderer import RenderStatus, render_plantuml_source

SOURCE = '@startuml\nactor "学生" as a_1\n@enduml\n'


def _jar_ready(tmp_path: Path, monkeypatch) -> None:
    """伪造 jar 存在的配置环境（settings 指向临时目录内假文件）。"""
    from app.config.settings import get_settings

    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"PK")  # 仅需 is_file() 为真
    monkeypatch.chdir(tmp_path)
    s = get_settings()
    monkeypatch.setattr(s, "plantuml_jar_path", str(jar))
    monkeypatch.setattr(s, "java_command", "java")
    monkeypatch.setattr(s, "outputs_dir", str(tmp_path / "outputs"))
    monkeypatch.setattr(s, "plantuml_timeout", 10.0)


def _patch_run(monkeypatch, returncode: int, produces_png: bool):
    """伪造 subprocess.run：按参数生成产物文件。"""
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        # 约束：参数列表 + shell=False
        assert isinstance(cmd, list)
        assert kwargs.get("shell") is False
        puml = Path(cmd[-1])
        out = puml.with_suffix(".png")
        if returncode == 0 and produces_png:
            out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake")
        return subprocess.CompletedProcess(cmd, returncode, "", "err" if returncode else "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fake_run)
    return original_run


def test_render_success_png(tmp_path, monkeypatch):
    """渲染成功：RENDERED + 正式存储文件存在 + 临时文件清理。"""
    _jar_ready(tmp_path, monkeypatch)
    produced: list = []

    def fake_run(cmd, **kwargs):
        puml = Path(cmd[-1])
        out = puml.with_suffix(".png")
        out.write_bytes(b"\x89PNG fake")
        produced.append(out)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fake_run)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.RENDERED
    assert result.format == "png"
    assert Path(result.path).read_bytes().startswith(b"\x89PNG")
    assert not produced[0].exists()  # 临时产物已清理


def test_render_success_svg(tmp_path, monkeypatch):
    """SVG 格式渲染成功。"""
    _jar_ready(tmp_path, monkeypatch)

    def fake_run(cmd, **kwargs):
        puml = Path(cmd[-1])
        puml.with_suffix(".svg").write_bytes(b"<svg>ok</svg>")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fake_run)
    result = render_plantuml_source(SOURCE, "svg")
    assert result.status == RenderStatus.RENDERED
    assert result.format == "svg"


def test_environment_missing_degrades(tmp_path, monkeypatch):
    """jar 不存在：source_only + 原因说明，不抛异常。"""
    monkeypatch.chdir(tmp_path)
    from app.config.settings import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "plantuml_jar_path", str(tmp_path / "nope.jar"))
    monkeypatch.setattr(s, "outputs_dir", str(tmp_path / "outputs"))
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "plantuml.jar" in result.reason


def test_process_failure_degrades_without_leak(tmp_path, monkeypatch):
    """进程失败：source_only，reason 不含命令行/路径/堆栈。"""
    _jar_ready(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.renderers.diagram_renderer.subprocess.run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "java.lang.Exception at C:/secret"),
    )
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "secret" not in (result.reason or "")
    assert "C:/" not in (result.reason or "")


def test_render_timeout_degrades(tmp_path, monkeypatch):
    """渲染超时：稳定降级并说明原因。"""
    _jar_ready(tmp_path, monkeypatch)

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 10)

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", slow_run)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "超时" in result.reason


def test_invalid_format_rejected(tmp_path, monkeypatch):
    """非法格式直接降级拒绝（不进入 subprocess）。"""
    _jar_ready(tmp_path, monkeypatch)
    result = render_plantuml_source(SOURCE, "pdf")
    assert result.status == RenderStatus.SOURCE_ONLY


def test_java_missing_degrades(tmp_path, monkeypatch):
    """java 命令不可用（进程启动失败）降级，不抛未处理异常。"""
    _jar_ready(tmp_path, monkeypatch)
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "java_command", "definitely-not-exist-java")
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
