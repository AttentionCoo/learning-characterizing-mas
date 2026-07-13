"""
讯飞星火 API 兼容性补丁

修复 langchain_openai 与讯飞星火 API 之间的兼容性问题：

1. 讯飞 API 在流式响应中可能返回 "choices": null（而非 "choices": [] 或缺失该字段），
   导致 langchain_openai 的 _convert_chunk_to_generation_chunk 在 len(choices) 时抛出
   TypeError: object of type 'NoneType' has no len()

2. 讯飞 API 的错误响应格式与 OpenAI 不同，HTTP 500 时可能仍返回 JSON body 含 choices: null

使用方式：在 main.py 最顶部（任何 ChatOpenAI 使用之前）调用 apply_patches()。
"""

import logging
from typing import Dict, Optional, Type

from langchain_openai.chat_models import base as lc_base

logger = logging.getLogger(__name__)

_original_convert = lc_base._convert_chunk_to_generation_chunk


def _patched_convert_chunk_to_generation_chunk(
    chunk: dict,
    default_chunk_class: Type,
    base_generation_info: Optional[Dict],
):
    """与原始函数行为一致，但对 choices 为 None 做安全兜底。

    讯飞星火在某些错误/边界场景下返回 {"choices": null, ...}，
    dict.get("choices", []) 在 key 存在但值为 None 时返回 None（而非默认值 []），
    导致后续 len(choices) 抛出 TypeError。此处强制将 None 转为 []。
    """
    try:
        return _original_convert(chunk, default_chunk_class, base_generation_info)
    except TypeError:
        # 当 chunk["choices"] 为 None 时，langchain_openai <= 0.1.25 会崩溃
        # 将 choices 替换为空列表后重试
        if chunk.get("choices") is None:
            error_code = chunk.get("code", "N/A")
            error_msg = chunk.get("message", "N/A")
            sid = chunk.get("sid", "N/A")
            model = chunk.get("model", "N/A")

            # 提取 usage 中的 token 信息，辅助判断是否因额度/配额问题
            usage = chunk.get("usage", {}) or {}
            total_tokens = usage.get("total_tokens", "N/A") if usage else "N/A"

            logger.warning(
                "⚠️ 讯飞星火返回 choices=null —— API 层面异常，已自动修正为空列表避免崩溃。\n"
                "  模型(model)=%s | 错误码(code)=%s | 错误信息(message)=%s\n"
                "  会话(sid)=%s | total_tokens=%s\n"
                "  可能原因: ① 模型名无效/未开通 ② APIKey 无该模型权限 ③ 配额耗尽\n"
                "  完整 chunk keys: %s",
                model, error_code, error_msg,
                sid, total_tokens,
                list(chunk.keys()),
            )
            fixed_chunk = {**chunk, "choices": []}
            return _original_convert(fixed_chunk, default_chunk_class, base_generation_info)
        raise


def apply_patches():
    """应用所有讯飞星火兼容性补丁。幂等——重复调用无副作用。"""
    current = lc_base._convert_chunk_to_generation_chunk
    if current is _patched_convert_chunk_to_generation_chunk:
        return  # 已打过补丁

    lc_base._convert_chunk_to_generation_chunk = _patched_convert_chunk_to_generation_chunk
    logger.info("✅ 讯飞星火兼容性补丁已激活（choices=null 兜底）")


def revert_patches():
    """回退补丁（仅用于测试）。"""
    current = lc_base._convert_chunk_to_generation_chunk
    if current is _patched_convert_chunk_to_generation_chunk:
        lc_base._convert_chunk_to_generation_chunk = _original_convert
        logger.info("讯飞星火兼容性补丁已回退")