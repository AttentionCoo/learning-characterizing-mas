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
    _summarize_tool_usage,
    emit_supervisor_progress,
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
    types = [e["type"] for e in events]
    # 先播报动作进度（"正在整合最终回答"），再进入逐 token 文本流
    assert types[0] == "thinking"
    assert events[0]["thinking"]["title"] == "正在整合最终回答"
    text_types = [t for t in types if t.startswith("text_")]
    assert text_types == ["text_start", "text_delta", "text_delta", "text_delta", "text_end"]
    stream_events = [e for e in events if e["type"].startswith("text_")]
    assert all(e["channel"] == "answer" for e in stream_events)
    assert stream_events[-1]["content"] == "同学们好，这是回答"


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


# ── 监督者动作进度（内部思考不外泄，但"在做什么"要可见）──

def test_compose_answer_skips_streaming_for_profile_build():
    """profile_build 的结果由确定性渲染 + replace 覆盖产出，
    这里再流式撰写一次会让回答被打到一半就被替换，且白花一次调用。"""
    llm = _StreamingLLM(["不该被生成"])

    def _run():
        sup = _supervisor(llm)
        return sup._compose_answer(
            _state(report_mode="profile_build"), "q", "监督者草稿", {},
        )

    answer, events = _collect_answer_stream(_run)

    assert answer == "监督者草稿", "应直接回退草稿"
    assert events == [], "不应产生任何流式事件"
    assert llm.prompts == [], "不应发起 LLM 调用"


# ── 调度结果自解释：让"0 次工具调用"不再是空白 ──

def test_summarize_tool_usage_lists_called_tools_in_chinese():
    trace = [
        {"role": "assistant", "tools": ["get_student_profile"], "results": ""},
        {"role": "assistant", "tools": ["evidence_search", "consult_experts"], "results": ""},
    ]
    title, detail = _summarize_tool_usage(trace)
    assert title == "调度完成"
    assert "读取学习画像" in detail
    assert "检索循证指南" in detail
    assert "召集专家会诊" in detail


def test_summarize_tool_usage_explains_direct_answer():
    """未调用任何工具时必须说明原因，否则轨迹上只剩一句「处理完成」。"""
    title, detail = _summarize_tool_usage([])
    assert title == "本轮直接作答"
    assert "未检索证据" in detail
    assert "未召集专家" in detail


def test_summarize_tool_usage_falls_back_to_raw_tool_name():
    trace = [{"role": "assistant", "tools": ["brand_new_tool"], "results": ""}]
    _, detail = _summarize_tool_usage(trace)
    assert "brand_new_tool" in detail, "未知工具名应原样透出而不是丢失"


def test_emit_supervisor_progress_pushes_thinking_step():
    events = []
    token = set_event_sink(events.append)
    try:
        emit_supervisor_progress("正在检索循证指南", "检索词：MCA 供血区")
    finally:
        reset_event_sink(token)

    assert len(events) == 1
    evt = events[0]
    assert evt["type"] == "thinking"
    assert evt["thinking"]["step"] == "supervisor"
    assert evt["thinking"]["title"] == "正在检索循证指南"
    assert "MCA 供血区" in evt["thinking"]["content"]


def test_emit_supervisor_progress_without_sink_is_silent():
    """无请求级 sink（非流式/单测场景）时必须静默，不能抛错影响调度。"""
    emit_supervisor_progress("正在召集专家会诊")  # 不应抛异常


def test_emit_supervisor_progress_survives_broken_sink():
    def _broken(_payload):
        raise RuntimeError("sink 已关闭")

    token = set_event_sink(_broken)
    try:
        emit_supervisor_progress("正在整合最终回答")  # 不应抛异常
    finally:
        reset_event_sink(token)
