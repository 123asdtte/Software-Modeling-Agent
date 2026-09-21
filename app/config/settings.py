"""全局配置：从环境变量与 .env 读取，禁止在代码中硬编码敏感信息。

注意：用户机器可能存在同名环境变量（如旧的 DEEPSEEK_API_KEY），
因此本项目 .env 使用 override=True 强制优先于系统环境变量，
避免程序误用旧密钥。
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    # 大模型（DeepSeek V4.1，OpenAI 兼容接口）
    deepseek_api_key: str = ""
    model_provider: str = "deepseek"  # deepseek / openai_compatible，预留切换
    model_name: str = "deepseek-flash"  # DeepSeek-V4.1-Flash；高配可换 deepseek-v4-pro
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.3
    max_tokens: int = 2048
    request_timeout: float = 60.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例配置（进程内缓存，避免重复读 .env）。"""
    return Settings()
