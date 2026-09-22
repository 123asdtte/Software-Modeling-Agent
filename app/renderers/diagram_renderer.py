"""PlantUML 本地图片渲染服务：PlantUML 源码 → PNG/SVG 文件。

安全与健壮性约束（评审冻结）：
- subprocess 参数列表 + shell=False + 超时，禁止 shell=True / os.system / 用户输入拼命令；
- 输出目录由代码控制（outputs/uml/），文件名 UUID，不接受用户指定路径；
- 只允许 png / svg；
- Java/jar 路径与超时全部来自 settings（环境变量可覆盖）；
- 渲染环境缺失（java/jar 不存在）→ SOURCE_ONLY 降级，不抛未处理异常；
- PlantUML 进程失败 → 记日志并返回带 reason 的 SOURCE_ONLY（API 层仍返回 200 + 源码）；
- 不在 import 阶段探测或启动外部进程。
"""

import subprocess
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.config.settings import get_settings
from app.storage.generated_files import cleanup_tmp, save_bytes_atomic

SUPPORTED_FORMATS = ("png", "svg")


class RenderStatus(str, Enum):
    """渲染结果状态：成功 / 降级（仅返回源码）。"""

    RENDERED = "rendered"
    SOURCE_ONLY = "source_only"


class RenderResult(BaseModel):
    """渲染结果：path 仅供服务端使用，绝不写入客户端响应。"""

    status: RenderStatus
    format: Literal["png", "svg"] | None = None
    path: str | None = None
    reason: str | None = None


def _environment_ready() -> tuple[bool, str | None]:
    """探测 plantuml.jar 是否就绪；不可用返回原因。

    不预跑 java -version 探测（避免每次渲染多一个子进程）：
    java 不可用会在渲染 subprocess 抛 FileNotFoundError，由调用处捕获降级。
    """
    jar = Path(get_settings().plantuml_jar_path)
    if not jar.is_file():
        return False, "PlantUML 渲染环境不可用（缺少 plantuml.jar）"
    return True, None


def render_plantuml_source(source: str, output_format: Literal["png", "svg"] = "png") -> RenderResult:
    """把 PlantUML 源码渲染为 PNG/SVG 文件（失败降级为仅源码）。

    Args:
        source: 完整 PlantUML 源码（来自确定性 renderer，非用户原始输入）。
        output_format: 目标格式，只允许 png / svg。

    Returns:
        RenderResult：RENDERED（path 为服务端内部路径）或 SOURCE_ONLY（带 reason）。
    """
    if output_format not in SUPPORTED_FORMATS:
        return RenderResult(status=RenderStatus.SOURCE_ONLY, format=None, reason=f"不支持的格式：{output_format}")

    ready, reason = _environment_ready()
    if not ready:
        return RenderResult(status=RenderStatus.SOURCE_ONLY, format=None, reason=reason)

    settings = get_settings()
    filename = f"render_{id(source) & 0xFFFFFFFF:08x}"  # 占位名仅用于临时文件；最终文件由 storage 重命名
    tmp_puml = Path(settings.outputs_dir) / "uml" / f"{filename}.puml"
    tmp_puml.parent.mkdir(parents=True, exist_ok=True)
    tmp_puml.write_text(source, encoding="utf-8")

    out_opt = "-tpng" if output_format == "png" else "-tsvg"
    try:
        proc = subprocess.run(
            [
                settings.java_command,
                "-jar",
                settings.plantuml_jar_path,
                out_opt,
                "-charset",
                "UTF-8",
                "-o",
                ".",
                str(tmp_puml),
            ],
            capture_output=True,
            text=True,
            timeout=settings.plantuml_timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("PlantUML 渲染超时（>%ss）", settings.plantuml_timeout)
        tmp_puml.unlink(missing_ok=True)
        cleanup_tmp("uml", tmp_puml.stem)
        return RenderResult(
            status=RenderStatus.SOURCE_ONLY,
            format=None,
            reason=f"图片渲染超时（>{settings.plantuml_timeout:.0f}s）",
        )
    except FileNotFoundError as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("PlantUML 渲染进程启动失败：%s", exc)
        tmp_puml.unlink(missing_ok=True)
        return RenderResult(status=RenderStatus.SOURCE_ONLY, format=None, reason="PlantUML 渲染环境不可用")

    produced = tmp_puml.with_suffix(f".{output_format}")
    if proc.returncode != 0 or not produced.is_file():
        logger = __import__("logging").getLogger(__name__)
        logger.warning("PlantUML 渲染失败（exit=%s, stderr=%s）", proc.returncode, (proc.stderr or "")[:200])
        tmp_puml.unlink(missing_ok=True)
        produced.unlink(missing_ok=True)
        return RenderResult(
            status=RenderStatus.SOURCE_ONLY,
            format=None,
            reason="图片渲染失败（源码语法或环境问题）",
        )

    # 成功：读出图片字节 → 原子写入正式存储（UUID 命名）→ 清理临时文件
    image_bytes = produced.read_bytes()
    saved_name = save_bytes_atomic("uml", output_format, image_bytes)
    tmp_puml.unlink(missing_ok=True)
    produced.unlink(missing_ok=True)

    saved_path = Path(settings.outputs_dir) / "uml" / saved_name
    return RenderResult(status=RenderStatus.RENDERED, format=output_format, path=str(saved_path))
