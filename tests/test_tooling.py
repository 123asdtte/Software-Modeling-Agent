"""工程质量基线配置的最小验证测试（纯标准库，不新增依赖）。

作用：pyproject.toml 若被误删/误改关键配置，本测试会失败，
保证 Ruff / pytest 基线可被 CI 和人工检查。
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _load() -> dict:
    with PYPROJECT.open("rb") as fp:
        return tomllib.load(fp)


def test_pyproject_exists_and_parses():
    """pyproject.toml 存在且是合法 TOML。"""
    assert PYPROJECT.is_file()
    data = _load()
    assert data["project"]["name"] == "ai-education-agent"


def test_ruff_baseline_config():
    """Ruff 基线：目标版本、行宽、规则集锁定。"""
    cfg = _load()["tool"]["ruff"]
    assert cfg["target-version"] == "py314"  # 与 venv 实际版本一致
    assert cfg["line-length"] == 120
    assert set(cfg["lint"]["select"]) == {"E", "F", "I", "B", "SIM"}
    # scripts 的 sys.path 插桩为刻意行为，E402 豁免必须有据可查
    assert "E402" in cfg["lint"]["per-file-ignores"]["scripts/*"]


def test_pytest_testpaths():
    """pytest 只从 tests/ 发现测试（保留现有发现方式）。"""
    assert _load()["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_eval_scripts_excluded_from_pytest_discovery():
    """评测脚本不以 test_ 开头，不会被 pytest 误收集。"""
    eval_dir = ROOT / "tests" / "evaluation"
    assert eval_dir.is_dir()
    collected = [p.name for p in eval_dir.glob("test_*.py")]
    assert collected == []
