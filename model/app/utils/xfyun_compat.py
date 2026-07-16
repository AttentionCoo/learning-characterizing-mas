"""
讯飞星火 API 兼容性补丁

修复 langchain_openai 与讯飞星火 API 之间的兼容性问题：

1. 讯飞 API 在流式响应中可能返回 "choices": null（而非 "choices": [] 或缺失该字段），
   导致 langchain_openai 的 chunk 转换函数在 len(choices) 时抛出
   TypeError: object of type 'NoneType' has no len()

2. 讯飞 API 的错误响应格式与 OpenAI 不同，HTTP 500 时可能仍返回 JSON body 含 choices: null

兼容 langchain-openai 新旧版本（函数名 0.x vs 1.x 不同）。

使用方式：在 main.py 最顶部（任何 ChatOpenAI 使用之前）调用 apply_patches()。
"""

import logging
from typing import Dict, Optional, Type

from langchain_openai.chat_models import base as lc_base

logger = logging.getLogger(__name__)

# ── langchain-openai 1.x 重命名了该函数，兼容新旧两种名称 ──
_CONVERT_ATTR = None
_original_convert = None

for _attr_name in (
    "_convert_responses_chunk_to_generation_chunk",   # langchain-openai >= 1.x
    "_convert_chunk_to_generation_chunk",              # langchain-openai <= 0.x
):
    if hasattr(lc_base, _attr_name):
        _CONVERT_ATTR = _attr_name
        _original_convert = getattr(lc_base, _attr_name)
        break

if _original_convert is None:
    raise ImportError(
        "无法在 langchain_openai.chat_models.base 中找到 chunk 转换函数，"
        "请检查 langchain-openai 版本兼容性。"
    )


def _patched_convert(chunk, default_chunk_class, base_generation_info):
    """与原始函数行为一致，但对 choices 为 None 做安全兜底。

    讯飞星火在某些错误/边界场景下返回 {"choices": null, ...}，
    dict.get("choices", []) 在 key 存在但值为 None 时返回 None（而非默认值 []），
    导致后续 len(choices) 抛出 TypeError。此处强制将 None 转为 []。
    """
    try:
        return _original_convert(chunk, default_chunk_class, base_generation_info)
    except TypeError:
        if chunk.get("choices") is None:
            error_code = chunk.get("code", "N/A")
            error_msg = chunk.get("message", "N/A")
            sid = chunk.get("sid", "N/A")
            model = chunk.get("model", "N/A")
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
    current = getattr(lc_base, _CONVERT_ATTR, None)
    if current is _patched_convert:
        return  # 已打过补丁

    setattr(lc_base, _CONVERT_ATTR, _patched_convert)
    logger.info("✅ 讯飞星火兼容性补丁已激活（choices=null 兜底，函数: %s）", _CONVERT_ATTR)


def revert_patches():
    """回退补丁（仅用于测试）。"""
    current = getattr(lc_base, _CONVERT_ATTR, None)
    if current is _patched_convert:
        setattr(lc_base, _CONVERT_ATTR, _original_convert)
        logger.info("讯飞星火兼容性补丁已回退")