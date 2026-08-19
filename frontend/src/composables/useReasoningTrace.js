import { ref } from 'vue'

export function useReasoningTrace() {
  const reasoningEntries = ref([])
  let eventSequence = 0

  function resetReasoningTrace() {
    reasoningEntries.value = []
    eventSequence = 0
  }

  function appendReasoningEvent(event, scope = '') {
    if (!event) return

    // M2 专家对话消息聚合：同一 scope 下连续到达的 agent_msg 事件
    // 并入上一条「专家会诊」条目，避免每个单条消息生成一张碎片卡片。
    if (event.phase === 'agent_msg') {
      const list = reasoningEntries.value
      const last = list.length ? list[list.length - 1] : null
      if (last && last.phase === 'agent_msg' && last.scope === scope) {
        const msg = (event.messages || [])[0]
        if (msg) last.messages.push(msg)
        last.title = `专家会诊对话（${last.messages.length} 条消息）`
        return
      }
      reasoningEntries.value.push({
        key: `${scope}:agent_msg:${eventSequence++}`,
        scope,
        step: event.step || 'reason',
        phase: 'agent_msg',
        title: `专家会诊对话（${(event.messages || []).length} 条消息）`,
        content: '',
        sources: [],
        debate: null,
        experts: null,
        messages: [...(event.messages || [])],
        blackboard: null,
      })
      return
    }

    const step = event.step || 'progress'
    reasoningEntries.value.push({
      key: `${scope}:${step}:${eventSequence++}`,
      scope,
      step,
      phase: event.phase || 'progress',
      title: event.title || 'AI 正在处理',
      content: event.content || '',
      sources: event.sources || [],
      debate: event.debate || null,
      experts: event.experts || null,
      // M2 专家间对话（agent_msg 事件）
      messages: event.messages || null,
      // M3 会诊黑板（blackboard 事件）
      blackboard: event.blackboard || null,
    })
  }

  return {
    reasoningEntries,
    resetReasoningTrace,
    appendReasoningEvent,
  }
}
