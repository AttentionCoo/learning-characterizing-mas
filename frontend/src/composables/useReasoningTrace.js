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
      // 权威事件缺省字段兜底：experts 可能为 null（普通事件推入的 phase='experts' 条目），
      // 直接读 .advices 会 TypeError
      if (!entry.experts || typeof entry.experts !== 'object') {
        entry.experts = { active: [], advices: [], debateRounds: 0, arbitration: '', selectionReason: '' }
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
    if (!kind) {
      // 辩论发言：debate:<轮>:<角色>。每位发言一条独立 channel（并行辩论时
      // 各写各的 history 条目，不会互相串字），权威 debate 事件到达后整体覆盖。
      const debateMatch = /^debate:(\d+):(.+)$/.exec(channel)
      if (!debateMatch) return null
      const round = Number(debateMatch[1])
      const role = debateMatch[2]
      let entry = findTailEntry(list, scope, (e) => e.phase === 'debate')
      if (!entry) {
        entry = {
          key: `${scope}:debate:${eventSequence++}`,
          scope,
          step: 'reason',
          phase: 'debate',
          title: '多专家辩论与仲裁',
          content: '',
          sources: [],
          experts: null,
          messages: null,
          blackboard: null,
          debate: { rounds: round, history: [], arbitration: '', skipped: false, skipReason: '' },
        }
        list.push(entry)
      }
      // 权威事件缺省字段兜底：debate 可能为 null（普通事件推入的 phase='debate' 条目），
      // 直接读 .history 会 TypeError
      if (!entry.debate || typeof entry.debate !== 'object') {
        entry.debate = { rounds: round, history: [], arbitration: '', skipped: false, skipReason: '' }
      }
      if (!Array.isArray(entry.debate.history)) entry.debate.history = []
      let item = entry.debate.history.find((h) => h.round === round && h.role === role)
      if (!item) {
        item = { round, role, content: '' }
        entry.debate.history.push(item)
      }
      if (round > (entry.debate.rounds || 0)) entry.debate.rounds = round
      const syncStreaming = () => {
        entry.streaming = entry.debate.history.some((h) => h.streaming)
      }
      return {
        begin() { item.streaming = true; syncStreaming() },
        append(delta) { item.content = (item.content || '') + delta },
        finish(full) { if (full) item.content = full; item.streaming = false; syncStreaming() },
      }
    }
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

  /** 生成结束后收口：清掉所有 streaming 标记。
   *
   * 正常完成路径已由各 finish() 清除；这里兜底 SSE 超时/断连/用户离页 abort
   * 时遗留的「生成中」状态——否则轨迹里会永久挂着"生成中"标签和闪烁光标。
   * target 传入消息自身的 reasoning 数组（聊天页），缺省用共享列表。
   */
  function settleReasoningTrace(target = null) {
    const list = target || reasoningEntries.value
    list.forEach((entry) => {
      entry.streaming = false
      if (entry.experts?.advices) {
        entry.experts.advices.forEach((a) => { a.streaming = false })
      }
      if (entry.debate?.history) {
        entry.debate.history.forEach((h) => { h.streaming = false })
      }
    })
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

    // 辩论结果（权威）：若流式辩论条目已存在，就地覆盖，避免整块重复出现
    if (event.phase === 'debate' && event.debate) {
      const entry = findTailEntry(list, scope, (e) => e.phase === 'debate' && !!e.debate)
      if (entry) {
        if (event.debate.rounds) entry.debate.rounds = event.debate.rounds
        if (Array.isArray(event.debate.history) && event.debate.history.length) {
          entry.debate.history = event.debate.history
        }
        if (event.debate.arbitration) entry.debate.arbitration = event.debate.arbitration
        if (event.debate.skipped) {
          entry.debate.skipped = true
          entry.debate.skipReason = event.debate.skipReason || ''
        }
        entry.streaming = false
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
    settleReasoningTrace,
    appendReasoningEvent,
  }
}
