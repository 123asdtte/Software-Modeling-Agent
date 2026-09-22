"""模型工厂：统一从这里获取 LLM 实例，禁止在各 Agent 中直接实例化模型。

当前走 TokenRhythm（基元律动）平台的 glm-5.3-flash（OpenAI 兼容接口，
推理模型）；如需切换其他 OpenAI 兼容模型，只需修改 settings 配置
（BASE_URL / MODEL_NAME / DEEPSEEK_API_KEY），上层代码不动。

timeout 参数化的原因：QA 单问输出短，默认 60s 够用；PPT/教案的大 JSON
生成（推理模型）实测可超 60s，需要更长的单请求超时（settings.gen_llm_timeout）。
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config.settings import get_settings


@lru_cache(maxsize=4)
def get_llm(timeout: float | None = None) -> ChatOpenAI:
    """按配置返回 LLM 实例（工厂方法，按超时值缓存复用客户端）。

    Args:
        timeout: 单请求超时（秒）；缺省用 settings.request_timeout。

    Returns:
        ChatOpenAI: 已配置 base_url / api_key / 模型名的实例。

    Raises:
        ValueError: 缺少 API Key 时抛出，提示先配置 .env。
    """
    settings = get_settings()
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
        timeout=timeout if timeout is not None else settings.request_timeout,
    )
