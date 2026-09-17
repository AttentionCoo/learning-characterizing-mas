"""监督者最终回答的独立流式撰写：与内部调度推理分离，逐 token 推送。

设计意图：监督者的中间思考（工具调度、选人理由、提示词）不得外泄，
学生可见的回答由 `_compose_answer` 单独流式生成；撰写失败时回退其草稿，
保证功能不退化。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.event_sink import get_event_sink, reset_event_sink, set_event_sink
from app.agents.orchestrators.supervisor import (
    TutorSupervisor,
    _ANSWER_SYSTEM,
    _build_answer_prompt,
)


def _supervisor(llm):
    return TutorSupervisor(llm=llm, retrieve_node=None, reason_node=None)


def _state(**overrides):
    state = {
        "case_text": "MCA 和 PCA 供血区怎么区分？",
        "intent_type": "tutor",
        "evidence": "",
        "profile_summary": "临床医学大三学生",
    }
    state.update(overrides)
    return state


class _StreamingLLM:
    """astream 逐段产出，记录收到的 prompt。"""

    def __init__(self, chunks, stream_should_fail=False):
        self.chunks = list(chunks)
        self.stream_should_fail = stream_should_fail
        self.prompts = []
        self.ainvoke_calls = 0

    async def astream(self, messages):
        self.prompts.append("\n".join(getattr(m, "content", "") for m in messages))
        if self.stream_should_fail:
            raise RuntimeError("不支持流式")
        for c in self.chunks:
            yield SimpleNamespace(content=c)

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1
        return SimpleNamespace(content="".join(self.chunks))


def _collect_answer_stream(coro_factory):
    """跑一次 _compose_answer，返回 (结果, 事件列表)。"""
    events = []
    token = set_event_sink(events.append)
    try:
        result = asyncio.run(coro_factory())
    finally:
        reset_event_sink(token)
    return result, events


def test_compose_answer_streams_over_answer_channel():
    llm = _StreamingLLM(["同学们", "好，", "这是回答"])
    sup = _supervisor(llm)

    answer, events = _collect_answer_stream(lambda: sup._compose_answer(
        _state(), "MCA 和 PCA 供血区怎么区分？", "草稿要点", {},
    ))

    assert answer == "同学们好，这是回答"
    assert [e["type"] for e in events] == [
        "text_start", "text_delta", "text_delta", "text_delta", "text_end",
    ]
    assert all(e["channel"] == "answer" for e in events)
    assert events[-1]["content"] == "同学们好，这是回答"


def test_compose_answer_prompt_carries_question_guidance_and_material():
    llm = _StreamingLLM(["ok"])
    sup = _supervisor(llm)
    workspace = {
        "evidence": "指南原文：rt-PA 时间窗 4.5 小时",
        "expert_advices": [{"role": "需求分析智能体", "content": "先讲机制"}],
        "convergence": "三层递进",
        "arbitration_result": "采纳收敛结论",
        "proposal": "综合提案正文",
    }

    _collect_answer_stream(lambda: sup._compose_answer(
        _state(), "MCA 和 PCA 供血区怎么区分？", "草稿要点", workspace,
    ))

    prompt = llm.prompts[0]
    assert _ANSWER_SYSTEM in prompt, "系统提示应约束不得提及内部流程"
    assert "MCA 和 PCA 供血区怎么区分？" in prompt
    assert "解答" in prompt, "应带上 tutor 意图的回答结构要求"
    assert "rt-PA 时间窗 4.5 小时" in prompt
    assert "先讲机制" in prompt
    assert "三层递进" in prompt
    assert "采纳收敛结论" in prompt
    assert "综合提案正文" in prompt
    assert "草稿要点" in prompt
    assert "临床医学大三学生" in prompt


def test_compose_answer_falls_back_to_draft_on_stream_failure():
    """流式失败时必须回退草稿，不能让学生看到空回答。"""
    llm = _StreamingLLM(["x"], stream_should_fail=True)
    sup = _supervisor(llm)

    answer, events = _collect_answer_stream(lambda: sup._compose_answer(
        _state(), "q", "监督者草稿全文", {},
    ))

    # 回退路径：stream_llm_text 内部改用 ainvoke，仍产出内容
    assert answer == "x"
    assert llm.ainvoke_calls == 1


def test_compose_answer_returns_draft_when_llm_raises():
    class _BrokenLLM:
        async def astream(self, messages):
            # 用不可达的 yield 使其成为异步生成器，与真实 LangChain LLM 的
            # .astream() 契约一致（否则会退化成返回协程，迭代时报 TypeError）
            raise RuntimeError("stream down")
            yield  # pragma: no cover

        async def ainvoke(self, messages):
            raise RuntimeError("invoke down")

    sup = _supervisor(_BrokenLLM())

    answer, _ = _collect_answer_stream(lambda: sup._compose_answer(
        _state(), "q", "监督者草稿全文", {},
    ))

    assert answer == "监督者草稿全文"


def test_compose_answer_without_sink_still_returns_text():
    """没有请求级 sink 时（非流式调用场景）不应报错，退化为普通调用。"""
    llm = _StreamingLLM(["回答"])
    sup = _supervisor(llm)

    answer = asyncio.run(sup._compose_answer(_state(), "q", "草稿", {}))

    assert answer == "回答"
    assert llm.ainvoke_calls == 1


def test_build_answer_prompt_handles_unknown_intent_and_empty_material():
    prompt = _build_answer_prompt("unknown_intent", "问题", "")
    assert "问题" in prompt
    assert "直接、结构清晰地回答" in prompt
    assert "无额外材料" in prompt


def test_answer_material_truncates_and_skips_empty_sections():
    sup = _supervisor(_StreamingLLM(["x"]))
    material = sup._answer_material(
        _state(profile_summary=""),
        {"evidence": "E" * 5000, "expert_advices": [], "proposal": ""},
        "",
    )
    assert "【学习画像】" not in material, "空画像不应出现标题"
    assert "【专家意见】" not in material
    assert "【综合提案】" not in material
    assert len(material) < 5000, "循证材料应被截断"
