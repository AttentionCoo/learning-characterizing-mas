"""逐 token 文本流式单测：增量事件序列、工具调用分片过滤、流式失败回退。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.text_stream import stream_chunks, stream_llm_text, stream_react_agent_text


class _FakeLLM:
    """astream 逐段产出；stream_should_fail=True 时抛错以验证回退。
    fail_after=N 时吐完前 N 片后抛错，模拟流式中途断开。"""

    def __init__(self, chunks, full=None, stream_should_fail=False, fail_after=None):
        self.chunks = list(chunks)
        self.full = full if full is not None else "".join(chunks)
        self.stream_should_fail = stream_should_fail
        self.fail_after = fail_after
        self.astream_calls = 0
        self.ainvoke_calls = 0

    async def astream(self, messages):
        self.astream_calls += 1
        if self.stream_should_fail:
            raise RuntimeError("该网关不支持流式")
        for i, c in enumerate(self.chunks):
            yield SimpleNamespace(content=c)
            if self.fail_after is not None and i + 1 >= self.fail_after:
                raise RuntimeError("流式中途断开")

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1
        return SimpleNamespace(content=self.full)


def test_stream_chunks_emits_start_delta_end_in_order():
    events = []

    async def main():
        async def gen():
            for c in ("你", "好", "世界"):
                yield SimpleNamespace(content=c)
        return await stream_chunks(gen(), emit=events.append, channel="expert:A", label="A")

    text = asyncio.run(main())
    assert text == "你好世界"
    assert [e["type"] for e in events] == [
        "text_start", "text_delta", "text_delta", "text_delta", "text_end",
    ]
    assert "".join(e.get("delta", "") for e in events) == "你好世界"
    assert events[-1]["content"] == "你好世界"
    assert events[0]["channel"] == "expert:A"


def test_stream_chunks_skips_tool_call_chunks():
    """ReAct 智能体的工具调用参数分片属于内部调度文本，不得外泄。"""
    events = []

    async def main():
        async def gen():
            yield SimpleNamespace(content="internal", tool_call_chunks=[{"name": "t"}])
            yield SimpleNamespace(content="最终", tool_call_chunks=None)
            yield SimpleNamespace(content="发言", tool_call_chunks=None)
        return await stream_chunks(
            gen(), emit=events.append, channel="expert:A", skip_tool_call_chunks=True,
        )

    text = asyncio.run(main())
    assert text == "最终发言"
    assert "internal" not in "".join(e.get("delta", "") for e in events)


def test_stream_chunks_handles_multimodal_content_parts():
    events = []

    async def main():
        async def gen():
            yield SimpleNamespace(content=[{"text": "片"}, {"text": "段"}])
        return await stream_chunks(gen(), emit=events.append, channel="synthesis")

    assert asyncio.run(main()) == "片段"


def test_stream_llm_text_falls_back_to_ainvoke_and_still_emits():
    """网关不支持流式时回退整段返回，但前端仍要拿到内容，否则区块会空着。"""
    events = []
    llm = _FakeLLM(["x"], full="完整回答", stream_should_fail=True)

    text = asyncio.run(stream_llm_text(
        llm, ["m"], emit=events.append, channel="arbitration", label="仲裁裁决",
    ))

    assert text == "完整回答"
    assert llm.ainvoke_calls == 1
    assert [e["type"] for e in events] == ["text_start", "text_delta", "text_end"]
    assert events[1]["delta"] == "完整回答"


def test_stream_llm_text_midstream_failure_only_reemits_text_end():
    """流式中途失败：增量已发过一部分，回退只能补 text_end 让下游覆盖。
    重发 delta 会让追加语义的通道（answer）拼出"半截 + 全文"。"""
    events = []
    llm = _FakeLLM(["同学", "们好", "这是", "完整回答"], full="同学们好这是完整回答", fail_after=2)

    text = asyncio.run(stream_llm_text(
        llm, ["m"], emit=events.append, channel="answer", label="最终回答",
    ))

    assert text == "同学们好这是完整回答"
    assert llm.ainvoke_calls == 1
    assert [e["type"] for e in events] == ["text_start", "text_delta", "text_delta", "text_end"]
    assert events[-1]["content"] == "同学们好这是完整回答"


def test_stream_llm_text_without_emit_uses_ainvoke():
    llm = _FakeLLM(["x"], full="完整回答")

    text = asyncio.run(stream_llm_text(llm, ["m"], emit=None, channel="synthesis"))

    assert text == "完整回答"
    assert llm.astream_calls == 0
    assert llm.ainvoke_calls == 1


def test_stream_react_agent_text_falls_back_when_no_emit():
    class _Agent:
        async def ainvoke(self, messages, config=None):
            return {"messages": [
                SimpleNamespace(content=""),
                SimpleNamespace(content="工具调用后的最终发言"),
            ]}

    text = asyncio.run(stream_react_agent_text(
        _Agent(), {"messages": []}, emit=None, channel="expert:A",
    ))
    assert text == "工具调用后的最终发言"


def test_stream_react_agent_text_streams_answer_only():
    """stream_mode='messages' 产出 (chunk, metadata) 元组，只推最终发言 token。"""
    events = []

    class _Agent:
        async def astream(self, messages, config=None, stream_mode=None):
            assert stream_mode == "messages"
            yield (SimpleNamespace(content="plan", tool_call_chunks=[{"name": "t"}]), {})
            yield (SimpleNamespace(content="正式", tool_call_chunks=None), {})
            yield (SimpleNamespace(content="发言", tool_call_chunks=None), {})

    text = asyncio.run(stream_react_agent_text(
        _Agent(), {"messages": []}, emit=events.append, channel="expert:A", label="A",
    ))
    assert text == "正式发言"
    assert "plan" not in "".join(e.get("delta", "") for e in events)


def test_stream_react_agent_text_discards_intermediate_round_text():
    """多轮 ReAct：工具调用轮里先出现的中间文本必须整轮丢弃（Model #7）。

    同一消息 id 内先缓冲文本，一旦出现工具调用分片即判定为内部调度轮，
    已缓冲的"我先检索一下"之类话术不得外泄；工具消息分片同样跳过。
    """
    events = []

    class _Agent:
        async def astream(self, messages, config=None, stream_mode=None):
            assert stream_mode == "messages"
            # 第一轮：先说一句过渡话术，然后发起工具调用（同一消息 id）
            yield (SimpleNamespace(content="我需要先检索证据", tool_call_chunks=None, type="ai", id="m1"), {})
            yield (SimpleNamespace(content="", tool_call_chunks=[{"name": "t"}], type="ai", id="m1"), {})
            yield (SimpleNamespace(content="检索结果", type="tool", id="m1"), {})
            # 第二轮：最终发言（新消息 id，无工具调用）
            yield (SimpleNamespace(content="正式", tool_call_chunks=None, type="ai", id="m2"), {})
            yield (SimpleNamespace(content="发言", tool_call_chunks=None, type="ai", id="m2"), {})

    text = asyncio.run(stream_react_agent_text(
        _Agent(), {"messages": []}, emit=events.append, channel="expert:A", label="A",
    ))
    assert text == "正式发言"
    joined = "".join(e.get("delta", "") for e in events)
    assert "我需要先检索证据" not in joined
    assert "检索结果" not in joined


def test_stream_react_agent_text_midstream_failure_does_not_rerun_agent():
    """中途失败：工具可能已执行过，重跑 agent 会重复检索/写共享记忆、双倍成本（Model #4）。

    已送达的增量用 text_end 收口，ainvoke 不得再被调用。
    """
    events = []

    class _Agent:
        def __init__(self):
            self.ainvoke_calls = 0

        async def astream(self, messages, config=None, stream_mode=None):
            yield (SimpleNamespace(content="同学", tool_call_chunks=None, type="ai", id="m1"), {})
            yield (SimpleNamespace(content="们好", tool_call_chunks=None, type="ai", id="m1"), {})
            raise RuntimeError("流式中途断开")

        async def ainvoke(self, messages, config=None):
            self.ainvoke_calls += 1
            raise AssertionError("中途失败后不应重跑 agent")

    agent = _Agent()
    text = asyncio.run(stream_react_agent_text(
        agent, {"messages": []}, emit=events.append, channel="expert:A", label="A",
    ))
    assert text == "同学们好"
    assert agent.ainvoke_calls == 0
    assert [e["type"] for e in events] == ["text_start", "text_delta", "text_delta", "text_end"]
    assert events[-1]["content"] == "同学们好"


def test_stream_react_agent_text_retries_when_failing_before_first_chunk():
    """首片前失败：尚未消费任何分片、无工具副作用，重跑整段返回是安全的。"""
    events = []

    class _Agent:
        def __init__(self):
            self.ainvoke_calls = 0

        async def astream(self, messages, config=None, stream_mode=None):
            raise RuntimeError("网关不支持流式")

        async def ainvoke(self, messages, config=None):
            self.ainvoke_calls += 1
            return {"messages": [SimpleNamespace(content=""), SimpleNamespace(content="最终发言")]}

    agent = _Agent()
    text = asyncio.run(stream_react_agent_text(
        agent, {"messages": []}, emit=events.append, channel="expert:A", label="A",
    ))
    assert text == "最终发言"
    assert agent.ainvoke_calls == 1
    assert [e["type"] for e in events] == ["text_start", "text_delta", "text_end"]
    assert events[-1]["content"] == "最终发言"


def test_stream_llm_text_returns_empty_when_llm_is_none():
    """llm 未注入时返回空串，不得解引用 None 抛 AttributeError（Model #5）。"""
    events = []
    text = asyncio.run(stream_llm_text(None, ["m"], emit=events.append, channel="synthesis"))
    assert text == ""
    assert events == []
