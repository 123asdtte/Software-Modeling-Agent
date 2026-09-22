"""PlantUML 本地渲染服务测试（全部 mock subprocess，不调真实 Java）。

真实渲染链路已在本机验证（Java 21 + plantuml 1.2026.8 → PNG 魔数正确），
单元测试用 monkeypatch 模拟，保证离线稳定。
"""

import subprocess
from pathlib import Path

from app.renderers.diagram_renderer import RenderStatus, render_plantuml_source

SOURCE = '@startuml\nactor "学生" as a_1\n@enduml\n'


def _jar_ready(tmp_path: Path, monkeypatch) -> Path:
    """伪造 jar 存在的配置环境（settings 指向临时目录内假文件），返回配置根。"""
    from app.config.settings import get_settings

    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"PK")  # 仅需 is_file() 为真
    monkeypatch.chdir(tmp_path)
    s = get_settings()
    monkeypatch.setattr(s, "plantuml_jar_path", str(jar))
    monkeypatch.setattr(s, "java_command", "java")
    monkeypatch.setattr(s, "outputs_dir", str(tmp_path / "outputs"))
    monkeypatch.setattr(s, "plantuml_timeout", 10.0)
    return tmp_path


def _patch_run(monkeypatch, returncode: int = 0, produces: bool = True):
    """伪造 subprocess.run：按参数在 puml 同目录生成产物（模拟真实行为）。"""

    def fake_run(cmd, **kwargs):
        # 约束：参数列表 + shell=False + 固定 cwd
        assert isinstance(cmd, list)
        assert kwargs.get("shell") is False
        assert kwargs.get("cwd") is not None  # 输出目录不依赖进程启动目录
        puml = Path(cmd[-1])
        if returncode == 0 and produces:
            suffix = ".png" if "-tpng" in cmd else ".svg"
            puml.with_suffix(suffix).write_bytes(b"fake-image-bytes")
        return subprocess.CompletedProcess(cmd, returncode, "", "err" if returncode else "")

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fake_run)


def _work_dir(root: Path) -> Path:
    return root / "outputs" / "uml"


def test_render_success_png(tmp_path, monkeypatch):
    """渲染成功：RENDERED + filename 指向存储文件 + 临时产物清理（finally）。"""
    root = _jar_ready(tmp_path, monkeypatch)
    _patch_run(monkeypatch, 0, produces=True)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.RENDERED
    assert result.format == "png"
    assert result.filename and result.filename.endswith(".png")
    stored = _work_dir(root) / result.filename
    assert stored.read_bytes().startswith(b"fake-image")
    # finally 清理：work_dir 内无临时 render_* 残留
    leftovers = [p.name for p in _work_dir(root).glob("render_*")]
    assert leftovers == []


def test_render_success_svg(tmp_path, monkeypatch):
    """SVG：使用 -tsvg、产物扩展名 .svg。"""
    _jar_ready(tmp_path, monkeypatch)
    seen_cmds: list = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(cmd)
        puml = Path(cmd[-1])
        puml.with_suffix(".svg").write_bytes(b"fake-svg")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fake_run)
    result = render_plantuml_source(SOURCE, "svg")
    assert result.status == RenderStatus.RENDERED
    assert result.format == "svg"
    assert result.filename.endswith(".svg")
    assert any("-tsvg" in c for c in seen_cmds)


def test_output_dir_independent_of_cwd(tmp_path, monkeypatch):
    """进程工作目录变化后，渲染产物仍落在受控 outputs/uml（评审 P1）。"""
    root = _jar_ready(tmp_path, monkeypatch)
    _patch_run(monkeypatch, 0, produces=True)
    other_cwd = tmp_path / "somewhere-else"
    other_cwd.mkdir(exist_ok=True)
    monkeypatch.chdir(other_cwd)  # 模拟 uvicorn 从其他目录启动
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.RENDERED
    assert Path(result.filename).name == result.filename  # 只返回文件名，无路径
    assert (_work_dir(root) / result.filename).is_file()


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
    """进程失败：source_only，reason 不含命令行/路径/堆栈；finally 清理生效。"""
    root = _jar_ready(tmp_path, monkeypatch)

    def fail_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "java.lang.Exception at C:/secret")

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", fail_run)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "secret" not in (result.reason or "")
    assert "C:/" not in (result.reason or "")
    leftovers = [p.name for p in _work_dir(root).glob("render_*")]
    assert leftovers == []


def test_render_timeout_degrades(tmp_path, monkeypatch):
    """渲染超时：稳定降级并说明原因（finally 清理生效）。"""
    root = _jar_ready(tmp_path, monkeypatch)

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 10)

    monkeypatch.setattr("app.renderers.diagram_renderer.subprocess.run", slow_run)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "超时" in result.reason
    leftovers = [p.name for p in _work_dir(root).glob("render_*")]
    assert leftovers == []


def test_java_missing_degrades(tmp_path, monkeypatch):
    """java 命令不可用（进程启动 FileNotFoundError）降级，不抛未处理异常。"""
    _jar_ready(tmp_path, monkeypatch)
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "java_command", "definitely-not-exist-java")
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    assert "PlantUML 渲染环境不可用" in result.reason


def test_storage_failure_still_cleans(tmp_path, monkeypatch):
    """save_bytes_atomic 失败（如磁盘写满）也走 finally 清理并降级。"""
    root = _jar_ready(tmp_path, monkeypatch)
    _patch_run(monkeypatch, 0, produces=True)
    import app.renderers.diagram_renderer as dr

    def broken_save(kind, ext, data):
        raise OSError("磁盘写满")

    # patch 必须打在使用方命名空间（renderer 顶部 import 绑定）
    monkeypatch.setattr(dr, "save_bytes_atomic", broken_save)
    result = render_plantuml_source(SOURCE, "png")
    assert result.status == RenderStatus.SOURCE_ONLY
    leftovers = [p.name for p in _work_dir(root).glob("render_*")]
    assert leftovers == []


def test_invalid_format_rejected(tmp_path, monkeypatch):
    """非法格式直接降级拒绝（不进入 subprocess）。"""
    _jar_ready(tmp_path, monkeypatch)
    result = render_plantuml_source(SOURCE, "pdf")
    assert result.status == RenderStatus.SOURCE_ONLY
