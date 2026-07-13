"""
验证讯飞星火兼容性补丁——模拟 choices=None 的 chunk 不会导致 TypeError。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_openai.chat_models import base as lc_base
from langchain_core.messages import AIMessageChunk
from app.utils.xfyun_compat import apply_patches, revert_patches

# 通过模块属性访问，确保拿到补丁后的版本
def get_patched_func():
    return lc_base._convert_chunk_to_generation_chunk


def test_choices_none_chunk():
    """模拟讯飞星火返回 choices=null 的场景。"""
    apply_patches()
    func = get_patched_func()

    bad_chunk = {
        "choices": None,
        "model": "generalv3",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    try:
        result = func(bad_chunk, AIMessageChunk, {})
        print(f"[PASS] choices=None: no crash, result={result}")
        return True
    except TypeError as e:
        print(f"[FAIL] choices=None: still crashed! {e}")
        return False


def test_normal_chunk():
    """确保正常 chunk 不受影响。"""
    func = get_patched_func()

    normal_chunk = {
        "choices": [{"delta": {"content": "hello"}, "index": 0}],
        "model": "generalv3",
    }

    try:
        result = func(normal_chunk, AIMessageChunk, {})
        assert result is not None
        print(f"[PASS] normal chunk: content={result.message.content}")
        return True
    except Exception as e:
        print(f"[FAIL] normal chunk: {e}")
        return False


def test_empty_choices():
    """确保原本的空 choices 逻辑不变。"""
    func = get_patched_func()

    empty_chunk = {"choices": [], "model": "generalv3"}

    try:
        result = func(empty_chunk, AIMessageChunk, {})
        assert result is not None
        print(f"[PASS] empty choices: returns empty ChatGenerationChunk")
        return True
    except Exception as e:
        print(f"[FAIL] empty choices: {e}")
        return False


def test_choices_missing():
    """choices 字段完全缺失。"""
    func = get_patched_func()

    missing_chunk = {"model": "generalv3"}

    try:
        result = func(missing_chunk, AIMessageChunk, {})
        assert result is not None
        print(f"[PASS] choices missing: returns empty ChatGenerationChunk")
        return True
    except Exception as e:
        print(f"[FAIL] choices missing: {e}")
        return False


if __name__ == "__main__":
    results = [
        test_choices_none_chunk(),
        test_normal_chunk(),
        test_empty_choices(),
        test_choices_missing(),
    ]
    print(f"\n{'='*50}")
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    if passed == total:
        print("All tests passed!")
    else:
        print("Some tests failed!")

    revert_patches()
