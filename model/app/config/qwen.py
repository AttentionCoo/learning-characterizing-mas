import os
from typing import Any


DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_CHAT_MODEL_DEFAULTS = {
    "max": "qwen-max",
    "plus": "qwen-plus",
    "turbo": "qwen-turbo",
}


def get_qwen_api_key(*, required: bool = True) -> str | None:
    """读取百炼 API Key，兼容项目已有的两个变量名。"""
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if required and not api_key:
        raise ValueError("QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量未设置")
    return api_key


def get_qwen_base_url() -> str:
    return os.getenv("QWEN_BASE_URL") or DEFAULT_QWEN_BASE_URL


def _force_turbo() -> bool:
    """全量切换开关：所有对话模型档位统一使用 qwen-turbo（省成本/提速演示）。

    需要恢复 max/plus/turbo 分档时，设 QWEN_FORCE_TURBO=false（或按档位覆盖 QWEN_MODEL_*）。
    """
    return os.getenv("QWEN_FORCE_TURBO", "true").lower() not in ("false", "0", "no")


def get_qwen_chat_model_name(tier: str) -> str:
    if tier not in _CHAT_MODEL_DEFAULTS:
        raise ValueError(f"不支持的 Qwen 模型档位: {tier}")
    if _force_turbo():
        return os.getenv("QWEN_MODEL_TURBO") or _CHAT_MODEL_DEFAULTS["turbo"]
    return os.getenv(f"QWEN_MODEL_{tier.upper()}") or _CHAT_MODEL_DEFAULTS[tier]


def create_qwen_chat_model(
    tier: str,
    *,
    model_name: str | None = None,
    **kwargs: Any,
):
    """创建统一走百炼 OpenAI 兼容接口的 Qwen 对话模型。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name or get_qwen_chat_model_name(tier),
        base_url=get_qwen_base_url(),
        api_key=get_qwen_api_key(),
        **kwargs,
    )


def get_qwen_embedding_model() -> str:
    return os.getenv("QWEN_EMBEDDING_MODEL") or "qwen3.7-text-embedding"


def get_qwen_embedding_dimension() -> int:
    raw_value = os.getenv("QWEN_EMBEDDING_DIMENSION") or "1024"
    dimension = int(raw_value)
    if dimension <= 0:
        raise ValueError("QWEN_EMBEDDING_DIMENSION 必须为正整数")
    return dimension


def get_qwen_rerank_model() -> str:
    return os.getenv("QWEN_RERANK_MODEL") or "qwen3-rerank"


def get_qwen_vision_model() -> str:
    return os.getenv("QWEN_VISION_MODEL") or "qwen-vl-max"
