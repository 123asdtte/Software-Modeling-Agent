"""可选的真实 PlantUML 渲染集成测试（默认 skip）。

启用：RUN_RENDER_INTEGRATION_TESTS=1 且 tools/plantuml.jar 存在。
执行：RUN_RENDER_INTEGRATION_TESTS=1 pytest -m render_integration -q
"""

import os
from pathlib import Path

import pytest

from app.renderers.diagram_renderer import RenderStatus, render_plantuml_source
from app.storage.generated_files import resolve_download_path

pytestmark = [pytest.mark.integration, pytest.mark.render_integration]

SOURCE = "@startuml" + chr(10) + 'actor "学生" as a_1' + chr(10) + "@enduml" + chr(10)


def _enabled() -> bool:
    return os.getenv("RUN_RENDER_INTEGRATION_TESTS") == "1" and Path("tools/plantuml.jar").is_file()


def test_real_render_png_and_svg():
    """真实渲染：PNG 与 SVG 均成功且可被下载解析。"""
    if not _enabled():
        pytest.skip("未启用渲染集成测试（需 RUN_RENDER_INTEGRATION_TESTS=1 与 tools/plantuml.jar）")
    png = render_plantuml_source(SOURCE, "png")
    assert png.status == RenderStatus.RENDERED
    assert png.filename.endswith(".png")
    stored = resolve_download_path("uml", png.filename)
    assert stored is not None and stored.read_bytes()[:4] == b"\x89PNG"

    svg = render_plantuml_source(SOURCE, "svg")
    assert svg.status == RenderStatus.RENDERED
    assert svg.filename.endswith(".svg")
    stored_svg = resolve_download_path("uml", svg.filename)
    assert stored_svg is not None
    assert stored_svg.read_bytes()[:5].lower() == b"<?xml" or stored_svg.read_bytes()[:4] == b"<svg"
