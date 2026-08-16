"""自实现 SSE 组件单测：帧编码、命名事件、心跳注入、响应头。"""
import asyncio

import pytest

from app.utils.sse import EventSourceResponse, encode_event


def test_encode_event_wraps_string_with_data_prefix():
    out = encode_event('{"type":"init"}').decode("utf-8")
    assert out == 'data: {"type":"init"}\r\n\r\n'


def test_encode_event_splits_multiline_into_multiple_data_lines():
    out = encode_event("line1\nline2").decode("utf-8")
    assert out == "data: line1\r\ndata: line2\r\n\r\n"


def test_encode_event_serializes_dict_as_json():
    out = encode_event({"type": "init", "中文": "值"}).decode("utf-8")
    assert out == 'data: {"type":"init","中文":"值"}\r\n\r\n'


def test_encode_event_passes_bytes_through():
    assert encode_event(b"raw-bytes") == b"raw-bytes"


def test_encode_event_named_event_dict():
    out = encode_event({
        "event": "error",
        "data": '{"type":"error","content":"x"}',
    }).decode("utf-8")
    assert "event: error\r\n" in out
    assert 'data: {"type":"error","content":"x"}\r\n' in out


@pytest.mark.asyncio
async def test_idle_ping_emits_heartbeat_during_silence():
    from app.utils.sse import _idle_ping

    async def slow_source():
        yield "a"
        await asyncio.sleep(0.6)
        yield "b"

    items = []
    async for item in _idle_ping(slow_source(), ping=0.2):
        items.append(item)

    assert items[0] == "a"
    assert ": ping" in items
    assert items[-1] == "b"


def test_response_headers_and_media_type():
    def gen():
        yield {"type": "init"}

    resp = EventSourceResponse(gen(), ping=15)
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
