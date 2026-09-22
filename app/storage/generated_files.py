"""生成文件安全存储：UUID 命名、原子写入、下载路径白名单校验。

安全策略（评审冻结）：
- 文件名由服务端生成（uuid4.hex），绝不接受用户输入的文件名或路径；
- 下载路径解析走扩展名白名单 + uuid 格式校验，防 `../`、URL 编码穿越与绝对路径；
- 写入采用「临时文件 → os.replace 原子替换」，避免客户端下载到半成品；
- 渲染失败时由调用方负责清理临时文件（本模块提供 cleanup）。
"""

import os
import uuid
from pathlib import Path

from app.config.settings import get_settings

# 每类生成文件允许的扩展名（下载白名单）
ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "ppt": {"pptx"},
    "lesson": {"docx"},
    "uml": {"png", "svg"},
}


def _base_dir() -> Path:
    return Path(get_settings().outputs_dir)


def save_bytes_atomic(kind: str, ext: str, data: bytes) -> str:
    """把字节内容原子写入 outputs/<kind>/<uuid>.<ext>，返回服务端文件名。

    Raises:
        ValueError: kind 或 ext 不在白名单。
    """
    ext = ext.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS.get(kind, set()):
        raise ValueError(f"kind={kind} 不允许扩展名 .{ext}")
    file_id = uuid.uuid4().hex
    target = _base_dir() / kind / f"{file_id}.{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.with_suffix(f".{ext}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)  # 原子替换，避免半成品被下载
    return f"{file_id}.{ext}"


def save_text_atomic(kind: str, ext: str, text: str) -> str:
    """文本版本：编码 UTF-8 后走同一原子写入路径。"""
    return save_bytes_atomic(kind, ext, text.encode("utf-8"))


def cleanup_tmp(kind: str, filename: str) -> None:
    """渲染失败时清理 .tmp 临时文件（不存在则忽略）。"""
    tmp = _base_dir() / kind / f"{filename}.tmp"
    tmp.unlink(missing_ok=True)


def resolve_download_path(kind: str, filename: str) -> Path | None:
    """解析下载请求：白名单通过且文件存在返回真实路径，否则 None。

    防线：uuid+扩展名正则（拒绝 ../、绝对路径、URL 编码穿越、非法扩展名）。
    """
    exts = "|".join(sorted(ALLOWED_EXTENSIONS.get(kind, set())))
    if not exts:
        return None
    stem = "[0-9a-f]{32}"
    import re

    if not re.fullmatch(rf"{stem}\.({exts})", filename):
        return None
    path = _base_dir() / kind / filename
    if not path.is_file():
        return None
    return path
