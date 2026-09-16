"""逐 token 文本流式单测：增量事件序列、工具调用分片过滤、流式失败回退。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.text_stream import stream_chunks, stream_llm_text, stream_react_agent_text


class _FakeLLM:
    """astream 逐段产出；stream_should_fail=True 时抛错以验证回退。"""

    def __init__(self, chunks, full=None, stream_should_fail=False):
        self.chunks = list(chunks)
        self.full = full if full is not None else "".join(chunks)
        self.stream_should_fail = stream_should_fail
        self.astream_calls = 0
        self.ainvoke_calls = 0

    async def astream(self, messages):
        self.astream_calls += 1
        if self.stream_should_fail:
            raise RuntimeError("该网关不支持流式")
        for c in self.chunks:
            yield SimpleNamespace(content=c)

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
