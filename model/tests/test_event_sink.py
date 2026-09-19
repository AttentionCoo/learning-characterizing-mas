"""实时事件通道单测：ContextVar sink 的隔离/恢复，以及队列抽取的哨兵语义。

背景：ReasonNode 在监督者路径下是被 `consult_experts` 工具手工调用的，LangGraph 的
stream writer 不可用，custom 事件不会冒泡。修复方式是用请求级 sink + 队列把事件
实时抽出来，这里覆盖该机制的三个关键性质。
"""
import asyncio

import pytest

from app.agents.event_sink import emit_event, get_event_sink, reset_event_sink, set_event_sink
from app.agents.orchestrators.learning_agent import _GRAPH_END, _GRAPH_ERROR, _drain_events


def test_sink_roundtrip():
    assert get_event_sink() is None
    collected = []
    token = set_event_sink(collected.append)
    try:
        # 绑定方法每次访问都是新对象，只能断言行为而不能用 `is` 比较
        sink = get_event_sink()
        assert sink is not None
        sink({"type": "x"})
        assert collected == [{"type": "x"}]
    finally:
        reset_event_sink(token)
    assert get_event_sink() is None


def test_sink_isolated_between_tasks():
    """两个并发请求各自的 sink 不能互相串台。"""
    async def worker(tag, out):
        token = set_event_sink(lambda p: out.append((tag, p)))
        try:
            await asyncio.sleep(0.01)
            get_event_sink()({"n": tag})
        finally:
            reset_event_sink(token)

    async def main():
        a, b = [], []
        await asyncio.gather(worker("A", a), worker("B", b))
        return a, b

    a, b = asyncio.run(main())
    assert a == [("A", {"n": "A"})]
    assert b == [("B", {"n": "B"})]


def test_reset_with_none_is_noop():
    reset_event_sink(None)
    assert get_event_sink() is None


def test_drain_yields_until_end_sentinel():
    """哨兵语义：收到 _GRAPH_END 就结束，不依赖 queue.empty()（消费快于生产时不可靠）。"""
    async def main():
        q = asyncio.Queue()
        await q.put(("custom", {"type": "a"}))
        await q.put(("updates", {"node": {}}))
        await q.put((_GRAPH_END, None))
        # 哨兵之后再塞数据也不应被消费
        await q.put(("custom", {"type": "late"}))
        return [item async for item in _drain_events(q)]

    got = asyncio.run(main())
    assert got == [("custom", {"type": "a"}), ("updates", {"node": {}})]


def test_drain_reraises_graph_error():
    """图任务的异常要在消费端原样抛出，走回原有的错误上报路径。"""
    async def main():
        q = asyncio.Queue()
        await q.put((_GRAPH_ERROR, RuntimeError("图执行失败")))
        await q.put((_GRAPH_END, None))
        return [item async for item in _drain_events(q)]

    with pytest.raises(RuntimeError, match="图执行失败"):
        asyncio.run(main())


def test_emit_event_prefers_request_sink():
    """emit_event：sink 优先，事件当场入队，绝不落到 writer 转发通道。"""
    collected = []
    token = set_event_sink(collected.append)
    try:
        assert emit_event({"type": "x"}) is True
        assert collected == [{"type": "x"}]
    finally:
        reset_event_sink(token)


def test_emit_event_without_sink_outside_graph_is_noop():
    """无 sink 且不在图节点上下文（writer 不可得）时：静默返回 False，不抛异常。"""
    assert get_event_sink() is None
    assert emit_event({"type": "x"}) is False


def test_node_start_precedes_content_in_sink_mode():
    """乱序回归（Model #2）：sink 模式下 node_start 必须先于节点内容入队。

    旧实现 node_start 走 writer（LangGraph 内部流稍后转发），节点内容走 sink
    （当场入队）→ 步骤卡稳定排到内容之后。
    """
    from langgraph.graph import END, StateGraph
    from typing import TypedDict

    from app.agents.orchestrators.clinical_graph import LearningGraphBuilder

    class _MiniState(TypedDict):
        x: str

    async def _body(state, **kwargs):
        get_event_sink()({"type": "content", "text": "node body"})
        return {"x": "done"}

    async def main():
        q: asyncio.Queue = asyncio.Queue()

        def sink(payload):
            q.put_nowait(("custom", payload))

        token = set_event_sink(sink)
        try:
            graph = StateGraph(_MiniState)
            graph.add_node("n", LearningGraphBuilder._with_node_events("n", _body))
            graph.set_entry_point("n")
            graph.add_edge("n", END)
            await graph.compile().ainvoke({"x": ""})
        finally:
            reset_event_sink(token)
        return [q.get_nowait() for _ in range(q.qsize())]

    events = asyncio.run(main())
    assert [e[1]["type"] for e in events] == ["node_start", "content"]


def test_executor_step_progress_precedes_step_content():
    """乱序回归（Model #2）：执行步骤卡必须先于该步骤产出的内容入队。"""

    class _DummyNode:
        async def run(self, state):
            get_event_sink()({"type": "content", "text": "step body"})
            return {"learning_questions": ["q1"]}

    from app.agents.orchestrators.nodes.executor_node import ExecutorNode

    node = ExecutorNode(retrieve_node=_DummyNode(), analysis_node=_DummyNode(), reason_node=_DummyNode())
    state = {
        "plan": {
            "steps": [
                {"step_type": "analyze", "title": "拆解需求"},
                {"step_type": "finalize", "title": "收尾"},
            ]
        }
    }

    async def main():
        collected = []
        token = set_event_sink(collected.append)
        try:
            await node.run(state)
        finally:
            reset_event_sink(token)
        return collected

    events = asyncio.run(main())
    assert [e["type"] for e in events] == ["thinking", "content", "thinking"]
    assert events[0]["thinking"]["title"] == "执行步骤 1/2：拆解需求"
