"""逐 token 文本流式：把一次 LLM 调用拆成 text_start / text_delta / text_end 事件。

## 为什么需要

专家发言、综合提案、辩论发言、仲裁裁决原先都用 `ainvoke`（一次性返回），
即使事件通道已经实时，单块文本仍是"生成完才整段出现"。改成 `astream` 后，
这些长文本会边生成边推增量，前端逐字打印。

## 设计要点

- **channel**：文本通道标识（如 `expert:需求分析智能体`、`synthesis`、`arbitration`），
  前端据此把增量路由到对应区块；同一通道的文本在被权威事件（experts/debate/blackboard）
  覆盖前是"流式草稿"。
- **回退**：模型或网关不支持流式时回退 `ainvoke`，功能不退化（只是退回整段返回）。
- **emit 可选**：没有 emit（例如单测或非流式调用）时退化为普通调用。
"""
import logging
from typing import AsyncIterator, List, Optional

logger = logging.getLogger(__name__)


def _chunk_text(chunk) -> str:
    """从 chunk 中取出文本增量，兼容字符串与多模态分片列表。"""
    content = getattr(chunk, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _emit(emit, payload: dict) -> None:
    if emit is None:
        return
    try:
        emit(payload)
    except Exception as e:  # noqa: BLE001 - 推送失败不应影响推理本身
        logger.debug(f"[text_stream] 事件推送失败: {e}")


async def stream_chunks(
    chunks: AsyncIterator,
    *,
    emit=None,
    channel: str,
    label: str = "",
    node: str = "reason",
    skip_tool_call_chunks: bool = False,
) -> str:
    """消费 chunk 流并推送增量事件，返回完整文本。

    skip_tool_call_chunks=True 时跳过"工具调用参数生成"阶段的分片
    （ReAct 智能体里那部分是内部调度文本，不属于最终发言）。
    """
    parts: List[str] = []
    started = False
    async for chunk in chunks:
        if skip_tool_call_chunks and getattr(chunk, "tool_call_chunks", None):
            continue
        delta = _chunk_text(chunk)
        if not delta:
            continue
        if not started:
            started = True
            _emit(emit, {"type": "text_start", "node": node, "channel": channel, "label": label})
        parts.append(delta)
        _emit(emit, {"type": "text_delta", "node": node, "channel": channel, "delta": delta})
    text = "".join(parts)
    if started:
        _emit(emit, {
            "type": "text_end", "node": node, "channel": channel,
            "label": label, "content": text,
        })
    return text


async def stream_llm_text(
    llm,
    messages,
    *,
    emit=None,
    channel: str,
    label: str = "",
    node: str = "reason",
) -> str:
    """逐 token 调用 LLM 并推送增量；不支持流式时回退 ainvoke。"""
    if emit is None or llm is None:
        res = await llm.ainvoke(messages)
        return _chunk_text(res)

    try:
        return await stream_chunks(
            llm.astream(messages), emit=emit, channel=channel, label=label, node=node,
        )
    except Exception as e:
        logger.warning(
            f"[text_stream] {channel} 逐 token 流式失败，回退整段返回: {type(e).__name__}: {e}"
        )
        res = await llm.ainvoke(messages)
        text = _chunk_text(res)
        if text:
            # 回退路径也要让前端拿到内容，否则该区块会空着
            _emit(emit, {"type": "text_start", "node": node, "channel": channel, "label": label})
            _emit(emit, {"type": "text_delta", "node": node, "channel": channel, "delta": text})
            _emit(emit, {
                "type": "text_end", "node": node, "channel": channel,
                "label": label, "content": text,
            })
        return text


async def stream_react_agent_text(
    agent,
    messages,
    *,
    emit=None,
    channel: str,
    label: str = "",
    node: str = "reason",
    config: Optional[dict] = None,
) -> str:
    """流式运行 ReAct 智能体，只把最终发言的 token 推给前端。

    工具调用参数生成阶段的分片（tool_call_chunks）是内部调度文本，必须跳过——
    既不属于最终发言，也不应外泄给前端。
    """
    if emit is None:
        result = await agent.ainvoke(messages, config=config or {})
        for msg in reversed(result.get("messages", []) or []):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    try:
        async def _chunks():
            async for item in agent.astream(
                messages, config=config or {}, stream_mode="messages",
            ):
                # stream_mode="messages" 产出 (message_chunk, metadata)
                yield item[0] if isinstance(item, tuple) else item

        text = await stream_chunks(
            _chunks(), emit=emit, channel=channel, label=label, node=node,
            skip_tool_call_chunks=True,
        )
        return text.strip()
    except Exception as e:
        logger.warning(
            f"[text_stream] {channel} ReAct 流式失败，回退整段返回: {type(e).__name__}: {e}"
        )
        result = await agent.ainvoke(messages, config=config or {})
        for msg in reversed(result.get("messages", []) or []):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                text = content.strip()
                _emit(emit, {"type": "text_start", "node": node, "channel": channel, "label": label})
                _emit(emit, {"type": "text_delta", "node": node, "channel": channel, "delta": text})
                _emit(emit, {
                    "type": "text_end", "node": node, "channel": channel,
                    "label": label, "content": text,
                })
                return text
        return ""
