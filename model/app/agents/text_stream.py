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
    state: Optional[dict] = None,
) -> str:
    """消费 chunk 流并推送增量事件，返回完整文本。

    skip_tool_call_chunks=True 时跳过"工具调用参数生成"阶段的分片
    （ReAct 智能体里那部分是内部调度文本，不属于最终发言）。

    state：可选的可变容器，记录流式进度：
    - 首片消费时写 {"any_chunk": True}（任何分片，含被跳过的工具分片）；
    - 首片增量发出时写 {"started": True}；
    - 中途失败时写 {"partial": 已收集文本} 后原样抛出。
    供调用方在流式中途失败后判断"是否已有增量送达/工具是否可能已执行"——
    已送达时回退路径只能补 text_end 让下游用全文覆盖，不能重发 delta，
    否则前端会把"半截 + 全文"拼在一起；ReAct 场景还据此避免重跑 agent。
    """
    parts: List[str] = []
    started = False
    try:
        async for chunk in chunks:
            if state is not None and not state.get("any_chunk"):
                state["any_chunk"] = True
            if skip_tool_call_chunks and getattr(chunk, "tool_call_chunks", None):
                continue
            delta = _chunk_text(chunk)
            if not delta:
                continue
            if not started:
                started = True
                if state is not None:
                    state["started"] = True
                _emit(emit, {"type": "text_start", "node": node, "channel": channel, "label": label})
            parts.append(delta)
            _emit(emit, {"type": "text_delta", "node": node, "channel": channel, "delta": delta})
    except Exception:
        # 中途失败：把已收集的文本交给调用方决定收口方式
        if state is not None:
            state["partial"] = "".join(parts)
        raise
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
    if llm is None:
        # 模型未注入：无内容可产出，直接返回空串（旧实现会解引用 None.ainvoke 抛 AttributeError）
        return ""
    if emit is None:
        res = await llm.ainvoke(messages)
        return _chunk_text(res)

    try:
        stream_state: dict = {}
        return await stream_chunks(
            llm.astream(messages), emit=emit, channel=channel, label=label, node=node,
            state=stream_state,
        )
    except Exception as e:
        logger.warning(
            f"[text_stream] {channel} 逐 token 流式失败，回退整段返回: {type(e).__name__}: {e}"
        )
        res = await llm.ainvoke(messages)
        text = _chunk_text(res)
        if text:
            # 回退路径也要让前端拿到内容，否则该区块会空着
            if stream_state.get("started"):
                # 已有增量送达：只补 text_end，下游（前端 finish / answer 通道的
                # replace）会用全文覆盖半截内容。重发 delta 会让追加语义的
                # 通道（answer）拼出"半截 + 全文"。
                _emit(emit, {
                    "type": "text_end", "node": node, "channel": channel,
                    "label": label, "content": text,
                })
            else:
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

    - 工具调用参数生成阶段的分片（tool_call_chunks）是内部调度文本，必须跳过——
      既不属于最终发言，也不应外泄给前端。
    - 流式失败分两种情况：首片前失败（无工具副作用，重跑整段返回）与
      中途失败（工具可能已执行过，重跑会重复检索/写共享记忆、双倍成本，
      此时用已收集文本收口，不再重跑）。
    """
    if emit is None:
        result = await agent.ainvoke(messages, config=config or {})
        for msg in reversed(result.get("messages", []) or []):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    stream_state: dict = {}
    try:
        async def _chunks():
            # 按消息 id 缓冲文本分片：同一消息内一旦出现工具调用分片，说明该轮是
            # 内部调度轮，已缓冲的文本（含"先检索再回答"这类中间话术）整轮丢弃；
            # 最终发言轮不含工具调用，缓冲在流结束时整体交出。
            # 流中途断开时也要先交出已缓冲的最终轮文本，否则下游以为无增量可收口。
            pending: List = []
            pending_id = None
            try:
                async for item in agent.astream(
                    messages, config=config or {}, stream_mode="messages",
                ):
                    # stream_mode="messages" 产出 (message_chunk, metadata)
                    chunk = item[0] if isinstance(item, tuple) else item
                    chunk_type = getattr(chunk, "type", None)
                    if chunk_type is not None and chunk_type not in ("ai", "AIMessageChunk"):
                        # 工具/系统消息分片不属于最终发言（SimpleNamespace 无 type 按 AI 处理）
                        continue
                    cid = getattr(chunk, "id", None)
                    if cid is None:
                        # 无消息 id 可关联：退化为旧行为（仅跳工具调用分片）
                        if not getattr(chunk, "tool_call_chunks", None):
                            yield chunk
                        continue
                    if cid != pending_id:
                        for c in pending:
                            yield c
                        pending = []
                        pending_id = cid
                    if getattr(chunk, "tool_call_chunks", None):
                        pending = []  # 工具调用轮：本轮已缓冲文本全部丢弃
                        continue
                    pending.append(chunk)
            finally:
                for c in pending:
                    yield c

        text = await stream_chunks(
            _chunks(), emit=emit, channel=channel, label=label, node=node,
            skip_tool_call_chunks=True, state=stream_state,
        )
        return text.strip()
    except Exception as e:
        logger.warning(
            f"[text_stream] {channel} ReAct 流式失败: {type(e).__name__}: {e}"
        )
        if stream_state.get("any_chunk"):
            # 中途失败：工具可能已执行过，重跑 agent 会重复检索/写共享记忆、
            # 双倍成本。已送达多少算多少，用已收集文本收口，不再重跑。
            partial = (stream_state.get("partial") or "").strip()
            if stream_state.get("started") and partial:
                _emit(emit, {
                    "type": "text_end", "node": node, "channel": channel,
                    "label": label, "content": partial,
                })
            return partial
        # 首片前失败：尚未消费任何分片，无工具副作用，重跑整段返回是安全的
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
