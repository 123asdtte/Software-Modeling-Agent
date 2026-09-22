"""生成文件安全存储测试（原子写入 / 白名单 / 穿越防护）。"""

import pytest

from app.storage.generated_files import (
    cleanup_tmp,
    resolve_download_path,
    save_bytes_atomic,
)


def test_save_and_resolve_roundtrip(tmp_path, monkeypatch):
    """保存 → 按文件名解析回真实路径。"""
    monkeypatch.chdir(tmp_path)
    name = save_bytes_atomic("uml", "png", b"\x89PNG fake")
    assert name.endswith(".png") and len(name.split(".")[0]) == 32
    path = resolve_download_path("uml", name)
    assert path is not None and path.read_bytes() == b"\x89PNG fake"


def test_save_rejects_bad_extension(tmp_path, monkeypatch):
    """白名单外扩展名（uml 只允许 png/svg）拒绝。"""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        save_bytes_atomic("uml", "exe", b"MZ")
    with pytest.raises(ValueError):
        save_bytes_atomic("uml", "md", b"x")


def test_resolve_rejects_traversal(tmp_path, monkeypatch):
    """路径穿越 / 非法文件名一律 None（API 层映射 404）。"""
    monkeypatch.chdir(tmp_path)
    for bad in ["../../.env", "not-a-uuid.png", "a/b.png", "x.svg.txt", "..%2F.env"]:
        assert resolve_download_path("uml", bad) is None


def test_resolve_missing_file_is_none(tmp_path, monkeypatch):
    """uuid 合法但文件不存在 → None。"""
    monkeypatch.chdir(tmp_path)
    assert resolve_download_path("uml", f"{'a' * 32}.png") is None


def test_atomic_write_no_tmp_leftover(tmp_path, monkeypatch):
    """原子替换后不残留 .tmp 文件。"""
    monkeypatch.chdir(tmp_path)
    name = save_bytes_atomic("lesson", "docx", b"PK docx")
    assert resolve_download_path("lesson", name) is not None
    leftovers = list((tmp_path / "outputs" / "lesson").glob("*.tmp"))
    assert leftovers == []


def test_cleanup_tmp(tmp_path, monkeypatch):
    """cleanup_tmp 删除 .tmp（不存在时静默）。"""
    monkeypatch.chdir(tmp_path)
    tmp = tmp_path / "outputs" / "uml" / "abc.png.tmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(b"half")
    cleanup_tmp("uml", "abc.png")
    assert not tmp.exists()
    cleanup_tmp("uml", "abc.png")  # 幂等
