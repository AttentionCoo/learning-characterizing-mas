import { ref } from 'vue'

export function useReasoningTrace() {
  const reasoningEntries = ref([])
  let eventSequence = 0

  /** 从尾部找同 scope 且满足条件的条目（权威事件要就地落进流式占位块）。 */
  function findTailEntry(list, scope, predicate) {
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const entry = list[i]
      if (entry.scope === scope && predicate(entry)) return entry
    }
    return null
  }

  /** 流式文本落点：按 channel 找到（或创建）承载它的条目与字段。 */
  function resolveStreamTarget(list, scope, channel, label) {
    if (channel.startsWith('expert:')) {
      const role = channel.slice('expert:'.length)
      let entry = findTailEntry(list, scope, (e) => e.phase === 'experts')
      if (!entry) {
        entry = {
          key: `${scope}:experts:${eventSequence++}`,
          scope,
          step: 'reason',
          phase: 'experts',
          title: '多专家协同',
          content: '',
          sources: [],
          debate: null,
          experts: { active: [], advices: [], debateRounds: 0, arbitration: '', selectionReason: '' },
          messages: null,
          blackboard: null,
        }
        list.push(entry)
      }
      if (!Array.isArray(entry.experts.advices)) entry.experts.advices = []
      let advice = entry.experts.advices.find((a) => a.role === role)
      if (!advice) {
        advice = { role, content: '' }
        entry.experts.advices.push(advice)
      }
      return {
        begin() { advice.streaming = true },
        append(delta) { advice.content = (advice.content || '') + delta },
        finish(full) { if (full) advice.content = full; advice.streaming = false },
      }
    }

    const kind = { synthesis: 'synthesis', convergence: 'convergence', arbitration: 'arbitration' }[channel]
    if (!kind) return null
    let entry = findTailEntry(list, scope, (e) => e.phase === 'verdict' && e.verdictKind === kind)
    if (!entry) {
      entry = {
        key: `${scope}:verdict:${kind}:${eventSequence++}`,
        scope,
        step: 'reason',
        phase: 'verdict',
        verdictKind: kind,
        verdictLabel: label || '',
        verdictText: '',
        title: label || '',
        content: '',
        sources: [],
        debate: null,
        experts: null,
        messages: null,
        blackboard: null,
      }
      list.push(entry)
    }
    if (label && !entry.verdictLabel) entry.verdictLabel = label
    return {
      begin() { entry.streaming = true },
      append(delta) { entry.verdictText = (entry.verdictText || '') + delta },
      finish(full) { if (full) entry.verdictText = full; entry.streaming = false },
    }
  }

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

    // 逐 token 文本流式（text_start / text_delta / text_end）：按 channel 落到对应区块，
    // 让长文本（专家发言、综合、收敛、仲裁）边生成边打印。
    if (event.textStream) {
      const { stage, channel, label, delta, content } = event.textStream
      if (!channel) return
      const target = resolveStreamTarget(list, scope, channel, label)
      if (!target) return
      if (stage === 'text_start') target.begin()
      else if (stage === 'text_delta') target.append(delta)
      else target.finish(content)
      return
    }

    // 单条专家发言（实时到达）：并入上一条「参与专家」条目，使其随每位专家完成
    // 逐条长出；与名单事件（experts）谁先到都能正确合流。
    if (event.expertSpeech) {
      const entry = findTailEntry(list, scope, (e) => e.phase === 'experts')
      if (entry && entry.experts) {
        if (!Array.isArray(entry.experts.advices)) entry.experts.advices = []
        const existing = entry.experts.advices.find((a) => a.role === event.expertSpeech.role)
        if (existing) {
          // 流式草稿已存在：用权威全文覆盖，且不重复追加
          if (event.expertSpeech.content) existing.content = event.expertSpeech.content
          existing.streaming = false
        } else {
          entry.experts.advices.push(event.expertSpeech)
        }
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

    // 专家名单（含选人理由）：若同一 scope 的「参与专家」条目已存在（流式发言先到），
    // 就地补齐名单与理由，避免拆成两块。
    if (event.phase === 'experts' && event.experts) {
      const entry = findTailEntry(list, scope, (e) => e.phase === 'experts' && !!e.experts)
      if (entry) {
        const incoming = event.experts
        if (incoming.active?.length) entry.experts.active = incoming.active
        if (incoming.selectionReason) entry.experts.selectionReason = incoming.selectionReason
        if (incoming.arbitration) entry.experts.arbitration = incoming.arbitration
        if (incoming.debateRounds) entry.experts.debateRounds = incoming.debateRounds
        if (incoming.advices?.length) {
          if (!Array.isArray(entry.experts.advices)) entry.experts.advices = []
          incoming.advices.forEach((a) => {
            const existing = entry.experts.advices.find((x) => x.role === a.role)
            if (existing) {
              if (a.content && !existing.content) existing.content = a.content
            } else {
              entry.experts.advices.push(a)
            }
          })
        }
        entry.title = event.title || entry.title
        return
      }
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
