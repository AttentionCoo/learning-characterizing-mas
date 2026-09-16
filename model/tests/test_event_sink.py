"""实时事件通道单测：ContextVar sink 的隔离/恢复，以及队列抽取的哨兵语义。

背景：ReasonNode 在监督者路径下是被 `consult_experts` 工具手工调用的，LangGraph 的
stream writer 不可用，custom 事件不会冒泡。修复方式是用请求级 sink + 队列把事件
实时抽出来，这里覆盖该机制的三个关键性质。
"""
import asyncio

import pytest

from app.agents.event_sink import get_event_sink, reset_event_sink, set_event_sink
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


def test_reason_node_emit_prefers_request_sink():
    """reason_node._emit 必须优先走请求级 sink（监督者路径下 writer 不可用）。"""
    import inspect

    from app.agents.orchestrators.nodes.reason_node import ReasonNode

    src = inspect.getsource(ReasonNode.run)
    assert "get_event_sink()" in src, "reason_node.run 未使用请求级 sink"
    # sink 在 writer 之前被尝试
    assert src.index("get_event_sink()") < src.index("writer(payload)")
