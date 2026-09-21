"""模型工厂：统一从这里获取 LLM 实例，禁止在各 Agent 中直接实例化模型。

当前接入 DeepSeek V4.1（OpenAI 兼容接口）；后续如需切换豆包等其他
OpenAI 兼容模型，只需修改本工厂或 settings 配置，上层代码不动。
"""

from langchain_openai import ChatOpenAI

from app.config.settings import Settings, get_settings


def get_llm(settings: Settings | None = None) -> ChatOpenAI:
    """按配置返回 DeepSeek LLM 实例（工厂方法）。

    Args:
        settings: 配置对象；不传则读取全局配置。

    Returns:
        ChatOpenAI: 已配置 base_url / api_key / 模型名的实例。

    Raises:
        ValueError: 缺少 API Key 时抛出，提示先配置 .env。
    """
    settings = settings or get_settings()
    if not settings.deepseek_api_key:
        raise ValueError(
            "未配置 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填写密钥。"
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.deepseek_api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.request_timeout,
    )
