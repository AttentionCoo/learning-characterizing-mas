import { ref } from 'vue'

export function useReasoningTrace() {
  const reasoningEntries = ref([])
  let eventSequence = 0

  function resetReasoningTrace() {
    reasoningEntries.value = []
    eventSequence = 0
  }

  function appendReasoningEvent(event, scope = '', target = null) {
    if (!event) return

    // 默认追加到共享列表（资源/评估/代码等单页生成场景）；
    // 聊天页可传入消息自身的 reasoning 数组，实现"每条 AI 回复各自留存推理轨迹"。
    const list = target || reasoningEntries.value

    // M2 专家对话消息聚合：同一 scope 下连续到达的 agent_msg 事件
    // 并入上一条「专家会诊」条目，避免每个单条消息生成一张碎片卡片。
    if (event.phase === 'agent_msg') {
      const last = list.length ? list[list.length - 1] : null
      if (last && last.phase === 'agent_msg' && last.scope === scope) {
        const msg = (event.messages || [])[0]
        if (msg) last.messages.push(msg)
        last.title = `专家会诊对话（${last.messages.length} 条消息）`
        return
      }
      list.push({
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
    const lastEntry = list.length ? list[list.length - 1] : null

    // 单条专家发言（实时到达）：并入上一条「参与专家」条目，使其随每位专家完成
    // 逐条长出；与名单事件（experts）谁先到都能正确合流。
    if (event.expertSpeech) {
      if (lastEntry && lastEntry.phase === 'experts' && lastEntry.scope === scope && lastEntry.experts) {
        if (!Array.isArray(lastEntry.experts.advices)) lastEntry.experts.advices = []
        lastEntry.experts.advices.push(event.expertSpeech)
        return
      }
      list.push({
        key: `${scope}:experts:${eventSequence++}`,
        scope,
        step: event.step || 'reason',
        phase: 'experts',
        title: '多专家协同',
        content: '',
        sources: [],
        debate: null,
        experts: {
          active: [],
          advices: [event.expertSpeech],
          debateRounds: 0,
          arbitration: '',
          selectionReason: '',
        },
        messages: null,
        blackboard: null,
      })
      return
    }

    // 专家名单（含选人理由）：若同一 scope 的「参与专家」条目已存在（发言先到），
    // 就地补齐名单与理由，避免拆成两块。
    if (event.phase === 'experts' && event.experts
      && lastEntry && lastEntry.phase === 'experts' && lastEntry.scope === scope && lastEntry.experts) {
      const incoming = event.experts
      if (incoming.active?.length) lastEntry.experts.active = incoming.active
      if (incoming.selectionReason) lastEntry.experts.selectionReason = incoming.selectionReason
      if (incoming.arbitration) lastEntry.experts.arbitration = incoming.arbitration
      if (incoming.debateRounds) lastEntry.experts.debateRounds = incoming.debateRounds
      if (incoming.advices?.length) {
        const known = new Set(lastEntry.experts.advices.map((a) => a.role))
        incoming.advices.forEach((a) => {
          if (!known.has(a.role)) lastEntry.experts.advices.push(a)
        })
      }
      lastEntry.title = event.title || lastEntry.title
      return
    }

    list.push({
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
