"""全局配置：从环境变量与 .env 读取，禁止在代码中硬编码敏感信息。

注意：用户机器可能存在同名环境变量（如旧的 DEEPSEEK_API_KEY），
因此本项目 .env 使用 override=True 强制优先于系统环境变量，
避免程序误用旧密钥。
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根（app/config/ 向上 2 级）：相对配置路径统一基于项目根解析，
# 不依赖进程启动 cwd（渲染子进程会切换 cwd）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(p: str | Path) -> Path:
    """相对路径基于项目根解析；绝对路径原样返回。"""
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


# 项目 .env 为权威配置，覆盖系统/用户级同名环境变量
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    """应用配置项。

    所有配置统一从这里读取：密钥走环境变量 / .env 文件，
    非敏感默认值（模型名、超时等）也可在此调整。
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    app_name: str = "AI-Education-Agent"
    app_version: str = "0.1.0"
    debug: bool = False

    # 大模型（TokenRhythm 平台 glm-5.3-flash，OpenAI 兼容接口；
    # 历史字段名 deepseek_api_key 沿用，改字段名需同步 .env 全量变更，不值当）
    deepseek_api_key: str = ""
    model_provider: str = "tokenrhythm"  # tokenrhythm / openai_compatible / deepseek，预留切换
    model_name: str = "glm-5.3-flash"  # 推理模型：reasoning 与回答共用 max_tokens 预算
    base_url: str = "https://tokenrhythm.studio/v1"
    # glm-5.3-flash 推理模型长回答实测可超 60s，单请求与整体墙钟同步放宽
    temperature: float = 0.3
    # deepseek-flash 为推理模型：reasoning tokens 与回答共用 max_tokens 预算，
    # 过小会导致 content 被 reasoning 吃空（实测 max_tokens=10 时 content 为空）
    max_tokens: int = 4096
    request_timeout: float = 90.0

    # /v1/qa 演示安全兜底：整体墙钟 + 并发上限 + 检索预算（LightRAG 默认
    # chunk_top_k=20、max_total_tokens=30000，会返回 2 万字符上下文，必须收紧）
    qa_timeout: float = 90.0
    qa_max_concurrency: int = 3
    qa_chunk_top_k: int = 6
    qa_max_total_tokens: int = 8000
    qa_max_entity_tokens: int = 1500
    qa_max_relation_tokens: int = 2000
    qa_context_max_chars: int = 12000
    qa_answer_retries: int = 1

    # 教学资源生成（PPT/教案）：结构化 JSON 多次调用，耗时高于 QA，放宽墙钟
    # glm-5.3-flash 为推理模型，单次大 JSON（教案 9 字段）生成实测可超 60s，
    # 单请求超时须与整条链路墙钟（gen_timeout）区分
    gen_timeout: float = 180.0
    gen_llm_timeout: float = 150.0
    gen_max_concurrency: int = 2
    outputs_dir: str = "outputs"

    # UML 用例图生成：独立并发/超时（不与 PPT/教案共享模糊的全局限制）
    uml_timeout: float = 150.0
    uml_llm_timeout: float = 150.0
    uml_max_concurrency: int = 2

    # PlantUML 本地图片渲染（jar 需手工放置，不进 Git；缺失时 API 降级返回源码）
    java_command: str = "java"
    plantuml_jar_path: str = "tools/plantuml.jar"
    plantuml_timeout: float = 60.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例配置（进程内缓存，避免重复读 .env）。"""
    return Settings()
