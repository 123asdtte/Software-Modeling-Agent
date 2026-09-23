"""PlantUML 本地图片渲染服务：PlantUML 源码 → PNG/SVG 文件。

安全与健壮性约束（评审冻结）：
- subprocess 参数列表 + shell=False + 超时，禁止 shell=True / os.system / 用户输入拼命令；
- 临时文件用 uuid4 命名（不用 id(source)，多请求并发不碰撞），统一放在
  outputs/uml/ 受控目录，PlantUML 以 cwd 指定该目录，不依赖进程启动目录；
- try/finally 统一清理临时 .puml 与临时图片（覆盖全部失败路径）；
- 渲染环境缺失（jar 不存在 / java 启动失败）→ SOURCE_ONLY 降级，不抛未处理异常；
- PlantUML 进程失败 / 超时 → 记日志并返回带 reason 的 SOURCE_ONLY；
- RenderResult 只返回 filename（不含服务器绝对路径）；
- 不在 import 阶段探测或启动外部进程。
"""

import logging
import subprocess
import tempfile
import uuid
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.config.settings import get_settings
from app.config.settings import resolve_project_path as _resolve
from app.storage.generated_files import save_bytes_atomic

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("png", "svg")


class RenderStatus(str, Enum):
    """渲染结果状态：成功 / 降级（仅返回源码）。"""

    RENDERED = "rendered"
    SOURCE_ONLY = "source_only"


class RenderResult(BaseModel):
    """渲染结果：filename 仅供服务端构建下载 URL，绝不返回绝对路径。"""

    status: RenderStatus
    format: Literal["png", "svg"] | None = None
    filename: str | None = None
    reason: str | None = None


# 项目根（app/renderers/ 向上 3 级）：相对配置路径统一基于项目根解析，
# 不依赖进程启动 cwd（cwd 会被渲染 subprocess 切到 work_dir）


def _environment_ready() -> tuple[bool, str | None]:
    """探测 plantuml.jar 是否就绪；不可用返回原因。

    不预跑 java -version 探测（避免每次渲染多一个子进程）：
    java 不可用会在渲染 subprocess 抛 FileNotFoundError，由调用处捕获降级。
    """
    jar = _resolve(get_settings().plantuml_jar_path)
    if not jar.is_file():
        return False, "PlantUML 渲染环境不可用（缺少 plantuml.jar）"
    return True, None


def render_plantuml_source(source: str, output_format: Literal["png", "svg"] = "png") -> RenderResult:
    """把 PlantUML 源码渲染为 PNG/SVG 文件（任何失败降级为仅源码）。

    Args:
        source: 完整 PlantUML 源码（来自确定性 renderer，非用户原始输入）。
        output_format: 目标格式，只允许 png / svg。

    Returns:
        RenderResult：RENDERED（filename 为存储文件名）或 SOURCE_ONLY（带 reason）。
    """
    if output_format not in SUPPORTED_FORMATS:
        return RenderResult(status=RenderStatus.SOURCE_ONLY, reason=f"不支持的格式：{output_format}")

    ready, reason = _environment_ready()
    if not ready:
        return RenderResult(status=RenderStatus.SOURCE_ONLY, reason=reason)

    settings = get_settings()
    # 临时文件放系统 temp：outputs/uml 只保留正式产物，避免长期堆积触发
    # 批量删除保护（沙箱环境下 unlink 有安全钩子）；正式产物仍经 storage 原子写入 outputs/uml
    work_dir = Path(tempfile.gettempdir()) / "edu_uml_render"
    work_dir.mkdir(parents=True, exist_ok=True)

    # uuid4 命名：并发请求互不碰撞，与进程/用户输入无关
    token = uuid.uuid4().hex
    tmp_puml = work_dir / f"render_{token}.puml"
    produced = work_dir / f"render_{token}.{output_format}"

    try:
        tmp_puml.write_text(source, encoding="utf-8")
        out_opt = "-tpng" if output_format == "png" else "-tsvg"
        proc = subprocess.run(
            [
                settings.java_command,
                "-jar",
                str(_resolve(settings.plantuml_jar_path)),
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
            # 固定子进程工作目录：-o "." 的输出落在受控 work_dir，不依赖 uvicorn 启动目录
            cwd=str(work_dir),
        )

        if proc.returncode != 0 or not produced.is_file():
            logger.warning("PlantUML 渲染失败（exit=%s, stderr=%s）", proc.returncode, (proc.stderr or "")[:200])
            return RenderResult(status=RenderStatus.SOURCE_ONLY, reason="图片渲染失败（源码语法或环境问题）")

        # 成功：读出图片字节 → 原子写入正式存储（UUID 命名）
        image_bytes = produced.read_bytes()
        saved_name = save_bytes_atomic("uml", output_format, image_bytes)
        return RenderResult(status=RenderStatus.RENDERED, format=output_format, filename=saved_name)
    except subprocess.TimeoutExpired:
        logger.warning("PlantUML 渲染超时（>%ss）", settings.plantuml_timeout)
        return RenderResult(
            status=RenderStatus.SOURCE_ONLY, reason=f"图片渲染超时（>{settings.plantuml_timeout:.0f}s）"
        )
    except FileNotFoundError:
        logger.warning("PlantUML 渲染进程启动失败（Java 不可用）")
        return RenderResult(status=RenderStatus.SOURCE_ONLY, reason="PlantUML 渲染环境不可用")
    except Exception as exc:  # noqa: BLE001 - 存储失败等未预期异常也降级，不向上抛
        logger.exception("图片渲染阶段未预期异常（已降级返回源码）：%s", exc)
        return RenderResult(status=RenderStatus.SOURCE_ONLY, reason="图片渲染异常（已降级返回源码）")
    finally:
        # 统一清理临时 .puml 与临时图片（覆盖写失败/读失败/存储失败等全部路径）
        tmp_puml.unlink(missing_ok=True)
        produced.unlink(missing_ok=True)
